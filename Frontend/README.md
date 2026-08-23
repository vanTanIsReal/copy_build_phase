# Orbit — Frontend

Frontend của Orbit, một AI agent nhúng trong ứng dụng chat (tóm tắt hội thoại, trích xuất task, nhắc
việc có xác nhận, lịch cá nhân Google Calendar). Đây là **2 app React + Vite riêng biệt** dùng chung
`Frontend/src/` qua import tương đối, không phải 1 SPA duy nhất:

- **`Frontend/user/`** — app người dùng thường (cổng 5173): Chat, AI Assistant, Tasks, Calendar,
  Reminders, Memory, Profile.
- **`Frontend/admin/`** — app quản trị (cổng 5174): Dashboard, Users, Conversations, User data, AI
  Management, AI Usage, Audit Log. Đăng nhập/đăng ký riêng, chỉ tài khoản role `admin` vào được.

Cả 2 app gọi API thật ở backend (`../src/`, FastAPI + LangGraph, mặc định `http://localhost:8000`) —
không còn dùng dữ liệu mẫu. Xem [../README.md](../README.md) ở gốc repo để chạy đầy đủ backend +
cả 2 app frontend; tài liệu này chỉ tập trung vào phần frontend và các lỗi thường gặp khi chạy `npm`
trên Windows.

## Công nghệ sử dụng

- React 18
- Vite
- React Router
- Bootstrap 5 và Bootstrap Icons
- React Hook Form
- FullCalendar
- Framer Motion

## Yêu cầu môi trường

Trước khi bắt đầu, máy cần có:

