# Manual Test Cases — Orbit (P-132)

> Bộ test case kiểm thử **thủ công** (khác với test tự động `pytest tests/` đã có trong CI) — theo
> format mentor gửi tham khảo. Người thực thi tự làm theo `Mô tả các bước`, ghi kết quả thật vào
> `Actual Result` và `Status` (PASS/FAIL/BLOCKED/SKIP).
>
> **Môi trường:** backend `http://localhost:8000` (`python scripts/run_dev.py`), app người dùng
> `http://localhost:5173` (`Frontend/user`), app admin `http://localhost:5174` (`Frontend/admin`,
> chỉ cần khi test nhóm Admin) — xem [../README.md](../README.md) mục "Cách chạy web" để setup.
> Một số nhóm cần `GOOGLE_API_KEY`/tương đương (AI) hoặc `GOOGLE_CALENDAR_CLIENT_ID/SECRET` (Calendar)
> điền thật trong `.env` — nếu thiếu, đánh dấu case đó `BLOCKED` kèm lý do thay vì `FAIL`.

## Tổng hợp kết quả

*(Điền lại sau khi chạy hết — đếm theo cột Status ở các bảng bên dưới)*

| Pass | Fail | Blocked | Skip | Tổng |
| --- | --- | --- | --- | --- |
| | | | | 64 |

---

## 1. Authentication & Authorization

| Test ID | Test Case | Mô tả các bước | Pre-conditions | Expected Result | Actual Result | Status |
| --- | --- | --- | --- | --- | --- | --- |
| AUTH-01 | Đăng ký tài khoản mới | 1. Vào `/register` 2. Nhập email chưa tồn tại + mật khẩu hợp lệ + tên hiển thị 3. Bấm "Create account" | Email chưa từng đăng ký | Tạo tài khoản thành công, tự đăng nhập, chuyển tới `/assistant` | | |
| AUTH-02 | Đăng ký trùng email | 1. Vào `/register` 2. Nhập email đã tồn tại 3. Bấm "Create account" | Đã có tài khoản với email đó (từ AUTH-01) | Hiện lỗi rõ ràng ("Could not create account" hoặc tương tự), không tạo tài khoản trùng | | |
| AUTH-03 | Đăng nhập đúng thông tin | 1. Vào `/login` 2. Nhập đúng email/mật khẩu vừa tạo 3. Bấm "Sign in" | Tài khoản đã tồn tại | Đăng nhập thành công, chuyển tới `/assistant`, JWT lưu trong localStorage | | |
| AUTH-04 | Đăng nhập sai mật khẩu | 1. Vào `/login` 2. Nhập đúng email, sai mật khẩu 3. Bấm "Sign in" | Tài khoản đã tồn tại | Hiện lỗi "Invalid email or password", không tạo session | | |
| AUTH-05 | Nút hiện/ẩn mật khẩu | 1. Vào `/login` 2. Gõ mật khẩu vào ô 3. Bấm icon con mắt | — | Mật khẩu chuyển giữa dạng ẩn (••••) và hiện chữ thật | | |
| AUTH-06 | Route được bảo vệ khi chưa đăng nhập | 1. Đăng xuất (hoặc mở tab ẩn danh) 2. Truy cập thẳng URL `/tasks` (hoặc `/chat`, `/calendar`...) | Chưa có JWT hợp lệ | Tự động chuyển hướng về `/login`, không hiện được nội dung trang | | |
| AUTH-07 | Đăng xuất | 1. Đăng nhập thành công 2. Bấm nút đăng xuất (avatar/TopNavbar) | Đang đăng nhập | Quay về `/login`, JWT bị xoá khỏi localStorage, truy cập lại route cũ bị chặn | | |
| AUTH-08 | Khôi phục phiên khi F5 | 1. Đăng nhập thành công 2. Nhấn F5 reload trang | Đang đăng nhập, đang ở 1 route protected | Vẫn ở nguyên trang đó, không bị đá về `/login`, thông tin user hiện đúng (gọi `GET /auth/me`) | | |
| AUTH-09 | Đăng nhập bằng Google | 1. Vào `/login` 2. Bấm nút "Sign in with Google" 3. Chọn tài khoản Google, đồng ý quyền | Đã cấu hình `GOOGLE_OAUTH_CLIENT_ID`/`VITE_GOOGLE_CLIENT_ID` thật | Lần đầu tự tạo tài khoản mới, các lần sau đăng nhập lại đúng tài khoản đó, chuyển vào `/assistant` | | |
| AUTH-10 | Đổi mật khẩu ở Profile | 1. Vào `/profile` 2. Nhập đúng mật khẩu cũ + mật khẩu mới 3. Lưu | Đang đăng nhập bằng tài khoản có mật khẩu (không phải tài khoản Google thuần) | Đổi thành công; đăng xuất rồi đăng nhập lại bằng mật khẩu mới hoạt động, mật khẩu cũ không còn dùng được | | |
| AUTH-11 | Đổi mật khẩu sai mật khẩu cũ | 1. Vào `/profile` 2. Nhập sai mật khẩu cũ 3. Lưu | Đang đăng nhập | Hiện lỗi, không đổi mật khẩu | | |

