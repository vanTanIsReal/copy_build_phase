# Quality Assurance Agent — Ngày 1

Ngày 1 khóa metadata, readiness rules, profile skeleton và fixture expectations. Phạm vi này chưa
nối Quality Agent vào `/chat`, chưa đọc database thật và chưa thực thi side effect; các phần đó thuộc
vertical slice các ngày tiếp theo.

## Contract metadata MVP

Mỗi fact QA đi qua `QualityWorkItem` và bắt buộc có `work_item_id`, `title`, `work_item_type`,
`severity`, `quality_status` và `source_id`.

| Field | Giá trị hợp lệ |
|---|---|
| `work_item_type` | `bug`, `test_case`, `release_check` |
| `severity` | `low`, `medium`, `high`, `critical` |
| `quality_status` | `open`, `testing`, `passed`, `failed`, `blocked` |

Schema là strict và immutable. Field ngoài contract bị từ chối. `source_id` là bắt buộc để mọi finding
có thể truy ngược tới nguồn đã được scope resolver/guard cho phép.

## Readiness rules v1

Rule được thực thi bằng code trong `evaluate_release_readiness`; model chỉ diễn giải kết quả và không
được tự đổi readiness.

Thứ tự ưu tiên:

1. `NOT_READY` nếu có critical bug chưa pass, thiếu required release check, hoặc required release check
   đang `failed`/`blocked`.
2. `AT_RISK` nếu có bug non-critical chưa pass, test `failed`/`blocked`, required release check còn
   `open`/`testing`, hoặc request chưa khai báo required release checks.
3. `READY` chỉ khi có ít nhất một required release check được khai báo, mọi required check đều hiện diện
   và `passed`, không còn bug unresolved và không còn test failed/blocked.

Thiếu dữ liệu được trả trong `data_gaps`. `READY` cùng `data_gaps` bị output schema từ chối.

## Guardrails đã khóa

- Không đọc raw Product Delivery conversations; chỉ nhận structured release/dependency reference.
- Không tự hạ severity, đóng bug, đổi status, gửi reminder hoặc tạo meeting.
- Side effect chỉ được tạo proposal để policy kiểm tra và chờ human confirmation.
- Mọi finding phải có `source_id`; không suy đoán fact bị thiếu.

## Golden fixture expectations

Nguồn chuẩn là 15 case `QLT-001` đến `QLT-015` trong
`eval/datasets/multi_agent_workspace_v1.jsonl`: 5 `NOT_READY`, 5 `AT_RISK`, 5 `READY`.
Test `test_day_one_has_exactly_fifteen_quality_fixture_expectations` chạy cùng readiness rules để chống
drift giữa schema/rule và dataset.

## Deliverables

- `src/agents/schemas/quality.py`
- `src/agents/profiles/quality_assurance.py`
- `tests/test_agents/test_quality_assurance.py`
- 15 fixture expectations trong dataset v1 hiện có

