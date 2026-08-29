"""Run three reproducible task-extraction accuracy passes through deployed `/chat`."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from scripts.eval_extract_tasks import DATASET, DATE_ACCURACY_THRESHOLD, F1_THRESHOLD, _score_case  # noqa: E402
from scripts.task_eval_metrics import parse_predicted  # noqa: E402

DEFAULT_OUTPUT = ROOT / "eval" / "extract_report.json"


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    return response.json()["access_token"]


async def run(args: argparse.Namespace) -> dict[str, Any]:
    tz = ZoneInfo(args.timezone)
    as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now(tz).date()
    api_base = os.getenv("STAGING_API_BASE_URL", "").rstrip("/")
    if not api_base:
        api_base = f"{os.environ['STAGING_BACKEND_URL'].rstrip('/')}/api/v1"
    credentials = [
        (os.getenv("E2E_USER_EMAIL"), os.getenv("E2E_USER_PASSWORD")),
        (os.getenv("E2E_SECOND_USER_EMAIL"), os.getenv("E2E_SECOND_USER_PASSWORD")),
    ]
    if any(not email or not password for email, password in credentials):
        raise ValueError("Both staging user accounts must be configured")

    work = [(run_index, case_index, case) for run_index in range(args.runs) for case_index, case in enumerate(DATASET)]
    queues = [work[::2], work[1::2]]
    raw_results: dict[tuple[int, int], dict[str, Any]] = {}

    async with httpx.AsyncClient(base_url=api_base, timeout=args.timeout_seconds) as client:
        tokens = await asyncio.gather(
            *(_login(client, email, password) for email, password in credentials if email and password)
        )

        async def worker(token: str, items: list[tuple[int, int, Any]]) -> None:
            for run_index, case_index, case in items:
                started = time.perf_counter()
                try:
                    response = await client.post(
                        "/chat",
                        headers={"Authorization": f"Bearer {token}"},
                        json={
                            "message": "Trích xuất các công việc trong hội thoại này",
                            "quick_action": "extract_tasks",
                            "messages": [{"role": "user", "sender": "Synthetic chat", "content": case.conversation}],
                        },
                    )
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                    passed_http = response.status_code == 200 and payload.get("status") == "completed"
                    raw_results[(run_index, case_index)] = {
                        "raw": payload.get("response", "[]") if passed_http else "[]",
                        "latency_ms": round(elapsed_ms, 3),
                        "status_code": response.status_code,
                        "error": None if passed_http else f"HTTP {response.status_code}: {payload.get('detail')}",
                    }
                except httpx.HTTPError as exc:
                    raw_results[(run_index, case_index)] = {
                        "raw": "[]",
                        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                        "status_code": None,
                        "error": type(exc).__name__,
                    }
                await asyncio.sleep(max(0.0, args.interval_seconds - (time.perf_counter() - started)))

        await asyncio.gather(*(worker(token, queue) for token, queue in zip(tokens, queues, strict=True)))

    reports = []
    for run_index in range(args.runs):
        total_tp = total_fp = total_fn = 0
        date_correct = date_checked = 0
        cases = []
        errors = []
        for case_index, case in enumerate(DATASET):
            result = raw_results[(run_index, case_index)]
            predicted = parse_predicted(result["raw"])
            tp, fp, fn, dates = _score_case(case.expected, predicted, as_of, tz)
            total_tp += tp
            total_fp += fp
            total_fn += fn
            date_correct += sum(dates)
            date_checked += len(dates)
            if result["error"]:
                errors.append({"case": case.name, "error": result["error"]})
            cases.append(
                {
                    "name": case.name,
                    "tp": tp,
                    "fp": fp,
                    "fn": fn,
                    "date_correct": sum(dates),
                    "date_checked": len(dates),
                    "latency_ms": result["latency_ms"],
                    "predicted": predicted,
                    "error": result["error"],
                }
            )
        precision = total_tp / (total_tp + total_fp) if total_tp + total_fp else 1.0
        recall = total_tp / (total_tp + total_fn) if total_tp + total_fn else 1.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        reports.append(
            {
                "run": run_index + 1,
                "case_count": len(DATASET),
                "title_precision": precision,
                "title_recall": recall,
                "title_f1": f1,
                "date_correct": date_correct,
                "date_checked": date_checked,
                "date_accuracy": date_correct / date_checked if date_checked else 1.0,
                "llm_errors": errors,
                "cases": cases,
            }
        )

    metrics = ("title_precision", "title_recall", "title_f1", "date_accuracy")
    return {
        "run_at": datetime.now(tz).isoformat(),
        "environment": "staging",
        "target": f"{api_base}/chat",
        "provider": os.getenv("EVAL_MODEL_PROVIDER"),
        "model": os.getenv("EVAL_MODEL_NAME"),
        "as_of": as_of.isoformat(),
        "timezone": args.timezone,
        "case_count": len(DATASET),
        "run_count": args.runs,
        "range": {
            metric: {"min": min(run[metric] for run in reports), "max": max(run[metric] for run in reports)}
            for metric in metrics
        },
        "date_checked_range": {
            "min": min(run["date_checked"] for run in reports),
            "max": max(run["date_checked"] for run in reports),
        },
        "gates": {"title_f1": F1_THRESHOLD, "date_accuracy": DATE_ACCURACY_THRESHOLD},
        "runs": reports,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", help="Must match the deployed prompt's calendar date")
    parser.add_argument("--timezone", default="Asia/Ho_Chi_Minh")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--interval-seconds", type=float, default=4.2)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.runs < 1 or args.interval_seconds <= 0 or args.timeout_seconds <= 0:
        raise SystemExit("runs, interval and timeout must be positive")
    report = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for current in report["runs"]:
        run_path = ROOT / "eval" / "results" / f"task-extraction-staging-run-{current['run']}.json"
        run_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            f"Run {current['run']}: P/R/F1={current['title_precision']:.1%}/"
            f"{current['title_recall']:.1%}/{current['title_f1']:.1%}; dates="
            f"{current['date_correct']}/{current['date_checked']} ({current['date_accuracy']:.1%})"
        )
    print(f"Aggregate report written to {args.output}")
    return 1 if any(run["llm_errors"] for run in report["runs"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
