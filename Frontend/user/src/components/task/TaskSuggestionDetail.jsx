// Small hover-reveal detail for a suggestion card: who proposed the commitment and the source
// message(s) Orbit read it from. source_messages[0] is always the proposal message (see
// task_routes._load_source_messages / proactive_service._task_payload), so its sender is "who
// proposed it" - no separate field needed. Renders nothing for a manually-created task (no
// source_messages) or before the backend/websocket payload for a task has caught up with this field.
export default function TaskSuggestionDetail({ task }) {
  const messages = task.source_messages
  if (!messages || !messages.length) return null
  const proposer = messages[0].sender_name

  return (
    <span className="task-suggestion-detail">
      <i className="bi bi-info-circle" tabIndex={0} />
      <div className="task-suggestion-detail-popover">
        <p className="task-suggestion-detail-proposer">
          <i className="bi bi-person-check me-1" />Đề xuất bởi <strong>{proposer}</strong>
        </p>
        <p className="task-suggestion-detail-label">Tin nhắn liên quan</p>
        {messages.map((message, index) => (
          <p className="task-suggestion-detail-message" key={index}>
            <strong>{message.sender_name}:</strong> {message.content}
          </p>
        ))}
      </div>
    </span>
  )
}
