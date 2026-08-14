# Khung metric đánh giá hệ thống AI Agent

Tài liệu này định nghĩa cách đánh giá chất lượng cho Orbit AI Agent theo 4 lớp: chất lượng đầu ra, hành vi agent và tool, retrieval/RAG, và vận hành hệ thống. Mục tiêu là tạo một quy trình có thể lặp lại, so sánh được giữa các phiên bản prompt/model và đủ rõ để dùng làm quality gate trước khi phát hành.

> Trạng thái hiện tại: Orbit chưa triển khai RAG/vector database. Tool `search_messages` tìm kiếm từ khóa bằng PostgreSQL `ILIKE` trong một hội thoại. Vì vậy các metric RAGAS ở mục 5 là kế hoạch áp dụng khi có pipeline retrieval thực sự; không được báo cáo chúng như kết quả hiện tại.

## 1. Nguyên tắc đánh giá

- Tách **deterministic tests** (pytest, schema, quyền truy cập, tool side effect) khỏi **LLM evaluation** (độ đúng, groundedness, chất lượng trả lời).
- Đánh giá end-to-end và từng thành phần riêng để biết lỗi đến từ planner, retrieval, tool hay câu trả lời cuối.
- Luôn lưu model, provider, prompt version, dataset version, thời gian chạy, nhiệt độ và cấu hình retrieval.
- Chạy mỗi case không xác định ít nhất 3 lần; báo cáo trung bình, độ lệch chuẩn và pass rate.
- Với hành động có side effect, ưu tiên tiêu chí đúng/sai có thể kiểm chứng hơn LLM-as-a-judge.
- Không dùng cùng một model để vừa tạo ground truth vừa chấm mà không có kiểm duyệt của con người.

## 2. Dataset đánh giá

Nên lưu mỗi case dưới dạng JSONL hoặc dataclass với các trường tối thiểu:

```json
{
  "id": "calendar-create-001",
  "category": "calendar_create",
  "language": "vi",
  "input": "Đặt lịch họp với An lúc 9 giờ sáng mai",
  "conversation_history": [],
  "expected_answer": "Xác nhận trước khi tạo sự kiện",
  "expected_tools": ["create_calendar_event"],
  "expected_arguments": {
    "title": "Họp với An",
    "start_local": "tomorrow 09:00"
  },
  "must_ask_confirmation": true,
  "reference_contexts": [],
  "tags": ["relative-date", "side-effect"]
}
```

Dataset cần bao phủ:

| Nhóm | Ví dụ |
|---|---|
| Trả lời trực tiếp | chào hỏi, câu hỏi không cần tool |
| Task extraction | một/nhiều task, không có task, ngày tương đối, tiếng Việt/Anh |
| Tool routing | task, reminder, calendar, summarize, search messages |
| Tool arguments | title, thời gian, timezone, priority, ID đối tượng |
| Human-in-the-loop | create/update/delete phải yêu cầu xác nhận |
| Hội thoại nhiều lượt | đại từ như “cái đó”, sửa yêu cầu, tham chiếu tin cũ |
| Memory | nhớ đúng thread/user, không rò rỉ dữ liệu giữa user |
| Failure handling | timeout, LLM lỗi, token Google hết hạn, tool trả lỗi |
| Safety/security | prompt injection, truy cập tài nguyên của user khác |
| Retrieval (tương lai) | có tài liệu đúng, không có tài liệu, tài liệu gây nhiễu |

Nên chia cố định thành `dev` để chỉnh prompt, `test` để báo cáo và một tập `challenge` chỉ chạy trước release. Không tối ưu prompt trực tiếp trên tập `test`.

## 3. Metric chất lượng Agent

### 3.1 Task extraction

Repo đã có `scripts/eval_extract_tasks.py`, đo micro-average:

- **Precision** = TP / (TP + FP): tỷ lệ task agent trích ra là đúng.
- **Recall** = TP / (TP + FN): tỷ lệ task thật được agent tìm thấy.
- **F1** = 2 × Precision × Recall / (Precision + Recall).
- **Date accuracy** = số task có ngày/giờ được resolve đúng / tổng task có ngày/giờ cần kiểm tra.
- Nên bổ sung **exact match** cho priority, assignee và timezone nếu schema hỗ trợ.

Chạy:

```powershell
.\.venv\Scripts\python.exe scripts\eval_extract_tasks.py
```

Ngưỡng ban đầu: F1 ≥ 0,80; date accuracy ≥ 0,90; không giảm quá 3 điểm phần trăm so với baseline đã duyệt.

### 3.2 Tool selection và arguments

| Metric | Công thức/ý nghĩa |
|---|---|
| Tool selection accuracy | Số case chọn đúng tập tool / tổng case cần hoặc không cần tool |
| Unnecessary tool-call rate | Case gọi tool khi không cần / tổng case không cần tool |
| Missing tool-call rate | Case không gọi tool cần thiết / tổng case cần tool |
| Argument exact match | Tất cả argument chuẩn hóa khớp ground truth |
| Argument field accuracy | Số field đúng / tổng field được chấm |
| Tool execution success rate | Tool hoàn thành đúng / tổng lần thực thi |
| Average tool calls per task | Phát hiện loop hoặc routing kém hiệu quả |
| Loop/step-limit rate | Run chạm giới hạn bước / tổng run |

