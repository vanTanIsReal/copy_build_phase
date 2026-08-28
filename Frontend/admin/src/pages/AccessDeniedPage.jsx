import { useAuth } from '../context/AuthContext'

export default function AccessDeniedPage() {
  const { logout } = useAuth()
  return <main className="admin-auth-state denied admin-shell"><span className="admin-auth-mark danger"><i className="bi bi-shield-lock" /></span><h1>Access denied</h1><p>This application is restricted to platform administrators.</p><div><a className="admin-secondary-button" href={import.meta.env.VITE_USER_APP_URL || 'https://c3-app-132-auo2.vercel.app'}>Open user application</a><button className="admin-primary-button" onClick={logout}>Sign out</button></div></main>
}
