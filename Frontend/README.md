# Orbit — AI Personal Assistant UI

Giao diện MVP cho trợ lý cá nhân AI tích hợp trong nền tảng chat. Dự án chỉ bao gồm frontend và sử dụng dữ liệu mẫu, không có backend, API hoặc chức năng xác thực thật.

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

Thay `<repository-url>` bằng đường dẫn Git của dự án:

```bash
git clone <repository-url>
```

Ví dụ:

```bash
git clone https://github.com/your-account/orbit-ai-assistant.git
```

### 2. Di chuyển vào thư mục dự án

```bash
cd orbit-ai-assistant
```

Nếu repository dùng tên thư mục khác, hãy thay `orbit-ai-assistant` bằng tên thư mục vừa clone.

### 3. Cài đặt thư viện

```bash
npm install
```

### 4. Chạy giao diện ở chế độ development

```bash
npm run dev
```

Terminal sẽ hiển thị địa chỉ tương tự:

```text
http://localhost:5173
```

Mở địa chỉ đó trong trình duyệt để xem giao diện.

## Các trang có sẵn

| Trang | Đường dẫn |
| --- | --- |
| Đăng nhập | `/login` |
| Đăng ký | `/register` |
| Trợ lý AI cá nhân | `/assistant` |
| Chat | `/chat` |
| Công việc | `/tasks` |
| Lịch | `/calendar` |
| Nhắc nhở | `/reminders` |
| Bộ nhớ AI | `/memory` |
| Hồ sơ và cài đặt | `/profile` |

Đường dẫn `/` sẽ tự chuyển đến trang `/assistant`.

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

### Cổng 5173 đang được sử dụng

Chạy ứng dụng bằng cổng khác:

```bash
npm run dev -- --port 5174
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
src/
├── components/    # Component dùng lại cho layout và từng tính năng
├── data/          # Dữ liệu mẫu
├── pages/         # Các trang của ứng dụng
├── router/        # Cấu hình React Router
├── main.jsx       # Điểm khởi tạo ứng dụng
└── styles.css     # Design system và responsive styles
```

## Lưu ý

- Dự án hiện chỉ là giao diện frontend.
- Dữ liệu chat, công việc, lịch và nhắc nhở đều là dữ liệu mẫu.
- Các nút thao tác không kết nối backend hoặc API thật.
- Login và Register chỉ minh họa giao diện và validation phía client.
