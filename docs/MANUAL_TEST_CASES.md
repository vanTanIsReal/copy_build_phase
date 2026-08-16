# Manual Test Cases — Orbit (P-132)

Tài liệu mô tả chi tiết 10 test case thủ công cho các luồng chính của Orbit. Người kiểm thử thực hiện lần lượt từng bước, đối chiếu kết quả mong đợi và ghi nhận bằng chứng thực tế.

## 1. Thông tin lần kiểm thử

| Trường | Giá trị |
| --- | --- |
| Phiên bản/Commit | |
| Môi trường | Local / Staging / Production |
| Ngày kiểm thử | |
| Người kiểm thử | |
| Trình duyệt/Thiết bị | |

## 2. Môi trường và dữ liệu chuẩn bị

- Backend chạy tại `http://localhost:8000` bằng `python scripts/run_dev.py`.
- User app chạy tại `http://localhost:5173` từ thư mục `Frontend/user`.
- Admin app chạy tại `http://localhost:5174` từ thư mục `Frontend/admin`.
- PostgreSQL đã được cấu hình và backend kết nối thành công.
- Có ít nhất ba tài khoản người dùng riêng biệt: User A, User B và User C.
- Có một tài khoản admin và một tài khoản user thường để kiểm tra phân quyền.
- Các test case AI cần LLM provider/API key hợp lệ và ngân sách token chưa vượt giới hạn.
- Test case Calendar cần cấu hình Google OAuth và thêm tài khoản Google dùng để test vào danh sách test user.
- Trình duyệt cho phép thông báo khi thực hiện test case Reminder.

## 3. Quy ước trạng thái

- `PASS`: Kết quả thực tế khớp toàn bộ kết quả mong đợi.
- `FAIL`: Có ít nhất một bước cho kết quả sai hoặc phát sinh lỗi.
- `BLOCKED`: Không thể tiếp tục do môi trường, dữ liệu hoặc dịch vụ phụ thuộc chưa sẵn sàng.
- Mỗi case `FAIL` hoặc `BLOCKED` cần ghi rõ bước lỗi, ảnh chụp/log và mã lỗi liên quan.

---

## TC-01 — Đăng ký tài khoản mới

**Mục tiêu:** Xác nhận người dùng có thể tạo tài khoản bằng thông tin hợp lệ và được đăng nhập vào hệ thống.

**Tiền điều kiện:**

- Email kiểm thử chưa tồn tại trong cơ sở dữ liệu.
- Backend và user app đang hoạt động.

**Dữ liệu kiểm thử:**

- Tên hiển thị: `Manual Test User`
- Email: dùng một email duy nhất, ví dụ `manual.test+<timestamp>@example.com`
- Mật khẩu: một mật khẩu đáp ứng chính sách hiện tại của hệ thống

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Mở `http://localhost:5173/register`. | Trang đăng ký hiển thị đầy đủ các trường bắt buộc và nút tạo tài khoản. |
| 2 | Để trống các trường bắt buộc rồi gửi form. | Form không được gửi; các trường thiếu dữ liệu hiển thị cảnh báo phù hợp. |
| 3 | Nhập tên, email và mật khẩu hợp lệ. | Dữ liệu được hiển thị đúng; mật khẩu được che trên giao diện. |
| 4 | Bấm **Create account** một lần. | Hệ thống tạo đúng một tài khoản, không xuất hiện lỗi và không tạo bản ghi trùng. |
| 5 | Quan sát URL và thông tin người dùng sau khi đăng ký. | Người dùng được đăng nhập tự động, chuyển đến `/assistant` và hiển thị đúng thông tin tài khoản. |
| 6 | Tải lại trang. | Phiên đăng nhập vẫn hợp lệ; người dùng không bị chuyển về trang đăng nhập. |

**Kết quả thực tế:**

**Trạng thái:** `PASS` / `FAIL` / `BLOCKED`

**Bằng chứng/Ghi chú:**

---

## TC-02 — Từ chối đăng nhập khi sai mật khẩu

**Mục tiêu:** Đảm bảo hệ thống không tạo phiên đăng nhập khi thông tin xác thực không hợp lệ.

**Tiền điều kiện:**