## 2. Chat 1-1 & Nhóm (realtime)

| Test ID | Test Case | Mô tả các bước | Pre-conditions | Expected Result | Actual Result | Status |
| --- | --- | --- | --- | --- | --- | --- |
| CHAT-01 | Tạo chat 1-1 mới | 1. Vào `/chat` 2. Bấm nút soạn tin (icon bút) 3. Tìm và chọn 1 người dùng khác 4. Gửi tin đầu tiên | Có ít nhất 2 tài khoản test | Tạo hội thoại 1-1 mới, hiện trong danh sách, tin nhắn gửi thành công | | |
| CHAT-02 | Tạo chat 1-1 trùng (dedupe) | 1. Từ tài khoản A, mở lại hội thoại 1-1 đã có với B (thử tạo mới lần nữa qua nút soạn tin, chọn đúng B) | Đã có hội thoại 1-1 A↔B từ CHAT-01 | Mở lại đúng hội thoại cũ, KHÔNG tạo hội thoại trùng thứ 2 | | |
| CHAT-03 | Tạo nhóm chat | 1. Bấm nút soạn tin 2. Chọn ≥2 người dùng 3. Đặt tên nhóm 4. Tạo | Có ≥3 tài khoản test | Tạo nhóm thành công, mọi thành viên đều thấy nhóm trong danh sách hội thoại của họ | | |
| CHAT-04 | Nhận tin nhắn realtime | 1. Mở cùng 1 hội thoại ở 2 trình duyệt/tài khoản khác nhau 2. Gửi tin từ tài khoản A | Cả 2 tài khoản đang mở đúng hội thoại đó | Tài khoản B nhận tin ngay lập tức, không cần F5 (qua WebSocket) | | |
| CHAT-05 | Đếm tin nhắn chưa đọc | 1. Tài khoản A gửi vài tin trong khi B không mở hội thoại đó 2. B vào `/chat` | B đang không mở đúng hội thoại lúc A gửi | Danh sách hội thoại của B hiện badge số tin chưa đọc đúng số lượng | | |
| CHAT-06 | Nhảy tới tin chưa đọc đầu tiên | 1. B có backlog nhiều tin chưa đọc trong 1 hội thoại dài 2. B mở hội thoại đó | Hội thoại có đủ tin nhắn để tạo backlog thật (hơn 1 màn hình) | Hiện nút/divider nhảy tới đúng tin đầu tiên chưa đọc, bấm vào cuộn đúng vị trí | | |
| CHAT-07 | Bật/tắt quyền AI ngay trên danh sách hội thoại | 1. Vào `/chat` 2. Gạt công tắc AI trên 1 dòng hội thoại trong danh sách | Đang đăng nhập, có ít nhất 1 hội thoại | Trạng thái đổi ngay, đồng bộ với badge trên header hội thoại đó và AIPanel (mở hội thoại ra kiểm tra lại) | | |
| CHAT-08 | Xoá hội thoại (chỉ với tôi) | 1. Mở menu "..." trên header hội thoại 2. Chọn Delete 3. Xác nhận | Đang có ít nhất 1 hội thoại | Hội thoại biến mất khỏi danh sách của người xoá; người còn lại vẫn thấy bình thường | | |
| CHAT-09 | Hội thoại đã xoá tự hiện lại khi có tin mới | 1. Sau CHAT-08, người còn lại gửi 1 tin mới vào hội thoại đó | Đã xoá hội thoại (chỉ với tôi) ở CHAT-08 | Hội thoại tự xuất hiện lại trong danh sách của người đã xoá | | |
| CHAT-10 | Rời nhóm | 1. Mở menu "..." trên header 1 nhóm chat 2. Chọn Leave 3. Xác nhận | Đang là thành viên 1 nhóm ≥3 người | Mất quyền truy cập hội thoại đó ngay; các thành viên còn lại thấy roster cập nhật realtime | | |

