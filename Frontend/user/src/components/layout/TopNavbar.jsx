import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

const getInitials = (name) => (name || '?').trim().split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()

export default function TopNavbar({ onMenu, notificationCount = 0, onNotifications }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const onLogout = () => { logout(); navigate('/login') }
  return (
    <header className="top-navbar">
      <button className="icon-btn mobile-menu" onClick={onMenu} aria-label="Open menu"><i className="bi bi-list" /></button>
      <div className="app-context"><i className="bi bi-command" /><strong>Orbit</strong></div>
      <div className="nav-actions">
        <button className="icon-btn position-relative" onClick={onNotifications} aria-label="Notifications" title="Notifications"><i className="bi bi-bell" />{notificationCount > 0 && <span className="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger">{notificationCount > 9 ? '9+' : notificationCount}</span>}</button>
        <button className="nav-avatar" onClick={() => navigate('/profile')} aria-label="Open profile" title="Profile">{getInitials(user?.display_name)}</button>
        <button className="icon-btn" onClick={onLogout} aria-label="Log out" title="Log out"><i className="bi bi-box-arrow-right" /></button>
      </div>
    </header>
  )
}
