import { useState } from 'react'

// Shown instead of accepting immediately when an AI-suggested task has no due_at - Orbit couldn't
// find a clear date/time in the conversation (e.g. "Mai đi ăn kem nhé" names a day but no time at
// all), so Accept still needs one human-in-the-loop step here before Calendar/Reminder sync has
// anything to schedule against. A task that already has a due_at skips this entirely and accepts
// the same way it always did - see TaskPage.jsx/TaskInboxPage.jsx's accept().
export default function ConfirmTaskDueDateModal({ task, onConfirm, onClose }) {
  const [dueAt, setDueAt] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  if (!task) return null

  const submit = async (event) => {
    event.preventDefault()
    if (!dueAt) return
    setSubmitting(true); setError('')
    try {
      await onConfirm(new Date(dueAt).toISOString())
    } catch (err) { setError(err.detail || 'Could not accept task.'); setSubmitting(false); return }
    setDueAt(''); setSubmitting(false)
  }

  return <div className="modal show d-block" tabIndex="-1" style={{background:'rgba(20,30,50,.32)'}} onClick={onClose}>
    <div className="modal-dialog modal-dialog-centered" onClick={event=>event.stopPropagation()}><div className="modal-content">
      <div className="modal-header"><h5 className="modal-title">Xác nhận ngày giờ</h5><button className="btn-close" onClick={onClose}/></div>
      <form onSubmit={submit}><div className="modal-body d-flex flex-column gap-3">
        <p className="text-secondary small mb-0">
          Orbit tìm thấy <strong>"{task.title}"</strong> trong hội thoại nhưng không rõ ngày giờ cụ thể. Chọn giúp trước khi xác nhận:
        </p>
        {error && <div className="auth-error">{error}</div>}
        <label className="form-label small mb-0">Ngày giờ
          <input type="datetime-local" className="form-control mt-1" value={dueAt} onChange={event=>setDueAt(event.target.value)} required autoFocus/>
        </label>
      </div><div className="modal-footer">
        <button type="button" className="btn btn-light" onClick={onClose}>Huỷ</button>
        <button className="btn btn-primary" disabled={submitting || !dueAt}>{submitting ? 'Đang xác nhận...' : 'Xác nhận'}</button>
      </div></form>
    </div></div>
  </div>
}