Với thời gian tương đối, chuẩn hóa về ISO 8601 theo `Asia/Ho_Chi_Minh` trước khi so sánh. Với chuỗi tự do như title, dùng exact match sau normalize kết hợp semantic judge có rubric; không chỉ dựa vào độ tương đồng embedding.

### 3.3 Chất lượng câu trả lời cuối

- **Task success rate**: người dùng đạt mục tiêu cuối cùng hay không.
- **Correctness**: nội dung có đúng ground truth và kết quả tool không.
- **Completeness**: có trả lời đủ các phần được hỏi không.
- **Instruction following**: đúng ngôn ngữ, format, ràng buộc và yêu cầu xác nhận.
- **Groundedness**: các khẳng định có được hỗ trợ bởi tool output/context không.
- **Hallucination rate**: tỷ lệ câu trả lời chứa ít nhất một khẳng định không có căn cứ.
- **Abstention accuracy**: khi thiếu dữ liệu, agent có nói rõ hoặc hỏi lại đúng lúc không.
- **Human rating**: thang 1–5 cho đúng, hữu ích, rõ ràng và tự nhiên.

LLM-as-a-judge nên dùng rubric 0–4 có mô tả rõ từng mức, chấm ẩn danh, đảo thứ tự khi so sánh A/B và kiểm tra tương quan với một mẫu do con người chấm.

### 3.4 Hội thoại, memory và tính riêng tư

- **Context retention accuracy**: trả lời đúng thông tin đã xuất hiện ở lượt trước.
- **Reference resolution accuracy**: hiểu đúng “nó”, “lịch đó”, “việc vừa nói”.
- **Cross-thread isolation**: không dùng dữ liệu từ thread khác.
- **Cross-user leakage rate**: số case lộ dữ liệu user khác; mục tiêu bắt buộc là 0.
- **Persistence success rate**: checkpoint vẫn đúng sau restart backend.
- **Search hit rate**: `search_messages` tìm thấy tin đúng khi từ khóa có mặt.
- **Search precision@k**: số kết quả keyword search liên quan trong top-k.

## 4. Metric workflow và human-in-the-loop

Các thao tác tạo/sửa/xóa Calendar hoặc Reminder phải được chấm riêng:

| Metric | Target đề xuất |
|---|---:|
| Confirmation compliance | 100% |
| Side effect before confirmation | 0% |
| Correct side effect after accept | ≥ 99% |
| Side effect after reject | 0% |
| Duplicate side-effect rate | 0% |
| Idempotency success khi retry | 100% với luồng hỗ trợ retry |

Một case chỉ pass end-to-end khi: chọn đúng tool, argument đúng, yêu cầu xác nhận đúng, side effect trong database/API đúng và câu trả lời cuối phản ánh đúng kết quả thực thi.

## 5. Đánh giá retrieval và RAGAS (khi triển khai RAG)

### 5.1 Retrieval metric truyền thống

Các metric này cần ground-truth document/chunk ID:

- **Hit Rate@k**: ít nhất một context đúng xuất hiện trong top-k.
- **Recall@k**: tỷ lệ context liên quan được tìm thấy trong top-k.
- **Precision@k**: tỷ lệ context trong top-k thực sự liên quan.
- **MRR**: trung bình nghịch đảo thứ hạng của kết quả đúng đầu tiên.
- **nDCG@k**: đo chất lượng xếp hạng khi relevance có nhiều mức.
- **Context redundancy**: tỷ lệ chunk trùng lặp hoặc gần trùng trong context.
- **Retrieval latency** và **index freshness**.

### 5.2 RAGAS

Một record đánh giá RAG thường cần `user_input`, `response`, `retrieved_contexts` và tùy metric có thêm `reference` hoặc `reference_contexts`.

| Metric RAGAS | Câu hỏi metric trả lời |
|---|---|
| Faithfulness | Các claim trong câu trả lời có suy ra được từ context đã lấy không? |
| Answer relevancy | Câu trả lời có tập trung đúng câu hỏi không? |
| Context precision | Context hữu ích có được xếp trước context nhiễu không? |
| Context recall | Retrieval có lấy đủ thông tin cần để tạo reference answer không? |
| Answer correctness | Câu trả lời giống và đúng với reference đến mức nào? |

Không dùng riêng một điểm RAGAS tổng hợp. Cần xem retrieval metrics và generation metrics tách biệt:

- Context recall thấp → vấn đề retrieval/chunking/query rewrite.
- Context tốt nhưng faithfulness thấp → vấn đề prompt/generation.
- Faithfulness cao nhưng answer correctness thấp → context hoặc reference không đủ/không đúng.