- Có một tài khoản user đang hoạt động.
- Người dùng đã đăng xuất hoặc đang sử dụng tab ẩn danh.

**Dữ liệu kiểm thử:** Email đúng của user và một mật khẩu sai.

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Mở `http://localhost:5173/login`. | Form đăng nhập hiển thị trường email, mật khẩu và nút **Sign in**. |
| 2 | Nhập email hợp lệ và mật khẩu sai. | Form nhận dữ liệu; mật khẩu không hiển thị dạng văn bản thuần. |
| 3 | Bấm **Sign in**. | Hệ thống từ chối đăng nhập và hiển thị thông báo email hoặc mật khẩu không đúng. |
| 4 | Quan sát URL và nội dung trang. | Người dùng vẫn ở trang đăng nhập và không xem được nội dung cần xác thực. |
| 5 | Tải lại trang rồi truy cập trực tiếp `/assistant`. | Không có phiên đăng nhập được tạo; trình duyệt chuyển về `/login`. |
| 6 | Đăng nhập lại bằng đúng mật khẩu. | Đăng nhập thành công, chứng minh tài khoản không bị thay đổi bởi lần thử sai. |

**Kết quả thực tế:**

**Trạng thái:** `PASS` / `FAIL` / `BLOCKED`

**Bằng chứng/Ghi chú:**

---

## TC-03 — Chặn truy cập khi chưa đăng nhập

**Mục tiêu:** Xác nhận route và dữ liệu riêng tư không thể truy cập nếu không có phiên đăng nhập hợp lệ.

**Tiền điều kiện:** Dùng tab ẩn danh hoặc xóa token/cookie đăng nhập của ứng dụng.

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Mở tab ẩn danh và truy cập trực tiếp `http://localhost:5173/tasks`. | Trình duyệt chuyển về `/login`; nội dung trang Tasks không xuất hiện. |
| 2 | Dùng nút Back của trình duyệt. | Trang được bảo vệ vẫn không hiển thị nếu chưa đăng nhập. |
| 3 | Truy cập trực tiếp `/assistant`. | Trình duyệt tiếp tục chuyển về `/login`. |
| 4 | Gửi một request đến API cần xác thực mà không có header Authorization. | Backend trả về `401 Unauthorized` hoặc phản hồi xác thực tương đương; không trả dữ liệu người dùng. |
| 5 | Đăng nhập hợp lệ rồi truy cập lại `/tasks`. | Trang Tasks hiển thị bình thường với dữ liệu thuộc đúng người dùng vừa đăng nhập. |

**Kết quả thực tế:**

**Trạng thái:** `PASS` / `FAIL` / `BLOCKED`

**Bằng chứng/Ghi chú:**

---

## TC-04 — Gửi và nhận tin nhắn theo thời gian thực

**Mục tiêu:** Kiểm tra tin nhắn 1-1 được lưu và chuyển đến người nhận qua realtime mà không bị trùng.

**Tiền điều kiện:**

- User A và User B đăng nhập trên hai trình duyệt hoặc hai cửa sổ độc lập.
- Hai user có một hội thoại 1-1 và cùng mở hội thoại đó.
- Kết nối WebSocket của cả hai phía đang hoạt động.

**Dữ liệu kiểm thử:** Tin nhắn duy nhất, ví dụ `Realtime test <timestamp>`.

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Tại User A, nhập nội dung tin nhắn nhưng chưa gửi. | Nút gửi sẵn sàng; nội dung chưa xuất hiện trong lịch sử chat của hai bên. |
| 2 | User A bấm gửi một lần. | Tin nhắn xuất hiện một lần trong khung chat của A, đúng nội dung, người gửi và thời gian. |
| 3 | Quan sát màn hình User B mà không tải lại trang. | B nhận được tin nhắn ngay qua realtime và tin nhắn chỉ xuất hiện một lần. |
| 4 | User B trả lời bằng một nội dung khác. | A nhận phản hồi ngay, đúng người gửi và đúng hội thoại. |
| 5 | Tải lại trang ở cả hai phía. | Hai tin nhắn vẫn tồn tại, đúng thứ tự và không có bản ghi trùng. |
| 6 | User B rời hội thoại; User A gửi thêm một tin. | Chỉ báo chưa đọc của B tăng phù hợp; khi B mở lại hội thoại, tin nhắn mới được hiển thị. |

