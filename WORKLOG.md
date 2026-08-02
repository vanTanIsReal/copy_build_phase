# Worklog — Team DRIVER ENGINEER

> Ghi lại tất cả công việc đã làm theo ngày. Ai làm gì, kết quả gì.

| Member | Task | Status | Output | Time |
| --- | --- | --- | --- | --- |
| Phạm Quốc Tuấn | Xây dựng hệ thống đăng ký/đăng nhập thật cho backend (FastAPI): DB SQLite qua SQLAlchemy async (`src/db/`), hash mật khẩu bằng bcrypt, JWT access token (`src/auth/`), endpoint `/api/v1/auth/register`, `/login`, `/me` (`src/api/auth_routes.py`) | Done | User đăng ký/đăng nhập được, token lưu và xác thực qua `Authorization: Bearer` | 2026-08-01 |
| Phạm Quốc Tuấn | Xây dựng API nhắn tin (chat 1-1 và nhóm): model Conversation/ConversationParticipant/Message, endpoint tạo/list conversation, lấy lịch sử tin nhắn có phân trang, đánh dấu đã đọc, tìm user để bắt đầu chat (`src/api/chat_routes.py`, `src/services/chat_service.py`) | Done | REST API cho chat 1-1 và nhóm hoạt động, có dedupe conversation trực tiếp | 2026-08-01 |
| Phạm Quốc Tuấn | Xây dựng kênh real-time bằng WebSocket (`src/websocket/`) để gửi/nhận tin nhắn tức thời, broadcast tới đúng thành viên trong conversation | Done | Đã smoke-test 2 user kết nối WS, gửi tin nhắn nhận real-time thành công | 2026-08-01 |
| Phạm Quốc Tuấn | Viết test tự động cho auth, chat, websocket (`tests/test_auth.py`, `tests/test_chat.py`, `tests/test_websocket.py`) và cập nhật `tests/conftest.py` dùng DB in-memory riêng cho test | Done | 37/37 test pass, ruff lint sạch | 2026-08-01 |
| Phạm Quốc Tuấn | Nối frontend (React) với backend thật: `AuthContext`, `ProtectedRoute`, form Login/Register gọi API thật thay vì điều hướng giả; `Sidebar`/`TopNavbar` hiển thị user thật và có nút đăng xuất | Done | Đăng nhập/đăng ký/đăng xuất hoạt động end-to-end trên giao diện | 2026-08-01 |
| Phạm Quốc Tuấn | Nối giao diện Chat với API thật + WebSocket: `ChatPage`, `ConversationList`, `ConversationHeader`, `MessageArea`, `MessageBubble` bỏ mock data, thêm `NewConversationModal` để bắt đầu chat 1-1/tạo nhóm | Done | Chat 1-1 và nhóm chạy real-time giữa nhiều tài khoản trên trình duyệt | 2026-08-01 |
| Phạm Quốc Tuấn | Chẩn đoán và hướng dẫn fix lỗi "không đăng nhập được" do backend chưa được khởi động lại sau khi tắt terminal | Done | Xác nhận tài khoản không mất (đọc DB), hướng dẫn chạy lại backend | 2026-08-01 |
