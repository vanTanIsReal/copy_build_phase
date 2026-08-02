# P-132 — Orbit AI Assistant

Dự án AI20K Build Phase: một AI agent nhúng trong ứng dụng chat, giúp tóm tắt hội thoại, trích xuất công việc/lịch hẹn, tạo nhắc nhở (có xác nhận trước khi thực hiện) và quản lý lịch cá nhân. Repo gồm 2 phần: **backend** (FastAPI + LangGraph, thư mục `src/`) và **frontend** (React + Vite, thư mục `Frontend/`).

## Hiện có gì

### Đã hoạt động thật (có backend, có database)

- **Đăng ký / Đăng nhập / Đăng xuất**: tài khoản lưu thật trong database (SQLite), mật khẩu hash bằng bcrypt, xác thực bằng JWT. Route bên trong ứng dụng (`/assistant`, `/chat`, `/tasks`, ...) được bảo vệ — chưa đăng nhập sẽ tự chuyển về `/login`.
- **Nhắn tin 1-1 và theo nhóm, real-time**: tạo cuộc trò chuyện 1-1 hoặc nhóm (chọn nhiều người), gửi/nhận tin nhắn tức thời qua WebSocket, xem lại lịch sử tin nhắn, đếm tin nhắn chưa đọc.
- **AI Agent (chat với AI)**: endpoint `/api/v1/chat` dùng LangGraph, có tool gọi Google Calendar và tạo nhắc nhở với bước xác nhận (human-in-the-loop) trước khi thực hiện.

### Mới là giao diện mẫu (chưa nối API thật)

Các trang Tasks, Calendar, Reminders, Memory, Profile, và tính năng AI Assistant tóm tắt/quản lý cá nhân (`/assistant`) hiện đang chạy trên dữ liệu mẫu (`Frontend/src/data/mockData.js`) — giao diện đã xong nhưng chưa nối vào backend.

## Kiến trúc

```
├── src/                  # Backend — FastAPI + LangGraph
│   ├── agents/           # Agent LangGraph (planner, tools, state)
│   ├── api/               # REST routes: auth, chat (người-với-người), agent chat
│   ├── auth/              # Hash mật khẩu, tạo/kiểm tra JWT
│   ├── db/                # SQLAlchemy models + session (SQLite)
│   ├── models/             # Pydantic schemas
│   ├── services/           # chat_service, scheduler, llm
│   ├── websocket/          # Kênh real-time cho chat
│   └── main.py             # Điểm khởi tạo FastAPI app
├── tests/                 # pytest cho backend
└── Frontend/               # Frontend — React + Vite
    └── src/
        ├── api/            # Gọi REST API + WebSocket client
        ├── context/         # AuthContext (JWT, user hiện tại)
        ├── hooks/            # useConversations, useMessages
        ├── components/        # Component theo tính năng (chat, layout, ...)
        ├── pages/              # Các trang ứng dụng
        └── router/              # React Router + ProtectedRoute
```

## Cách chạy web (local development)

Cần chạy **song song 2 server** — backend (cổng 8000) và frontend (cổng 5173) — mỗi lần dùng app đều cần mở cả hai (backend không tự chạy nền, tắt terminal là tắt server).

### 1. Chuẩn bị

- Python 3.11+
- Node.js 18+ và npm
- Đã clone repo và `cd` vào thư mục gốc dự án

### 2. Chạy Backend

```bash
# Tạo virtual environment (chỉ cần làm 1 lần)
python -m venv .venv

# Kích hoạt venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# Cài dependency
pip install -r requirements.txt

# Tạo file cấu hình (chỉ cần làm 1 lần)
cp .env.example .env
# Mở .env, điền OPENAI_API_KEY nếu muốn dùng tính năng AI chat.
# DATABASE_URL mặc định là sqlite:///./data/app.db, không cần cài Postgres.

# Chạy server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Nếu có `make` (macOS/Linux, hoặc cài Make trên Windows): dùng `make run` thay cho lệnh `uvicorn` ở trên.

Kiểm tra backend đã chạy: mở `http://localhost:8000/health` phải trả về `{"status":"ok",...}`. Swagger UI (danh sách toàn bộ API) ở `http://localhost:8000/docs`.

### 3. Chạy Frontend

Mở một terminal khác:

```bash
cd Frontend
npm install
npm run dev
```

Mở `http://localhost:5173` trong trình duyệt. Frontend mặc định gọi backend tại `http://localhost:8000/api/v1` — nếu backend chạy ở địa chỉ khác, tạo file `Frontend/.env` từ `Frontend/.env.example` và sửa `VITE_API_BASE_URL`/`VITE_WS_BASE_URL`.

### 4. Dùng thử

1. Vào `http://localhost:5173/register`, tạo tài khoản.
2. Mở thêm một trình duyệt/tab ẩn danh khác, tạo tài khoản thứ hai.
3. Từ tài khoản thứ nhất, vào trang **Chats**, bấm nút bút (soạn tin nhắn) để chọn người và bắt đầu chat 1-1 hoặc chọn nhiều người để tạo nhóm.
4. Gửi tin nhắn — tài khoản còn lại sẽ nhận tin nhắn theo thời gian thực nếu đang mở cùng cuộc trò chuyện, hoặc thấy số tin nhắn chưa đọc.

### Chạy test backend

```bash
pytest tests/ -v
# hoặc: make test
```

## Công nghệ sử dụng

| Layer | Công nghệ |
| --- | --- |
| AI Agent | LangGraph + LangChain (OpenAI) |
| Backend | FastAPI, SQLAlchemy (async) + SQLite, JWT (PyJWT) + bcrypt, WebSocket |
| Frontend | React 18, Vite, React Router, React Hook Form, Bootstrap 5, Framer Motion |
| Test | pytest, pytest-asyncio, httpx |
| Lint | ruff |

## Tài liệu khác

- [CLAUDE.md](CLAUDE.md) — hướng dẫn chi tiết cho AI coding assistant làm việc trong repo này (quy ước code, lệnh chạy đầy đủ).
- [Frontend/README.md](Frontend/README.md) — hướng dẫn riêng cho frontend (cấu trúc, xử lý lỗi thường gặp khi chạy npm trên Windows).
- [Frontend/detai.md](Frontend/detai.md) — đề bài / yêu cầu gốc của dự án.
- [WORKLOG.md](WORKLOG.md) — nhật ký công việc theo ngày của cả nhóm.
- [docs/guide/](docs/guide/) — tài liệu khóa học AI20K (setup, LangGraph, FastAPI, testing, deploy).