**Kết quả thực tế:**

**Trạng thái:** `PASS` / `FAIL` / `BLOCKED`

**Bằng chứng/Ghi chú:**

---

## TC-05 — Tạo hội thoại nhóm

**Mục tiêu:** Xác nhận nhóm chat được tạo đúng tên, đúng thành viên và không lộ cho người ngoài nhóm.

**Tiền điều kiện:** User A, User B và User C đang hoạt động; chuẩn bị thêm User D để kiểm tra người ngoài nhóm nếu có.

**Dữ liệu kiểm thử:** Tên nhóm duy nhất, ví dụ `Manual Test Group <timestamp>`.

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 1 | User A mở `/chat` và chọn chức năng tạo hội thoại mới. | Form tạo hội thoại hiển thị danh sách người dùng và trường tên nhóm. |
| 2 | Chọn User B và User C, nhập tên nhóm rồi xác nhận. | Hệ thống tạo một nhóm với A, B, C; nhóm xuất hiện trong danh sách hội thoại của A. |
| 3 | Kiểm tra danh sách thành viên và tên nhóm. | Tên nhóm khớp dữ liệu nhập; không thiếu hoặc thừa thành viên. |
| 4 | Kiểm tra màn hình User B và User C. | Nhóm xuất hiện trong danh sách hội thoại của cả B và C mà không cần tạo lại. |
| 5 | User A gửi một tin nhắn vào nhóm. | B và C nhận tin realtime; nội dung hiển thị đúng trong đúng nhóm. |
| 6 | Kiểm tra bằng tài khoản User D không thuộc nhóm. | D không thấy nhóm, không nhận sự kiện realtime và không thể đọc lịch sử nhóm qua giao diện/API. |
| 7 | Tải lại trang của một thành viên. | Nhóm, danh sách thành viên và lịch sử tin nhắn vẫn được lưu chính xác. |

**Kết quả thực tế:**

**Trạng thái:** `PASS` / `FAIL` / `BLOCKED`

**Bằng chứng/Ghi chú:**

---

## TC-06 — AI tóm tắt hội thoại

**Mục tiêu:** Kiểm tra AI tạo một bản tóm tắt đúng phạm vi hội thoại và không gây tác dụng phụ.

**Tiền điều kiện:**

- Hội thoại có tối thiểu 20 tin nhắn với một số quyết định và đầu việc rõ ràng.
- Người dùng đã bật quyền AI cho hội thoại.
- LLM được cấu hình hợp lệ và còn ngân sách token.

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Mở hội thoại có dữ liệu và mở AI Panel. | AI Panel hiển thị các hành động khả dụng, bao gồm **Summarize**. |
| 2 | Chọn phạm vi tóm tắt nếu giao diện hỗ trợ. | Phạm vi được chọn và hiển thị rõ ràng trước khi gửi yêu cầu. |
| 3 | Bấm **Summarize** một lần. | Giao diện hiển thị trạng thái đang xử lý và ngăn gửi trùng ngoài ý muốn. |
| 4 | Chờ phản hồi hoàn tất. | Một bản tóm tắt dễ đọc được hiển thị; nội dung phản ánh đúng các ý chính trong phạm vi đã chọn. |
| 5 | Đối chiếu tên người, quyết định, deadline và đầu việc với hội thoại gốc. | Không bịa thêm dữ kiện quan trọng; các thông tin được nêu khớp nội dung nguồn. |
| 6 | Kiểm tra hội thoại, task, reminder và calendar. | Thao tác tóm tắt không tự tạo tin nhắn, task, reminder hoặc sự kiện ngoài ý muốn. |
| 7 | Tải lại trang nếu kết quả được thiết kế để lưu. | Kết quả được giữ hoặc mất đúng theo thiết kế; không xuất hiện nhiều bản sao. |

**Kết quả thực tế:**

**Trạng thái:** `PASS` / `FAIL` / `BLOCKED`

**Bằng chứng/Ghi chú:**

---

## TC-07 — Tạo và hoàn thành task

**Mục tiêu:** Xác nhận người dùng có thể tạo task, lưu đúng dữ liệu và cập nhật trạng thái hoàn thành.

