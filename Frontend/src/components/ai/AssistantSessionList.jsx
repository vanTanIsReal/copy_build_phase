import { useState } from 'react'

const sessions = [
  { id: 1, title: 'Tổng quan hôm nay', preview: 'Lịch, task và deadline...', time: 'Bây giờ', active: true },
  { id: 2, title: 'Chuẩn bị launch meeting', preview: 'Tóm tắt các quyết định...', time: 'Hôm qua' },
  { id: 3, title: 'Công việc tuần này', preview: 'Các task ưu tiên cao...', time: '28 Jul' },
  { id: 4, title: 'Northstar follow-up', preview: 'Deadline và người phụ trách...', time: '25 Jul' },
]

export default function AssistantSessionList() {
  const [search, setSearch] = useState('')
  const visible = sessions.filter(item => item.title.toLowerCase().includes(search.toLowerCase()))
  return <aside className="assistant-sessions">
    <div className="assistant-session-head"><div><span>Personal space</span><h2>Trợ lý của tôi</h2></div><button className="icon-btn primary-soft" aria-label="Cuộc trò chuyện mới"><i className="bi bi-plus-lg" /></button></div>
    <div className="session-search"><i className="bi bi-search"/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Tìm cuộc trò chuyện"/></div>
    <div className="session-caption">Gần đây</div>
    <div className="session-items">{visible.map(item=><button className={`session-item ${item.active?'active':''}`} key={item.id}><span className="session-item-icon"><i className="bi bi-chat-square-text"/></span><span className="session-item-copy"><strong>{item.title}</strong><small>{item.preview}</small></span><time>{item.time}</time></button>)}</div>
    <div className="assistant-private"><i className="bi bi-shield-check"/><div><strong>Không gian riêng tư</strong><small>Chỉ bạn có thể xem nội dung tại đây.</small></div></div>
  </aside>
}