## 3. AI Agent — Quick Actions & Ask Orbit

| Test ID | Test Case | Mô tả các bước | Pre-conditions | Expected Result | Actual Result | Status |
| --- | --- | --- | --- | --- | --- | --- |
| AGENT-01 | Summarize hội thoại | 1. Mở 1 hội thoại có vài tin nhắn 2. Bấm icon AI trên header → Summarize | Đã cấp quyền AI cho hội thoại này (xem CHAT-07); có API key LLM hợp lệ trong `.env` | Trả về đúng 1 bản tóm tắt (không lặp 3 định dạng), nội dung phản ánh đúng tin nhắn thật | | |
| AGENT-02 | Extract tasks | 1. Trong hội thoại có nhắc tới việc cần làm/lịch hẹn 2. Bấm "Extract tasks" | Đã cấp quyền AI; hội thoại có nội dung task thật | Task được trích ra, xuất hiện trong `/tasks` mục "AI suggestions" với status `suggested` | | |
| AGENT-03 | Find schedule / Deadlines | 1. Bấm lần lượt "Find schedule" và "Deadlines" trong AIPanel | Đã cấp quyền AI | Trả lời có nội dung liên quan tới lịch/hạn chót được nhắc trong hội thoại | | |
| AGENT-04 | Ask Orbit — câu hỏi tự do | 1. Gõ 1 câu hỏi tự do vào ô "Ask Orbit" (vd "tóm tắt hộ tôi ai đang phải làm gì") 2. Gửi | Đã cấp quyền AI | Nhận được câu trả lời liên quan, hiển thị đúng định dạng markdown (đậm/gạch đầu dòng render thật, không hiện `**`/`-` thô) | | |
| AGENT-05 | Chặn khi chưa cấp quyền AI | 1. Tắt quyền AI cho 1 hội thoại (CHAT-07) 2. Thử bấm Summarize/Ask Orbit | Đã tắt quyền AI cho hội thoại đang mở | AIPanel disable quick action, báo rõ "Permission required" — không gọi được API AI | | |
| AGENT-06 | AI Assistant cá nhân (`/assistant`) — hỏi tự do | 1. Vào `/assistant` 2. Gõ câu hỏi tự do 3. Gửi | Đang đăng nhập | Nhận câu trả lời từ agent, hiện trong khung chat, markdown render đúng | | |
| AGENT-07 | Danh sách phiên chat cũ ở `/assistant` | 1. Chat vài lượt ở `/assistant` 2. Bấm nút tạo phiên mới/chọn phiên khác 3. Bấm lại vào phiên cũ | Đã có ít nhất 1 phiên chat trước đó | Danh sách bên trái hiện đúng các phiên thật (tiêu đề lấy từ tin đầu tiên); bấm vào tải đúng lại lịch sử hội thoại đó | | |
| AGENT-08 | Panel ngữ cảnh ở `/assistant` | 1. Vào `/assistant`, quan sát panel bên phải | Có sẵn vài task/sự kiện lịch/memory thật | Hiện đúng dữ liệu thật (task cần chú ý, lịch sắp tới, memory) — không phải số liệu cố định | | |

## 4. AI Agent — Human-in-the-loop (Calendar & Reminder)

