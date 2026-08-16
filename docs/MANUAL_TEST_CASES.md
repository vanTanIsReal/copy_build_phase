# Manual Test Cases — Orbit (P-132)

> Bộ 10 test case kiểm thử thủ công cho các luồng chính của Orbit. Người kiểm thử thực hiện theo
> cột **Các bước**, sau đó điền **Kết quả thực tế** và **Trạng thái** (`PASS`, `FAIL` hoặc `BLOCKED`).

## Môi trường kiểm thử

- Backend: `http://localhost:8000` (`python scripts/run_dev.py`)
- User app: `http://localhost:5173` (`Frontend/user`)
- Admin app: `http://localhost:5174` (`Frontend/admin`), chỉ dùng cho TC-10
- Có ít nhất hai tài khoản người dùng; các case AI/Calendar cần API key hoặc OAuth tương ứng trong `.env`

## Danh sách test case

| Test ID | Test Case | Tiền điều kiện | Các bước | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
| --- | --- | --- | --- | --- | --- | --- |
| TC-01 | Đăng ký tài khoản mới | Email chưa tồn tại trong hệ thống | 1. Mở `/register`.<br>2. Nhập tên, email và mật khẩu hợp lệ.<br>3. Bấm **Create account**. | Tài khoản được tạo; người dùng tự động đăng nhập và được chuyển đến `/assistant`. | | |
| TC-02 | Đăng nhập sai mật khẩu | Đã có tài khoản hợp lệ | 1. Mở `/login`.<br>2. Nhập đúng email nhưng sai mật khẩu.<br>3. Bấm **Sign in**. | Hiển thị thông báo email hoặc mật khẩu không đúng; không tạo phiên đăng nhập. | | |
| TC-03 | Chặn truy cập khi chưa đăng nhập | Trình duyệt không có JWT hợp lệ | 1. Mở tab ẩn danh.<br>2. Truy cập trực tiếp `/tasks`. | Tự động chuyển về `/login`; nội dung trang Tasks không được hiển thị. | | |
| TC-04 | Gửi và nhận tin nhắn realtime | Hai tài khoản đang mở cùng một hội thoại trên hai trình duyệt | 1. Tài khoản A gửi một tin nhắn.<br>2. Quan sát màn hình của tài khoản B. | B nhận đúng tin nhắn ngay, không cần tải lại trang; tin nhắn không bị hiển thị trùng. | | |
| TC-05 | Tạo nhóm chat | Có ít nhất ba tài khoản người dùng | 1. Mở `/chat`.<br>2. Bấm nút tạo hội thoại.<br>3. Chọn ít nhất hai người khác, nhập tên nhóm.<br>4. Xác nhận tạo. | Nhóm được tạo đúng tên và thành viên; nhóm xuất hiện trong danh sách hội thoại của mọi thành viên. | | |
| TC-06 | AI tóm tắt hội thoại | Hội thoại có nhiều tin nhắn, đã bật quyền AI và cấu hình LLM hợp lệ | 1. Mở hội thoại.<br>2. Mở AI Panel.<br>3. Chọn **Summarize**. | Hiển thị một bản tóm tắt đúng nội dung hội thoại, định dạng dễ đọc và không lặp kết quả. | | |
| TC-07 | Tạo và hoàn thành task | Người dùng đã đăng nhập | 1. Mở `/tasks`.<br>2. Bấm **Add task** và nhập tiêu đề, hạn, độ ưu tiên.<br>3. Lưu task.<br>4. Đánh dấu task hoàn thành. | Task mới xuất hiện với đúng dữ liệu; sau bước 4 trạng thái chuyển sang hoàn thành và vẫn đúng sau khi tải lại trang. | | |
| TC-08 | Reminder phát đúng giờ | Người dùng đã đăng nhập và cho phép thông báo nếu trình duyệt yêu cầu | 1. Mở `/reminders`.<br>2. Tạo reminder có thời gian sau hiện tại khoảng hai phút.<br>3. Chờ đến thời điểm đã đặt. | Reminder ban đầu có trạng thái `scheduled`; đến giờ hệ thống hiển thị thông báo và chuyển trạng thái thành `fired`. | | |
| TC-09 | Kết nối và tạo sự kiện Google Calendar | Đã cấu hình Calendar OAuth; tài khoản Google là test user | 1. Mở `/calendar` và bấm **Connect Google Calendar**.<br>2. Đăng nhập Google, cấp quyền.<br>3. Tạo một sự kiện mới trên giao diện Orbit. | Kết nối thành công; sự kiện hiển thị đúng thời gian trên Orbit và trên đúng tài khoản Google Calendar. | | |
| TC-10 | Admin khóa và mở khóa người dùng | Có một tài khoản admin và một tài khoản user thường | 1. Admin đăng nhập tại `http://localhost:5174`.<br>2. Mở `/users` và khóa tài khoản user.<br>3. Thử đăng nhập bằng user đó.<br>4. Admin mở khóa rồi thử đăng nhập lại. | Khi bị khóa, user không đăng nhập được và nhận thông báo rõ ràng; sau khi mở khóa, user đăng nhập bình thường. | | |

## Tổng hợp kết quả

| Pass | Fail | Blocked | Chưa chạy | Tổng |
| --- | --- | --- | --- | --- |
| | | | | 10 |
