import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { createTask } from '../../api/tasks'

// Mirrors NewReminderModal.jsx's shape - only `title` is required server-side
// (TaskCreateRequest in src/models/task_schemas.py), due_at/priority are optional.
export default function NewTaskModal({ open, onClose, onCreated }) {
  const { token } = useAuth()
  const [title, setTitle] = useState('')
  const [dueAt, setDueAt] = useState('')
  const [priority, setPriority] = useState('Medium')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  if (!open) return null

  const submit = async (e) => {
    e.preventDefault()
    if (!title.trim()) return
    setSubmitting(true); setError('')
    try {
      const task = await createTask(token, {
        title: title.trim(),
        due_at: dueAt ? `${dueAt}:00` : null,
        priority,
      })
      onCreated(task)
      onClose()
      setTitle(''); setDueAt(''); setPriority('Medium')
    } catch (err) { setError(err.detail || 'Could not create task') }
    finally { setSubmitting(false) }
  }

  return (
    <div className="modal show d-block" tabIndex="-1" style={{ background: 'rgba(20,30,50,.32)' }} onClick={onClose}>
      <div className="modal-dialog modal-dialog-centered" onClick={e => e.stopPropagation()}>
        <div className="modal-content">
          <div className="modal-header"><h5 className="modal-title">Add task</h5><button className="btn-close" onClick={onClose} /></div>
          <form onSubmit={submit}>
            <div className="modal-body d-flex flex-column gap-3">
              {error && <div className="auth-error">{error}</div>}
              <input className="form-control" placeholder="Task title" value={title} onChange={e => setTitle(e.target.value)} required />
              <div className="row g-2">
                <div className="col"><label className="form-label small">Due at (optional)</label><input type="datetime-local" className="form-control" value={dueAt} onChange={e => setDueAt(e.target.value)} /></div>
                <div className="col"><label className="form-label small">Priority</label><select className="form-select" value={priority} onChange={e => setPriority(e.target.value)}><option value="Low">Low</option><option value="Medium">Medium</option><option value="High">High</option></select></div>
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-light" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={submitting}>{submitting ? 'Adding...' : 'Add task'}</button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
