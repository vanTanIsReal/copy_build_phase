import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { getUsageStatus } from '../../api/usage'

const nav = [
  ['assistant', 'bi-stars', 'AI Assistant'], ['chat', 'bi-chat-dots', 'Chats'], ['tasks', 'bi-check2-square', 'Tasks'],
  ['tasks/inbox', 'bi-inbox', 'Inbox'],
  ['calendar', 'bi-calendar4-week', 'Calendar'], ['reminders', 'bi-bell', 'Reminders'],
  ['memory', 'bi-stars', 'Memory'], ['profile', 'bi-person', 'Profile'],
]

const getInitials = (name) => (name || '?').trim().split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()

// Admin console lives at a separate origin now (Frontend/admin, its own login) - no more "Admin"
// nav section/links here, see Frontend/admin/src/AdminShell.jsx for the admin-only nav instead.
export default function Sidebar({ open, onClose }) {
  const { user, token } = useAuth()
  const [usage, setUsage] = useState(null)

  useEffect(() => {
    if (!token) return
    getUsageStatus(token).then(setUsage).catch(() => setUsage(null))
  }, [token])

  const usedPct = usage ? Math.min(100, Math.max(0, usage.used_pct)) : 0

  return (
    <>
      <div className={`sidebar-backdrop ${open ? 'show' : ''}`} onClick={onClose} />
      {/* app-sidebar keeps all structural/positioning/responsive CSS (styles.css) untouched -
          the Tailwind utilities below are additive-only (Design brief Phase 1: glassmorphism).
          Loaded after styles.css in main.jsx so bg-background/80 wins over .app-sidebar's plain
          `background:#fff`. */}
      <aside className={`app-sidebar ${open ? 'open' : ''} bg-background/80 backdrop-blur-md border-r border-white/10`}>
        <div className="brand"><span className="brand-mark"><i className="bi bi-command" /></span><span>Orbit</span></div>
        <nav className="sidebar-nav">
          <div className="nav-caption">Workspace</div>
          {nav.map(([path, icon, label]) => (
            // `end` matters here: without it, `/tasks` would also read as "active" while on
            // `/tasks/inbox` (NavLink prefix-matches by default), highlighting both at once.
            <NavLink key={path} to={`/${path}`} end onClick={onClose} className={({ isActive }) => `side-link ${label === 'AI Assistant' ? 'assistant-link' : ''} ${isActive ? 'active' : ''}`}>
              <i className={`bi ${icon}`} /><span>{label}</span>{label === 'AI Assistant' && <span className="new-pill">New</span>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="ai-usage">
            <div className="d-flex align-items-center gap-2 mb-2"><i className="bi bi-stars" /><strong>Ngân sách AI hôm nay</strong><span>{usage ? `${usage.used_pct}%` : '—'}</span></div>
            <div className="progress"><div className="progress-bar" style={{ width: `${usedPct}%` }} /></div>
            <small>{usage ? `${usage.tokens_used_today.toLocaleString()} / ${usage.daily_token_budget ? usage.daily_token_budget.toLocaleString() : '∞'} tokens · reset mỗi ngày` : 'Không tải được số liệu'}</small>
          </div>
          <NavLink to="/profile" className="user-mini"><span className="avatar-photo">{getInitials(user?.display_name)}</span><span><strong>{user?.display_name || 'Loading...'}</strong><small>{user?.email}</small></span><i className="bi bi-three-dots ms-auto" /></NavLink>
        </div>
      </aside>
    </>
  )
}
