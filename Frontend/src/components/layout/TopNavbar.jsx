import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

const getInitials = (name) => (name || '?').trim().split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()

export default function TopNavbar({ onMenu, notifications = [], onClearNotifications }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const onLogout = () => { logout(); navigate('/login') }
  return (
    <header className="top-navbar">
      <button className="icon-btn mobile-menu" onClick={onMenu} aria-label="Open menu"><i className="bi bi-list" /></button>
      <div className="global-search"><i className="bi bi-search" /><input aria-label="Search" placeholder="Search anything..."/><kbd>⌘ K</kbd></div>
      <div className="nav-actions">
        <div className="dropdown"><button className="icon-btn" data-bs-toggle="dropdown" aria-label="Help" title="Help"><i className="bi bi-question-circle" /></button><div className="dropdown-menu dropdown-menu-end nav-help-menu p-3"><strong>Orbit quick help</strong><p>Grant AI permission inside a chat before using Summarize, Extract tasks, or Ask Orbit.</p><p>Connect Google Calendar on the Calendar page before asking Orbit to manage events.</p><a href="mailto:support@orbit.local">Contact support</a></div></div>
        <div className="dropdown"><button className="icon-btn notification-btn" data-bs-toggle="dropdown" aria-label="Notifications" title="Notifications"><i className="bi bi-bell" />{notifications.length > 0 && <span />}</button><div className="dropdown-menu dropdown-menu-end notification-menu"><div className="notification-menu-head"><strong>Notifications</strong>{notifications.length > 0 && <button onClick={onClearNotifications}>Clear</button>}</div>{notifications.length ? notifications.map(item => <button className="notification-menu-item" key={item.id} onClick={() => item.href && navigate(item.href)}><i className={`bi ${item.icon}`} /><span><strong>{item.title}</strong><small>{item.detail}</small></span></button>) : <p className="notification-empty">No new notifications.</p>}</div></div>
        <button className="nav-avatar" onClick={() => navigate('/profile')} aria-label="Open profile" title="Profile">{getInitials(user?.display_name)}</button>
        <button className="icon-btn" onClick={onLogout} aria-label="Log out" title="Log out"><i className="bi bi-box-arrow-right" /></button>
      </div>
    </header>
  )
}