**Tiền điều kiện:** Người dùng đã đăng nhập và có quyền truy cập trang Tasks.

**Dữ liệu kiểm thử:**

- Tiêu đề: `Hoàn thành báo cáo manual test`
- Hạn: một thời điểm trong tương lai
- Độ ưu tiên: `High` hoặc giá trị tương đương trên giao diện

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Mở `/tasks`. | Trang hiển thị danh sách task và nút **Add task**. |
| 2 | Bấm **Add task**. | Form/modal tạo task mở và hiển thị các trường cần thiết. |
| 3 | Thử lưu khi chưa nhập tiêu đề. | Hệ thống không tạo task và hiển thị cảnh báo trường bắt buộc. |
| 4 | Nhập tiêu đề, hạn và độ ưu tiên theo dữ liệu kiểm thử rồi lưu. | Task được tạo đúng một lần và xuất hiện trong danh sách với dữ liệu chính xác. |
| 5 | Tải lại trang. | Task vẫn tồn tại; deadline và độ ưu tiên không bị thay đổi. |
| 6 | Đánh dấu task là hoàn thành. | Trạng thái task chuyển sang hoàn thành và giao diện phản ánh thay đổi ngay. |
| 7 | Tải lại trang hoặc đăng nhập lại. | Trạng thái hoàn thành vẫn được lưu chính xác. |

**Kết quả thực tế:**

**Trạng thái:** `PASS` / `FAIL` / `BLOCKED`

**Bằng chứng/Ghi chú:**

---

## TC-08 — Reminder được kích hoạt đúng thời điểm

**Mục tiêu:** Xác nhận reminder được lưu, kích hoạt một lần vào đúng thời điểm và chỉ gửi cho chủ sở hữu.

**Tiền điều kiện:**

- Người dùng đã đăng nhập.
- Backend scheduler và WebSocket đang hoạt động.
- Trình duyệt đã cho phép thông báo nếu ứng dụng sử dụng browser notification.

**Dữ liệu kiểm thử:** Reminder có tiêu đề duy nhất và thời gian kích hoạt sau hiện tại khoảng 2–3 phút.

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Mở `/reminders` và chọn tạo reminder mới. | Form tạo reminder hiển thị trường nội dung và thời gian. |
| 2 | Nhập dữ liệu kiểm thử rồi lưu. | Reminder xuất hiện với đúng nội dung, đúng thời gian và trạng thái `scheduled` hoặc tương đương. |
| 3 | Chuyển sang trang khác trong ứng dụng nhưng không đóng trình duyệt. | Phiên đăng nhập và kết nối realtime vẫn hoạt động. |
| 4 | Chờ đến thời điểm đã đặt. | Toast/browser notification xuất hiện gần đúng thời điểm, đúng nội dung và chỉ xuất hiện một lần. |
| 5 | Mở lại `/reminders`. | Reminder chuyển sang trạng thái `fired` hoặc trạng thái đã kích hoạt tương đương. |
| 6 | Tải lại trang và chờ thêm một khoảng ngắn. | Trạng thái vẫn được lưu; reminder không kích hoạt lặp ngoài cấu hình. |
| 7 | Kiểm tra bằng tài khoản khác. | Tài khoản khác không nhận và không xem được reminder của người tạo. |

**Kết quả thực tế:**

**Trạng thái:** `PASS` / `FAIL` / `BLOCKED`

**Bằng chứng/Ghi chú:**

---

## TC-09 — Kết nối và tạo sự kiện Google Calendar

**Mục tiêu:** Xác nhận OAuth hoạt động và sự kiện được đồng bộ đến đúng Google Calendar của người dùng.

**Tiền điều kiện:**

- Google OAuth client đã được cấu hình đúng redirect URI.
- Tài khoản Google kiểm thử nằm trong danh sách test user nếu ứng dụng OAuth chưa được publish.
- Người dùng Orbit đã đăng nhập và chưa kết nối nhầm tài khoản Google khác.

**Dữ liệu kiểm thử:**

