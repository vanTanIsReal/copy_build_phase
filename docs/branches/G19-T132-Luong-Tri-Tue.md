# Báo cáo nhánh G19-T132-Lương-Trí-Tuệ

## Thông tin nhánh

- **Nhánh:** `G19-T132-Lương-Trí-Tuệ`
- **Sản phẩm:** Orbit AI Assistant
- **Mục tiêu:** Hoàn thiện nền tảng chat realtime, AI agent, quản trị và thiết kế lại authorization theo mô hình workspace-first.
- **Design spec:** [Workspace Authorization Foundation](../superpowers/specs/2026-08-03-workspace-authorization-foundation-design.md)
- **Implementation plan:** [Workspace Authorization Foundation Plan](../superpowers/plans/2026-08-03-workspace-authorization-foundation.md)

Tài liệu này phân biệt rõ tính năng đã chạy, tính năng mới hoàn thành một phần và phần mới dừng ở thiết kế. Một mục chỉ được chuyển sang **Đã triển khai** sau khi code, test và build tương ứng đều pass.

## Những phần đã triển khai trên nhánh

### Chat realtime

- Tạo conversation trực tiếp và conversation nhóm.
- Không tạo trùng direct conversation giữa cùng hai tài khoản.
- Lưu message history trong SQLite qua SQLAlchemy async.
- Gửi và nhận message realtime qua FastAPI WebSocket.
- Tự reconnect WebSocket ở frontend.
- Kiểm tra participant trước khi cho đọc hoặc gửi message.
- Theo dõi unread count và mark conversation đã đọc.

### Authentication và quản trị hiện tại

- Đăng ký, đăng nhập và lấy thông tin current user.
- Hash password bằng bcrypt.
- JWT bearer authentication cho REST API.
- Role hiện tại gồm `user/admin`, khóa hoặc mở tài khoản.
- Admin dashboard, user management và conversation moderation.

Mô hình admin hiện tại là legacy behavior. Design mới đã tách `platform_admin` khỏi workspace owner/admin và loại bỏ quyền đọc nội dung mặc định; phần refactor này chưa được đánh dấu đã triển khai.

### AI Agent

- LangGraph planner/tool loop.
- Groq qua `langchain-groq` với model mặc định `llama-3.3-70b-versatile`.
- Tool tóm tắt conversation.
- Google Calendar create/list tool.
- Reminder scheduling bằng APScheduler.
- Human-in-the-loop bằng LangGraph `interrupt()` trước khi tạo event hoặc reminder.
- Prompt tóm tắt được ràng buộc để không lặp nhiều định dạng.

### Chất lượng và tài liệu

- Backend test suite cho auth, admin, chat, WebSocket và agent tools.
- Ruff lint configuration.
- Vite production build cho frontend.
- README, Architecture, System Overview và Roadmap phản ánh trạng thái mock/real.
- Design spec và implementation plan có checkbox/commit tracking.

### Workspace foundation — giai đoạn 1

- Đăng ký user tạo Personal Workspace trong cùng database transaction.
- API `GET /api/v1/workspaces` chỉ trả workspace user được sở hữu hoặc có active membership.
- API `POST /api/v1/workspaces` tạo Organization Workspace và active owner membership.
- Personal Workspace từ chối mọi membership.
- Organization Workspace không được tạo với owner không tồn tại hoặc inactive.
- Owner cuối cùng không thể bị hạ xuống admin.
- Sáu workspace tests mới đã được thêm; toàn bộ backend suite hiện có 52 tests.

### Workspace migration — giai đoạn 2

- Alembic async migration framework với revision `20260803_01`.
- Preflight từ chối owner mơ hồ, owner cấu hình không hợp lệ và orphan participant.
- `--dry-run` chỉ trả báo cáo count/owner ID, không ghi database.
- Backfill Personal Workspace, Organization Workspace mặc định, membership và conversation workspace scope.
- Legacy `admin` được backfill thành `platform_admin` ở database, nhưng ORM chưa sử dụng role mới trước Task 4.
- Migration chạy lại idempotent trên SQLite tạm và có state transition `running/failed/completed`.
- Sáu migration tests mới đưa backend suite lên 58 tests.

## Đã thiết kế, chưa triển khai đầy đủ

### Workspace-first authorization còn lại