| Test ID | Test Case | Mô tả các bước | Pre-conditions | Expected Result | Actual Result | Status |
| --- | --- | --- | --- | --- | --- | --- |
| HITL-01 | Tạo sự kiện lịch qua chat — xác nhận | 1. Ở `/assistant` hoặc AIPanel, gõ "đặt lịch họp team 3h chiều mai" 2. Chờ thẻ xác nhận hiện ra 3. Bấm "Xác nhận" | Đã Connect Google Calendar (xem CAL-01) | Hiện thẻ xác nhận có đủ tiêu đề/thời gian TRƯỚC khi tạo; sau khi xác nhận, sự kiện thật xuất hiện trên `/calendar` và trên Google Calendar thật | | |
| HITL-02 | Tạo sự kiện lịch qua chat — huỷ | 1. Lặp lại như HITL-01 nhưng bấm "Huỷ" ở bước xác nhận | Đã Connect Google Calendar | KHÔNG có sự kiện nào được tạo trên Google Calendar; agent xác nhận đã huỷ | | |
| HITL-03 | Cảnh báo trùng lịch + gợi ý khung giờ thay thế | 1. Đã có sẵn 1 sự kiện trong khung giờ X 2. Nhờ agent tạo sự kiện mới trùng khung giờ X | Đã Connect Google Calendar, đã có sẵn 1 event trong khung giờ sẽ test | Thẻ xác nhận cảnh báo trùng lịch, gợi ý tối đa 2 khung giờ trống thay thế trước khi tạo | | |
| HITL-04 | Tạo reminder qua chat — xác nhận | 1. Gõ "nhắc tôi gọi khách hàng lúc 5h chiều nay" 2. Bấm Xác nhận | — | Hiện thẻ xác nhận trước; sau khi xác nhận, reminder thật xuất hiện trong `/reminders` | | |
| HITL-05 | Sửa/xoá sự kiện lịch qua chat | 1. Nhờ agent "đổi giờ họp team sang 4h chiều" (event đã tạo ở HITL-01) 2. Xác nhận | Đã có event thật từ HITL-01 | Thẻ xác nhận hiện đúng thay đổi; sau xác nhận, event trên Google Calendar cập nhật đúng giờ mới | | |
| HITL-06 | Chưa Connect Calendar — agent báo rõ thay vì treo | 1. Dùng tài khoản CHƯA Connect Google Calendar 2. Nhờ agent tạo sự kiện lịch | Tài khoản test chưa Connect Calendar | Agent trả lời hướng dẫn kết nối Calendar trước, không bị treo/lỗi im lặng | | |

## 5. Tasks

| Test ID | Test Case | Mô tả các bước | Pre-conditions | Expected Result | Actual Result | Status |
| --- | --- | --- | --- | --- | --- | --- |
| TASK-01 | Tạo task thủ công | 1. Vào `/tasks` 2. Bấm "Add task" 3. Điền tiêu đề/hạn/priority 4. Lưu | — | Task mới xuất hiện trong bảng chính, `source="manual"` | | |
| TASK-02 | Accept task AI đề xuất | 1. Có task trong mục "AI suggestions" (từ AGENT-02 hoặc proactive) 2. Bấm "Accept" | Có ít nhất 1 AI suggestion, có `due_at` | Task chuyển từ "suggested" sang chính thức; nếu có `due_at`, tự tạo thêm sự kiện Calendar + Reminder thật | | |
| TASK-03 | Dismiss task AI đề xuất | 1. Bấm "Dismiss" trên 1 AI suggestion | Có ít nhất 1 AI suggestion | Task biến mất khỏi mục suggestions, không vào danh sách chính thức | | |
| TASK-04 | Đánh dấu hoàn thành / xoá task | 1. Trên 1 task đã có, bấm hoàn thành, sau đó bấm xoá | Có ít nhất 1 task pending | Trạng thái đổi đúng, lỗi (nếu có) báo qua toast thay vì im lặng | | |
| TASK-05 | Task Inbox nhóm đúng 4 mức | 1. Chuẩn bị vài task: 1 quá hạn, 1 sắp đến hạn <48h, 1 priority cao, 1 suggestion chưa xử lý 2. Vào `/tasks/inbox` | Có đủ 4 loại task như mô tả | Mỗi task nằm đúng nhóm tương ứng, không lẫn nhóm | | |
| TASK-06 | Realtime đồng bộ giữa 2 tab | 1. Mở `/tasks` ở 2 tab 2. Ở tab A, Accept 1 suggestion | Có sẵn 1 AI suggestion | Tab B tự cập nhật ngay không cần F5 | | |