- Tiêu đề: `Orbit manual calendar test <timestamp>`
- Thời gian bắt đầu: một thời điểm trong tương lai
- Thời lượng: 30 hoặc 60 phút

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Mở `/calendar` và bấm **Connect Google Calendar**. | Trình duyệt chuyển đến luồng đăng nhập/cấp quyền của Google. |
| 2 | Chọn tài khoản Google test và chấp thuận các quyền được yêu cầu. | Trình duyệt quay về Orbit; giao diện báo kết nối thành công và không lộ token OAuth. |
| 3 | Tạo sự kiện bằng dữ liệu kiểm thử trên giao diện Orbit. | Hệ thống báo tạo thành công; sự kiện xuất hiện một lần trên lịch Orbit. |
| 4 | Mở Google Calendar của đúng tài khoản vừa kết nối. | Sự kiện xuất hiện đúng tiêu đề, ngày, giờ và thời lượng. |
| 5 | Tải lại trang Calendar trong Orbit. | Sự kiện vẫn hiển thị và không bị nhân đôi. |
| 6 | Kiểm tra múi giờ hiển thị ở cả Orbit và Google Calendar. | Thời gian tương ứng chính xác theo múi giờ được cấu hình, không bị lệch ngày hoặc lệch giờ ngoài ý muốn. |

**Kết quả thực tế:**

**Trạng thái:** `PASS` / `FAIL` / `BLOCKED`

**Bằng chứng/Ghi chú:**

---

## TC-10 — Admin khóa và mở khóa người dùng

**Mục tiêu:** Kiểm tra admin có thể thay đổi trạng thái tài khoản và user bị khóa không thể đăng nhập.

**Tiền điều kiện:**

- Có một tài khoản admin đăng nhập được tại `http://localhost:5174`.
- Có một tài khoản User A đang hoạt động và biết thông tin đăng nhập.
- Không sử dụng chính tài khoản admin làm đối tượng bị khóa.

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Admin đăng nhập vào admin app. | Đăng nhập thành công và trang quản trị hiển thị đúng quyền admin. |
| 2 | Mở trang quản lý Users và tìm User A. | User A xuất hiện đúng email/tên và đang ở trạng thái hoạt động. |
| 3 | Chọn thao tác khóa User A và xác nhận. | Hệ thống báo thành công; trạng thái User A chuyển sang bị khóa và không tạo thay đổi cho user khác. |
| 4 | Đăng xuất User A nếu đang đăng nhập, sau đó thử đăng nhập lại. | Hệ thống từ chối đăng nhập và hiển thị thông báo tài khoản bị khóa hoặc thông báo phù hợp. |
| 5 | Thử gọi API bằng phiên/token cũ của User A nếu thiết kế yêu cầu vô hiệu hóa phiên. | Request bị từ chối theo chính sách khóa tài khoản; không trả dữ liệu riêng tư. |
| 6 | Admin quay lại danh sách Users và mở khóa User A. | Hệ thống báo thành công; trạng thái User A trở lại hoạt động. |
| 7 | User A đăng nhập lại bằng thông tin cũ. | Đăng nhập thành công; dữ liệu cũ của user vẫn còn nguyên. |
| 8 | Kiểm tra audit log nếu hệ thống hỗ trợ. | Có bản ghi đúng admin, user mục tiêu, hành động khóa/mở khóa và thời gian thực hiện. |

**Kết quả thực tế:**

**Trạng thái:** `PASS` / `FAIL` / `BLOCKED`

**Bằng chứng/Ghi chú:**

---

## 4. Tổng hợp kết quả

| Test ID | Chức năng | Trạng thái | Mã lỗi/Ticket | Ghi chú |
| --- | --- | --- | --- | --- |
| TC-01 | Đăng ký tài khoản mới | | | |
| TC-02 | Đăng nhập sai mật khẩu | | | |
| TC-03 | Chặn truy cập khi chưa đăng nhập | | | |
| TC-04 | Tin nhắn realtime | | | |
| TC-05 | Tạo hội thoại nhóm | | | |
| TC-06 | AI tóm tắt hội thoại | | | |
| TC-07 | Tạo và hoàn thành task | | | |
| TC-08 | Reminder đúng thời điểm | | | |
| TC-09 | Google Calendar | | | |
| TC-10 | Admin khóa/mở khóa user | | | |

| Pass | Fail | Blocked | Chưa chạy | Tổng |
| --- | --- | --- | --- | --- |
| | | | | 10 |