- [Git](https://git-scm.com/downloads)
- [Node.js](https://nodejs.org/) phiên bản 18 trở lên
- npm (được cài kèm Node.js)

Kiểm tra bằng Terminal, PowerShell hoặc Command Prompt:

```bash
git --version
node --version
npm --version
```

## Tải và chạy dự án từ Git

### 1. Clone repository

```bash
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-132.git
cd P-132
```

### 2. Chạy backend trước

Cả 2 app frontend đều gọi API thật — không có backend chạy sẵn thì đăng nhập/đăng ký và mọi trang
đều lỗi. Xem [../README.md](../README.md) mục "Cách chạy web" để setup + chạy backend (cổng 8000)
trước khi tiếp tục các bước dưới đây.

### 3. Chọn app rồi cài đặt + chạy

`Frontend/` chứa **2 app Vite độc lập**, mỗi app tự cài dependency và chạy dev server riêng —
`npm install`/`npm run dev` chạy thẳng ở `Frontend/` (không `cd` vào app nào) sẽ không tìm thấy
`package.json` nào cả.

**App người dùng** (cổng 5173, dùng cho việc phát triển/test hằng ngày):

```bash
cd Frontend/user
npm install
npm run dev
```

Mở `http://localhost:5173`.

**App admin** (cổng 5174, chỉ cần khi thật sự vào trang quản trị — xem [../README.md](../README.md)
mục "Cách chạy web" bước 3b để biết cách tạo tài khoản admin đầu tiên):

```bash
cd Frontend/admin
npm install
npm run dev
```

Mở `http://localhost:5174`.

## Các trang có sẵn

### App người dùng (`Frontend/user/`, cổng 5173)

| Trang | Đường dẫn |
| --- | --- |
| Đăng nhập | `/login` |
| Đăng ký | `/register` |
| Trợ lý AI cá nhân | `/assistant` |
| Chat | `/chat` |
| Công việc | `/tasks` |
| Inbox nhiệm vụ ưu tiên | `/tasks/inbox` |
| Lịch | `/calendar` |
| Nhắc nhở | `/reminders` |
| Bộ nhớ AI | `/memory` |
| Hồ sơ và cài đặt | `/profile` |

Đường dẫn `/` tự chuyển đến `/assistant`.

### App admin (`Frontend/admin/`, cổng 5174)

| Trang | Đường dẫn |
| --- | --- |
| Đăng nhập / Đăng ký admin | `/login`, `/register` (form riêng, không dùng chung với app người dùng) |
| Dashboard | `/` |
| Users | `/users` |
| Conversations | `/conversations` |
| User data (Task/Reminder/Memory toàn hệ thống) | `/user-data` |
| AI Management | `/ai-management` |
| AI Usage | `/ai-usage` |
| Audit Log | `/audit-log` |

## Build phiên bản production

Tạo bản build tối ưu:

```bash
npm run build
```

Kết quả sẽ nằm trong thư mục `dist/`.

Chạy thử bản production trên máy:

```bash
npm run preview
```

Sau đó mở địa chỉ được Vite hiển thị trong Terminal.

## Xử lý lỗi thường gặp

### PowerShell báo `npm.ps1 cannot be loaded`

Nếu Windows chặn script PowerShell, dùng file thực thi `npm.cmd`:

```powershell
npm.cmd install
npm.cmd run dev
```

Hoặc mở Command Prompt thay vì PowerShell rồi chạy lại các lệnh `npm` thông thường.

### Cổng 5173 (hoặc 5174) đang được sử dụng

Cổng 5174 giờ dành riêng cho app admin (`Frontend/admin/`) — đang chạy song song thì đừng dùng
`--port 5174` cho app user, sẽ đụng cổng. Cần cổng khác thì chọn số bất kỳ chưa dùng:

```bash
npm run dev -- --port 5175
```

### Giao diện hoặc dependency hoạt động không đúng sau khi cập nhật code

Xóa thư mục `node_modules` và file `package-lock.json`, sau đó cài lại:

PowerShell:

```powershell
Remove-Item -Recurse -Force node_modules
Remove-Item -Force package-lock.json
npm.cmd install
```

macOS/Linux:

```bash
rm -rf node_modules package-lock.json
npm install
```

## Cấu trúc chính

```text
Frontend/
├── src/                  # DÙNG CHUNG giữa user/ và admin/ (import tương đối, không tự build)
│   ├── api/                # Gọi REST API thật + WebSocket client
│   ├── context/              # AuthContext (JWT, user hiện tại), ToastContext
│   ├── hooks/                  # useConversations, useMessages, ...
│   ├── components/               # Component theo tính năng (chat, task, ai, common, layout, ...)
│   ├── pages/                      # Các trang ứng dụng (trừ 7 trang admin, ở admin/src/)
│   ├── router/                       # ProtectedRoute (dùng ở app user)
│   ├── utils/                          # datetime.js, taskGrouping.js, ...
│   └── data/mockData.js                 # Còn tồn tại nhưng KHÔNG được import ở đâu nữa — mọi
│                                          # trang đã nối API thật, đừng nhầm là còn dùng mock
├── user/                 # App #1 — người dùng thường, cổng 5173 (UserRouter + AppLayout)
│   └── src/main.jsx, UserRouter.jsx, vite.config.js, .env.example, package.json
└── admin/                # App #2 — platform admin, cổng 5174, đăng nhập/đăng ký riêng
    └── src/               # 7 trang admin để PHẲNG ở đây (AdminDashboardPage.jsx, ...), không
                              nằm trong pages/admin/ như cấu trúc cũ — chỉ sửa file ở đây, đừng
                              tạo lại pages/admin/
```

## Lưu ý

- Cả 2 app gọi API + WebSocket thật ở backend (`../src/`, FastAPI + LangGraph) — không còn trang nào
  dùng dữ liệu mẫu (`Frontend/src/data/mockData.js` vẫn tồn tại trong repo nhưng không được import
  ở đâu cả).
- Login/Register (cả app người dùng lẫn app admin) là xác thực thật: mật khẩu hash bcrypt, JWT trả
  về từ backend, không phải giả lập phía client.
- Mỗi app tự đọc biến môi trường riêng (`Frontend/user/.env`, `Frontend/admin/.env`, từ
  `.env.example` tương ứng) để trỏ `VITE_API_BASE_URL`/`VITE_WS_BASE_URL` — mặc định cả hai đều gọi
  `http://localhost:8000/api/v1`.
