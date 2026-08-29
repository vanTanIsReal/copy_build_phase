# Evaluation Evidence — Orbit

Generated at `2026-08-29T13:26:06.606137+00:00` from source revision `17aa87d`
with uncommitted evaluation changes.

This report never converts missing evidence into a passing score. `PENDING` means the runner or
protocol exists but no current result artifact is available.

## 1. Release evidence summary

| Evidence | Result | Gate | Status |
|---|---:|---:|---|
| Automated tests | 414/414 passed, 0 skipped | No failures/errors | PASS |
| Source coverage | 66.8% | >=60% | PASS |
| Formal Agent acceptance | 50.0% case pass | Dataset gates | FAIL |
| Task title F1 | 97.0% | >=70% | PASS |
| Deadline accuracy | 95.3% | >=70% | PASS |
| API latency P95 | 21.2 ms | Configured runner gate | PASS |
| Staging chat | 10/10; P95 4545.1 ms | All complete; P95 <=5000 ms | PASS |
| PostgreSQL memory harness | 17/17 passed | No failures/errors | PASS |
| Staging WebSocket | 0/5 connected | 5 connections and all deliveries | FAIL |
| Staging HTTP load | 85/100 2xx | All requests return 2xx | FAIL |
| Browser functional E2E | User/admin login, chat, and routes | All functional checks pass | PASS |
| Browser accessibility | Serious/critical findings remain | Zero serious/critical findings | FAIL |
| Lighthouse aggregate | Both user/admin surfaces | All configured web gates pass | FAIL |
| Google Calendar OAuth | PARTIAL | Interactive consent and token exchange | FAIL |
| User feedback | Pending | >=5 participants | PENDING |

## 2. Vì sao từng mục là FAIL hoặc PENDING

Kết luận phát hành tổng thể: **FAIL** vì một hoặc nhiều gate bắt buộc dưới đây chưa đạt.

- **Formal Agent acceptance = FAIL:** chỉ 50.0% số case đạt; `case_pass_rate` 50.0% so với ngưỡng 80.0%; `tool_routing_accuracy` 59.3% so với ngưỡng 95.0%; `memory_isolation_pass_rate` 0.0% so với ngưỡng 100.0%.

- **Staging WebSocket = FAIL:** chỉ mở được 0/5 kết nối. Handshake trả về `Unexpected server response: 403`, nên không thể đo độ trễ phân phối hoặc quan sát event reminder qua WebSocket.

- **Staging HTTP load = FAIL:** chỉ 85/100 request trả về 2xx; phân bố status là `{"200": 85, "429": 15}`. 15 phản hồi HTTP 429 cho thấy đã chạm rate limit; đây không phải lỗi sập 5xx, nhưng vẫn không đạt gate yêu cầu toàn bộ request trả về 2xx.

- **Browser accessibility = FAIL:** gate yêu cầu không có lỗi serious/critical, nhưng ghi nhận 14 lỗi theo route user và 11 lỗi theo route admin. Các nhóm lỗi gồm `button-name, color-contrast, empty-table-header, heading-order, label, landmark-unique, nested-interactive, page-has-heading-one, select-name`; tổng theo route có thể lặp lại cùng một nhóm lỗi.

- **Lighthouse aggregate = FAIL:** performance user 61 < 80 và LCP user 6505.108 ms > 2500 ms; accessibility admin 83 < 90 và LCP admin 3642.232 ms > 2500 ms. Accessibility user, performance admin và hai phép đo CLS đều đạt, nhưng gate tổng yêu cầu tất cả phép kiểm tra cùng đạt.

- **Google Calendar OAuth = FAIL/PARTIAL:** cấu hình runtime tạo thành công URL cấp quyền Google và callback origin khớp staging, nhưng `currently_connected` là `false` và consent tương tác là `NOT_RUN`. Chưa có authorization code/token exchange, nên chưa thể đánh dấu truy cập Calendar riêng tư là PASS.

- **User feedback = PENDING:** mới ghi nhận 0/5 người dùng thật bắt buộc. 5 phản hồi được tạo là dữ liệu kiểm thử hư cấu đã gắn nhãn rõ ràng và không được tính vào bằng chứng phát hành.

## 3. Current measured AI quality

- Formal acceptance: `2026-08-29T08:22:15.022026+00:00` using
  `openrouter/openai/gpt-4.1-mini`.
- Task extraction: `60` cases; title precision
  `96.0%`, recall
  `98.0%`, F1 `97.0%`.
- Missing or failed gates remain release risks even when deterministic unit tests pass.

## 4. Synthetic feedback (not release evidence)

The synthetic demo contains `5` fictional
participants and is labeled `INSUFFICIENT_DATA`. It is useful only to exercise the reporting pipeline and is never
substituted for the real feedback row above.

## 5. Reproducible commands

```powershell
python scripts/run_coverage.py
python scripts/benchmark_api_latency.py --base-url http://127.0.0.1:8000 --endpoint /health
python scripts/eval_user_agent.py
python scripts/eval_extract_tasks.py
python scripts/summarize_user_feedback.py
python scripts/generate_evaluation_evidence.py
```

## 6. Traceability and evidence locations

- Requirement-to-test-to-code map: [`TRACEABILITY_MATRIX.md`](TRACEABILITY_MATRIX.md)
- Manual scenarios: [`../MANUAL_TEST_CASES.md`](../MANUAL_TEST_CASES.md)
- Screenshot/video evidence: [`../Deliverables/evidence/`](../Deliverables/evidence/)
- Formal acceptance: [`results/agent_acceptance_latest.md`](results/agent_acceptance_latest.md)
- PostgreSQL memory harness: [`results/memory-harness-postgres-latest.md`](results/memory-harness-postgres-latest.md)
- Staging realtime/load: [`results/realtime-load-staging-latest.md`](results/realtime-load-staging-latest.md)
- Browser E2E/accessibility: [`results/browser-e2e-staging-latest.md`](results/browser-e2e-staging-latest.md)
- Lighthouse: [`results/lighthouse-staging-latest.md`](results/lighthouse-staging-latest.md)
- Calendar OAuth: [`results/calendar-oauth-staging-latest.md`](results/calendar-oauth-staging-latest.md)
- Synthetic feedback demo: [`results/user-feedback-synthetic-demo.md`](results/user-feedback-synthetic-demo.md)
- Evaluation protocols and commands: [`README.md`](README.md)

## 7. Evidence still requiring human/external execution

- User satisfaction requires real anonymized participants; no synthetic rating is accepted.
- Calendar token exchange requires a user to complete Google's interactive consent flow.
- INP requires real-user or controlled interaction data; navigation-only Lighthouse does not measure it.
- Coverage/JUnit artifacts must be regenerated after material source changes.
