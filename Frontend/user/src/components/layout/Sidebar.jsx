import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { getUsageStatus } from '../../api/usage'

const nav = [
  ['assistant', 'bi-stars', 'AI Assistant'], ['chat', 'bi-chat-dots', 'Chats'], ['tasks', 'bi-check2-square', 'Tasks'],
  ['tasks/inbox', 'bi-inbox', 'Inbox'],
  ['calendar', 'bi-calendar4-week', 'Calendar'], ['reminders', 'bi-bell', 'Reminders'],
  ['memory', 'bi-stars', 'Memory'], ['workspaces', 'bi-diagram-3', 'Workspaces'],
  ['workspace-briefs', 'bi-file-earmark-bar-graph', 'Briefs'], ['profile', 'bi-person', 'Profile'],
]

const getInitials = (name) => (name || '?').trim().split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()

export default function Sidebar({ open, onClose, tasksIconRef, flightPulse }) {
  const { user, token, isAdmin } = useAuth()
  const adminUrl = import.meta.env.VITE_ADMIN_APP_URL || 'http://localhost:5174'
  // Real workspace-wide AI usage today (src/api/v1/usage/status) - there's no per-user credit
  // balance in the backend, only a shared daily token budget, so this is that, not "your" quota.
  const [usage, setUsage] = useState(null)
  useEffect(() => {
    if (!token) return
    let cancelled = false
    const load = () => getUsageStatus(token).then((data) => { if (!cancelled) setUsage(data) }).catch(() => {})
    load()
    const interval = setInterval(load, 60_000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [token])
  const usedPct = usage ? Math.min(100, Math.round(usage.used_pct)) : null
  return (
    <>
      <div className={`sidebar-backdrop ${open ? 'show' : ''}`} onClick={onClose} />
      {/* Structural sizing/position/mobile-slide behavior stays on `.app-sidebar` (orbit-fx.css,
          scoped `.orbit-fx .app-sidebar` overrides of Frontend/shared/styles.css) - the classes
          below are purely the cosmetic "floating glass panel" surface, per the Tailwind sidebar
          spec: detached margins, rounded corners, translucent blur, soft shadow. */}
      <aside className={`app-sidebar ${open ? 'open' : ''} rounded-2xl border border-white/10 bg-orbit-panel/85 backdrop-blur-xl shadow-orbit-panel`}>
        <div className="brand"><span className="brand-mark"><i className="bi bi-command" /></span><span>Orbit</span></div>
        <nav className="sidebar-nav">
          <div className="nav-caption">Personal</div>
          {nav.map(([path, icon, label]) => (
            // `end` matters here: without it, `/tasks` would also read as "active" while on
            // `/tasks/inbox` (NavLink prefix-matches by default), highlighting both at once.
            <NavLink key={path} to={`/${path}`} end onClick={onClose} className={({ isActive }) => `side-link ${label === 'AI Assistant' ? 'assistant-link' : ''} ${isActive ? 'active' : ''} ${path === 'tasks' && flightPulse ? 'flight-pulse' : ''}`}>
              <i className={`bi ${icon}`} ref={path === 'tasks' ? tasksIconRef : undefined} /><span>{label}</span>{label === 'AI Assistant' && <span className="new-pill">New</span>}
            </NavLink>
          ))}
          {isAdmin && <><div className="nav-caption">Administration</div><a className="side-link" href={adminUrl}><i className="bi bi-box-arrow-up-right" /><span>Open Admin</span></a></>}
        </nav>
        <div className="sidebar-bottom">
          <div className="ai-usage"><div className="d-flex align-items-center gap-2 mb-2"><i className="bi bi-stars" /><strong>AI usage today</strong><span>{usedPct === null ? '…' : `${usedPct}%`}</span></div><div className="progress"><div className="progress-bar" style={{width: `${usedPct ?? 0}%`}} /></div><small>{usage ? `${usage.tokens_used_today.toLocaleString()} / ${usage.daily_token_budget.toLocaleString()} tokens · shared across workspace · resets at midnight` : 'Loading…'}</small></div>
          <NavLink to="/profile" className="user-mini"><span className="avatar-photo">{getInitials(user?.display_name)}</span><span><strong>{user?.display_name || 'Loading...'}</strong><small>{user?.email}</small></span><i className="bi bi-three-dots ms-auto" /></NavLink>
        </div>
      </aside>
    </>
  )
}
