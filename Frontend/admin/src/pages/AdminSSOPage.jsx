import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function AdminSSOPage() {
  const { loginWithHandoff } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [error, setError] = useState('')
  const started = useRef(false)
  useEffect(() => {
    if (started.current) return
    started.current = true
    const ticket = params.get('ticket')
    if (!ticket) { setError('Missing admin sign-in ticket'); return }
    loginWithHandoff(ticket).then(() => navigate('/admin', { replace: true })).catch(() => setError('Admin sign-in link expired.'))
  }, [loginWithHandoff, navigate, params])
  return <main className="admin-auth-state admin-shell"><span className="admin-auth-mark"><i className="bi bi-shield-check" /></span><h1>{error || 'Signing you in...'}</h1>{error && <a className="admin-primary-button" href="/login">Go to sign in</a>}</main>
}