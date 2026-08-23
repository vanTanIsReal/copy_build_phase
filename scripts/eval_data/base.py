"""The original 8 hand-written eval cases - moved verbatim out of eval_extract_tasks.py (pure
refactor, not a behavior change) when the dataset was split into scripts/eval_data/."""

from datetime import timedelta

from scripts.eval_data.schema import EvalCase, ExpectedTask, next_weekday

DATASET: list[EvalCase] = [
    EvalCase(
        name="single_task_explicit_weekday",
        conversation="Alice: Nhớ gửi báo cáo doanh thu cho sếp trước thứ Sáu này nhé.\nBob: ok để mình làm.",
        expected=[ExpectedTask(keywords=("báo cáo",), expected_date=lambda today: next_weekday(today, 4))],
    ),
    EvalCase(
        name="single_task_relative_date",
        conversation="Bob: Can you review the PR by tomorrow morning? It's blocking the release.",
        expected=[ExpectedTask(keywords=("PR",), expected_date=lambda today: today + timedelta(days=1))],
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
            ExpectedTask(keywords=("ngân sách", "budget"), expected_date=lambda today: next_weekday(today, 4)),
            ExpectedTask(
                keywords=("địa điểm", "phòng", "venue", "offsite"),
                expected_date=lambda today: next_weekday(today, 4),
            ),
            ExpectedTask(keywords=("khách", "catering", "ăn uống"), expected_date=lambda today: next_weekday(today, 4)),
        ],
    ),
    EvalCase(
        name="appointment_not_just_task",
        conversation="Chị ơi 3h chiều mai mình có hẹn khám răng, nhớ nhắc em nhé.",
        expected=[
            ExpectedTask(
                keywords=("khám răng",),
                expected_date=lambda today: today + timedelta(days=1),
                expected_hour_range=(14, 16),
            )
        ],
    ),
    EvalCase(
        name="task_buried_in_small_talk",
        conversation=(
            "Alice: haha đúng là vậy đó\n"
            "Bob: đúng rồi, à mà quên, mai deadline nộp đề cương dự án rồi đó\n"
            "Alice: ừ biết rồi, cảm ơn nhắc"
        ),
        expected=[ExpectedTask(keywords=("đề cương",), expected_date=lambda today: today + timedelta(days=1))],
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
