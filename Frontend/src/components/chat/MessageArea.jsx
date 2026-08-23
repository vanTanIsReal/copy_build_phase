import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'

export default function MessageArea({ conversation, messages, currentUserId, onSend, loading, firstUnreadMessageId, unreadCount }) {
  const [draft, setDraft] = useState('')
  const scrollRef = useRef(null)
  const [unreadDismissed, setUnreadDismissed] = useState(false)

  useEffect(() => { scrollRef.current?.scrollIntoView({ block: 'end' }) }, [messages])
  // New unread marker (new conversation, or same conversation reopened) - show the button again.
  useEffect(() => { setUnreadDismissed(false) }, [firstUnreadMessageId])

  const submit = (e) => { e.preventDefault(); if (!draft.trim()) return; onSend(draft.trim()); setDraft('') }

  // Only true when the marked message is actually among the currently loaded ones - useMessages
  // sizes its initial fetch to cover the known unread backlog, but in the rare case a backlog is
  // larger than the backend's page cap, the target may not be loaded; hide the button rather than
  // show one that silently does nothing on click.
  const unreadTargetLoaded = firstUnreadMessageId && messages.some(m => m.id === firstUnreadMessageId)

  const jumpToUnread = () => {
    document.getElementById(`msg-${firstUnreadMessageId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setUnreadDismissed(true)
  }

  return (
    <div className="message-area">
      {unreadTargetLoaded && !unreadDismissed && (
        <button type="button" className="jump-to-unread-btn" onClick={jumpToUnread}>
          <i className="bi bi-arrow-up" /> {unreadCount} tin nhắn mới
        </button>
      )}
      <div className="messages-scroll">
        <div className="date-divider"><span>Today</span></div>
        {loading && <p className="text-muted small text-center mt-3">Đang tải tin nhắn...</p>}
        {!loading && messages.map(m => (
          <div key={m.id} id={`msg-${m.id}`}>
            {m.id === firstUnreadMessageId && <div className="unread-divider"><span>{unreadCount} tin nhắn mới</span></div>}
            <MessageBubble message={m} own={m.sender_id === currentUserId} />
          </div>
        ))}
        <div ref={scrollRef} />
      </div>
      <form className="composer" onSubmit={submit}>
        <div className="composer-main"><button type="button" className="icon-btn"><i className="bi bi-paperclip" /></button><input value={draft} onChange={e => setDraft(e.target.value)} placeholder={`Message ${conversation.name}...`} /><button type="button" className="icon-btn"><i className="bi bi-emoji-smile" /></button><button className="send-btn" aria-label="Send"><i className="bi bi-send-fill" /></button></div>
        <div className="composer-help"><span><i className="bi bi-stars" /> Type <strong>@orbit</strong> to ask AI</span><span>Enter to send</span></div>
      </form>
    </div>
  )
}
