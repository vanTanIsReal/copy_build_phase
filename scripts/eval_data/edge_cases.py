"""Additional synthetic cases targeting specific failure modes not easily produced on demand in a
natural back-and-forth (real_conversations.py) - timezone/midnight boundaries, sarcasm/rhetorical
questions that must NOT become tasks, more date-phrase variety, third-party FYIs, and recall under
a longer task list. Paraphrased/invented by the dev team, not copied from any real conversation -
same sourcing note as real_conversations.py.
"""

from datetime import timedelta

from scripts.eval_data.schema import EvalCase, ExpectedTask, next_weekday

DATASET: list[EvalCase] = [
    # Category: midnight/timezone boundary - "tonight" said late should still resolve to today's
    # date, at a late hour, not accidentally roll over to tomorrow.
    EvalCase(
        name="late_night_today_deadline",
        conversation="Trang: anh gửi giúp em bản báo cáo trước 11h tối nay nhé, gấp lắm",
        expected=[
            ExpectedTask(keywords=("báo cáo",), expected_date=lambda today: today, expected_hour_range=(22, 23))
        ],
    ),
    # Category: early-tomorrow-morning hour range.
    EvalCase(
        name="early_tomorrow_morning",
        conversation="Huy: nhớ gọi cho khách sáng sớm mai lúc 7h nhé, đừng để trễ",
        expected=[
            ExpectedTask(keywords=("gọi", "khách"), expected_date=lambda today: today + timedelta(days=1), expected_hour_range=(6, 8))
        ],
    ),
    # Category: sarcasm/hyperbolic complaint that mentions a deadline but isn't a real commitment
    # request - precision stress test.
    EvalCase(
        name="sarcastic_complaint_not_a_task",
        conversation="Duy: chắc tối nay lại phải cày báo cáo tới sáng luôn quá, khổ thân tôi ghê",
        expected=[],
    ),
    # Category: rhetorical/complaining question, not an actual request for anyone to do anything.
    EvalCase(
        name="rhetorical_question_not_a_task",
        conversation="Mai: chẳng lẽ lại phải nộp báo cáo vào Chủ nhật nữa à, mệt quá",
        expected=[],
    ),
    # Category: third-party FYI - informing the group about someone else's deadline, not asking
    # the reader (or anyone in the chat) to do anything.
    EvalCase(
        name="third_party_fyi_not_actionable",
        conversation="Long: nghe nói bên team design họ phải nộp bản demo cho khách thứ Sáu này đó",
        expected=[],
    ),
    # Category: explicit past-completion after being asked - recap phrased as a direct reply,
    # closer to how it happens in a real thread than base.py's standalone recap case.
    EvalCase(
        name="explicit_past_completion_reply",
        conversation=(
            "Sếp: em nộp báo cáo chi phí tuần này chưa?\nEm: dạ em nộp hôm qua rồi ạ, sếp kiểm tra giúp em nhé"
        ),
        expected=[],
    ),
    # Category: English date phrase "EOD Friday".
    EvalCase(
        name="date_phrase_eod_friday",
        conversation="Sam: Please send the client the final invoice by EOD Friday, no later.",
        # Both "hóa đơn" and "hoá đơn" are valid modern-vs-traditional placements of the tone mark
        # for the same word - accept either spelling, same reasoning as the multi-keyword OR
        # pattern used throughout this dataset for translation variance.
        expected=[
            ExpectedTask(keywords=("invoice", "hóa đơn", "hoá đơn"), expected_date=lambda today: next_weekday(today, 4))
        ],
    ),
    # Category: Vietnamese "cuối tháng" (end of month) - loose enough to just check recall, not a
    # specific date (end-of-month resolution is genuinely ambiguous even for a human), so no
    # expected_date assertion here.
    EvalCase(
        name="date_phrase_end_of_month",
        conversation="Yến: nhớ chốt số liệu doanh thu cuối tháng này nhé, sếp cần để họp",
        expected=[ExpectedTask(keywords=("doanh thu",), expected_date=None)],
    ),
    # Category: Vietnamese "đầu tuần sau" (early next week) - loose window, recall-only.
    EvalCase(
        name="date_phrase_early_next_week",
        conversation="Đạt: gửi lại bản hợp đồng đã sửa đầu tuần sau giúp anh nhé",
        expected=[ExpectedTask(keywords=("hợp đồng",), expected_date=None)],
    ),
    # Category: request phrased as a question that still functions as a real ask (not rhetorical -
    # contrast with rhetorical_question_not_a_task above).
    EvalCase(
        name="request_phrased_as_question",
        conversation="Phương: chị gửi lại bản thiết kế trước thứ Sáu này được không ạ?",
        expected=[ExpectedTask(keywords=("thiết kế",), expected_date=lambda today: next_weekday(today, 4))],
    ),
    # Category: longer list (4 items) to stress recall count beyond base.py's 3-item case.
    EvalCase(
        name="four_tasks_one_message",
        conversation=(
            "Sếp: trước thứ Sáu này team làm giúp anh 4 việc: 1) chốt ngân sách quý, "
            "2) gửi báo giá cho khách A, 3) đặt lịch họp với đối tác, 4) in tài liệu cho buổi demo."
        ),
        expected=[
            ExpectedTask(keywords=("ngân sách",), expected_date=lambda today: next_weekday(today, 4)),
            ExpectedTask(keywords=("báo giá",), expected_date=lambda today: next_weekday(today, 4)),
            ExpectedTask(keywords=("lịch họp", "đối tác"), expected_date=lambda today: next_weekday(today, 4)),
            ExpectedTask(keywords=("tài liệu", "in"), expected_date=lambda today: next_weekday(today, 4)),
        ],
    ),
    # Category: same task confirmed by two different people in the thread - must not be extracted
    # twice (extract_tasks has no dedup requirement in its contract, but a well-behaved run should
    # still only surface it once per mention, not duplicate per speaker who agrees) - scored the
    # same as a single-task case; if the model doubles it up, false-positive count catches it.
    EvalCase(
        name="same_task_confirmed_by_two_people",
        conversation=(
            "Sếp: cả nhóm nhớ nộp báo cáo tháng trước thứ Hai nhé\n"
            "An: dạ em nhớ rồi ạ\n"
            "Bình: em cũng nhớ rồi sếp ơi"
        ),
        expected=[ExpectedTask(keywords=("báo cáo",), expected_date=lambda today: next_weekday(today, 0))],
    ),
    # Category: birthday/personal reminder rather than a work task - still a real appointment,
    # extract_tasks isn't scoped to "work only" so this should still be picked up.
    EvalCase(
        name="personal_reminder_not_work",
        conversation="Ngọc: đừng quên sinh nhật mẹ tao thứ Bảy này nha, nhớ mua quà",
        expected=[ExpectedTask(keywords=("sinh nhật", "quà"), expected_date=lambda today: next_weekday(today, 5))],
    ),
    # Category: "in N days" relative phrase.
    EvalCase(
        name="date_phrase_in_two_days",
        conversation="Khánh: nộp bản nháp thiết kế trong 2 ngày nữa giúp mình nhé.",
        expected=[ExpectedTask(keywords=("thiết kế",), expected_date=lambda today: today + timedelta(days=2))],
    ),
    # Category: greeting/small talk only - no task at all, different tone than base.py's casual
    # chat case (more messages, still nothing actionable).
    EvalCase(
        name="pure_small_talk_longer",
        conversation=(
            "Vân: chào buổi sáng\nĐức: chào chị, ngủ ngon không\nVân: ổn, mai đi làm sớm ghê\nĐức: em cũng vậy"
        ),
        expected=[],
    ),
    # Category: complaint about a PAST missed deadline - backward-looking, not a new task.
    EvalCase(
        name="past_missed_deadline_complaint",
        conversation="Tùng: hôm qua deadline nộp báo cáo mà quên mất, chết rồi",
        expected=[],
    ),
    # Category: explicit cancellation phrased differently from real_conversations.py's version -
    # "thôi khỏi" instead of "khỏi cần" - precision stress test with different phrasing.
    EvalCase(
        name="task_cancelled_different_phrasing",
        conversation=(
            "Hải: nhớ đặt vé máy bay cho chuyến công tác thứ Ba nhé\nHải: à thôi khỏi, chuyến đi bị huỷ rồi"
        ),
        expected=[],
    ),
    # Category: two unrelated tasks with two different explicit dates in the same message (not a
    # conflict - two separate items, not the same item revised).
    EvalCase(
        name="two_tasks_two_different_dates",
        conversation=(
            "Quản lý: nộp báo cáo tuần trước thứ Sáu này, còn báo cáo tháng thì để đầu tuần sau cũng được."
        ),
        expected=[
            ExpectedTask(keywords=("báo cáo tuần", "tuần"), expected_date=lambda today: next_weekday(today, 4)),
            ExpectedTask(keywords=("báo cáo tháng", "tháng"), expected_date=None),
        ],
    ),
    # Category: apology/excuse for being late on something, without re-committing to a new date -
    # should not fabricate a new task with a guessed date.
    EvalCase(
        name="apology_without_new_commitment",
        conversation="Trâm: xin lỗi mọi người, báo cáo của em bị trễ, em đang cố gắng hoàn thành",
        expected=[],
    ),
    # Category: explicit urgent same-day task with no clock time - date-only, no hour check.
    EvalCase(
        name="urgent_same_day_no_time",
        conversation="Bảo: gấp lắm, nộp ngay hồ sơ thầu hôm nay giúp anh nhé",
        expected=[ExpectedTask(keywords=("hồ sơ thầu", "hồ sơ"), expected_date=lambda today: today)],
    ),
]
