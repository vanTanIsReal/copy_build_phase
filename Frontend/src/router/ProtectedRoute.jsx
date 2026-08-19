import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Skeleton } from '../components/ui/skeleton'

export default function ProtectedRoute() {
  const { user, loading } = useAuth()
  if (loading) return <div className="auth-loading"><Skeleton className="h-10 w-10 rounded-full" /></div>
  return user ? <Outlet /> : <Navigate to="/login" replace />
}
