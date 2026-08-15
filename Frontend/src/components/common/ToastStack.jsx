// Visual shell for ToastContext's generic toasts - deliberately top-right so it never overlaps
// the existing WebSocket-driven toasts (ReminderToast/TaskSuggestedToast/BudgetAlertToast, all
// bottom-right). Reuses the same Bootstrap card conventions as those three for visual consistency.
export default function ToastStack({ toasts, onDismiss }) {
  if (!toasts.length) return null
  return (
    <div style={{ position: 'fixed', top: 24, right: 24, zIndex: 1100, display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 360 }}>
      {toasts.map(t => (
        <div
          key={t.id}
          role="alert"
          className={`border rounded-3 p-3 bg-body shadow-lg d-flex align-items-start gap-2 border-${t.variant === 'success' ? 'success' : 'danger'}`}
        >
          <i className={`bi ${t.variant === 'success' ? 'bi-check-circle-fill text-success' : 'bi-exclamation-triangle-fill text-danger'} fs-5`} />
          <div className="flex-grow-1"><small>{t.message}</small></div>
          <button className="btn-close" aria-label="Đóng" onClick={() => onDismiss(t.id)} />
        </div>
      ))}
    </div>
  )
}
