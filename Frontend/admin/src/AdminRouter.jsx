import { useEffect } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { useAuth } from '../../src/context/AuthContext'
import AdminShell from './AdminShell'
import AdminLoginPage from './AdminLoginPage'
import AdminRegisterPage from './AdminRegisterPage'
import AdminDashboardPage from './AdminDashboardPage'
import AdminUsersPage from './AdminUsersPage'
import AdminConversationsPage from './AdminConversationsPage'
import AdminUserDataPage from './AdminUserDataPage'
import AdminAIManagementPage from './AdminAIManagementPage'
import AdminAIUsagePage from './AdminAIUsagePage'
import AdminAuditLogPage from './AdminAuditLogPage'

function AdminGuard() {
  const { user, loading, isAdmin, logout } = useAuth()
  // A non-admin who somehow gets a token into this app (e.g. shared browser profile) is signed
  // out immediately rather than just redirected - so the stale non-admin session doesn't linger.
  useEffect(() => {
    if (user && !isAdmin) logout()
  }, [user, isAdmin, logout])

  if (loading) return <div className="auth-loading">Loading admin console...</div>
  if (!user || !isAdmin) return <Navigate to="/login" replace />
  return <Outlet />
}

export default function AdminRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<AdminLoginPage />} />
        <Route path="/register" element={<AdminRegisterPage />} />
        <Route element={<AdminGuard />}>
          <Route element={<AdminShell />}>
            <Route index element={<AdminDashboardPage />} />
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="conversations" element={<AdminConversationsPage />} />
            <Route path="user-data" element={<AdminUserDataPage />} />
            <Route path="ai-management" element={<AdminAIManagementPage />} />
            <Route path="ai-usage" element={<AdminAIUsagePage />} />
            <Route path="audit-log" element={<AdminAuditLogPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
