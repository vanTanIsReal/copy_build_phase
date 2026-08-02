import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function AdminRoute() {
  const { user, loading, isAdmin } = useAuth()
  if (loading) return <div className="auth-loading">Loading...</div>
  if (!user) return <Navigate to="/login" replace />
  return isAdmin ? <Outlet /> : <Navigate to="/assistant" replace />
}
