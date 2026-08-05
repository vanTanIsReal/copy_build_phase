import { createContext, useContext, useEffect, useState } from 'react'
import * as authApi from '../api/auth'

const TOKEN_KEY = 'orbit_token'
const AuthContext = createContext(null)
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true'
const DEMO_USER = {
  id: 'demo-user',
  email: 'alex.rivera@orbit.demo',
  display_name: 'Alex Rivera',
  role: 'user',
  is_active: true,
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => DEMO_MODE ? 'demo-token' : localStorage.getItem(TOKEN_KEY))
  const [user, setUser] = useState(() => DEMO_MODE ? DEMO_USER : null)
  const [loading, setLoading] = useState(!DEMO_MODE)

  useEffect(() => {
    if (DEMO_MODE) { setLoading(false); return }
    if (!token) { setUser(null); setLoading(false); return }
    authApi.getMe(token)
      .then(setUser)
      .catch(() => { localStorage.removeItem(TOKEN_KEY); setToken(null); setUser(null) })
      .finally(() => setLoading(false))
  }, [token])

  const login = async (email, password) => {
    if (DEMO_MODE) {
      setUser({ ...DEMO_USER, email })
      setToken('demo-token')
      return
    }
    const data = await authApi.login({ email, password })
    localStorage.setItem(TOKEN_KEY, data.access_token)
    setUser(data.user)
    setToken(data.access_token)
  }

  const register = async (email, password, display_name) => {
    if (DEMO_MODE) {
      setUser({ ...DEMO_USER, email, display_name })
      setToken('demo-token')
      return
    }
    const data = await authApi.register({ email, password, display_name })
    localStorage.setItem(TOKEN_KEY, data.access_token)
    setUser(data.user)
    setToken(data.access_token)
  }

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
  }

  const isAdmin = user?.role === 'admin'

  return (
    <AuthContext.Provider value={{ user, token, loading, isAdmin, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