## 6. Calendar

| Test ID | Test Case | Mô tả các bước | Pre-conditions | Expected Result | Actual Result | Status |
| --- | --- | --- | --- | --- | --- | --- |
| CAL-01 | Connect Google Calendar | 1. Vào `/calendar` (chưa từng connect) 2. Bấm "Connect Google Calendar" 3. Chọn tài khoản Google, đồng ý quyền | Đã cấu hình `GOOGLE_CALENDAR_CLIENT_ID/SECRET` thật, email test nằm trong Test users của OAuth consent | Popup Google thật hiện ra, sau khi đồng ý popup tự đóng, `/calendar` chuyển sang hiện lịch thật | | |
| CAL-02 | Tạo sự kiện từ UI | 1. Trên `/calendar` đã connect, bấm tạo sự kiện mới 2. Điền thông tin 3. Lưu | Đã Connect Calendar | Sự kiện hiện trên FullCalendar VÀ trên Google Calendar thật của đúng tài khoản đó | | |
| CAL-03 | Sửa/xoá sự kiện từ UI | 1. Bấm vào 1 sự kiện đã tạo 2. Sửa giờ hoặc xoá | Có sẵn ≥1 sự kiện từ CAL-02 | Thay đổi phản ánh đúng trên cả UI và Google Calendar thật | | |
| CAL-04 | Cách ly dữ liệu giữa 2 user | 1. User A và User B tự Connect 2 tài khoản Google KHÁC NHAU 2. A tạo 1 sự kiện | 2 tài khoản Orbit, 2 Google account riêng biệt đã Connect | Sự kiện của A KHÔNG hiện trên `/calendar` của B | | |
| CAL-05 | Đồng bộ 2 chiều — tạo trực tiếp trên Google Calendar | 1. Vào Google Calendar thật (ngoài app Orbit) 2. Tạo 1 sự kiện mới trực tiếp trên đó | Đã Connect Calendar, đang online trên Orbit | Trong khoảng ~20s (`CALENDAR_POLL_INTERVAL_SECONDS`), sự kiện tự xuất hiện trên `/calendar` không cần F5 | | |
| CAL-06 | Đúng giờ hiển thị theo timezone | 1. Tạo 1 sự kiện lúc 9:00 sáng giờ Việt Nam | Đã Connect Calendar | FullCalendar hiện đúng 9:00 sáng, không lệch múi giờ | | |
| CAL-07 | "Tuần này tôi có lịch gì" hỏi qua chat | 1. Đã có 1 sự kiện đầu tuần (không phải hôm nay) 2. Hỏi agent "tuần này tôi có lịch gì" | Đã Connect Calendar, có ≥1 event đầu tuần | Agent liệt kê đúng cả sự kiện đầu tuần, không chỉ từ thời điểm hỏi trở đi | | |

## 7. Reminders

| Test ID | Test Case | Mô tả các bước | Pre-conditions | Expected Result | Actual Result | Status |
| --- | --- | --- | --- | --- | --- | --- |
| REM-01 | Tạo reminder qua UI | 1. Vào `/reminders` 2. Tạo reminder mới, đặt giờ gần (vd +2 phút) | — | Reminder hiện trong danh sách với status "scheduled" | | |
| REM-02 | Reminder bắn đúng giờ | 1. Chờ tới đúng giờ đã đặt ở REM-01 | Có reminder sắp tới giờ | Toast/thông báo realtime hiện đúng lúc, dù đang ở trang nào của app; status đổi thành "fired" | | |
| REM-03 | Reminder sống sót qua restart backend | 1. Tạo reminder giờ gần 2. Restart backend (Ctrl+C rồi chạy lại `run_dev.py`) trước giờ hẹn 3. Chờ tới giờ | Có quyền restart backend trong lúc test | Reminder vẫn bắn đúng giờ dù backend đã restart giữa chừng | | |

## 8. Memory

