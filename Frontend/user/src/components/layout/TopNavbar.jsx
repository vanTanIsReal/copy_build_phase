import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

const getInitials = (name) => (name || '?').trim().split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()

export default function TopNavbar({ onMenu }) {
  const { user, logout } = useAuth()
  const [helpOpen, setHelpOpen] = useState(false)
  const navigate = useNavigate()
  const onLogout = () => { logout(); navigate('/login') }
  return (
    <header className="top-navbar">
      <button className="icon-btn mobile-menu" onClick={onMenu} aria-label="Open menu"><i className="bi bi-list" /></button>
      <div className="app-context"><i className="bi bi-command" /><strong>Orbit</strong></div>
      <div className="nav-actions">
        <button className="icon-btn" aria-label="Help" title="Help" onClick={() => setHelpOpen(open => !open)}><i className="bi bi-question-circle" /></button>
        <button className="icon-btn notification-btn" aria-label="Open reminders" title="Open reminders" onClick={() => navigate("/reminders")}><i className="bi bi-bell" /><span /></button>
        <button className="nav-avatar" aria-label="Open profile" title="Open profile" onClick={() => navigate("/profile")}>{getInitials(user?.display_name)}</button>
        <button className="icon-btn" onClick={onLogout} aria-label="Log out" title="Log out"><i className="bi bi-box-arrow-right" /></button>
      </div>
      {helpOpen && <div className="top-help-popover"><strong>Orbit Help</strong><span>Use the sidebar to open Chats, Tasks, Calendar and Reminders.</span><button onClick={() => { setHelpOpen(false); navigate("/profile#ai") }}>Open AI settings</button></div>}
    </header>
  )
}
