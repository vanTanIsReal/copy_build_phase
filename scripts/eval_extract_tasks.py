"""Accuracy eval for the `extract_tasks` agent tool against a small hand-labeled dataset.

Calls the real LLM configured in `.env` (GOOGLE_API_KEY/GROQ_API_KEY + LLM_PROVIDER) - this
is a manual dev tool, not part of `pytest tests/` (CI has no real API key), and it costs real
tokens/quota to run. Use it to sanity-check accuracy after changing the extraction prompt or
swapping models/providers.

Usage:
    python scripts/eval_extract_tasks.py
"""
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Titles are Vietnamese; Windows consoles often default to a codepage (cp1252) that can't
# encode them, which crashes plain print() - force UTF-8 stdout regardless of platform default.
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.tools.task_tool import extract_tasks  # noqa: E402

F1_THRESHOLD = 0.7


@dataclass
class ExpectedTask:
    # Case-insensitive substrings expected in a predicted task's title - any one matching counts,
    # since extract_tasks always titles in Vietnamese and there's more than one valid phrasing.
    keywords: tuple[str, ...]


@dataclass
class EvalCase:
    name: str
    conversation: str
    expected: list[ExpectedTask]


DATASET: list[EvalCase] = [
    EvalCase(
        name="single_task_explicit_weekday",
        conversation="Alice: Nhớ gửi báo cáo doanh thu cho sếp trước thứ Sáu này nhé.\nBob: ok để mình làm.",
        expected=[ExpectedTask(keywords=("báo cáo",))],
    ),
    EvalCase(
        name="single_task_relative_date",
        conversation="Bob: Can you review the PR by tomorrow morning? It's blocking the release.",
        expected=[ExpectedTask(keywords=("PR",))],
    ),
    EvalCase(
        name="multiple_tasks_one_message",
        conversation=(
            "Manager: Team, before Friday please: 1) send me the Q3 budget draft, "
            "2) book the venue for the offsite, 3) confirm catering headcount."
        ),
        expected=[
            # extract_tasks always titles in Vietnamese (see task_tool.py's prompt), even for an
            # English conversation - accept a few plausible translations, not just one exact phrasing.
            ExpectedTask(keywords=("ngân sách", "budget")),
            ExpectedTask(keywords=("địa điểm", "phòng", "venue", "offsite")),
            ExpectedTask(keywords=("khách", "catering", "ăn uống")),
        ],
    ),
    EvalCase(
        name="appointment_not_just_task",
        conversation="Chị ơi 3h chiều mai mình có hẹn khám răng, nhớ nhắc em nhé.",
        expected=[ExpectedTask(keywords=("khám răng",))],
    ),
    EvalCase(
        name="task_buried_in_small_talk",
        conversation=(
            "Alice: haha đúng là vậy đó\n"
            "Bob: đúng rồi, à mà quên, mai deadline nộp đề cương dự án rồi đó\n"
            "Alice: ừ biết rồi, cảm ơn nhắc"
        ),
        expected=[ExpectedTask(keywords=("đề cương",))],
    ),
    EvalCase(
        name="no_task_casual_chat",
        conversation="Bob: haha đúng rồi\nAlice: :)) vui thế\nBob: hôm nay trời đẹp ghê",
        expected=[],
    ),
    EvalCase(
        name="no_task_past_tense_recap",
        conversation="Alice: Hôm qua mình đã gửi báo cáo rồi, sếp đã duyệt xong.",
        expected=[],
    ),
    EvalCase(
        name="question_is_not_a_task",
        conversation="Bob: What time does the meeting usually start on Mondays?",
        expected=[],
    ),
]


def _parse_predicted(raw: str) -> list[dict]:
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _score_case(expected: list[ExpectedTask], predicted: list[dict]) -> tuple[int, int, int]:
    """Greedy keyword matching. Returns (true_positives, false_positives, false_negatives)."""
    remaining = list(predicted)
    true_positives = 0
    for exp in expected:
        match = next(
            (p for p in remaining if any(kw.lower() in p.get("title", "").lower() for kw in exp.keywords)), None
        )
        if match is not None:
            remaining.remove(match)
            true_positives += 1
    false_negatives = len(expected) - true_positives
    false_positives = len(remaining)
    return true_positives, false_positives, false_negatives


async def main() -> None:
    total_tp = total_fp = total_fn = 0
    print(f"Running task-extraction accuracy eval on {len(DATASET)} cases...\n")

    for case in DATASET:
        raw = await extract_tasks.coroutine(state={"context": case.conversation})
        predicted = _parse_predicted(raw)
        tp, fp, fn = _score_case(case.expected, predicted)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        status = "OK  " if fp == 0 and fn == 0 else "MISS"
        print(
            f"[{status}] {case.name}: expected={len(case.expected)} predicted={len(predicted)} "
            f"tp={tp} fp={fp} fn={fn}"
        )
        if fp or fn:
            print(f"       predicted titles: {[p.get('title') for p in predicted]}")

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 1.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    print(f"\nPrecision: {precision:.1%}  Recall: {recall:.1%}  F1: {f1:.1%}")
    if f1 < F1_THRESHOLD:
        print(f"Below {F1_THRESHOLD:.0%} F1 threshold - review the extraction prompt/model.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