| Test ID | Test Case | Mô tả các bước | Pre-conditions | Expected Result | Actual Result | Status |
| --- | --- | --- | --- | --- | --- | --- |
| MEM-01 | Thêm memory mới | 1. Vào `/memory` 2. Bấm "Add memory" 3. Điền category/tiêu đề/chi tiết 4. Lưu | — | Memory mới xuất hiện trong danh sách | | |
| MEM-02 | Sửa/xoá memory | 1. Mở menu 3 chấm trên 1 memory 2. Sửa nội dung, lưu 3. Xoá | Có ≥1 memory từ MEM-01 | Thay đổi/xoá phản ánh đúng, không cần F5 | | |
| MEM-03 | Search + lọc theo category | 1. Gõ từ khoá vào ô search 2. Chuyển qua các tab category | Có ≥3 memory với category khác nhau | Kết quả lọc đúng theo từ khoá và category chọn | | |

## 9. Admin

| Test ID | Test Case | Mô tả các bước | Pre-conditions | Expected Result | Actual Result | Status |
| --- | --- | --- | --- | --- | --- | --- |
| ADM-01 | Đăng nhập admin | 1. Vào `http://localhost:5174/login` 2. Đăng nhập bằng tài khoản role `admin` | Đã có tài khoản admin (`INITIAL_ADMIN_EMAIL` hoặc bootstrap qua `ADMIN_BOOTSTRAP_KEY`) | Vào được Dashboard; tài khoản không phải admin bị từ chối dù đúng mật khẩu | | |
| ADM-02 | Đổi role user | 1. Vào `/users` 2. Chọn 1 user thường 3. Đổi role thành admin rồi đổi lại | Có ≥1 user role `user` | Đổi thành công, phản ánh ngay trên bảng; user đó đăng nhập lại có quyền tương ứng | | |
| ADM-03 | Khoá/mở tài khoản | 1. Trên `/users`, khoá 1 tài khoản 2. Thử đăng nhập bằng tài khoản đó | Có ≥1 user không phải chính admin đang thao tác | Tài khoản bị khoá không đăng nhập được; mở khoá lại thì đăng nhập được bình thường | | |
| ADM-04 | Kiểm duyệt/xoá hội thoại | 1. Vào `/conversations` 2. Xem tin nhắn 1 hội thoại 3. Xoá hội thoại đó | Có ≥1 hội thoại thật | Xem được nội dung tin nhắn; sau khi xoá, hội thoại biến mất khỏi cả 2 phía user | | |
| ADM-05 | Đổi Daily token budget | 1. Vào Dashboard 2. Sửa giá trị "Daily token budget" 3. Lưu | Đang đăng nhập admin | Áp dụng ngay không cần restart backend, phản ánh đúng ở stat card | | |
| ADM-06 | Cảnh báo vượt ngân sách token | 1. Hạ tạm `DAILY_TOKEN_BUDGET` xuống rất thấp (vd 50) qua ADM-05 2. Dùng tính năng AI ở app user tới khi vượt 80% | Đã hạ budget thấp | Toast cảnh báo `usage_budget_alert` hiện ở BẤT KỲ trang nào admin đang mở (cả app user lẫn admin nếu tài khoản đó có role admin) | | |
| ADM-07 | Chặn gọi LLM khi vượt hẳn ngân sách | 1. Tiếp tục dùng AI tới khi vượt 100% budget | Đã vượt 80% ở ADM-06 | `/chat` bị chặn hẳn với thông báo rõ ràng, không chỉ cảnh báo suông | | |
| ADM-08 | AI Management — đổi provider/model | 1. Vào `/ai-management` 2. Đổi provider/model/temperature 3. Lưu | Có API key hợp lệ cho provider định đổi sang | Áp dụng ngay cho lượt gọi LLM tiếp theo, không cần restart backend | | |
| ADM-09 | AI Usage — xem chi phí | 1. Vào `/ai-usage` | Đã có usage log thật (từ các test AGENT-* ở trên) | Hiện đúng token đã dùng, chi phí ước tính, breakdown theo ngày/model | | |
| ADM-10 | Audit Log ghi đúng hành động | 1. Thực hiện 1 hành động có audit (vd đổi role ở ADM-02) 2. Vào `/audit-log` | Vừa thực hiện 1 hành động admin | Có entry mới ghi đúng ai đã làm gì, tìm/lọc được | | |
