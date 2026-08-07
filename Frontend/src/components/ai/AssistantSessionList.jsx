import { useState } from 'react'

export const INITIAL_SESSIONS = [
  {
    id: 1,
    title: 'Tổng quan hôm nay',
    preview: 'Lịch, task và deadline...',
    time: 'Bây giờ',
    messages: [
      { id: 'm1', own: true, text: 'Tổng hợp lịch, task và deadline của tôi hôm nay' },
      { id: 'm2', own: false, text: 'Hôm nay bạn có 2 cuộc họp và 1 deadline quan trọng:\n1. 10:00 AM - Họp team Sync-up\n2. 02:30 PM - Gặp đối tác dự án\n3. Deadline: Nộp báo cáo tuần trước 17:00.' }
    ]
  },
  {
    id: 2,
    title: 'Chuẩn bị launch meeting',
    preview: 'Tóm tắt các quyết định...',
    time: 'Hôm qua',
    messages: [
      { id: 'm3', own: true, text: 'Tóm tắt các quyết định trong cuộc họp Launch meeting' },
      { id: 'm4', own: false, text: 'Các quyết định quan trọng:\n- Chốt ngày ra mắt chính thức vào thứ 6 tuần tới.\n- Đã phân công Frontend cho An, Backend cho Bình.\n- Mọi người hoàn thiện testing trước thứ 4.' }
    ]
  },
  {
    id: 3,
    title: 'Công việc tuần này',
    preview: 'Các task ưu tiên cao...',
    time: '28 Jul',
    messages: [
      { id: 'm5', own: true, text: 'Các task ưu tiên cao tuần này là gì?' },
      { id: 'm6', own: false, text: 'Danh sách task ưu tiên cao tuần này:\n- Hoàn thiện tích hợp API thanh toán\n- Viết tài liệu hướng dẫn sử dụng cho Partner\n- Đánh giá mã nguồn (Code Review) trước khi release' }
    ]
  },
  {
    id: 4,
    title: 'Northstar follow-up',
    preview: 'Deadline và người phụ trách...',
    time: '25 Jul',
    messages: [
      { id: 'm7', own: true, text: 'Deadline và người phụ trách dự án Northstar?' },
      { id: 'm8', own: false, text: 'Thông tin dự án Northstar:\n- Người phụ trách: Minh (Lead), Lan (Design)\n- Milestone tiếp theo: 15/08/2026.' }
    ]
  },
]

export default function AssistantSessionList({ activeId, onSelectSession, onNewSession, sessions = INITIAL_SESSIONS }) {
  const [search, setSearch] = useState('')
  const visible = sessions.filter(item => item.title.toLowerCase().includes(search.toLowerCase()))

  return (
    <aside className="assistant-sessions">
      <div className="assistant-session-head">
        <div>
          <span>Personal space</span>
          <h2>Trợ lý của tôi</h2>
        </div>
        <button
          className="icon-btn primary-soft"
          aria-label="Cuộc trò chuyện mới"
          title="Tạo cuộc trò chuyện mới"
          onClick={onNewSession}
        >
          <i className="bi bi-plus-lg" />
        </button>
      </div>
      <div className="session-search">
        <i className="bi bi-search"/>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Tìm cuộc trò chuyện"
        />
      </div>
      <div className="session-caption">Gần đây</div>
      <div className="session-items">
        {visible.map(item => (
          <button
            className={`session-item ${activeId === item.id ? 'active' : ''}`}
            key={item.id}
            onClick={() => onSelectSession(item)}
          >
            <span className="session-item-icon">
              <i className="bi bi-chat-square-text"/>
            </span>
            <span className="session-item-copy">
              <strong>{item.title}</strong>
              <small>{item.preview}</small>
            </span>
            <time>{item.time}</time>
          </button>
        ))}
      </div>
      <div className="assistant-private">
        <i className="bi bi-shield-check"/>
        <div>
          <strong>Không gian riêng tư</strong>
          <small>Chỉ bạn có thể xem nội dung tại đây.</small>
        </div>
      </div>
    </aside>
  )
}

