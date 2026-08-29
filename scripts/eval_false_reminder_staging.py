"""Measure proactive false reminders through the deployed chat and PostgreSQL pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.db import session as db_session  # noqa: E402
from src.db.models import UsageLog  # noqa: E402
from src.services import usage_service  # noqa: E402

DEFAULT_DATASET = ROOT / "eval" / "datasets" / "non_commitment_messages_v1.json"
DEFAULT_JSON = ROOT / "eval" / "results" / "false-reminder-staging-latest.json"
DEFAULT_MD = ROOT / "eval" / "results" / "false-reminder-staging-latest.md"


async def _login(client: httpx.AsyncClient, email: str, password: str) -> dict[str, Any]:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    return response.json()


def _headers(account: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {account['access_token']}"}


async def _usage_count(user_id: str, since: datetime) -> int:
    async with db_session.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count()).select_from(UsageLog).where(
                    UsageLog.user_id == user_id,
                    UsageLog.created_at >= since,
                )
            )
        ).scalar_one()


async def _usage_rows(user_id: str, since: datetime) -> list[UsageLog]:
    async with db_session.async_session_maker() as db:
        return list(
            (
                await db.execute(
                    select(UsageLog).where(
                        UsageLog.user_id == user_id,
                        UsageLog.created_at >= since,
                    )
                )
            )
            .scalars()
            .all()
        )


async def _tasks(client: httpx.AsyncClient, account: dict[str, Any]) -> list[dict[str, Any]]:
    response = await client.get("/tasks?limit=500", headers=_headers(account))
    response.raise_for_status()
    return response.json()


async def run(args: argparse.Namespace) -> dict[str, Any]:
    data = json.loads(args.dataset.read_text(encoding="utf-8"))
    cases = data["cases"]
    api_base = os.getenv("STAGING_API_BASE_URL", "").rstrip("/")
    if not api_base:
        api_base = f"{os.environ['STAGING_BACKEND_URL'].rstrip('/')}/api/v1"
    required = (
        "E2E_USER_EMAIL",
        "E2E_USER_PASSWORD",
        "E2E_SECOND_USER_EMAIL",
        "E2E_SECOND_USER_PASSWORD",
    )
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise ValueError(f"Missing deployment credentials: {', '.join(missing)}")

    started_at = datetime.now(UTC)
    sent: list[dict[str, Any]] = []
    send_errors: list[dict[str, Any]] = []
    created_task_ids: list[str] = []
    conversation_id = None
    async with httpx.AsyncClient(base_url=api_base, timeout=args.timeout_seconds) as client:
        primary, secondary = await asyncio.gather(
            _login(client, os.environ["E2E_USER_EMAIL"], os.environ["E2E_USER_PASSWORD"]),
            _login(
                client,
                os.environ["E2E_SECOND_USER_EMAIL"],
                os.environ["E2E_SECOND_USER_PASSWORD"],
            ),
        )
        before_primary, before_secondary = await asyncio.gather(
            _tasks(client, primary),
            _tasks(client, secondary),
        )
        before_ids = {task["id"] for task in [*before_primary, *before_secondary]}

        create = await client.post(
            "/conversations",
            headers=_headers(primary),
            json={
                "type": "group",
                "participant_ids": [secondary["user"]["id"]],
                "name": f"Eval false reminder {started_at:%Y%m%d-%H%M%S}",
            },
        )
        create.raise_for_status()
        conversation_id = create.json()["id"]
        policy = await client.put(
            f"/conversations/{conversation_id}/ai-policy",
            headers=_headers(primary),
            json={"enabled": True},
        )
        policy.raise_for_status()

        for index, case in enumerate(cases, start=1):
            response = None
            request_started = time.perf_counter()
            for attempt in range(args.send_retries + 1):
                response = await client.post(
                    f"/conversations/{conversation_id}/messages",
                    headers=_headers(primary),
                    json={"content": case["content"]},
                )
                if response.status_code < 500:
                    break
                await asyncio.sleep(5 * (attempt + 1))
            elapsed_ms = (time.perf_counter() - request_started) * 1000
            if response is None or response.status_code >= 400:
                send_errors.append(
                    {
                        "case_id": case["id"],
                        "status_code": response.status_code if response is not None else None,
                    }
                )
                print(f"[{index:02d}/{len(cases):02d}] ERROR {case['id']}", flush=True)
                continue
            sent.append(
                {
                    "case_id": case["id"],
                    "category": case["category"],
                    "message_id": response.json()["id"],
                    "send_latency_ms": round(elapsed_ms, 3),
                }
            )
            print(f"[{index:02d}/{len(cases):02d}] sent {case['id']}", flush=True)
            await asyncio.sleep(args.send_interval_seconds)

        deadline = time.monotonic() + args.processing_timeout_seconds
        while time.monotonic() < deadline:
            completed_calls = await _usage_count(primary["user"]["id"], started_at)
            if completed_calls >= len(sent):
                break
            await asyncio.sleep(5)
        await asyncio.sleep(args.settle_seconds)

        after_primary, after_secondary = await asyncio.gather(
            _tasks(client, primary),
            _tasks(client, secondary),
        )
        new_tasks = [task for task in [*after_primary, *after_secondary] if task["id"] not in before_ids]
        message_to_case = {item["message_id"]: item["case_id"] for item in sent}
        false_positive_cases: set[str] = set()
        for task in new_tasks:
            if task.get("source") != "proactive":
                continue
            source_ids = task.get("source_message_ids") or []
            false_positive_cases.update(message_to_case[source_id] for source_id in source_ids if source_id in message_to_case)
            created_task_ids.append(task["id"])

        for account, tasks in ((primary, after_primary), (secondary, after_secondary)):
            owned_new_ids = {task["id"] for task in tasks if task["id"] in created_task_ids}
            for task_id in owned_new_ids:
                delete = await client.delete(f"/tasks/{task_id}", headers=_headers(account))
                if delete.status_code not in {204, 404}:
                    delete.raise_for_status()

        await client.post(f"/conversations/{conversation_id}/leave", headers=_headers(primary))
        await client.post(f"/conversations/{conversation_id}/leave", headers=_headers(secondary))

    usage_rows = await _usage_rows(primary["user"]["id"], started_at)
    total_cost = sum(
        usage_service._estimate_cost(
            row.provider,
            row.model,
            row.prompt_tokens,
            row.completion_tokens,
            row.total_tokens,
        )[0]
        for row in usage_rows
    )
    return {
        "run_at": datetime.now(UTC).isoformat(),
        "environment": "staging",
        "target": api_base,
        "database": "deployment PostgreSQL",
        "dataset_id": data["dataset_id"],
        "dataset_version": data["version"],
        "case_count": len(cases),
        "sent_count": len(sent),
        "send_errors": send_errors,
        "category_counts": {
            category: sum(case["category"] == category for case in cases)
            for category in sorted({case["category"] for case in cases})
        },
        "false_positive_count": len(false_positive_cases),
        "false_positive_rate": len(false_positive_cases) / len(cases),
        "false_positive_case_ids": sorted(false_positive_cases),
        "proactive_tasks_created": len(created_task_ids),
        "usage_calls_observed": len(usage_rows),
        "usage_prompt_tokens": sum(row.prompt_tokens for row in usage_rows),
        "usage_completion_tokens": sum(row.completion_tokens for row in usage_rows),
        "usage_total_tokens": sum(row.total_tokens for row in usage_rows),
        "usage_estimated_cost_usd": round(total_cost, 8),
        "synthetic_tasks_deleted": len(created_task_ids),
        "synthetic_conversation_cleanup_requested": conversation_id is not None,
        "cases": sent,
    }


def render_markdown(report: dict[str, Any]) -> str:
    return f"""# False Reminder Evaluation — Deployment

- Cases: `{report['case_count']}` synthetic non-commitment messages
- Slices: `{report['category_counts']}`
- False positives: `{report['false_positive_count']}` (`{report['false_positive_rate']:.1%}`)
- Usage calls observed: `{report['usage_calls_observed']}`
- Tokens: `{report['usage_total_tokens']}`
- Estimated model cost: `${report['usage_estimated_cost_usd']:.8f}`
- Cleanup: `{report['synthetic_tasks_deleted']}` synthetic tasks deleted; conversation cleanup requested
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--send-interval-seconds", type=float, default=3.0)
    parser.add_argument("--send-retries", type=int, default=2)
    parser.add_argument("--processing-timeout-seconds", type=float, default=240.0)
    parser.add_argument("--settle-seconds", type=float, default=10.0)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = asyncio.run(run(args))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = render_markdown(report)
    args.output_md.write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0 if report["sent_count"] == report["case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
