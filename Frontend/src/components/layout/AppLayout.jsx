import { useCallback, useRef, useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopNavbar from './TopNavbar'
import ReminderToast from './ReminderToast'
import TaskSuggestedToast from './TaskSuggestedToast'
import BudgetAlertToast from './BudgetAlertToast'
import { useAuth } from '../../context/AuthContext'
import { useChatSocket } from '../../api/useWebSocket'

export default function AppLayout() {
  const [open, setOpen] = useState(false)
  const { token } = useAuth()
  const handlersRef = useRef(new Set())
  const [toastReminder, setToastReminder] = useState(null)
  const [toastTask, setToastTask] = useState(null)
  const [toastBudget, setToastBudget] = useState(null)

  const subscribe = useCallback((handler) => {
    handlersRef.current.add(handler)
    return () => handlersRef.current.delete(handler)
  }, [])

  const { sendJson } = useChatSocket(token, (data) => {
    handlersRef.current.forEach(handler => handler(data))
    if (data.type === 'reminder_fired') setToastReminder(data.reminder)
    if (data.type === 'task_suggested') setToastTask(data.task)
    if (data.type === 'usage_budget_alert') setToastBudget(data)
  })

  return (
    <div className="app-shell">
      <Sidebar open={open} onClose={() => setOpen(false)} />
      <div className="app-column"><TopNavbar onMenu={() => setOpen(true)} /><main className="app-main"><Outlet context={{ sendJson, subscribe }} /></main></div>
      {toastReminder && <ReminderToast reminder={toastReminder} onClose={() => setToastReminder(null)} />}
      {toastTask && <TaskSuggestedToast task={toastTask} onClose={() => setToastTask(null)} />}
      {toastBudget && <BudgetAlertToast alert={toastBudget} onClose={() => setToastBudget(null)} />}
    </div>
  )
}
