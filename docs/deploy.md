# Hướng dẫn deploy — bấm dashboard từng bước

Đây là bản hướng dẫn thao tác cụ thể đi kèm [../DEPLOYMENT.md](../DEPLOYMENT.md) (kế hoạch + quyết
định — đọc trước file đó để hiểu **vì sao**, file này chỉ trả lời **bấm gì ở đâu**). Thứ tự dưới đây
là D-1 "Dựng hạ tầng" trong DEPLOYMENT.md.

**Quyết định đã chốt ở đây:** deploy **cả 2 app frontend** (`Frontend/user/` và `Frontend/admin/`)
thành **2 Vercel project riêng** — mỗi app đã có `package.json`/`vite.config.js` độc lập, tách project
đơn giản hơn và đúng với cấu trúc thật hiện tại hơn là gộp lại. Nếu chỉ cần demo tính năng user, có
thể bỏ qua toàn bộ phần "Vercel — app admin" bên dưới và không tạo project đó.

Trước khi bắt đầu, hoàn tất checklist D-2 trong DEPLOYMENT.md (build Docker local đã chạy được,
`pytest`/`ruff` xanh, đã sinh `SECRET_KEY`/`CREDENTIAL_ENCRYPTION_KEY`, đã chốt tên service).

Quy ước tên dùng xuyên suốt bên dưới — đổi nếu bạn chọn tên khác, nhưng đổi nhất quán ở mọi bước:

| Placeholder | Giá trị ví dụ |
|---|---|
| `<backend-url>` | `https://orbit-backend.onrender.com` |
| `<user-url>` | `https://orbit-user.vercel.app` |
| `<admin-url>` | `https://orbit-admin.vercel.app` |

---

## Bước 1 — Supabase (Postgres)

1. [supabase.com](https://supabase.com) → New project → chọn region gần Render nhất (Singapore nếu
   Render deploy ở đó) → đặt mật khẩu DB, lưu ngay vào password manager.
2. Đợi project khởi tạo xong (~2 phút) → **Project Settings → Database → Connection string**.
3. Chọn tab **Session pooler** (port `5432`), **KHÔNG** chọn Transaction pooler (`6543`) — pooler
   transaction phá server-side prepared statement mà `asyncpg` dùng mặc định (xem cảnh báo trong
   [.env.production.example](../.env.production.example)).
4. Copy connection string dạng `postgresql://postgres.xxxx:[PASSWORD]@...:5432/postgres`, thay
   `[PASSWORD]` bằng mật khẩu thật đã đặt ở bước 1. Đây là giá trị `DATABASE_URL` — **không** thêm
   `?sslmode=...` vào cuối.
5. Lưu connection string này lại, sẽ dùng ở Bước 4.

## Bước 2 — Google Cloud Console (2 OAuth Client riêng)

Cần **2 OAuth Client** tách biệt — xem lý do ở bảng "Design Decisions" trong
[../ARCHITECTURE.md](../ARCHITECTURE.md) (đăng nhập chỉ verify ID token, Calendar cần
authorization-code + secret).

### 2a. OAuth Consent Screen

