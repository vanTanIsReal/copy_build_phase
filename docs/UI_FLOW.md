# UI Flow & Wireframe — Orbit

> Bản đồ màn hình và luồng người dùng · Cập nhật 2026-08-04
> Wireframe trực quan: mở [wireframes.html](wireframes.html) bằng trình duyệt.

---

## 1. Sitemap

```mermaid
graph TD
    Root["/"] -->|redirect| Assistant

    subgraph Public["Công khai"]
        Login["/login"]
        Register["/register"]
    end

    subgraph Protected["ProtectedRoute — cần JWT"]
        Assistant["/assistant<br/>AI Assistant"]
        Chat["/chat<br/>Chats + AI Panel"]
        Tasks["/tasks<br/>Task inbox"]
        Calendar["/calendar"]
        Reminders["/reminders"]
        Memory["/memory"]
        Profile["/profile"]
    end

    subgraph AdminOnly["AdminRoute — role=admin"]
        AdminDash["/admin<br/>Dashboard"]
        AdminUsers["/admin/users"]
        AdminConv["/admin/conversations"]
        AdminData["/admin/user-data"]
    end

    Login -->|đăng nhập| Assistant
    Register -->|đăng ký| Assistant
    Protected -.->|chưa đăng nhập| Login
    AdminOnly -.->|không phải admin| Assistant

    style Public fill:#fef3c7,stroke:#d97706,color:#000
    style Protected fill:#dbeafe,stroke:#2563eb,color:#000
    style AdminOnly fill:#fce7f3,stroke:#db2777,color:#000
```

**Layout chung (`AppLayout`):** Sidebar trái (Workspace: AI Assistant · Chats · Tasks · Calendar ·
Reminders · Memory · Profile; mục Admin chỉ hiện với role admin) + TopNavbar + vùng nội dung.
Một kết nối WebSocket duy nhất mở ở `AppLayout` và chia sẻ xuống các trang qua Outlet context.

## 2. Luồng chính — Tóm tắt & trích xuất task từ chat

```mermaid
sequenceDiagram
    actor U as Người dùng
    participant FE as ChatPage + AIPanel
    participant API as POST /api/v1/chat
    participant AG as LangGraph Agent
    participant T as Tool

    U->>FE: Bấm "Summarize" / "Extract tasks"
    FE->>API: {message, conversation_id, thread_id}
    API->>API: Verify user là participant
    API->>AG: invoke(thread_id)
    AG->>T: summarize_conversation / extract_tasks
    T-->>AG: Kết quả (terminal tool → kết thúc ngay)
    AG-->>FE: {status: "ok", reply}
    alt Extract tasks
        FE->>API: POST /tasks (status="suggested")
        FE-->>U: Hiện trong "AI suggestions" chờ Accept/Dismiss
    else Summarize
        FE-->>U: Hiện bản tóm tắt trong panel
    end
```

## 3. Luồng human-in-the-loop — Tạo lịch / nhắc việc

Đây là luồng **bắt buộc** cho mọi hành động có tác dụng phụ.

```mermaid
sequenceDiagram
    actor U as Người dùng
    participant FE as AIPanel / PersonalAIChat
    participant API as /api/v1/chat
    participant AG as Agent
    participant G as Google Calendar / Scheduler

    U->>FE: "Đặt lịch họp team 3h chiều mai"
    FE->>API: POST /chat
    API->>AG: invoke
    AG->>AG: Gọi create_calendar_event → interrupt()
    AG-->>FE: {status: "interrupted", draft: {...}}
    FE-->>U: Thẻ xác nhận — hiện rõ tiêu đề, thời gian
    alt Người dùng bấm "Xác nhận"
        U->>FE: Xác nhận
        FE->>API: POST /chat/resume {thread_id, approved: true}
        API->>AG: resume
        AG->>G: Tạo thật
        G-->>AG: event_id + link
        AG-->>FE: {status: "ok", reply + link}
        FE-->>U: "Đã tạo sự kiện" + link Google Calendar
    else Người dùng bấm "Huỷ"
        U->>FE: Huỷ
        FE->>API: POST /chat/resume {approved: false}
        AG-->>FE: Đã huỷ — không có gì được tạo
    end
```

**Nguyên tắc UI:** thẻ xác nhận phải hiện **đủ thông tin sẽ được ghi** (tiêu đề, ngày giờ, người
nhận) trước khi người dùng bấm — không được chỉ hiện "Bạn có chắc không?".

