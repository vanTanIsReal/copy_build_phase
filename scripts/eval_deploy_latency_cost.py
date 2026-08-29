"""Measure deployed chat latency and attributable token cost using deployment PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from scripts.benchmark_api_latency import summarize_latencies  # noqa: E402
from src.db import session as db_session  # noqa: E402
from src.db.models import UsageLog  # noqa: E402
from src.services import usage_service  # noqa: E402

DEFAULT_JSON = ROOT / "eval" / "results" / "deploy-latency-cost-latest.json"
DEFAULT_MD = ROOT / "eval" / "results" / "deploy-latency-cost-latest.md"
FALSE_REMINDER_JSON = ROOT / "eval" / "results" / "false-reminder-staging-latest.json"


async def _login(client: httpx.AsyncClient, path: str, email: str, password: str) -> dict[str, Any]:
    response = await client.post(path, json={"email": email, "password": password})
    response.raise_for_status()
    return response.json()


async def _run_series(
    client: httpx.AsyncClient,
    account: dict[str, Any],
    *,
    purpose: str,
    count: int,
    interval_seconds: float,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    conversation = [
        {"role": "user", "sender": "An", "content": "Tôi sẽ gửi báo cáo kiểm thử trước thứ Sáu."},
        {"role": "assistant", "sender": "Bình", "content": "Tôi sẽ cập nhật tài liệu API vào sáng mai."},
        {"role": "user", "sender": "An", "content": "Bug đăng nhập hôm qua đã sửa xong."},
        {"role": "assistant", "sender": "Bình", "content": "Quyết định dùng phương án B cho release."},
    ] * 5
    if purpose == "planner":
        body = {"message": "Hãy cho biết ngắn gọn Orbit hỗ trợ được gì cho công việc."}
    else:
        body = {
            "message": "Tóm tắt hội thoại" if purpose == "summary" else "Trích xuất công việc",
            "quick_action": "summarize" if purpose == "summary" else "extract_tasks",
            "messages": conversation,
        }
    samples = []
    for index in range(count):
        started = time.perf_counter()
        try:
            response = await client.post("/chat", headers=headers, json=body)
            elapsed_ms = (time.perf_counter() - started) * 1000
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            passed = response.status_code == 200 and payload.get("status") == "completed"
            samples.append(
                {
                    "index": index + 1,
                    "elapsed_ms": round(elapsed_ms, 3),
                    "status_code": response.status_code,
                    "agent_status": payload.get("status"),
                    "passed": passed,
                }
            )
            print(f"[{purpose} {index + 1:02d}/{count:02d}] HTTP {response.status_code}", flush=True)
        except httpx.HTTPError as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            samples.append(
                {
                    "index": index + 1,
                    "elapsed_ms": round(elapsed_ms, 3),
                    "status_code": None,
                    "agent_status": None,
                    "passed": False,
                    "error": type(exc).__name__,
                }
            )
            print(f"[{purpose} {index + 1:02d}/{count:02d}] {type(exc).__name__}", flush=True)
        await asyncio.sleep(max(0.0, interval_seconds - (time.perf_counter() - started)))
    successful = [sample["elapsed_ms"] for sample in samples if sample["passed"]]
    return {
        "request_count": count,
        "success_count": len(successful),
        "metrics": summarize_latencies(successful) if successful else None,
        "failures": [sample for sample in samples if not sample["passed"]],
    }


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


def _usage_summary(rows: list[UsageLog], expected_calls: int) -> dict[str, Any]:
    if not rows:
        return {"observed_calls": 0, "expected_calls": expected_calls}
    input_tokens = sum(row.prompt_tokens for row in rows)
    output_tokens = sum(row.completion_tokens for row in rows)
    costs = [
        usage_service._estimate_cost(
            row.provider,
            row.model,
            row.prompt_tokens,
            row.completion_tokens,
            row.total_tokens,
        )[0]
        for row in rows
    ]
    return {
        "provider": rows[0].provider,
        "model": rows[0].model,
        "observed_calls": len(rows),
        "expected_calls": expected_calls,
        "average_input_tokens": round(input_tokens / len(rows), 2),
        "average_output_tokens": round(output_tokens / len(rows), 2),
        "average_total_tokens": round(sum(row.total_tokens for row in rows) / len(rows), 2),
        "average_cost_usd": round(sum(costs) / len(costs), 8),
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    api_base = os.getenv("STAGING_API_BASE_URL", "").rstrip("/")
    if not api_base:
        api_base = f"{os.environ['STAGING_BACKEND_URL'].rstrip('/')}/api/v1"
    async with httpx.AsyncClient(base_url=api_base, timeout=args.timeout_seconds) as client:
        summary_account, task_account, planner_account = await asyncio.gather(
            _login(client, "/auth/login", os.environ["E2E_USER_EMAIL"], os.environ["E2E_USER_PASSWORD"]),
            _login(
                client,
                "/auth/login",
                os.environ["E2E_SECOND_USER_EMAIL"],
                os.environ["E2E_SECOND_USER_PASSWORD"],
            ),
            _login(
                client,
                "/auth/admin/login",
                os.environ["E2E_ADMIN_EMAIL"],
                os.environ["E2E_ADMIN_PASSWORD"],
            ),
        )
        since = datetime.now(UTC) - timedelta(seconds=2)
        summary_latency, task_latency, planner_latency = await asyncio.gather(
            _run_series(
                client,
                summary_account,
                purpose="summary",
                count=args.quick_action_requests,
                interval_seconds=args.interval_seconds,
            ),
            _run_series(
                client,
                task_account,
                purpose="task_extraction",
                count=args.quick_action_requests,
                interval_seconds=args.interval_seconds,
            ),
            _run_series(
                client,
                planner_account,
                purpose="planner",
                count=args.planner_requests,
                interval_seconds=args.interval_seconds,
            ),
        )
    await asyncio.sleep(3)
    summary_rows, task_rows, planner_rows = await asyncio.gather(
        _usage_rows(summary_account["user"]["id"], since),
        _usage_rows(task_account["user"]["id"], since),
        _usage_rows(planner_account["user"]["id"], since),
    )
    false_report = json.loads(FALSE_REMINDER_JSON.read_text(encoding="utf-8"))
    usage = {
        "summary": _usage_summary(summary_rows, args.quick_action_requests),
        "task_extraction": _usage_summary(task_rows, args.quick_action_requests),
        "planner": _usage_summary(planner_rows, args.planner_requests),
        "proactive_relevance": {
            "observed_calls": false_report["usage_calls_observed"],
            "expected_calls": false_report["case_count"],
            "average_total_tokens": round(
                false_report["usage_total_tokens"] / false_report["usage_calls_observed"], 2
            ),
            "average_cost_usd": round(
                false_report["usage_estimated_cost_usd"] / false_report["usage_calls_observed"], 8
            ),
        },
    }
    frequencies = {"summary": 10, "task_extraction": 10, "planner": 120, "proactive_relevance": 1000}
    known_cost = sum(
        usage[purpose].get("average_cost_usd", 0) * frequency for purpose, frequency in frequencies.items()
    )
    return {
        "run_at": datetime.now(UTC).isoformat(),
        "environment": "staging",
        "target": f"{api_base}/chat",
        "database": "deployment PostgreSQL",
        "latency": {
            "summary": summary_latency,
            "task_extraction": task_latency,
            "planner": planner_latency,
        },
        "daily_token_budget": await usage_service.get_daily_token_budget(),
        "usage_by_purpose": usage,
        "frequency_assumptions_per_1000_messages": frequencies,
        "known_cost_subtotal_per_1000_messages_usd": round(known_cost, 6),
        "unmeasured_cost_components": ["proactive_extraction", "rolling_summary"],
        "cost_total_is_complete": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    latency = report["latency"]
    lines = [
        "# Deployment Latency and Cost Evidence",
        "",
        f"- Target: `{report['target']}`",
        f"- Effective daily token budget: `{report['daily_token_budget']}`",
        "",
        "| Purpose | Success | P50 | P95 | Avg input | Avg output | Cost/call |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for purpose in ("summary", "task_extraction", "planner"):
        current = latency[purpose]
        metric = current["metrics"] or {}
        usage = report["usage_by_purpose"][purpose]
        lines.append(
            f"| {purpose} | {current['success_count']}/{current['request_count']} | "
            f"{metric.get('p50_ms', 'n/a')} ms | {metric.get('p95_ms', 'n/a')} ms | "
            f"{usage.get('average_input_tokens', 'n/a')} | {usage.get('average_output_tokens', 'n/a')} | "
            f"${usage.get('average_cost_usd', 0):.8f} |"
        )
    lines.extend(
        [
            "",
            f"Known subtotal per 1,000 messages: **${report['known_cost_subtotal_per_1000_messages_usd']:.6f}**.",
            "",
            "This is not a full total: proactive extraction and rolling summary cannot be separated "
            "because the deployed `usage_logs` table has no purpose label.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick-action-requests", type=int, default=25)
    parser.add_argument("--planner-requests", type=int, default=5)
    parser.add_argument("--interval-seconds", type=float, default=4.2)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
