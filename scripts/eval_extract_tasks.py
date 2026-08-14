"""Accuracy eval for the `extract_tasks` agent tool against a hand-labeled dataset (see
scripts/eval_data/ - split by source: base.py is the original 8 cases, real_conversations.py and
edge_cases.py are the later expansion, see that package's docstring for how they were sourced).

Calls the real LLM configured in `.env` (GOOGLE_API_KEY/GROQ_API_KEY + LLM_PROVIDER) - this
is a manual dev tool, not part of `pytest tests/` (CI has no real API key), and it costs real
tokens/quota to run. Use it to sanity-check accuracy after changing the extraction prompt or
swapping models/providers.

Scores two separate things, because they fail independently:
  - Title extraction (precision/recall/F1) - did it find the right item at all.
  - Date accuracy - for items with a date/time in the conversation, did it resolve relative
    dates ("tomorrow", "this Friday") against the *actual* current date. This is the ràng
    buộc đề bài cares about most directly ("giảm false reminder") and title P/R/F1 alone
    doesn't catch it - a task can have a perfect title and a wrong year.

Usage:
    python scripts/eval_extract_tasks.py
"""
import asyncio
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Titles are Vietnamese; Windows consoles often default to a codepage (cp1252) that can't
# encode them, which crashes plain print() - force UTF-8 stdout regardless of platform default.
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.eval_data import DATASET, ExpectedTask  # noqa: E402
from src.agents.tools.task_tool import extract_tasks  # noqa: E402
from src.config import get_settings  # noqa: E402

F1_THRESHOLD = 0.7
DATE_ACCURACY_THRESHOLD = 0.7


def _parse_predicted(raw: str) -> list[dict]:
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _check_date(predicted: dict, expected: ExpectedTask, today: date, tz: ZoneInfo) -> bool | None:
    """Returns True/False if a date was expected and could be checked, None if not applicable
    (this expected item carries no date to check against)."""
    if expected.expected_date is None:
        return None
    raw_due = predicted.get("due_at")
    if not raw_due:
        return False  # a date was expected in the conversation but nothing was extracted
    try:
        parsed = datetime.fromisoformat(raw_due)
    except ValueError:
        return False
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(tz)
    if parsed.date() != expected.expected_date(today):
        return False
    if expected.expected_hour_range is not None:
        lo, hi = expected.expected_hour_range
        if not (lo <= parsed.hour <= hi):
            return False
    return True


def _score_case(
    expected: list[ExpectedTask], predicted: list[dict], today: date, tz: ZoneInfo
) -> tuple[int, int, int, list[bool]]:
    """Greedy keyword matching. Returns (true_positives, false_positives, false_negatives,
    date_check_results) - date_check_results has one True/False entry per expected item whose
    title matched AND that carries an expected date (skips items with expected_date=None)."""
    remaining = list(predicted)
    true_positives = 0
    date_results: list[bool] = []
    for exp in expected:
        match = next(
            (p for p in remaining if any(kw.lower() in p.get("title", "").lower() for kw in exp.keywords)), None
        )
        if match is not None:
            remaining.remove(match)
            true_positives += 1
            date_ok = _check_date(match, exp, today, tz)
            if date_ok is not None:
                date_results.append(date_ok)
    false_negatives = len(expected) - true_positives
    false_positives = len(remaining)
    return true_positives, false_positives, false_negatives, date_results


async def main() -> None:
    settings = get_settings()
    tz = ZoneInfo(settings.calendar_timezone)
    today = datetime.now(tz).date()

    total_tp = total_fp = total_fn = 0
    total_date_correct = total_date_checked = 0
    print(f"Running task-extraction accuracy eval on {len(DATASET)} cases (today = {today}, {settings.calendar_timezone})...\n")

    for case in DATASET:
        raw = await extract_tasks.coroutine(state={"context": case.conversation})
        predicted = _parse_predicted(raw)
        tp, fp, fn, date_results = _score_case(case.expected, predicted, today, tz)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        total_date_correct += sum(date_results)
        total_date_checked += len(date_results)

        title_ok = fp == 0 and fn == 0
        dates_ok = all(date_results)
        status = "OK  " if title_ok and dates_ok else "MISS"
        date_summary = f" dates={sum(date_results)}/{len(date_results)}" if date_results else ""
        print(
            f"[{status}] {case.name}: expected={len(case.expected)} predicted={len(predicted)} "
            f"tp={tp} fp={fp} fn={fn}{date_summary}"
        )
        if fp or fn or not dates_ok:
            print(f"       predicted: {[(p.get('title'), p.get('due_at')) for p in predicted]}")

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 1.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    date_accuracy = total_date_correct / total_date_checked if total_date_checked else 1.0

    print(f"\nTitle extraction — Precision: {precision:.1%}  Recall: {recall:.1%}  F1: {f1:.1%}")
    print(f"Date accuracy — {total_date_correct}/{total_date_checked} correct ({date_accuracy:.1%})")

    failed = False
    if f1 < F1_THRESHOLD:
        print(f"Below {F1_THRESHOLD:.0%} F1 threshold - review the extraction prompt/model.")
        failed = True
    if date_accuracy < DATE_ACCURACY_THRESHOLD:
        print(
            f"Below {DATE_ACCURACY_THRESHOLD:.0%} date-accuracy threshold - relative dates are "
            "resolving wrong (check the current-date grounding in the extraction prompt)."
        )
        failed = True
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
