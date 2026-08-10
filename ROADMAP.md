# Roadmap — hoàn thiện "AI Agent Trợ lý cá nhân trong Chat" theo đề bài

Đề bài gốc: [Frontend/detai.md](Frontend/detai.md). Kiến trúc/quyết định công nghệ chi tiết:
[ARCHITECTURE.md](ARCHITECTURE.md). Nhật ký chi tiết từng thay đổi: [WORKLOG.md](WORKLOG.md). Tài
liệu này chỉ theo dõi **tiến độ theo yêu cầu đề bài** — cập nhật trạng thái mỗi khi một mục hoàn
thành.

## Bảng hiện trạng (gap analysis)

| Yêu cầu | Trạng thái | Ghi chú |
| --- | --- | --- |
| Deploy online, đăng nhập, ≥2 role | 🟡 Một phần | Auth (JWT+bcrypt) + role user/admin đã chạy thật; `Dockerfile`/`docker-compose.yml` có sẵn nhưng **chưa deploy lên domain public**, chưa có CD |
| Tóm tắt hội thoại theo yêu cầu | 🟢 Xong | Nút Summarize trong `AIPanel.jsx` gọi `/api/v1/chat` thật |
| Trích xuất task + tạo nhắc việc có xác nhận | 🟢 Xong | Tool `extract_tasks` + `create_reminder` (human-in-the-loop), `/tasks` và `/reminders` nối API thật |
| Hiển thị lịch cá nhân | 🟢 Xong | `/calendar` gọi Google Calendar API thật (CRUD đầy đủ) |
| Memory hội thoại | 🟢 Xong | `AsyncPostgresSaver` khi `DATABASE_URL` là Postgres — bền vững qua restart backend |
| Xử lý lỗi cơ bản | 🟢 Xong | `ChatResponse` có `status: "error"` trả lỗi thật; agent không gọi LLM lần 2 gây lỗi 400 |
| Agent chủ động phát hiện cam kết | 🟢 Xong | `proactive_service.py` — pre-filter regex + kiểm tra `ai_permissions` của người gửi + LLM xác nhận, tạo Task gợi ý, đẩy realtime. Nhận task với due_at rồi bấm **Accept** trong `/tasks` (chính là bước xác nhận human-in-the-loop) sẽ tự tạo thêm sự kiện Google Calendar + Reminder thật (`task_routes.py::_add_to_calendar_and_reminder`) |
| Đồng bộ Google Calendar 2 chiều | 🟢 Xong | Ghi (app→Google) qua REST/agent tool; đọc thay đổi từ Google qua polling `syncToken` (`poll_calendar_changes`, mỗi 20s) — xem ghi chú bên dưới về giới hạn |
| Dashboard "inbox nhiệm vụ" ưu tiên | 🟢 Xong | `/tasks/inbox` (`TaskInboxPage.jsx`, nav "Inbox" trong Sidebar) — view tách riêng khỏi `/tasks`, nhóm theo 4 mức ưu tiên (cần quyết định / quá hạn / sắp đến hạn trong 48h / priority cao), realtime qua cùng kênh WebSocket đã có |
| Cảnh báo vượt hạn mức token/chi phí | 🟢 Xong | `usage_service._maybe_alert_budget` đẩy WebSocket `usage_budget_alert` tới mọi admin đang online ngay khi vượt 80%/100% (edge-triggered, không lặp lại nếu không có ngưỡng mới vượt) — hiện ở bất kỳ trang nào admin đang mở (`BudgetAlertToast`), không chỉ khi mở Admin dashboard; **và** `usage_service.is_over_budget()` chặn hẳn cuộc gọi LLM mới (`/chat`, proactive detection) một khi đã chạm ngân sách — `/chat/resume` cố tình được miễn trừ để không làm treo một hành động con người đã xác nhận rồi. Verify thật qua UI (không phải chỉ unit test): xem WORKLOG.md |
| Đánh giá độ chính xác trích xuất task | 🟢 Xong (mẫu nhỏ) | `scripts/eval_extract_tasks.py` — chấm riêng title (P/R/F1) và **date accuracy** (`due_at` có resolve đúng "ngày mai"/"thứ Sáu này" theo ngày chạy thật không — 2 thứ lệch pha, title đúng không đảm bảo ngày đúng). Hiện tại: Title F1 = 100%, Date accuracy = 100% trên 8 case tay (VI+EN, 7/8 case có ngày); nên coi là bằng chứng ban đầu, chưa phải benchmark quy mô lớn |
| Ràng buộc: quyền riêng tư tin nhắn / agent chỉ đọc hội thoại được cấp quyền | 🟢 Xong | `/api/v1/chat` chặn user A mượn nội dung hội thoại của user B qua `conversation_id` giả, **và** bảng `ai_permissions` thật (`conversation_id`, `user_id`, `granted`) — mặc định **chưa cấp quyền**, `POST /api/v1/chat` từ chối (403) đọc bất kỳ `conversation_id` nào chưa được chính người dùng đó cấp quyền qua `GET/PUT /conversations/{id}/ai-permission`. Nút bật/tắt trong `ConversationHeader.jsx` (badge cạnh tên hội thoại) và `AIPanel.jsx` dùng chung 1 nguồn trạng thái, gọi API thật. `proactive_service.maybe_suggest_task` (dò cam kết chạy nền trên mọi tin nhắn mới) cũng kiểm tra quyền này trước khi gọi LLM — tắt là AI không đọc kể cả khi chạy nền, không riêng gì lúc mở AI panel |
| Ràng buộc: tối ưu độ trễ/chi phí (cache embedding, batch LLM call) | ⚪ Không áp dụng được | App không dùng vector store/embedding ở đâu cả nên không có gì để cache; pre-filter regex trước khi gọi LLM (proactive detection) là tối ưu duy nhất thực sự áp dụng được |
| Ràng buộc: human-in-the-loop trước khi tạo/gửi lịch, nhắc việc | 🟢 Xong | `interrupt()` bắt buộc cho mọi tool có tác dụng phụ (calendar CRUD, `create_reminder`) |