1. [console.cloud.google.com](https://console.cloud.google.com) → chọn hoặc tạo project → **APIs &
   Services → OAuth consent screen**.
2. User Type: **External** (trừ khi cả nhóm dùng chung 1 Google Workspace → **Internal**, xem P1
   trong DEPLOYMENT.md).
3. Thêm scope Calendar nếu chưa có (`.../auth/calendar`).
4. **Test users**: thêm email của mọi người sẽ đăng nhập/test (kể cả admin) — thiếu bước này Google
   trả `access_denied` ngay ở màn hình consent.
5. Publishing status giữ **Testing** cho demo ngắn (refresh token hết hạn sau 7 ngày — xem P1
   DEPLOYMENT.md để quyết cách xử lý trước khi qua bước tiếp).

### 2b. Client #1 — Sign in with Google

1. **Credentials → Create Credentials → OAuth client ID** → Application type: **Web application**.
2. Name: `orbit-signin`.
3. **Authorized JavaScript origins**: thêm `<user-url>` (ví dụ `https://orbit-user.vercel.app`).
   Không cần Authorized redirect URIs (flow này chỉ verify ID token phía client, không có callback
   server).
4. Create → copy **Client ID** → đây là `GOOGLE_OAUTH_CLIENT_ID` (backend) **và**
   `VITE_GOOGLE_CLIENT_ID` (Frontend/user) — cùng 1 giá trị.

### 2c. Client #2 — Google Calendar (authorization-code)

1. **Create Credentials → OAuth client ID** → Web application → Name: `orbit-calendar`.
2. **Authorized redirect URIs**: thêm đúng
   `<backend-url>/api/v1/calendar/oauth/callback` — phải khớp EXACT (kể cả dấu `/` cuối) với
   `GOOGLE_CALENDAR_REDIRECT_URI` sẽ khai ở Bước 4. Đây là domain **backend**, không phải frontend.
3. Create → copy **Client ID** và **Client secret** → `GOOGLE_CALENDAR_CLIENT_ID` /
   `GOOGLE_CALENDAR_CLIENT_SECRET`.
4. **APIs & Services → Library** → bật **Google Calendar API** nếu chưa bật.

## Bước 3 — Sinh secret

Chạy local (đã có trong checklist D-2, nhắc lại ở đây để tiện copy):

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"                                  # SECRET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"     # CREDENTIAL_ENCRYPTION_KEY
```

Lưu cả 2 vào password manager của nhóm — đổi `SECRET_KEY` sau khi có user = mọi người bị đăng xuất;
đổi `CREDENTIAL_ENCRYPTION_KEY` sau khi có user connect Calendar = mọi refresh token thành rác.

## Bước 4 — Render (backend)

1. [dashboard.render.com](https://dashboard.render.com) → **New → Blueprint** → connect repo GitHub
   chứa project này.
2. Render đọc [render.yaml](../render.yaml) tự động. Trước khi apply, **sửa 1 dòng trong file** (rồi
   commit/push): `plan: free` → `plan: starter` — xem lý do bắt buộc Starter (không phải free) ở mục
   1 DEPLOYMENT.md (free sleep sau 15 phút = scheduler chết).
3. Apply Blueprint. Render sẽ hỏi giá trị cho các biến `sync: false` — điền theo bảng dưới (đối chiếu
   đầy đủ với [.env.production.example](../.env.production.example)):

   | Biến | Giá trị |
   |---|---|
   | `DATABASE_URL` | Connection string Supabase (Bước 1) |
   | `SECRET_KEY` | Sinh ở Bước 3 |
   | `CREDENTIAL_ENCRYPTION_KEY` | Sinh ở Bước 3 |
   | `GOOGLE_API_KEY` | API key Gemini (hoặc để trống nếu dùng Groq/OpenAI — sửa thêm `LLM_PROVIDER` trong Environment sau khi apply) |
   | `GROQ_API_KEY` / `OPENAI_API_KEY` | Để trống nếu không dùng |
   | `GOOGLE_OAUTH_CLIENT_ID` | Client ID #1 (Bước 2b) |
   | `GOOGLE_CALENDAR_CLIENT_ID` | Client ID #2 (Bước 2c) |
   | `GOOGLE_CALENDAR_CLIENT_SECRET` | Client secret #2 (Bước 2c) |
   | `GOOGLE_CALENDAR_REDIRECT_URI` | `<backend-url>/api/v1/calendar/oauth/callback` |
   | `INITIAL_ADMIN_EMAIL` | Email sẽ được gán role admin tự động khi đăng ký lần đầu |
   | `CORS_ORIGINS` | `<user-url>,<admin-url>` — **không khoảng trắng sau dấu phẩy**, không `/` cuối |
   | `FRONTEND_ORIGIN` | `<user-url>` |

4. Sau khi service tạo xong, vào **Environment** → thêm/sửa 2 biến không có trong Blueprint (không
   bắt buộc lúc apply nhưng nên đặt ngay theo D-1 trong DEPLOYMENT.md):
   - `CALENDAR_POLL_INTERVAL_SECONDS=60` (thay vì 20 mặc định — tránh tốn quota Calendar API)
5. Đợi build xong (theo dõi tab **Logs**) → mở `<backend-url>/health` → kỳ vọng
   `{"status":"ok","env":"production"}`. Nếu container start rồi chết ngay, xem bảng "Sự cố hay gặp"
   mục 6 DEPLOYMENT.md.
6. **Settings → Deploy Hook** → copy URL (dạng `https://api.render.com/deploy/srv-xxx?key=yyy`) —
   dùng ở Bước 6.

## Bước 5 — Vercel (app user)

1. [vercel.com](https://vercel.com) → **Add New → Project** → import repo GitHub.
2. **Root Directory**: `Frontend/user` (bấm Edit cạnh Root Directory để chọn).
3. Framework Preset: Vercel tự nhận diện Vite — giữ mặc định (Build Command `npm run build`, Output
   Directory `dist`).
4. **Environment Variables** — thêm 3 biến (áp dụng cho Production, Preview, Development đều được):

   | Biến | Giá trị |
   |---|---|
   | `VITE_API_BASE_URL` | `<backend-url>/api/v1` |
   | `VITE_WS_BASE_URL` | `wss://` + phần domain của backend + `/api/v1/ws` (ví dụ `wss://orbit-backend.onrender.com/api/v1/ws`) — **bắt buộc `wss://`, không phải `ws://`**, đây là biến build-time nên sai là phải build lại chứ đổi env không đủ |
   | `VITE_GOOGLE_CLIENT_ID` | Client ID #1 (Bước 2b) |

5. Deploy. `Frontend/user/vercel.json` đã có rewrite SPA (`/(.*) → /index.html`) nên route con
   (`/tasks/inbox`, `/assistant`, ...) F5 không bị 404 — verify lại ở Bước D-day. (Không dùng
   `Frontend/vercel.json` ở cấp cha — với Root Directory = `Frontend/user`, Vercel không đọc file đó.)
6. Copy URL Vercel cấp (`<user-url>`) → quay lại Render **Environment**, cập nhật `CORS_ORIGINS` và
   `FRONTEND_ORIGIN` nếu lúc Bước 4 mới điền placeholder — service sẽ tự restart khi đổi env.
7. Quay lại Google Cloud Console Client #1 (Bước 2b) → xác nhận Authorized JavaScript origins đã
   đúng `<user-url>` thật (không phải domain đoán trước).

## Bước 6 — Vercel (app admin) — bỏ qua nếu demo chỉ cần phía user

Lặp lại Bước 5 với khác biệt:

1. **Root Directory**: `Frontend/admin`.
2. Environment Variables: chỉ 2 biến, **không có** `VITE_GOOGLE_CLIENT_ID` (app admin không có nút
   Sign in with Google):

   | Biến | Giá trị |
   |---|---|
   | `VITE_API_BASE_URL` | `<backend-url>/api/v1` |
   | `VITE_WS_BASE_URL` | `wss://.../api/v1/ws` (giống Bước 5) |

3. Deploy → copy `<admin-url>` → cập nhật `CORS_ORIGINS` trên Render thành `<user-url>,<admin-url>`
   (đã làm ở Bước 5.6 nếu làm đúng thứ tự, kiểm tra lại cho chắc).
4. Đăng nhập lần đầu tại `<admin-url>` bằng email đúng `INITIAL_ADMIN_EMAIL` đã khai ở Bước 4 — hoặc
   dùng `ADMIN_BOOTSTRAP_KEY` nếu cần tạo thêm admin thứ 2 (xem README.md).

## Bước 7 — GitHub Actions (CI/CD)

1. Repo → **Settings → Secrets and variables → Actions**.
2. Tab **Secrets** → New repository secret: `RENDER_DEPLOY_HOOK_URL` = URL copy ở Bước 4.6.
3. Tab **Variables** → New repository variable: `RENDER_URL` = `<backend-url>` (không có dấu `/`
   cuối — [deploy.yml](../.github/workflows/deploy.yml) nối trực tiếp `${{ vars.RENDER_URL }}/health`).
4. Xác nhận `ci.yml` đã chạy xanh trên `main` (không chỉ trên PR) — nếu chưa, push 1 commit vặt lên
   `main` để kích hoạt.
5. `deploy.yml` chỉ trigger thật từ lần chạy tiếp theo trên `main` sau khi file này tồn tại
   (`workflow_run` không fire cho chính commit thêm nó) — chạy tay lần đầu qua **Actions → Deploy →
   Run workflow** (`workflow_dispatch`) để xác nhận Deploy Hook hoạt động.

## Bước 8 — Tắt keep-alive (chỉ sau khi Render đã lên Starter)

1. **Actions → keep-alive.yml → ⋯ → Disable workflow**.
2. Không xoá file — chỉ disable, phòng khi sau này hạ về free tier lại cần.

---

## Sau bước 8

Toàn bộ hạ tầng đã dựng xong. Tiếp theo là mục **"D-day — Nghiệm thu"** trong
[../DEPLOYMENT.md](../DEPLOYMENT.md) — chạy checklist đó trước khi coi deploy hoàn tất, đặc biệt bài
test reminder (hẹn 5 phút và ngồi đợi bắn thật) là bằng chứng duy nhất scheduler sống trên production.

Gặp lỗi giữa chừng → tra bảng "Sự cố hay gặp" (mục 6, DEPLOYMENT.md) trước khi đoán mò.

Sau demo, đừng quên mục **"Teardown"** (mục 4, DEPLOYMENT.md) — đây là phần hay bị quên nhất và là
lý do bị trừ tiền tháng thứ 2.
