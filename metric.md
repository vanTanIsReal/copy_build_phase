# Agent Evaluation Metrics

Tài liệu này mô tả các chỉ số dùng để đánh giá khả năng trích xuất task của hệ thống agent.

## Cách chạy

```powershell
.\.venv\Scripts\python.exe scripts\eval_extract_tasks.py
```

Mặc định, kết quả chi tiết được ghi vào:

```text
eval/results/task_extraction_latest.json
```

Có thể chọn đường dẫn khác:

```powershell
.\.venv\Scripts\python.exe scripts\eval_extract_tasks.py --output eval/results/my_report.json
```

Script sử dụng LLM thật được cấu hình trong `.env`, do đó có thể tiêu tốn token hoặc quota API.

## Các metric

### Precision

Tỷ lệ task dự đoán đúng trên tổng số task agent đã trích xuất.

```text
Precision = TP / (TP + FP)
```

Precision thấp cho thấy agent tạo nhiều task không tồn tại trong hội thoại.

### Recall

Tỷ lệ task được phát hiện trên tổng số task thực tế cần trích xuất.

```text
Recall = TP / (TP + FN)
```

Recall thấp cho thấy agent bỏ sót nhiều task.

### F1 Score

Trung bình điều hòa giữa Precision và Recall.

```text
F1 = 2 × Precision × Recall / (Precision + Recall)
```

Ngưỡng hiện tại: **F1 >= 70%**.

### Exact-match rate

Tỷ lệ test case mà agent trích xuất đúng toàn bộ task, không thừa và không thiếu. Output không hợp lệ cũng được tính là không exact-match.

```text
Exact-match rate = số case đúng hoàn toàn / tổng số case
```

### Valid-output rate

Tỷ lệ phản hồi có thể parse thành một JSON array, trong đó mỗi phần tử là một object.

```text
Valid-output rate = số output hợp lệ / tổng số case
```

Mục tiêu khuyến nghị: **100%**.

### Date accuracy

Tỷ lệ ngày hoặc thời gian được trích xuất đúng đối với các task có thông tin deadline. Metric này kiểm tra cả ngày tương đối như `tomorrow`, `mai` hoặc `this Friday` theo múi giờ cấu hình của hệ thống.

```text
Date accuracy = số ngày đúng / tổng số ngày được kiểm tra
```

Ngưỡng hiện tại: **Date accuracy >= 70%**.

### Latency

Thời gian agent xử lý một test case, tính bằng millisecond.

- `latency_mean_ms`: thời gian trung bình.
- `latency_p50_ms`: 50% request hoàn thành nhanh hơn hoặc bằng giá trị này.
- `latency_p95_ms`: 95% request hoàn thành nhanh hơn hoặc bằng giá trị này.

Mục tiêu khuyến nghị: **P95 < 3 giây**. Kết quả có thể thay đổi theo model, provider và tình trạng mạng.

## Ý nghĩa TP, FP và FN

| Ký hiệu | Ý nghĩa |
|---|---|
| TP | Task được agent trích xuất và khớp với dữ liệu kỳ vọng |
| FP | Task được agent tạo ra nhưng không có trong dữ liệu kỳ vọng |
| FN | Task có trong dữ liệu kỳ vọng nhưng agent bỏ sót |

## Tiêu chí đạt đề xuất

| Metric | Ngưỡng |
|---|---:|
| F1 Score | >= 70% |
| Date accuracy | >= 70% |
| Exact-match rate | >= 80% |
| Valid-output rate | 100% |
| Latency P95 | < 3.000 ms |

Script hiện trả exit code khác `0` khi F1 hoặc Date accuracy thấp hơn ngưỡng cấu hình. Các metric còn lại được ghi nhận để theo dõi và chưa làm thất bại lần chạy.

## Báo cáo JSON

Báo cáo gồm hai phần:

- `metrics`: kết quả tổng hợp của toàn bộ dataset.
- `cases`: kết quả chi tiết theo từng test case, bao gồm số lượng task kỳ vọng, số lượng dự đoán, TP/FP/FN, độ chính xác ngày và latency.

Không nên commit API key, nội dung `.env` hoặc dữ liệu hội thoại nhạy cảm vào báo cáo eval.