🟢 Xong · 🟡 Một phần · ⚪ Không áp dụng · 🔴 Chưa có

## Còn lại — theo độ ưu tiên

1. **Deploy online thật** — hạng mục lớn nhất còn thiếu. Backend lên Render/Railway (hoặc VPS),
   frontend lên Vercel, Postgres quản lý (Supabase/Railway Postgres); thêm
   `.github/workflows/deploy.yml`. Đây cũng là điều kiện để nâng cấp đồng bộ Calendar từ polling lên
   webhook `events.watch` thật của Google (cần domain public HTTPS).
2. **Mở rộng eval harness** — bộ 8 case tay hiện tại chỉ đủ làm bằng chứng ban đầu; nên thêm case
   thật từ hội thoại người dùng (ẩn danh) để đo chính xác hơn trước khi báo cáo con số cuối.
3. **Rate limiting** — chưa có trên bất kỳ endpoint nào; cần trước khi mở public thật (mục 1).

## Ngoài phạm vi (quyết định có chủ đích)

- Không đổi frontend sang Next.js, không đổi backend sang NestJS.
- Không tự implement mã hoá E2E thật cho tin nhắn — thay vào đó dự định thực thi đúng tinh thần
  "chỉ đọc hội thoại được cấp quyền" qua bảng `ai_permissions` (mục 2 ở trên), panel AI đã có dòng
  minh bạch báo người dùng nội dung sẽ được gửi sang Gemini/Groq.
- Không dùng BullMQ/Redis/Socket.IO — giữ nguyên APScheduler + WebSocket thuần đã có.
- Không xây vector store dài hạn (Qdrant/pgvector/ChromaDB) — yêu cầu "Cơ bản" về memory đã đạt qua
  `AsyncPostgresSaver`, yêu cầu memory cá nhân đã đạt qua tính năng Memory (ghi chú người dùng tự
  thêm); không có nhu cầu semantic search rõ ràng để biện minh thêm 1 service. Xem
  [ARCHITECTURE.md](ARCHITECTURE.md) mục Vector Store.
- Không xây chức năng "Quên mật khẩu" — cần SMTP/email service thật để gửi link đặt lại, dự án chưa
  có và quyết định bỏ qua thay vì làm bản giả (2026-08-03). Nút "Forgot password?" trên `LoginPage`
  hiện vẫn là nút chưa nối gì cả.

---
Mỗi mục ở trên đủ lớn để cần một phiên plan + review riêng trước khi code — không gộp chung nhiều
mục vào 1 lần triển khai.