## 4. Luồng proactive — Agent tự phát hiện cam kết

```mermaid
sequenceDiagram
    actor A as User A
    participant WS as WebSocket
    participant PS as proactive_service
    participant LLM
    participant DB
    actor UI as UI của User A

    A->>WS: Gửi tin "Mai anh gửi báo giá cho em nhé"
    WS-->>A: Tin nhắn hiện ngay (không bị chặn)
    WS->>PS: Chạy nền (asyncio.create_task)
    PS->>PS: Pre-filter regex VI+EN
    PS->>LLM: Có phải cam kết/lịch hẹn không?
    LLM-->>PS: Có → {title, due_at}
    PS->>DB: Tạo Task (source=proactive, status=suggested)
    PS->>WS: Đẩy task_suggested
    WS-->>UI: Toast "Orbit tìm thấy 1 việc" → tới Tasks inbox
```

Pre-filter regex chạy **trước** khi gọi LLM để không tốn token cho tin nhắn hiển nhiên không phải
cam kết ("ok", "haha", emoji…).

## 5. Trạng thái Task

```mermaid
stateDiagram-v2
    [*] --> suggested: AI trích xuất / proactive
    [*] --> pending: Người dùng tự tạo
    suggested --> pending: Accept
    suggested --> dismissed: Dismiss
    pending --> in_progress: Bắt đầu làm
    in_progress --> completed: Hoàn thành
    pending --> completed: Hoàn thành
    completed --> [*]
    dismissed --> [*]
```

## 6. Mô tả từng màn hình

| Màn hình | Thành phần chính | Nguồn dữ liệu |
| --- | --- | --- |
| **/login, /register** | Form email + mật khẩu, link chuyển qua lại | `POST /auth/login`, `/auth/register` |
| **/assistant** | Chat trực tiếp với agent; giữ `thread_id`; nút Xác nhận/Huỷ trong bong bóng chat; panel ngữ cảnh bên phải | `POST /chat`, `/chat/resume` |
| **/chat** | 3 cột: danh sách hội thoại · khung tin nhắn realtime · **AIPanel** (Summarize, Extract tasks, Suggest reminder, Find schedule, Deadlines, ô Ask Orbit, thẻ quyền AI) | `/conversations`, `/messages`, WS, `POST /chat` |
| **/tasks** | Stat card · mục "AI suggestions" (Accept/Dismiss) · bảng task chính sort theo due_at + priority · ô search | `GET/POST /tasks`, WS `task_*` |
| **/calendar** | FullCalendar (timezone Asia/Ho_Chi_Minh) · modal chi tiết sự kiện có nút xoá | `/calendar/events`, WS `calendar_event_*` |
| **/reminders** | Danh sách nhắc việc theo trạng thái; toast realtime khi fire | `/reminders`, WS `reminder_fired` |
| **/memory** | Search + tab lọc theo category (sinh từ dữ liệu thật) · modal thêm/sửa · dropdown Edit/Delete | `/memories` |
| **/profile** | Thông tin cá nhân (tên, chức danh, timezone) · đổi mật khẩu (verify mật khẩu cũ) | `PATCH /auth/me`, `POST /auth/me/password` |
| **/admin** | Stat card user/hội thoại/tin nhắn + **token hôm nay & % ngân sách** · banner đỏ khi ≥80% | `GET /admin/stats` |
| **/admin/users** | Bảng user, đổi role, khoá/mở tài khoản | `/admin/users` |
| **/admin/conversations** | Danh sách hội thoại, xem tin nhắn, xoá | `/admin/conversations` |
| **/admin/user-data** | Task / Reminder / Memory toàn hệ thống, xoá được | `/admin/tasks`, `/reminders`, `/memories` |

## 7. Quy ước thiết kế

- **Sidebar cố định** ở desktop, thu vào drawer ở mobile (Bootstrap 5, mobile-friendly theo đề bài).
- **Mọi thao tác AI có tác dụng phụ** → thẻ xác nhận màu nổi bật, 2 nút Xác nhận / Huỷ.
- **Task do AI đề xuất** luôn tách khỏi task chính thức bằng khối "AI suggestions" riêng.
- **Ngày giờ** hiển thị qua `Frontend/src/utils/datetime.js` (Intl, cố định `Asia/Ho_Chi_Minh`) —
  không tự format rải rác trong component.
- **Trạng thái rỗng** (chưa có task/reminder/memory) có hướng dẫn hành động, không để trắng.
