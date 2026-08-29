"""Evaluate proactive false positives, deployed quick-action latency, budget and task cost.

The model calls use the configured provider and persist their normal UsageLog rows through the
configured DATABASE_URL. All prompts and staging chat payloads are synthetic.
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import os
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

# Standalone evidence runs must not depend on an optional tracing account.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import httpx
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from scripts.benchmark_api_latency import summarize_latencies  # noqa: E402
from src.agents.nodes.planner_node import planner_node  # noqa: E402
from src.agents.tools.summarize_tool import generate_summary  # noqa: E402
from src.agents.tools.task_tool import generate_tasks_json  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.db import session as db_session  # noqa: E402
from src.db.models import Message, SystemConfig, User  # noqa: E402
from src.services import conversation_summary_service, proactive_service, usage_service  # noqa: E402
from src.services.guardrail_service import wrap_untrusted_text  # noqa: E402
from src.services.llm import get_llm  # noqa: E402

DEFAULT_DATASET = ROOT / "eval" / "datasets" / "non_commitment_messages_v1.json"
DEFAULT_JSON = ROOT / "eval" / "results" / "operational-metrics-latest.json"
DEFAULT_MD = ROOT / "eval" / "results" / "operational-metrics-latest.md"
PURPOSE = contextvars.ContextVar("evaluation_purpose", default="unlabelled")


def _load_dataset(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) < 30:
        raise ValueError("Non-commitment dataset must contain at least 30 cases")
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)) or not all(case.get("content") for case in cases):
        raise ValueError("Non-commitment cases need unique IDs and non-empty content")
    return data


def _usage_tokens(metadata: dict[str, Any] | None) -> tuple[int, int, int]:
    metadata = metadata if isinstance(metadata, dict) else {}
    prompt = int(metadata.get("input_tokens", metadata.get("prompt_tokens", 0)) or 0)
    completion = int(metadata.get("output_tokens", metadata.get("completion_tokens", 0)) or 0)
    total = int(metadata.get("total_tokens", prompt + completion) or prompt + completion)
    return prompt, completion, total


class UsageCapture:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._original = usage_service.log_usage

    async def log(self, **kwargs: Any) -> None:
        prompt, completion, total = _usage_tokens(kwargs.get("usage_metadata"))
        self.rows.append(
            {
                "purpose": PURPOSE.get(),
                "provider": kwargs["provider"],
                "model": kwargs["model"],
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
            }
        )
        await self._original(**kwargs)

    def install(self) -> None:
        usage_service.log_usage = self.log

    def restore(self) -> None:
        usage_service.log_usage = self._original


async def _timed(purpose: str, factory: Callable[[], Awaitable[Any]]) -> tuple[Any, float]:
    token = PURPOSE.set(purpose)
    started = time.perf_counter()
    try:
        return await factory(), (time.perf_counter() - started) * 1000
    finally:
        PURPOSE.reset(token)


async def _invoke_logged(prompt: str, purpose: str) -> tuple[Any, float]:
    settings = get_settings()

    async def invoke() -> Any:
        result = await get_llm().ainvoke(prompt)
        await usage_service.log_usage(
            provider=settings.llm_provider,
            model=settings.model_name,
            usage_metadata=getattr(result, "usage_metadata", None),
        )
        return result

    return await _timed(purpose, invoke)


def _synthetic_window(content: str) -> tuple[list[tuple[Message, User]], dict[str, str], set[str]]:
    sender_id = "eval-sender"
    other_id = "eval-other"
    sender = User(id=sender_id, email="eval-sender@example.invalid", display_name="An", password_hash="unused")
    message = Message(
        id=f"eval-{uuid4()}",
        conversation_id="eval-conversation",
        sender_id=sender_id,
        content=content,
        created_at=datetime.now(UTC),
    )
    return [(message, sender)], {"An": sender_id, "Bình": other_id}, {sender_id, other_id}


def _verified_candidate_count(raw: str, window: list[tuple[Message, User]]) -> int:
    try:
        data = json.loads(proactive_service._strip_fence(raw))
    except (TypeError, ValueError):
        return 0
    commitments = data.get("commitments") if isinstance(data, dict) else None
    if not isinstance(commitments, list):
        return 0
    roster = {"An": "eval-sender", "Bình": "eval-other"}
    eligible = set(roster.values())
    count = 0
    for commitment in commitments:
        if not isinstance(commitment, dict) or commitment.get("cancelled"):
            continue
        proposal_idx = commitment.get("proposal_message_index")
        if not proactive_service._is_plain_int(proposal_idx) or not 1 <= proposal_idx <= len(window):
            continue
        owners = commitment.get("owners")
        if not isinstance(owners, list):
            continue
        count += sum(
            proactive_service._verify_owner(
                owner,
                window=window,
                roster=roster,
                eligible_ids=eligible,
                proposal_idx=proposal_idx,
                is_direct=False,
            )
            is not None
            for owner in owners
        )
    return count


async def evaluate_false_reminders(data: dict[str, Any], concurrency: int) -> dict[str, Any]:
    settings = get_settings()
    semaphore = asyncio.Semaphore(concurrency)

    async def evaluate(case: dict[str, str]) -> dict[str, Any]:
        async with semaphore:
            relevance, relevance_ms = await _invoke_logged(
                proactive_service._build_relevance_prompt(case["content"]),
                "proactive_relevance_false_dataset",
            )
            relevant = proactive_service._parse_relevant(relevance.content)
            candidates = 0
            extraction_ms = None
            error = None
            if relevant:
                window, roster, eligible = _synthetic_window(case["content"])
                prompt = proactive_service._build_window_prompt(
                    window,
                    now=datetime.now(ZoneInfo(settings.calendar_timezone)),
                    tz_name=settings.calendar_timezone,
                    visible_participants=[name for name, user_id in roster.items() if user_id in eligible],
                    is_direct=False,
                )
                try:
                    extraction, extraction_ms = await _invoke_logged(
                        prompt, "proactive_extraction_false_dataset"
                    )
                    candidates = _verified_candidate_count(str(extraction.content), window)
                except Exception as exc:  # noqa: BLE001 - preserve evaluation failure
                    error = f"{type(exc).__name__}: {exc}"
            return {
                "id": case["id"],
                "category": case["category"],
                "relevant": relevant,
                "candidate_count": candidates,
                "relevance_latency_ms": round(relevance_ms, 3),
                "extraction_latency_ms": round(extraction_ms, 3) if extraction_ms is not None else None,
                "error": error,
            }

    results = await asyncio.gather(*(evaluate(case) for case in data["cases"]))
    false_positive_cases = [result["id"] for result in results if result["candidate_count"] > 0]
    return {
        "dataset_id": data["dataset_id"],
        "dataset_version": data["version"],
        "case_count": len(results),
        "relevance_positive_count": sum(result["relevant"] for result in results),
        "extraction_count": sum(result["extraction_latency_ms"] is not None for result in results),
        "false_positive_count": len(false_positive_cases),
        "false_positive_rate": len(false_positive_cases) / len(results),
        "false_positive_case_ids": false_positive_cases,
        "error_count": sum(result["error"] is not None for result in results),
        "cases": results,
    }


def _summary_context() -> str:
    lines = []
    for index in range(1, 161):
        speaker = "An" if index % 2 else "Bình"
        lines.append(f"{speaker}: Cập nhật {index}: tiến độ module thanh toán ổn định, chưa có blocker mới.")
    lines.extend(
        [
            "An: Quyết định dùng phương án B cho API thanh toán.",
            "Bình: Tôi sẽ gửi báo cáo kiểm thử trước thứ Sáu.",
            "An: Câu hỏi còn mở là thời điểm chuyển traffic production.",
        ]
    )
    return "\n".join(lines)


def _task_context() -> str:
    return "\n".join(
        [
            "An: Bình gửi báo cáo kiểm thử trước thứ Sáu nhé.",
            "Bình: Đồng ý, tôi sẽ hoàn thành trước 17 giờ thứ Năm.",
            "An: Tôi sẽ cập nhật tài liệu API vào sáng mai.",
            "Bình: Bug đăng nhập hôm qua đã sửa xong rồi.",
        ]
    )


async def measure_task_costs(repetitions: int) -> dict[str, Any]:
    settings = get_settings()
    latency: dict[str, list[float]] = {
        purpose: []
        for purpose in (
            "summary",
            "task_extraction",
            "planner",
            "proactive_relevance",
            "proactive_extraction",
            "rolling_summary",
        )
    }
    summary_context = _summary_context()
    task_context = _task_context()
    window, roster, eligible = _synthetic_window("Tôi sẽ gửi báo cáo kiểm thử trước 17 giờ thứ Năm.")
    proactive_prompt = proactive_service._build_window_prompt(
        window,
        now=datetime.now(ZoneInfo(settings.calendar_timezone)),
        tz_name=settings.calendar_timezone,
        visible_participants=[name for name, user_id in roster.items() if user_id in eligible],
        is_direct=False,
    )
    rolling_prompt = (
        f"{conversation_summary_service._ROLLING_SUMMARY_PROMPT}\n\n"
        "PREVIOUS SUMMARY:\n(no previous summary yet)\n\n"
        f"NEW MESSAGES:\n{wrap_untrusted_text(task_context, label='new_messages')}"
    )

    for _ in range(repetitions):
        _, elapsed = await _timed("summary", lambda: generate_summary(summary_context))
        latency["summary"].append(elapsed)
        _, elapsed = await _timed("task_extraction", lambda: generate_tasks_json(task_context))
        latency["task_extraction"].append(elapsed)
        _, elapsed = await _timed(
            "planner",
            lambda: planner_node({"messages": [HumanMessage(content="Bạn có thể hỗ trợ công việc gì?")]}),
        )
        latency["planner"].append(elapsed)
        _, elapsed = await _invoke_logged(
            proactive_service._build_relevance_prompt("Tôi sẽ gửi báo cáo trước 17 giờ thứ Năm."),
            "proactive_relevance",
        )
        latency["proactive_relevance"].append(elapsed)
        _, elapsed = await _invoke_logged(proactive_prompt, "proactive_extraction")
        latency["proactive_extraction"].append(elapsed)
        _, elapsed = await _invoke_logged(rolling_prompt, "rolling_summary")
        latency["rolling_summary"].append(elapsed)

    return {
        "provider": settings.llm_provider,
        "model": settings.model_name,
        "repetitions": repetitions,
        "latency_ms": {purpose: summarize_latencies(values) for purpose, values in latency.items()},
    }


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    return response.json()["access_token"]


async def _latency_series(
    client: httpx.AsyncClient,
    *,
    token: str,
    action: str,
    request_count: int,
    interval_seconds: float,
) -> dict[str, Any]:
    messages = [
        {"role": "user" if index % 2 else "assistant", "sender": "An" if index % 2 else "Bình", "content": line}
        for index, line in enumerate(_task_context().splitlines() * 5, start=1)
    ]
    body = {
        "message": "Tóm tắt hội thoại công việc này" if action == "summarize" else "Trích xuất công việc",
        "quick_action": action,
        "messages": messages,
    }
    samples: list[dict[str, Any]] = []
    for index in range(request_count):
        started = time.perf_counter()
        try:
            response = await client.post(
                "/chat", json=body, headers={"Authorization": f"Bearer {token}"}
            )
            elapsed = (time.perf_counter() - started) * 1000
            payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            samples.append(
                {
                    "index": index + 1,
                    "elapsed_ms": round(elapsed, 3),
                    "status_code": response.status_code,
                    "agent_status": payload.get("status"),
                    "passed": response.status_code == 200 and payload.get("status") == "completed",
                }
            )
        except httpx.HTTPError as exc:
            elapsed = (time.perf_counter() - started) * 1000
            samples.append(
                {
                    "index": index + 1,
                    "elapsed_ms": round(elapsed, 3),
                    "status_code": None,
                    "agent_status": None,
                    "passed": False,
                    "error": type(exc).__name__,
                }
            )
        await asyncio.sleep(max(0.0, interval_seconds - (time.perf_counter() - started)))
    successful = [sample["elapsed_ms"] for sample in samples if sample["passed"]]
    return {
        "request_count": request_count,
        "success_count": len(successful),
        "metrics": summarize_latencies(successful) if successful else None,
        "failures": [sample for sample in samples if not sample["passed"]],
    }


async def measure_staging_latency(request_count: int, interval_seconds: float) -> dict[str, Any]:
    api_base = os.getenv("STAGING_API_BASE_URL", "").rstrip("/")
    if not api_base:
        api_base = f"{os.environ['STAGING_BACKEND_URL'].rstrip('/')}/api/v1"
    required = (
        "E2E_USER_EMAIL",
        "E2E_USER_PASSWORD",
        "E2E_SECOND_USER_EMAIL",
        "E2E_SECOND_USER_PASSWORD",
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise ValueError(f"Missing staging credentials: {', '.join(missing)}")
    async with httpx.AsyncClient(base_url=api_base, timeout=120.0) as client:
        summary_token, task_token = await asyncio.gather(
            _login(client, os.environ["E2E_USER_EMAIL"], os.environ["E2E_USER_PASSWORD"]),
            _login(client, os.environ["E2E_SECOND_USER_EMAIL"], os.environ["E2E_SECOND_USER_PASSWORD"]),
        )
        summary, tasks = await asyncio.gather(
            _latency_series(
                client,
                token=summary_token,
                action="summarize",
                request_count=request_count,
                interval_seconds=interval_seconds,
            ),
            _latency_series(
                client,
                token=task_token,
                action="extract_tasks",
                request_count=request_count,
                interval_seconds=interval_seconds,
            ),
        )
    return {
        "target": f"{api_base}/chat",
        "provider": os.getenv("EVAL_MODEL_PROVIDER"),
        "model": os.getenv("EVAL_MODEL_NAME"),
        "endpoint_streaming": False,
        "summary": summary,
        "task_extraction": tasks,
    }


async def read_budget() -> dict[str, Any]:
    settings = get_settings()
    async with db_session.async_session_maker() as db:
        config = await db.get(SystemConfig, "default")
    actual = await usage_service.get_daily_token_budget()
    url = make_url(settings.database_url)
    return {
        "actual_tokens_per_day": actual,
        "env_default_tokens_per_day": settings.daily_token_budget,
        "system_config_override": config.daily_token_budget if config else None,
        "source": "system_config" if config and config.daily_token_budget is not None else "environment",
        "database": {"host": url.host, "port": url.port, "name": url.database},
    }


def build_cost_table(capture: UsageCapture) -> dict[str, Any]:
    settings = get_settings()
    frequencies = {
        "summary": 10,
        "task_extraction": 10,
        "planner": 120,
        "proactive_relevance": 1000,
        "proactive_extraction": 100,
        "rolling_summary": 33,
    }
    rows = []
    for purpose, frequency in frequencies.items():
        samples = [row for row in capture.rows if row["purpose"] == purpose]
        if not samples:
            continue
        input_average = statistics.fmean(row["prompt_tokens"] for row in samples)
        output_average = statistics.fmean(row["completion_tokens"] for row in samples)
        cost_average = statistics.fmean(
            usage_service._estimate_cost(
                row["provider"],
                row["model"],
                row["prompt_tokens"],
                row["completion_tokens"],
                row["total_tokens"],
            )[0]
            for row in samples
        )
        rows.append(
            {
                "purpose": purpose,
                "model": settings.model_name,
                "calls_measured": len(samples),
                "average_input_tokens": round(input_average, 2),
                "average_output_tokens": round(output_average, 2),
                "average_cost_usd": round(cost_average, 8),
                "frequency_per_1000_messages": frequency,
                "estimated_cost_per_1000_messages_usd": round(cost_average * frequency, 6),
            }
        )
    return {
        "rows": rows,
        "total_estimated_cost_per_1000_messages_usd": round(
            sum(row["estimated_cost_per_1000_messages_usd"] for row in rows), 6
        ),
        "assumptions": {
            "A_eligible_messages_reaching_relevance": 1.0,
            "A_reason": "Current code has no regex pre-filter; each eligible allowed message calls relevance.",
            "B_relevant_share_after_relevance": 0.10,
            "B_reason": "Planning assumption; production prevalence is not labelled in usage_logs.",
            "C_manual_summary_calls": 10,
            "C_manual_task_extraction_calls": 10,
            "D_regular_chat_turns": 120,
            "D_average_planner_rounds": 1.0,
            "rolling_summary_calls": 33,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    false = report["false_reminder"]
    latency = report["staging_chat_latency"]
    summary = latency["summary"]
    tasks = latency["task_extraction"]
    budget = report["daily_token_budget"]
    cost = report["cost"]
    lines = [
        "# Operational Agent Evaluation",
        "",
        f"- Run at: `{report['run_at']}`",
        f"- Local model: `{report['local_model']['provider']}/{report['local_model']['model']}`",
        f"- Deploy database: `{budget['database']['host']}/{budget['database']['name']}`",
        "",
        "## False reminder",
        "",
        f"- Sample: `{false['case_count']}` synthetic non-commitment messages",
        f"- False positives: `{false['false_positive_count']}` ({false['false_positive_rate']:.1%})",
        f"- Relevance positives/full extraction calls: `{false['relevance_positive_count']}`",
        "",
        "## Deployed `/chat` quick-action latency",
        "",
        "| Action | Success | P50 | P95 |",
        "|---|---:|---:|---:|",
        f"| Summary | {summary['success_count']}/{summary['request_count']} | "
        f"{summary['metrics']['p50_ms'] if summary['metrics'] else 'n/a'} ms | "
        f"{summary['metrics']['p95_ms'] if summary['metrics'] else 'n/a'} ms |",
        f"| Task extraction | {tasks['success_count']}/{tasks['request_count']} | "
        f"{tasks['metrics']['p50_ms'] if tasks['metrics'] else 'n/a'} ms | "
        f"{tasks['metrics']['p95_ms'] if tasks['metrics'] else 'n/a'} ms |",
        "",
        "## Daily token budget",
        "",
        f"- Effective: `{budget['actual_tokens_per_day']}` token/day from `{budget['source']}`",
        f"- Environment fallback: `{budget['env_default_tokens_per_day']}` token/day",
        "",
        "## Model cost",
        "",
        "| Purpose | Input avg | Output avg | Cost/call | Frequency/1,000 | Cost/1,000 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in cost["rows"]:
        lines.append(
            f"| {row['purpose']} | {row['average_input_tokens']:.2f} | "
            f"{row['average_output_tokens']:.2f} | ${row['average_cost_usd']:.8f} | "
            f"{row['frequency_per_1000_messages']} | "
            f"${row['estimated_cost_per_1000_messages_usd']:.6f} |"
        )
    lines.extend(
        [
            "",
            f"Estimated total per 1,000 messages: **${cost['total_estimated_cost_per_1000_messages_usd']:.6f}**.",
            "",
            "Assumptions A/B/C/D are recorded in the JSON artifact; B is an explicit planning "
            "assumption because usage logs do not label real-message prevalence.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--false-concurrency", type=int, default=8)
    parser.add_argument("--cost-repetitions", type=int, default=3)
    parser.add_argument("--latency-requests", type=int, default=25)
    parser.add_argument("--latency-interval-seconds", type=float, default=4.2)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict[str, Any]:
    data = _load_dataset(args.dataset)
    settings = get_settings()
    capture = UsageCapture()
    capture.install()
    try:
        budget = await read_budget()
        false_reminder, cost_measurement, staging_latency = await asyncio.gather(
            evaluate_false_reminders(data, args.false_concurrency),
            measure_task_costs(args.cost_repetitions),
            measure_staging_latency(args.latency_requests, args.latency_interval_seconds),
        )
    finally:
        capture.restore()
    return {
        "run_at": datetime.now(UTC).isoformat(),
        "local_model": {"provider": settings.llm_provider, "model": settings.model_name},
        "daily_token_budget": budget,
        "false_reminder": false_reminder,
        "staging_chat_latency": staging_latency,
        "task_cost_measurement": cost_measurement,
        "cost": build_cost_table(capture),
    }


def main() -> int:
    args = parse_args()
    if min(args.false_concurrency, args.cost_repetitions, args.latency_requests) < 1:
        raise SystemExit("Concurrency, repetitions and request counts must be positive")
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
