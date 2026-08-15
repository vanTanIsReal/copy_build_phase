import { createContext, useCallback, useContext, useRef, useState } from 'react'
import ToastStack from '../components/common/ToastStack'

const ToastContext = createContext(null)

let nextId = 0

// Generic app-wide toast queue - fills the gap the 3 existing WebSocket-driven toasts
// (ReminderToast/TaskSuggestedToast/BudgetAlertToast in components/layout/) don't cover: showing
// the result of any failed API call/user action, not just those 3 specific server-pushed events.
// Mounted above AuthProvider in both main.jsx files so AuthContext's own session-check can use it.
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timers = useRef(new Map())

  const dismissToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
    const timer = timers.current.get(id)
    if (timer) { clearTimeout(timer); timers.current.delete(id) }
  }, [])

  const pushToast = useCallback((message, variant = 'error') => {
    const id = ++nextId
    setToasts(prev => [...prev, { id, variant, message }])
    timers.current.set(id, setTimeout(() => dismissToast(id), 5000))
  }, [dismissToast])

  return (
    <ToastContext.Provider value={{ pushToast }}>
      {children}
      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}
