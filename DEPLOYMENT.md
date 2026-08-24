# Kế hoạch hạ tầng triển khai — Orbit

**Phạm vi: deploy chạy thật trong 1–2 tuần rồi gỡ.** Mọi quyết định dưới đây đều tối ưu cho cửa sổ
đó — không phải cho một hệ thống chạy nhiều tháng. Phần [Cố tình KHÔNG làm](#cố-tình-không-làm) giải
thích những gì bị lược bỏ và lý do, để sau này ai đọc lại không tưởng là thiếu sót.

Tài liệu này là **kế hoạch + quyết định**. Bản hướng dẫn bấm dashboard chi tiết từng bước sống ở
[docs/deploy.md](docs/deploy.md) — đã viết lại (2026-08-17) cho đúng cấu trúc hiện tại (2 app Vite
riêng `Frontend/user/`/`Frontend/admin/`, mỗi app 1 Vercel project). Quyết định: deploy **cả 2 app**,
nhưng docs/deploy.md ghi rõ chỗ có thể bỏ qua app admin nếu demo chỉ cần phía user.

---

## 1. Chốt stack và chi phí

| Thành phần | Lựa chọn | Chi phí |
|---|---|---|
| Backend (FastAPI + WS + scheduler) | **Render, gói Starter** | **$7 / tháng** |
| Postgres | **Supabase free** (Session pooler) | $0 |
| Frontend (Vite SPA) | **Vercel Hobby** | $0 |
| Domain | **Không mua** — dùng `*.onrender.com` + `*.vercel.app` | $0 |
| CI/CD | GitHub Actions | $0 |
| | **Tổng** | **$7, tối đa $14 nếu tràn sang tháng thứ 2** |

Nằm dưới ngân sách $10–20/tháng đã đặt ra, và phần dư cố ý không tiêu.

**Vì sao Starter $7 chứ không phải free:** Render free sleep sau 15 phút không request. App này chạy
APScheduler **in-process** — service ngủ thì reminder không bắn và calendar polling dừng, đúng hai
tính năng cốt lõi. `keep-alive.yml` (ping mỗi 10 phút) chỉ giảm thiểu chứ không xử lý được: cron của
GitHub là best-effort, trễ vài phút là chuyện thường, và cold start còn thêm ~30–50 giây. Với demo
1–2 tuần, $7 để loại bỏ hẳn một lớp rủi ro là đổi chác dễ chịu nhất trong toàn bộ kế hoạch này.

➡️ Sau khi lên Starter, **tắt `keep-alive.yml`** (Actions → workflow → Disable). Không còn tác dụng gì
ngoài việc gây nhiễu log.

**Vì sao không mua domain:** ~$10–15/năm cho thứ dùng 2 tuần, cộng thêm chờ DNS và phải khai lại
toàn bộ origin/redirect URI trong Google Cloud Console. Hai URL mặc định hoạt động đầy đủ, kể cả
HTTPS và WSS.

---

## 2. Kiến trúc production

```
   Trình duyệt
        │  HTTPS + WSS
        ├──────────────────────────► Vercel  (2 SPA tĩnh: app user + app admin, mỗi app vercel.json riêng)
        │
        └──────────────────────────► Render  (1 instance Docker, KHÔNG scale)
                                        │        ├─ FastAPI + WebSocket in-memory
                                        │        ├─ APScheduler (reminders, calendar poll)
                                        │        └─ LangGraph + AsyncPostgresSaver
                                        │
                                        ├─────► Supabase Postgres  (data + jobstore + checkpoint)
                                        ├─────► Google Gemini API
                                        └─────► Google Calendar API

   GitHub push → CI (lint + pytest) → Deploy Hook → Render
```

### Ràng buộc cứng: **luôn luôn đúng 1 instance**

Không được bật autoscaling hay tăng instance count trên Render, kể cả khi thấy chậm:

- `src/websocket/manager.py` giữ kết nối trong `dict` của tiến trình. Hai instance → user A nối
  instance 1, user B nối instance 2, tin nhắn A gửi B **không bao giờ tới**.
- `scheduler.add_job(...)` chạy in-process. `SQLAlchemyJobStore` chỉ persist job, **không có leader
  election** → mỗi reminder bắn 2 lần, calendar poll chạy 2 luồng song song và tranh nhau syncToken.

Nghẽn thì tăng RAM/CPU của **cùng một** instance (scale up), tuyệt đối không scale out. Với quy mô
demo, gói Starter thừa sức.

---

## 3. Phải sửa trước khi deploy

### 🔴 P0 — Dockerfile không chạy được (ĐÃ SỬA trong lần này)

Bản cũ `pip install --user` (vào `/root/.local`) rồi `USER appuser`. Trên Debian `/root` có mode
`0700`, nên appuser không traverse vào được → `uvicorn: command not found`, container exit ngay lúc
start. Vì repo chưa từng deploy thật nên lỗi này chưa lộ ra.

Đã đổi sang virtualenv `/opt/venv`, kèm 2 thay đổi cần cho môi trường thật:

- `PYTHONUNBUFFERED=1` — `src/main.py` dùng `print()`; stdout ghi vào pipe là block-buffered, không
  có biến này thì traceback lúc `init_db()`/`init_checkpointer()` có thể chết trước khi kịp hiện
  trong Render Logs, làm việc debug deploy hỏng gần như bất khả thi.
- `--proxy-headers --forwarded-allow-ips='*'` — app luôn nằm sau edge proxy của Render.

**Bắt buộc verify local trước khi push** (chưa chạy thử được trong môi trường soạn tài liệu này):

```bash
docker build -t orbit-test .
docker run --rm -e DATABASE_URL="postgresql://..." -p 8000:8000 orbit-test
curl localhost:8000/health     # kỳ vọng {"status":"ok","env":"..."}
```

### 🟠 P1 — Refresh token Google Calendar **hết hạn sau đúng 7 ngày**

Rủi ro nghiêm trọng nhất của cửa sổ 1–2 tuần, và nó rơi đúng vào giữa kỳ.

OAuth consent screen ở trạng thái **Testing** thì Google cho mọi refresh token hết hạn sau 7 ngày.
App này lưu refresh token Calendar của từng user (`google_calendar_credentials`, mã hoá Fernet). Sang
ngày thứ 8, mọi kết nối Calendar đứt với lỗi `invalid_grant: Token has been expired or revoked` —
trong khi login và chat vẫn bình thường, nên rất dễ tưởng là bug code.

Ba cách xử lý, chọn theo hoàn cảnh:

| Cách | Phù hợp khi | Đánh đổi |
|---|---|---|
| Chấp nhận, hẹn ngày reconnect | Demo gọn trong ≤7 ngày | Phải nhớ bấm "Connect Google Calendar" lại; đừng để trúng hôm chấm |
| Đổi consent screen sang **In production** | Cần Calendar sống đủ 2 tuần | Scope `calendar` là sensitive → có thể bị yêu cầu verification; nộp sớm |
| User type **Internal** | Cả nhóm dùng chung 1 Google Workspace | Chỉ tài khoản trong tổ chức đó dùng được |

Quyết ngay từ ngày đầu, đừng để phát hiện vào ngày thứ 8.

### 🟢 P2 — Chặn chi phí LLM + rate limiting

Rate limiting đã có (slowapi, in-memory — xem [ARCHITECTURE.md](ARCHITECTURE.md)): auth
(`/register` 5/phút, `/login`+`/google` 10/phút theo IP), `/chat` 15/phút/user, CRUD còn lại
60/phút/user. `RATE_LIMIT_*` trong [render.yaml](render.yaml) đã có giá trị mặc định hợp lý, không
cần chỉnh thêm cho demo 1–2 tuần.

Lớp bảo vệ ví tiền vẫn là `DAILY_TOKEN_BUDGET` → `is_over_budget()` chặn hẳn `/chat` và proactive
detection khi chạm ngưỡng, cộng với `ai_permissions` (mặc định chưa cấp quyền, agent không tự đọc
hội thoại) — rate limiting là trục khác (chặn burst/spam theo phút), không thay thế trục này.

Việc cần làm: **đặt `DAILY_TOKEN_BUDGET` thấp hơn dev** (gợi ý 100k–150k) và kiểm tra `/admin`
mỗi ngày.

### 🟢 P3 — Không cần Alembic cho lần này

`init_db()` gọi `Base.metadata.create_all`, tức là **tạo bảng mới thì được, đổi schema bảng cũ thì
im lặng không làm gì**. Với DB production tạo mới tinh và schema đóng băng trong 2 tuần, đây không
phải vấn đề.

Điều kiện: **đóng băng schema từ lúc deploy**. Nếu buộc phải đổi cột giữa kỳ → chấp nhận drop &
tạo lại DB (mất dữ liệu demo), hoặc chạy `ALTER TABLE` tay trên Supabase SQL Editor rồi ghi vào
[WORKLOG.md](WORKLOG.md). Không sửa `src/db/models.py` rồi deploy và tưởng là xong.

---

## 4. Lộ trình

### D-2 — Chuẩn bị (làm ở máy local, chưa tốn tiền)

- [ ] Build & chạy Docker local như mục P0 → `/health` trả 200
- [ ] `pytest tests/ -v` và `ruff check .` xanh trên `main`
- [ ] Xác nhận `ci.yml` **đã chạy xanh thật trên `main`**, không chỉ trên PR
- [ ] Sinh `SECRET_KEY` + `CREDENTIAL_ENCRYPTION_KEY`, lưu password manager của nhóm
- [ ] Quyết cách xử lý mục P1 (Testing 7 ngày / In production / Internal)
- [ ] Chốt tên service: `orbit-backend.onrender.com`, `orbit-frontend.vercel.app`

### D-1 — Dựng hạ tầng

Theo [docs/deploy.md](docs/deploy.md) bước 1→8 (Supabase → Google Cloud Console → Render → Vercel
user/admin → GitHub Actions → tắt keep-alive). File đó đã gộp sẵn các điểm khác biệt so với cấu hình
mặc định trong repo (đổi `plan: free` → `starter` trong render.yaml, `CALENDAR_POLL_INTERVAL_SECONDS=60`,
disable `keep-alive.yml` sau khi Starter chạy).

Đối chiếu biến môi trường với [.env.production.example](.env.production.example) — file này ghi rõ
những chỗ production khác dev, đặc biệt: `CORS_ORIGINS` không được có khoảng trắng (`main.py` dùng
`.split(",")` không `.strip()`), và `DATABASE_URL` không được thêm `?sslmode=`.

### D-day — Nghiệm thu

- [ ] Đăng ký + đăng nhập bằng email/password trên URL Vercel, DevTools Console sạch CORS
- [ ] Sign in with Google
- [ ] Chat 1-1 và nhóm: 2 trình duyệt khác nhau, tin nhắn hiện realtime — **xác nhận WSS**, không
      phải polling (Network → WS → thấy frame chạy)
- [ ] Grant AI permission → hỏi agent → có phản hồi
- [ ] Tạo reminder qua agent → hiện bước xác nhận (human-in-the-loop) → **hẹn cách 5 phút và ngồi
      đợi nó bắn thật**. Đây là bài test duy nhất chứng minh scheduler sống trên production.
- [ ] Connect Google Calendar → tạo event qua agent → mở Google Calendar thật thấy event
- [ ] Đăng nhập tài khoản `INITIAL_ADMIN_EMAIL` → `/admin` hiện usage
- [ ] Bấm sai mật khẩu ở `/login` liên tục >10 lần/phút → thấy lỗi 429 (xác nhận rate limiting sống
      trên production, không chỉ chạy đúng ở local)
- [ ] Mở thẳng `https://<vercel-url>/tasks/inbox` (F5 giữa route con) → không 404
- [ ] Push 1 commit vặt lên `main` → CI xanh → Deploy tự chạy → Render có deploy event mới

### Trong 1–2 tuần — kiểm tra 5 phút mỗi ngày

- Render Dashboard → Events: có restart bất thường không
- Render Logs: lọc `Traceback`
- `/admin`: token đã dùng so với `DAILY_TOKEN_BUDGET`
- Nếu Calendar đang ở chế độ Testing: **đánh dấu ngày thứ 7** trên lịch nhóm

Trước buổi demo/chấm: mở trang trước ~10 phút, bấm qua đúng luồng sẽ trình bày.

### Sau demo — teardown (đừng bỏ qua)

Đây là phần hay bị quên nhất và là lý do người ta bị trừ tiền tháng thứ 2.

- [ ] Render: Settings → **Delete Service** (hoặc hạ về free nếu còn muốn giữ link)
- [ ] Kiểm tra Billing của Render đã về $0 cho chu kỳ tới
- [ ] Supabase: pause hoặc xoá project
- [ ] Vercel: xoá project (hoặc giữ, không tốn phí)
- [ ] Google Cloud Console: xoá 2 OAuth Client, hoặc gỡ hết origin/redirect URI production
- [ ] Thu hồi `GOOGLE_API_KEY` đã dùng cho production (đừng dùng lại cho dev)
- [ ] GitHub: xoá secret `RENDER_DEPLOY_HOOK_URL`, variable `RENDER_URL`; disable workflow `Deploy`
- [ ] Tải bản backup DB cuối cùng nếu muốn giữ dữ liệu demo
- [ ] Ghi kết quả + số liệu vào [WORKLOG.md](WORKLOG.md) / [ROADMAP.md](ROADMAP.md) khi URL còn sống

---

## 5. Backup & khôi phục

Supabase free **không có** point-in-time recovery. Trong 2 tuần, rủi ro thực tế không phải hỏng đĩa
mà là một câu lệnh xoá nhầm hoặc `create_all` chạy trên DB sai.

[.github/workflows/db-backup.yml](.github/workflows/db-backup.yml) (mới thêm, **tuỳ chọn**) dump
Postgres mỗi đêm 02:00 giờ VN, mã hoá GPG, lưu artifact 30 ngày. Bật bằng cách tạo 2 secret:
`DATABASE_URL_RO` và `BACKUP_PASSPHRASE`. Nếu thấy thừa cho 2 tuần thì tối thiểu **chạy tay 1 lần
trước buổi demo** (Actions → DB Backup → Run workflow).

Khôi phục:

```bash
gpg --decrypt --output orbit.dump orbit-YYYYMMDD.dump.gpg
pg_restore --clean --if-exists --no-owner --no-privileges -d "<DATABASE_URL>" orbit.dump
```

Backup cùng chỗ với `CREDENTIAL_ENCRYPTION_KEY`: mất key thì refresh token Calendar trong bản dump
là dữ liệu rác, restore xong ai cũng phải kết nối lại.

---

## 6. Sự cố hay gặp

| Triệu chứng | Nguyên nhân thường gặp |
|---|---|
| Container start rồi chết ngay | Đọc Render Logs: traceback từ `init_db()` (sai `DATABASE_URL`/SSL) hoặc `init_checkpointer()` (sai conninfo psycopg) |
| Request bị chặn bởi CORS | `CORS_ORIGINS` có khoảng trắng hoặc dấu `/` cuối — `main.py` không strip |
| WebSocket không kết nối | `VITE_WS_BASE_URL` dùng `ws://` thay vì `wss://`. Là biến build-time → sửa xong phải **redeploy Vercel**, không phải chỉ đổi env |
| Calendar báo `invalid_grant` | Đúng mốc 7 ngày của consent screen Testing — xem P1 |
| `redirect_uri_mismatch` | `GOOGLE_CALENDAR_REDIRECT_URI` phải khớp EXACT với Google Console, kể cả dấu `/` cuối, và trỏ về domain **backend** |
| Google trả `access_denied` | Tài khoản chưa nằm trong "Test users" của consent screen |
| Reminder không bắn | Kiểm tra service không ngủ (đã lên Starter chưa) + `SCHEDULER_TIMEZONE` |
| Lỗi 429 "Rate limit exceeded" bất ngờ khi demo | Bình thường nếu bấm rất nhanh liên tục (tiêu biểu: F5 lặp lại `/chat`); đợi ~1 phút. Nếu xảy ra ở mức dùng bình thường, nâng tạm `RATE_LIMIT_*` trên Render → Environment (không cần redeploy, chỉ restart service) |
| Đổi env trên Render không ăn | Render restart service khi đổi env, nhưng biến `VITE_*` thì nằm ở Vercel và cần build lại |
| Rollback | Render Dashboard → Deploys → chọn deploy cũ → **Rollback**. Nhanh hơn revert git rồi chờ CI |

---

## 7. Cố tình KHÔNG làm

Vì hạ tầng chỉ sống 1–2 tuần, những hạng mục sau bị loại bỏ **có chủ ý**, không phải bỏ sót:

| Bỏ qua | Lý do |
|---|---|
| Alembic / migration | DB tạo mới, schema đóng băng 2 tuần — xem P3 |
| Domain riêng + DNS | $10–15/năm cho 2 tuần, đổi lại phải khai lại toàn bộ OAuth origin |
| Sentry / APM | Render Logs + kiểm tra 5 phút/ngày là đủ cho quy mô này |
| Pin phiên bản dependency | `requirements.txt` toàn `>=`. Rủi ro là bản build sau vài tháng khác bản hôm nay — trong 2 tuần thì không kịp xảy ra |
| pgvector / persistent disk cho Chroma | `chromadb` đang bị comment trong `requirements.txt`, `./data` là ephemeral và hiện không ai phụ thuộc vào nó |
| Staging environment | Nhân đôi công dựng, cho một hệ thống sống 14 ngày |
| Tự host VPS + Caddy | Rẻ hơn ~$2/tháng nhưng đổi lấy việc tự lo TLS, firewall, backup, systemd — vô nghĩa ở quy mô thời gian này |

**Nếu sau này quyết định chạy dài hạn**, thứ tự làm lại: (1) Alembic, (2) pin dependency,
(3) Sentry, (4) domain riêng, (5) nâng Supabase lên gói có backup. (Rate limiting đã xong, không
còn nằm trong danh sách này.)

---

## 8. File liên quan

| File | Vai trò | Trạng thái |
|---|---|---|
| [Dockerfile](Dockerfile) | Image backend | **Vừa sửa** — fix bug `/root/.local` |
| [.dockerignore](.dockerignore) | Loại `Frontend/`, `data/`, `secrets/` khỏi image | **Vừa sửa** |
| [.env.production.example](.env.production.example) | Template biến môi trường production | **Mới** |
| [.github/workflows/db-backup.yml](.github/workflows/db-backup.yml) | Backup DB mã hoá hằng đêm | **Mới**, tuỳ chọn |
| [render.yaml](render.yaml) | Render Blueprint | Có sẵn — đổi `plan: free` → `starter` |
| [.github/workflows/ci.yml](.github/workflows/ci.yml) | Lint + test, có Postgres service | Có sẵn |
| [.github/workflows/deploy.yml](.github/workflows/deploy.yml) | CD qua Deploy Hook, gate sau CI | Có sẵn |
| [.github/workflows/keep-alive.yml](.github/workflows/keep-alive.yml) | Chống sleep gói free | **Disable sau khi lên Starter** |
| [Frontend/user/vercel.json](Frontend/user/vercel.json), [Frontend/admin/vercel.json](Frontend/admin/vercel.json) | SPA rewrite, 1 file/app | **Mới** (2026-08-17) — `Frontend/vercel.json` cũ (viết cho 1 project Root Directory = `Frontend`) đã lỗi thời: khi Root Directory trỏ vào `Frontend/user`/`Frontend/admin`, Vercel coi thư mục đó là gốc và không đọc `vercel.json` ở cấp cha — thiếu file mới thì F5 vào route con sẽ 404 |
| [docs/deploy.md](docs/deploy.md) | Hướng dẫn bấm dashboard từng bước | **Viết lại** (2026-08-17) |
