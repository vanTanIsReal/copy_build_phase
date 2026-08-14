import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../../src/context/AuthContext'
import { useChatSocket } from '../../src/api/useWebSocket'
import BudgetAlertToast from '../../src/components/layout/BudgetAlertToast'

const links = [
  ['/', 'bi-speedometer2', 'Dashboard'],
  ['/users', 'bi-people', 'Users'],
  ['/conversations', 'bi-chat-square-text', 'Conversations'],
  ['/user-data', 'bi-database', 'User data'],
  ['/ai-management', 'bi-robot', 'AI Management'],
  ['/ai-usage', 'bi-bar-chart-line', 'AI Usage'],
  ['/audit-log', 'bi-shield-check', 'Audit Log'],
]

export default function AdminShell() {
  const { user, token, logout } = useAuth()
  const navigate = useNavigate()
  const [toastBudget, setToastBudget] = useState(null)
  const signOut = () => { logout(); navigate('/login', { replace: true }) }

  // Same real-time budget alert as the user app's AppLayout.jsx (see usage_service.
  // _maybe_alert_budget - it broadcasts to every online admin, regardless of which frontend
  // they're connected from), so this console keeps showing it even though it's a separate app now.
  useChatSocket(token, (data) => {
    if (data.type === 'usage_budget_alert') setToastBudget(data)
  })

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-sidebar-brand"><span><i className="bi bi-command" /></span><strong>Orbit</strong><small>PLATFORM ADMIN</small></div>
        <div className="admin-sidebar-caption">Management</div>
        <nav>{links.map(([to, icon, label]) => <NavLink key={to} to={to} end={to === '/'}><i className={`bi ${icon}`} /><span>{label}</span></NavLink>)}</nav>
        <div className="admin-sidebar-footer"><div className="admin-identity"><i className="bi bi-person-circle" /><span><strong>{user?.display_name}</strong><small>{user?.email}</small></span></div><button onClick={signOut}><i className="bi bi-box-arrow-right" /> Sign out</button></div>
      </aside>
      <div className="admin-content">
        <header className="admin-topbar"><div><span className="admin-topbar-kicker">Platform control center</span><strong>Administration</strong></div><span className="admin-secure-badge"><i className="bi bi-shield-check" /> Admin only</span></header>
        <main className="admin-main"><Outlet /></main>
      </div>
      {toastBudget && <BudgetAlertToast alert={toastBudget} onClose={() => setToastBudget(null)} dashboardHref="/" />}
    </div>
  )
}
