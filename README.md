# P-132 — Orbit AI Assistant

Dự án AI20K Build Phase: một AI agent nhúng trong ứng dụng chat, giúp tóm tắt hội thoại, trích xuất công việc/lịch hẹn, tạo nhắc nhở (có xác nhận trước khi thực hiện) và quản lý lịch cá nhân. Repo gồm 2 phần: **backend** (FastAPI + LangGraph, thư mục `src/`) và **frontend** (React + Vite, thư mục `Frontend/`).

## Hiện có gì

### Đã hoạt động thật (có backend, có database)

- **Đăng ký / Đăng nhập / Đăng xuất**: tài khoản lưu thật trong database (SQLite hoặc PostgreSQL), mật khẩu hash bằng bcrypt, xác thực bằng JWT. Route bên trong ứng dụng (`/assistant`, `/chat`, `/tasks`, ...) được bảo vệ — chưa đăng nhập sẽ tự chuyển về `/login`.
- **Agent nhớ hội thoại bền vững qua PostgreSQL**: khi `DATABASE_URL` là Postgres, agent dùng `AsyncPostgresSaver` — hội thoại/interrupt sống sót qua restart backend (SQLite thì mất, dùng `MemorySaver` tạm). Trên Windows, bắt buộc chạy bằng `python scripts/run_dev.py` thay vì `uvicorn` CLI trực tiếp — xem mục "Cách chạy web" bên dưới.
- **Nhắn tin 1-1 và theo nhóm, real-time**: tạo cuộc trò chuyện 1-1 hoặc nhóm (chọn nhiều người), gửi/nhận tin nhắn tức thời qua WebSocket, xem lại lịch sử tin nhắn, đếm tin nhắn chưa đọc.
- **AI Agent (chat với AI)**: endpoint `/api/v1/chat` (yêu cầu đăng nhập) dùng LangGraph với OpenAI `gpt-4o-mini`, có tool gọi Google Calendar và tạo nhắc nhở với bước xác nhận (human-in-the-loop) trước khi thực hiện.
- **AI Assistant cá nhân** (`/assistant`): khung chat riêng nối thẳng vào agent thật ở trên (không phải dữ liệu mẫu) — hỏi tự do, khi agent muốn tạo lịch/nhắc việc sẽ hiện nút Xác nhận/Huỷ ngay trong chat.
- **Phân quyền Admin**: tài khoản có 2 role (`user`/`admin`). Trang `/admin` (Dashboard, Users, Conversations) chỉ hiển thị và truy cập được với tài khoản `admin` — xem thống kê hệ thống, đổi role/khoá-mở khoá tài khoản, xem/xoá hội thoại để kiểm duyệt, và theo dõi lượng token AI đã dùng trong ngày (cảnh báo khi gần chạm ngân sách `DAILY_TOKEN_BUDGET`).
- **Tóm tắt hội thoại theo yêu cầu**: trong trang Chat, bấm icon AI trên header → **Summarize** — AI đọc tin nhắn thật (theo scope 20/50 tin gần nhất đang chọn) và trả về bản tóm tắt.
- **Trích xuất Task từ hội thoại**: cùng panel AI → **Extract tasks** — AI tìm việc cần làm/lịch hẹn trong hội thoại, lưu vào trang `/tasks` mục "AI suggestions"; người dùng bấm **Accept**/**Dismiss** để xác nhận. Panel AI còn có **Find schedule**, **Deadlines**, **Suggest reminder** (hiện nút Xác nhận/Huỷ ngay trong panel vì tạo reminder cần human-in-the-loop), cùng ô **Ask Orbit** để hỏi tự do về hội thoại đang xem.
- **Lịch cá nhân (Google Calendar thật, đồng bộ 2 chiều, realtime)**: trang `/calendar` gọi thẳng Google Calendar API (cần tự cấu hình OAuth — xem `scripts/google_oauth_setup.py`) để xem, tạo, sửa và xoá sự kiện thật. Agent cũng dùng chung API này (`list/create/update/delete_calendar_event` tool) nên có thể quản lý lịch qua chat, không chỉ qua UI. Mọi thay đổi (từ UI, từ chat, hoặc tạo/sửa/xoá trực tiếp trong chính Google Calendar) đều đẩy qua WebSocket tới mọi người đang mở `/calendar` — không cần refresh. Thay đổi từ phía Google được bắt bằng cách polling định kỳ (`CALENDAR_POLL_INTERVAL_SECONDS`, mặc định 20s) chứ chưa dùng webhook thật của Google (cần domain public HTTPS mà project chưa deploy).
- **Nhắc nhở bền vững + realtime**: trang `/reminders` tạo nhắc nhở thật, lưu DB, sống sót qua restart server (APScheduler + `SQLAlchemyJobStore`); khi đến giờ, đẩy thông báo realtime qua WebSocket dù đang ở trang nào.
- **Hồ sơ cá nhân** (`/profile`): sửa tên/chức danh/timezone/tuỳ chọn thông báo và đổi mật khẩu — lưu thật vào database, không còn là dữ liệu mẫu.
- **Memory cá nhân** (`/memory`): thêm/sửa/xoá "điều Orbit nên nhớ về bạn" (sở thích, thói quen, thông tin người liên quan...), lọc theo danh mục và tìm kiếm — lưu thật vào database.
- **Agent chủ động (proactive), realtime**: mỗi tin nhắn mới trong Chat được rà tự động (pre-filter rẻ + LLM xác nhận) — nếu chứa cam kết/lịch hẹn/hạn chót, Orbit tự tạo gợi ý và đẩy thẳng vào `/tasks` mục "AI suggestions" qua WebSocket (không cần refresh) kèm toast, không cần người dùng chủ động yêu cầu. Toàn bộ thao tác Task (accept/dismiss/complete/xoá) cũng đồng bộ realtime giữa các tab/thiết bị.
- **Múi giờ thống nhất Asia/Ho_Chi_Minh (Hà Nội)**: mọi nơi hiển thị ngày giờ (Chat, Task, Calendar, Reminder, Memory, Admin) đều quy về giờ Hà Nội bất kể múi giờ máy người xem, qua `Frontend/src/utils/datetime.js`. Backend cũng cố định giờ Hà Nội cho scheduler (reminder fire đúng giờ dù server chạy múi giờ khác) và mốc "hôm nay" của thống kê token.

### Công cụ đánh giá (dev, không phải tính năng người dùng)

- `scripts/eval_extract_tasks.py` — đo Precision/Recall/F1 của việc trích xuất task trên bộ dữ liệu tay (8 case tiếng Việt + Anh, có cả case không có task để đo độ chính xác). Gọi LLM thật nên không nằm trong `pytest tests/` — chạy tay: `python scripts/eval_extract_tasks.py`. Kết quả gần nhất (model `openai/gpt-oss-20b` qua Groq): **Precision/Recall/F1 = 100%** (8/8 case), ổn định qua nhiều lần chạy.

### Chưa xong

- **Deploy online**: có `Dockerfile`/`docker-compose.yml` nhưng chưa deploy lên domain public.

## Kiến trúc

> **Backend nằm ở thư mục [`src/`](src/) ở gốc repo** (FastAPI + LangGraph), tách biệt hoàn toàn với frontend ở [`Frontend/`](Frontend/) (React + Vite). Chạy backend bằng lệnh `uvicorn src.main:app ...` từ thư mục gốc repo, không phải từ bên trong `src/`.

```
├── src/                  # Backend — FastAPI + LangGraph
│   ├── agents/           # Agent LangGraph (planner, tools, state)
│   ├── api/               # REST routes: auth, chat (người-với-người), agent chat
│   ├── auth/              # Hash mật khẩu, tạo/kiểm tra JWT
│   ├── db/                # SQLAlchemy models + session (SQLite/PostgreSQL)
│   ├── models/             # Pydantic schemas
│   ├── services/           # chat_service, scheduler, llm, usage_service
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
# Mở .env, điền OPENAI_API_KEY nếu muốn dùng tính năng AI chat và đặt MODEL_NAME=gpt-4o-mini.
# DATABASE_URL mặc định là sqlite:///./data/app.db, không cần cài Postgres. Đổi sang
#   postgresql://... nếu muốn agent nhớ hội thoại bền vững qua các lần restart backend (SQLite thì mất).
# Điền INITIAL_ADMIN_EMAIL nếu muốn tài khoản đăng ký với email đó tự động có quyền admin.

# Chạy server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Nếu có `make` (macOS/Linux, hoặc cài Make trên Windows): dùng `make run` thay cho lệnh `uvicorn` ở trên.

**Windows + PostgreSQL**: dùng `python scripts/run_dev.py` thay cho lệnh `uvicorn` ở trên (cùng `--reload`, cùng cổng 8000). Lý do: agent memory bền vững (`AsyncPostgresSaver`) cần `SelectorEventLoop`, nhưng CLI `uvicorn` trên Windows luôn chọn `ProactorEventLoop` trước cả khi app được import, không có cờ nào sửa được — `run_dev.py` gọi `uvicorn.run()` trực tiếp bằng Python để chỉ định đúng loại event loop. Với SQLite thì dùng lệnh nào cũng như nhau.

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
5. Muốn thử trang **Admin**: đăng ký một tài khoản với email trùng `INITIAL_ADMIN_EMAIL` đã đặt trong `.env` (hoặc đổi role một tài khoản có sẵn thành `admin` trực tiếp trong DB) — tài khoản đó sẽ thấy mục "Admin" trong Sidebar, vào được `/admin`.
6. Muốn thử **AI Summarize / Extract tasks / Find schedule / Deadlines / Ask Orbit**: cần điền `OPENAI_API_KEY` thật trong `.env`. Trong 1 cuộc trò chuyện có vài tin nhắn, bấm icon AI trên header (⭐) rồi thử từng quick action, hoặc gõ câu hỏi tự do vào ô "Ask Orbit".
7. Muốn thử **AI Assistant cá nhân** (`/assistant`): vào trang này và chat trực tiếp — nếu bạn yêu cầu tạo lịch/nhắc việc, agent sẽ hỏi lại xác nhận ngay trong khung chat trước khi tạo thật.
8. Muốn xem **theo dõi token AI**: vào `/admin` (cần tài khoản admin, xem bước 5) — 2 stat card "AI tokens used today"/"AI requests today" và banner cảnh báo khi dùng ≥80% ngân sách `DAILY_TOKEN_BUDGET`.
9. Muốn thử **Agent chủ động**: gửi 1 tin nhắn kiểu "nhớ họp lúc 3h chiều mai nhé" trong trang Chat — vài giây sau sẽ có toast "Orbit spotted a commitment" ở góc phải, và gợi ý xuất hiện trong `/tasks` mục "AI suggestions".
10. Muốn thử **Memory**: vào `/memory`, bấm "Add memory" để lưu một điều bạn muốn Orbit nhớ, sửa/xoá qua menu 3 chấm trên mỗi thẻ.

### Chạy test backend

```bash
pytest tests/ -v
# hoặc: make test
```

## Công nghệ sử dụng

| Layer | Công nghệ |
| --- | --- |
| AI Agent | LangGraph + LangChain (OpenAI, `gpt-4o-mini`) |
| Backend | FastAPI, SQLAlchemy (async) + SQLite/PostgreSQL, JWT (PyJWT) + bcrypt, WebSocket |
| Agent memory | LangGraph checkpointer — `MemorySaver` (SQLite, mất khi restart) hoặc `AsyncPostgresSaver` (bền vững, khi `DATABASE_URL` là Postgres) |
| Frontend | React 18, Vite, React Router, React Hook Form, Bootstrap 5, Framer Motion |
| Test | pytest, pytest-asyncio, httpx |
| Lint | ruff |

## Tài liệu thiết kế (deliverable "Chốt bài toán + thiết kế")

- [docs/BRIEF.md](docs/BRIEF.md) — 1-page brief: vấn đề, người dùng, giải pháp, phạm vi, chỉ số thành công, rủi ro.
- [docs/PRD.md](docs/PRD.md) — PRD: user stories + acceptance criteria, yêu cầu phi chức năng, ERD, API surface, luồng agent.
- [docs/UI_FLOW.md](docs/UI_FLOW.md) — sitemap, luồng người dùng (tóm tắt/trích task, human-in-the-loop, proactive), mô tả từng màn hình.
- [docs/wireframes.html](docs/wireframes.html) — wireframe các màn hình chính (mở bằng trình duyệt).
- [docs/AI_LOG.md](docs/AI_LOG.md) — setup & bằng chứng hệ thống ghi log sử dụng AI trong repo.

## Tài liệu khác

- [CLAUDE.md](CLAUDE.md) — hướng dẫn chi tiết cho AI coding assistant làm việc trong repo này (quy ước code, lệnh chạy đầy đủ).
- [Frontend/README.md](Frontend/README.md) — hướng dẫn riêng cho frontend (cấu trúc, xử lý lỗi thường gặp khi chạy npm trên Windows).
- [Frontend/detai.md](Frontend/detai.md) — đề bài / yêu cầu gốc của dự án.
- [ARCHITECTURE.md](ARCHITECTURE.md) — kiến trúc hệ thống hiện tại và các quyết định công nghệ.
- [ROADMAP.md](ROADMAP.md) — bảng đối chiếu từng yêu cầu đề bài với trạng thái thật hiện tại + việc còn lại theo độ ưu tiên.
- [WORKLOG.md](WORKLOG.md) — nhật ký công việc theo ngày của cả nhóm.
- [docs/guide/](docs/guide/) — tài liệu khóa học AI20K (setup, LangGraph, FastAPI, testing, deploy).