- Organization member/admin/guest APIs và invitation lifecycle.
- Platform Admin tách khỏi workspace administration.
- Resource role `manager/participant/viewer`.
- Principal `workspace_user/external_contact`.
- Support access có thời hạn, owner approval và audit log.
- Migration idempotent, dry-run và owner invariant.

### Contact/Relationship Graph

- Relationship có scope theo workspace.
- Relationship type, priority, trust level và project context.
- AI chỉ đề xuất relationship; người dùng xác nhận trước khi lưu metadata quan trọng.
- External contact không được xem directory hoặc dữ liệu ngoài conversation được mời.

### Những UI còn dùng dữ liệu mẫu

- Personal Assistant tổng hợp task/calendar/memory.
- Tasks, Calendar, Reminders, Memory và Profile.
- Một số quick action trong AI panel ngoài Summarize.

## Công nghệ sử dụng

| Nhóm | Công nghệ | Mục đích |
| --- | --- | --- |
| Backend API | FastAPI, Uvicorn, Pydantic 2 | REST API, validation và lifecycle |
| Database | SQLAlchemy 2 async, SQLite, aiosqlite | Persistence cho auth/chat |
| Migration | Alembic | Schema versioning cho workspace foundation |
| Authentication | PyJWT, bcrypt, email-validator | JWT, password hashing, email schema |
| Realtime | FastAPI WebSocket | Chat realtime và notification transport |
| AI orchestration | LangGraph, LangChain | Agent state, tools và human-in-the-loop |
| LLM | Groq, `langchain-groq` | Planner và summarization |
| Calendar | Google Calendar API clients | Đọc/tạo calendar event |
| Scheduler | APScheduler | Reminder jobs |
| Frontend | React 18, Vite 5, React Router | SPA và route protection |
| UI | Bootstrap 5, Bootstrap Icons, Framer Motion | Layout, icon và animation |
| Form | React Hook Form | Login/register validation |
| Test | pytest, pytest-asyncio, httpx | Unit và API integration tests |
| Quality | Ruff | Python lint/format checks |
| Container | Docker, Docker Compose | Backend runtime và local data volume |

## Cách chạy nhánh

### Backend trên Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Không commit `.env`. Điền `GROQ_API_KEY` khi cần gọi AI và sử dụng JWT secret có ít nhất 32 byte nếu chạy ngoài môi trường demo.

### Frontend

```powershell
Set-Location Frontend
npm install
npm run dev
```

Mở `http://localhost:5173`. Swagger ở `http://localhost:8000/docs`, health check ở `http://localhost:8000/health`.

### Test và lint

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check src tests
Set-Location Frontend
npm run build
```

### Workspace migration

```powershell
# Không ghi database
.\.venv\Scripts\python.exe scripts\migrate_workspace_foundation.py --dry-run

# Khi có nhiều admin legacy, owner phải được chọn rõ ràng
.\.venv\Scripts\python.exe scripts\migrate_workspace_foundation.py --dry-run --bootstrap-owner-user-id <USER_ID>
.\.venv\Scripts\python.exe scripts\migrate_workspace_foundation.py --bootstrap-owner-user-id <USER_ID>
```

Sao lưu database trước lệnh cuối. Không chạy migration thật nếu dry-run báo owner mơ hồ, owner không hợp lệ hoặc orphan participant.

### Docker

```powershell
docker compose up --build
```

Docker Compose hiện chạy backend ở cổng `8000`; frontend vẫn chạy riêng bằng Vite.

## Cách kiểm tra chat realtime

1. Chạy backend và frontend.
2. Mở trình duyệt thường, đăng ký tài khoản A.
3. Mở cửa sổ ẩn danh, đăng ký tài khoản B.
4. A tạo direct hoặc group conversation có B.
5. Hai tài khoản mở cùng conversation và gửi message.
6. Kiểm tra message xuất hiện tức thời, reload vẫn còn lịch sử và unread count hoạt động khi conversation chưa mở.
7. Trong DevTools → Network → WS, kiểm tra kết nối `/api/v1/ws?token=...` có status `101` và frame `send_message/new_message`.

## Quy tắc cập nhật tiến độ

- Plan là nguồn theo dõi task và commit: `docs/superpowers/plans/2026-08-03-workspace-authorization-foundation.md`.
- Chỉ đánh dấu task hoàn thành sau khi verification tương ứng pass.
- README này được cập nhật ở mỗi checkpoint để không mô tả thiết kế như code đã chạy.
- Thay đổi của người dùng trong `.env.example` không được stage cùng commit tính năng.