Ngưỡng khởi đầu sau khi có baseline: faithfulness ≥ 0,90; answer relevancy ≥ 0,80; context precision ≥ 0,75; context recall ≥ 0,80. Ngưỡng phải được hiệu chỉnh bằng dataset thật và đánh giá con người, không coi điểm judge là chân lý tuyệt đối.

### 5.3 Kiểm thử RAG bắt buộc

- Câu hỏi có đáp án rõ trong tài liệu.
- Câu hỏi cần tổng hợp từ nhiều chunk/tài liệu.
- Câu hỏi không có đáp án: agent phải từ chối suy đoán.
- Tài liệu mâu thuẫn hoặc khác phiên bản: ưu tiên nguồn mới/đáng tin.
- Prompt injection nằm trong tài liệu: không được coi chỉ dẫn trong tài liệu là system instruction.
- Kiểm tra phân quyền retrieval để không lấy tài liệu của tenant/user khác.

## 6. Metric hiệu năng, chi phí và độ tin cậy

Đo theo p50, p95 và p99, không chỉ dùng trung bình:

| Nhóm | Metric |
|---|---|
| Latency | time-to-first-token, end-to-end latency, tool latency, retrieval latency |
| Reliability | success rate, timeout rate, retry rate, exception rate |
| Token | input/output/total tokens mỗi request và mỗi task thành công |
| Cost | chi phí mỗi request, mỗi user, mỗi task thành công |
| Capacity | request/giây, concurrent sessions, DB pool saturation |
| Availability | uptime của API, LLM provider và external tools |

Target ban đầu gợi ý: API không gọi LLM p95 < 500 ms; agent end-to-end p95 < 8 giây cho luồng không có external API chậm; error rate < 1%; ghi nhận 100% usage LLM. Điều chỉnh target sau khi có số liệu baseline thực tế.

## 7. Safety và security evaluation

- Prompt injection success rate.
- Unauthorized tool-call rate.
- Cross-user/tenant data leakage rate.
- Secret/credential exposure rate.
- PII leakage rate.
- Destructive action without confirmation rate.
- Invalid/expired token acceptance rate.
- Rate-limit bypass rate.

Các lỗi rò rỉ dữ liệu, vượt quyền hoặc side effect chưa xác nhận là **release blocker**, không lấy trung bình với các metric chất lượng khác.

## 8. Quality gate đề xuất

| Gate | Điều kiện pass ban đầu |
|---|---:|
| Pytest | 100% test pass |
| Ruff | Không có lỗi |
| Task extraction F1 | ≥ 0,80 |
| Date accuracy | ≥ 0,90 |
| Tool selection accuracy | ≥ 0,90 |
| Confirmation compliance | 100% |
| Cross-user leakage | 0 case |
| End-to-end task success | ≥ 0,85 |
| Hallucination rate trên factual set | ≤ 0,05 |
| Agent latency p95 | < 8 giây, trừ case external API được gắn nhãn |

Ngoài ngưỡng tuyệt đối, chặn release nếu metric chính giảm quá 3 điểm phần trăm hoặc latency/cost tăng trên 20% so với baseline mà không có lý do được duyệt.

## 9. Quy trình chạy và báo cáo

1. Chạy deterministic tests và lint.
2. Chạy component eval: extraction, routing, arguments, retrieval.
3. Chạy end-to-end dataset với model thật; lưu raw trace và tool calls.
4. Chạy judge tự động, sau đó người đánh giá kiểm tra toàn bộ case lỗi và ít nhất 10% case pass.
5. So sánh với baseline theo cùng dataset/config.
6. Ghi kết quả vào `eval/results/` và quyết định pass/fail theo quality gate.

Lệnh hiện có:

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m pytest tests -v
.\.venv\Scripts\python.exe scripts\eval_extract_tasks.py
```

Mẫu báo cáo mỗi lần chạy:

```markdown
# Agent Evaluation — YYYY-MM-DD

- Git commit:
- Dataset version:
- Provider/model:
- Prompt version:
- Runs per case:
- Evaluator model/version:

| Metric | Baseline | Current | Delta | Target | Status |
|---|---:|---:|---:|---:|---|
| Task extraction F1 | | | | 0.80 | |
| Date accuracy | | | | 0.90 | |
| Tool selection accuracy | | | | 0.90 | |
| End-to-end task success | | | | 0.85 | |
| Latency p95 | | | | 8 s | |
| Cost/successful task | | | | | |

## Failure analysis

| Case ID | Failure layer | Expected | Actual | Root cause | Action |
|---|---|---|---|---|---|
```

## 10. Thứ tự triển khai thực tế

1. Mở rộng dataset hiện có và giữ metric extraction làm baseline.
2. Thêm trace chuẩn hóa cho planner, tool name, arguments, latency và token usage.
3. Viết evaluator deterministic cho tool routing, arguments, confirmation và side effects.
4. Thêm end-to-end task success cùng rubric human/LLM judge.
5. Chỉ thêm RAGAS sau khi dự án có ingestion, chunking, embedding và retrieval thực sự.

