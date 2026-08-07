# 1-Page Brief — Orbit

> AI Agent Trợ lý cá nhân trong Chat (tóm tắt hội thoại, nhắc việc, lên lịch)

| | |
| --- | --- |
| **Team** | DRIVER ENGINEER — P-132 (AI20K Build Phase Cohort 3) |
| **Repo** | https://github.com/AI20K-Build-Phase-Cohort-3/P-132 |
| **Đề bài gốc** | [Frontend/detai.md](../Frontend/detai.md) |
| **Tài liệu liên quan** | [PRD.md](PRD.md) · [UI_FLOW.md](UI_FLOW.md) · [wireframes.html](wireframes.html) · [AI_LOG.md](AI_LOG.md) · [../ARCHITECTURE.md](../ARCHITECTURE.md) · [../ROADMAP.md](../ROADMAP.md) |
| **Cập nhật** | 2026-08-04 |

---

## 1. Vấn đề

Người dùng nền tảng chat của Tập đoàn X nhận hàng trăm tin nhắn mỗi ngày qua nhiều nhóm (gia đình,
công việc, cộng đồng bất động sản). Việc cần làm, lịch hẹn và lời hứa bị **chôn vùi trong luồng tin
nhắn**: đọc lại thì tốn thời gian, không đọc lại thì bỏ lỡ.

Ba nỗi đau cụ thể:

1. **Không nắm được nhóm đang nói gì** sau vài trăm tin nhắn chưa đọc.
2. **Việc cần làm nằm rải rác trong chat**, không ai chuyển thành task/nhắc việc thủ công.
3. **Lịch hẹn chốt trong chat không vào calendar** → quên, trễ, phải hỏi lại.

## 2. Người dùng mục tiêu

| Vai trò | Nhu cầu chính |
| --- | --- |
| **Người dùng thường** | Tóm tắt nhóm chat dài, biết mình đang nợ việc gì, được nhắc đúng lúc, lịch tự vào Google Calendar |
| **Admin** | Quản lý user/hội thoại, kiểm duyệt nội dung, theo dõi hạn mức token/chi phí AI của hệ thống |

## 3. Giải pháp

**Orbit** — AI agent nhúng ngay trong app chat, không phải một app rời. Agent dùng LangGraph theo
mô hình *planner → tool → (human confirm) → trả lời*, đọc hội thoại được cấp quyền và:

- **Tóm tắt** hội thoại dài theo yêu cầu (1 nút trong khung chat).
- **Trích xuất task** từ tin nhắn → vào "inbox nhiệm vụ" chờ người dùng Accept/Dismiss.
- **Tạo nhắc việc & sự kiện lịch** — luôn hiện thẻ xác nhận trước khi thực thi.
- **Chủ động (proactive)**: mỗi tin nhắn mới được lọc regex rồi hỏi LLM xem có phải cam kết/lịch hẹn
  không; nếu có → tự gợi ý task, đẩy realtime qua WebSocket.
- **Nhớ ngữ cảnh**: memory hội thoại bền vững qua restart (LangGraph checkpointer trên Postgres) +
  trang Memory cho ghi chú cá nhân dài hạn.

## 4. Nguyên tắc thiết kế (không đánh đổi)

1. **Human-in-the-loop bắt buộc** — mọi tool có tác dụng phụ (tạo/sửa/xoá lịch, tạo nhắc việc) đều
   dừng ở `interrupt()` chờ người dùng bấm Xác nhận. Không có đường tắt, kể cả khi test.
2. **Agent chỉ đọc hội thoại được cấp quyền** — backend verify người gọi có thật sự là participant
   của `conversation_id` trước khi cho agent xử lý.
3. **Minh bạch dữ liệu** — nói rõ với người dùng rằng nội dung tin nhắn được gửi sang LLM provider
   (Gemini/Groq) khi dùng tính năng AI.
4. **Thà thiếu còn hơn sai** — ưu tiên giảm false reminder hơn là bắt được mọi task.

## 5. Phạm vi

**Trong phạm vi (đã build):** Auth JWT + 2 role · chat 1-1/nhóm realtime · agent tóm tắt / trích
task / reminder / calendar CRUD (human-in-the-loop) · Google Calendar 2 chiều · proactive detection ·
memory · dashboard admin + cảnh báo token · eval độ chính xác trích task.

**Ngoài phạm vi (quyết định có chủ đích):** không đổi stack sang Next.js/NestJS · không tự implement
mã hoá E2E · không dùng vector DB/embedding (app chưa có nhu cầu semantic search thật, nên không có
gì để "cache embedding" như tech stack gợi ý).

## 6. Chỉ số thành công

| Chỉ số | Mục tiêu | Hiện tại |
| --- | --- | --- |
| Độ chính xác trích task (F1) | ≥ 85% | 100% trên 8 case tay (VI+EN) — mẫu nhỏ, xem [ROADMAP](../ROADMAP.md) |
| Hành động có tác dụng phụ được xác nhận | 100% | 100% (`interrupt()` bắt buộc) |
| Test backend pass | 100% | Pass toàn bộ ở lần chạy gần nhất (87/87 tại WORKLOG 2026-08-03, +3 test calendar sync bổ sung sau đó), ruff sạch |
| Reminder sống sót qua restart backend | Có | Có (`SQLAlchemyJobStore`) |
| Deploy online | Có | **Chưa** — hạng mục lớn nhất còn lại |

## 7. Rủi ro & cách xử lý

| Rủi ro | Xử lý |
| --- | --- |
| Hết quota LLM free-tier (đã xảy ra thật với Gemini) | Cấu hình `LLM_PROVIDER` đổi provider qua `.env`; ghi `usage_logs` + cảnh báo khi ≥80% `DAILY_TOKEN_BUDGET` |
| Agent tạo nhầm lịch/nhắc việc | Human-in-the-loop + eval trích task trước khi đổi prompt/model |
| Rò rỉ nội dung tin nhắn | Kiểm tra quyền participant ở backend; không hardcode secret; thông báo minh bạch trong UI |
| LLM tính sai ngày giờ tương đối | Inject ngày giờ hiện tại (Asia/Ho_Chi_Minh) vào system prompt |

## 8. Trạng thái & bước tiếp theo

Sản phẩm đã chạy end-to-end ở local (backend `:8000` + frontend `:5173`, Postgres). Ba việc lớn còn
lại, theo thứ tự ưu tiên: **(1)** deploy online thật + CD, **(2)** bảng quyền `ai_permissions` theo
từng conversation thay cho toggle local ở UI, **(3)** mở rộng bộ eval trích task. Chi tiết trong
[ROADMAP.md](../ROADMAP.md).
