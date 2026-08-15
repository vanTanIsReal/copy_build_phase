import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

// Restored from a version that was accidentally lost in a branch revert (commit 15842b6) - the
// working tree had regressed to a search box/help/bell/avatar that all silently did nothing.
// Client-side only: no API dependency, just a static page/feature index + React Router navigation.
const destinations = [
  { label: 'Orbit Assistant', keywords: 'ai ask assistant agent orbit', path: '/assistant', icon: 'bi-stars' },
  { label: 'Chats', keywords: 'messages conversations people groups', path: '/chat', icon: 'bi-chat-dots' },
  { label: 'Tasks', keywords: 'work todos deadlines action items', path: '/tasks', icon: 'bi-list-task' },
  { label: 'Task inbox', keywords: 'priority triage suggested', path: '/tasks/inbox', icon: 'bi-inbox' },
  { label: 'Calendar', keywords: 'events meetings schedule dates', path: '/calendar', icon: 'bi-calendar3' },
  { label: 'Reminders', keywords: 'alerts notifications alarms', path: '/reminders', icon: 'bi-alarm' },
  { label: 'Memory', keywords: 'remember preferences context', path: '/memory', icon: 'bi-journal-bookmark' },
  { label: 'Profile', keywords: 'account settings password', path: '/profile', icon: 'bi-person' },
]

const getInitials = (name) => (name || '?').trim().split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()

export default function TopNavbar({ onMenu }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const normalized = query.trim().toLowerCase()
  const results = useMemo(() => normalized
    ? destinations.filter(item => `${item.label} ${item.keywords}`.toLowerCase().includes(normalized))
    : destinations, [normalized])

  useEffect(() => {
    const focusSearch = event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); inputRef.current?.focus(); setOpen(true)
      }
    }
    window.addEventListener('keydown', focusSearch)
    return () => window.removeEventListener('keydown', focusSearch)
  }, [])

  const choose = item => { navigate(item.path); setQuery(''); setOpen(false) }
  const onKeyDown = event => {
    if (event.key === 'Enter' && results[0]) { event.preventDefault(); choose(results[0]) }
    if (event.key === 'Escape') { setQuery(''); setOpen(false); inputRef.current?.blur() }
  }
  const onLogout = () => { logout(); navigate('/login') }

  return (
    <header className="top-navbar">
      <button className="icon-btn mobile-menu" onClick={onMenu} aria-label="Open menu"><i className="bi bi-list" /></button>
      <div className="global-search" onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 120)}>
        <i className="bi bi-search" />
        <input ref={inputRef} aria-label="Search" placeholder="Search pages and features..." value={query} onChange={e => { setQuery(e.target.value); setOpen(true) }} onKeyDown={onKeyDown} />
        <kbd>Ctrl K</kbd>
        {open && (
          <div className="global-search-results">
            {results.map(item => (
              <button type="button" key={item.path} onMouseDown={e => e.preventDefault()} onClick={() => choose(item)}>
                <i className={`bi ${item.icon}`} /><span>{item.label}</span><i className="bi bi-arrow-right-short" />
              </button>
            ))}
            {!results.length && <p>No matching page or feature.</p>}
          </div>
        )}
      </div>

      <div className="nav-actions">
        <button className="icon-btn" title="Trợ giúp & Hướng dẫn" aria-label="Trợ giúp" onClick={() => setHelpOpen(true)}>
          <i className="bi bi-question-circle" />
        </button>
        <button className="icon-btn notification-btn" title="Xem thông báo & Nhắc nhở" aria-label="Nhắc nhở" onClick={() => navigate('/reminders')}>
          <i className="bi bi-bell" />
          <span />
        </button>
        <button className="nav-avatar" title="Hồ sơ cá nhân" aria-label="Hồ sơ cá nhân" onClick={() => navigate('/profile')}>
          {getInitials(user?.display_name)}
        </button>
        <button className="icon-btn" onClick={onLogout} aria-label="Log out" title="Đăng xuất">
          <i className="bi bi-box-arrow-right" />
        </button>
      </div>

      {helpOpen && (
        <div className="modal show d-block" tabIndex="-1" style={{ background: 'rgba(20,30,50,.4)' }} onClick={() => setHelpOpen(false)}>
          <div className="modal-dialog modal-dialog-centered" onClick={e => e.stopPropagation()}>
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title"><i className="bi bi-patch-question me-2" />Hướng dẫn & Hỏi đáp nhanh</h5>
                <button className="btn-close" onClick={() => setHelpOpen(false)} />
              </div>
              <div className="modal-body">
                <div className="d-flex flex-column gap-3">
                  <div><strong>🤖 AI Assistant (`/assistant`)</strong><p className="small text-muted mb-0">Hỏi tự do về lịch trình, công việc, tạo nhắc nhở và quản lý sự kiện Google Calendar bằng ngôn ngữ tự nhiên.</p></div>
                  <div><strong>💬 Chats (`/chat`)</strong><p className="small text-muted mb-0">Nhắn tin 1-1 hoặc tạo nhóm. AI sẽ tự động lắng nghe và trích xuất công việc/hạn chót từ hội thoại.</p></div>
                  <div><strong>📅 Calendar &amp; Reminders</strong><p className="small text-muted mb-0">Đồng bộ lịch Google Calendar 2 chiều và nhận thông báo nhắc nhở theo thời gian thực.</p></div>
                  <div><strong>💡 Ngân sách AI trong Sidebar</strong><p className="small text-muted mb-0">Là phần trăm hạn mức token AI chung của hệ thống đã dùng trong ngày (nhằm quản lý chi phí và tránh lạm dụng).</p></div>
                </div>
              </div>
              <div className="modal-footer">
                <button className="btn btn-primary btn-sm" onClick={() => { setHelpOpen(false); navigate('/assistant') }}>Hỏi AI ngay</button>
                <button className="btn btn-light btn-sm" onClick={() => setHelpOpen(false)}>Đóng</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </header>
  )
}
