"""Coverage expansion: 11 positive and 12 negative task-extraction cases.

Combined with base/edge/real datasets this produces 60 cases at a 60:40 positive/negative ratio.
The cases emphasize English, negation, completed work and longer multi-speaker conversations.
"""

from datetime import timedelta

from scripts.eval_data.schema import EvalCase, ExpectedTask, next_week_weekday, next_weekday

DATASET: list[EvalCase] = [
    EvalCase(
        name="negative_greeting_and_weekend_chat",
        conversation="An: Chào cả nhà!\nBình: Cuối tuần mọi người có vui không?\nChi: Vui lắm, cảm ơn nhé.",
        expected=[],
    ),
    EvalCase(
        name="negative_information_question_english",
        conversation="Alex: What time does the support rotation normally start on weekdays?",
        expected=[],
    ),
    EvalCase(
        name="negative_completed_release_recap",
        conversation="Lan: We shipped the patch yesterday and QA already signed it off.",
        expected=[],
    ),
    EvalCase(
        name="negative_explicit_do_not_action",
        conversation="Minh: Đừng tạo báo cáo mới nhé, bản cuối đã gửi khách rồi.",
        expected=[],
    ),
    EvalCase(
        name="negative_third_party_assignment",
        conversation="An: Team đối tác sẽ cập nhật hợp đồng trước thứ Sáu; phía mình chỉ cần theo dõi.",
        expected=[],
    ),
    EvalCase(
        name="negative_hypothetical_task",
        conversation="Bình: Nếu dự án được duyệt thì có thể chúng ta sẽ cần viết migration, nhưng chưa quyết định.",
        expected=[],
    ),
    EvalCase(
        name="negative_quoted_instruction",
        conversation="Chi: Ví dụ trong tài liệu ghi 'hãy gửi báo cáo ngày mai', đây chỉ là câu mẫu thôi.",
        expected=[],
    ),
    EvalCase(
        name="negative_rhetorical_deadline_english",
        conversation="David: Do we really need another impossible Friday deadline every sprint?",
        expected=[],
    ),
    EvalCase(
        name="negative_long_multi_party_status_only",
        conversation=(
            "An: Backend hiện ổn định.\nBình: Frontend cũng không còn blocker.\n"
            "Chi: QA hôm qua pass hết rồi.\nDũng: Khách hàng đã xem demo.\n"
            "An: Tuyệt, cảm ơn mọi người.\nBình: Không có đầu việc mới."
        ),
        expected=[],
    ),
    EvalCase(
        name="negative_cancelled_after_long_discussion",
        conversation=(
            "Mai: Ta từng định làm báo cáo benchmark.\nNam: Tôi đã chuẩn bị dữ liệu.\n"
            "Mai: Nhưng khách vừa huỷ yêu cầu.\nNam: Vậy dừng nhé, không ai cần làm tiếp."
        ),
        expected=[],
    ),
    EvalCase(
        name="negative_availability_statement",
        conversation="Huy: Sáng mai tôi bận từ 9 đến 11 giờ, chỉ báo để mọi người biết.",
        expected=[],
    ),
    EvalCase(
        name="negative_past_due_without_recommitment",
        conversation="Trang: Báo cáo đó đã trễ hạn tuần trước và dự án cũng đóng rồi.",
        expected=[],
    ),
    EvalCase(
        name="positive_english_explicit_deadline",
        conversation="Alice: I will send the incident report by 4 PM tomorrow.",
        expected=[
            ExpectedTask(
                keywords=("incident", "sự cố", "báo cáo"),
                expected_date=lambda today: today + timedelta(days=1),
                expected_hour_range=(15, 17),
            )
        ],
    ),
    EvalCase(
        name="positive_english_two_actions",
        conversation="Bob: Please review PR 912 today and publish the release notes on Friday.",
        expected=[
            ExpectedTask(keywords=("PR 912", "review"), expected_date=lambda today: today),
            ExpectedTask(keywords=("release note", "ghi chú"), expected_date=lambda today: next_weekday(today, 4)),
        ],
    ),
    EvalCase(
        name="positive_multi_party_two_owners",
        conversation=(
            "Lan: Cần chốt checklist release trước thứ Năm.\nMinh: Tôi nhận phần checklist.\n"
            "Hà: Tôi sẽ gửi biên bản QA vào chiều mai.\nLan: Cảm ơn hai bạn."
        ),
        expected=[
            ExpectedTask(keywords=("checklist",), expected_date=lambda today: next_weekday(today, 3)),
            ExpectedTask(keywords=("QA", "biên bản"), expected_date=lambda today: today + timedelta(days=1)),
        ],
    ),
    EvalCase(
        name="positive_long_chat_task_at_end",
        conversation=(
            "An: Sáng nay traffic ổn.\nBình: Dashboard cũng ổn.\nChi: QA không thấy regression.\n"
            "Dũng: Khách phản hồi tích cực.\nAn: Vậy tốt rồi.\nBình: À, tôi sẽ gửi số liệu chi phí trước 10h sáng mai."
        ),
        expected=[
            ExpectedTask(
                keywords=("chi phí", "số liệu"),
                expected_date=lambda today: today + timedelta(days=1),
                expected_hour_range=(9, 11),
            )
        ],
    ),
    EvalCase(
        name="positive_corrected_deadline_english",
        conversation=(
            "Sam: I'll deliver the proposal on Wednesday.\nSam: Correction: make that Thursday at 3 PM."
        ),
        expected=[
            ExpectedTask(
                keywords=("proposal", "đề xuất"),
                expected_date=lambda today: next_weekday(today, 3),
                expected_hour_range=(14, 16),
            )
        ],
    ),
    EvalCase(
        name="positive_next_monday_vietnamese",
        conversation="Phương: Tôi sẽ hoàn tất tài liệu onboarding trước thứ Hai tuần sau.",
        expected=[
            ExpectedTask(keywords=("onboarding", "tài liệu"), expected_date=lambda today: next_week_weekday(today, 0))
        ],
    ),
    EvalCase(
        name="positive_code_switch_with_time",
        conversation="Tuấn: Mai 2 PM mình sẽ update deployment checklist nhé.",
        expected=[
            ExpectedTask(
                keywords=("deployment", "checklist"),
                expected_date=lambda today: today + timedelta(days=1),
                expected_hour_range=(13, 15),
            )
        ],
    ),
    EvalCase(
        name="positive_question_as_request_english",
        conversation="Manager: Could you send the customer invoice by noon tomorrow?",
        expected=[
            ExpectedTask(
                keywords=("invoice", "hóa đơn", "hoá đơn"),
                expected_date=lambda today: today + timedelta(days=1),
                expected_hour_range=(11, 13),
            )
        ],
    ),
    EvalCase(
        name="positive_three_tasks_multi_party",
        conversation=(
            "Lead: Trước thứ Sáu cần ba việc.\nAn: Tôi chốt ngân sách.\n"
            "Bình: Tôi đặt phòng demo.\nChi: Tôi gửi danh sách khách."
        ),
        expected=[
            ExpectedTask(keywords=("ngân sách",), expected_date=lambda today: next_weekday(today, 4)),
            ExpectedTask(keywords=("phòng", "demo"), expected_date=lambda today: next_weekday(today, 4)),
            ExpectedTask(keywords=("danh sách", "khách"), expected_date=lambda today: next_weekday(today, 4)),
        ],
    ),
    EvalCase(
        name="positive_same_day_urgent_english",
        conversation="Nina: Please upload the signed contract before 6 PM today.",
        expected=[
            ExpectedTask(
                keywords=("contract", "hợp đồng"),
                expected_date=lambda today: today,
                expected_hour_range=(17, 19),
            )
        ],
    ),
    EvalCase(
        name="positive_task_after_completed_item",
        conversation="Hà: Báo cáo cũ đã xong. Tôi sẽ gửi thêm phụ lục cho khách vào sáng mai.",
        expected=[
            ExpectedTask(keywords=("phụ lục",), expected_date=lambda today: today + timedelta(days=1))
        ],
    ),
]
