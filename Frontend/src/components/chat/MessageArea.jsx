import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'

export default function MessageArea({ conversation, messages, currentUserId, onSend }) {
  const [draft, setDraft] = useState('')
  const scrollRef = useRef(null)

  useEffect(() => { scrollRef.current?.scrollIntoView({ block: 'end' }) }, [messages])

  const submit = (e) => { e.preventDefault(); if (!draft.trim()) return; onSend(draft.trim()); setDraft('') }

  return (
    <div className="message-area">
      <div className="messages-scroll">
        <div className="date-divider"><span>Today</span></div>
        {messages.map(m => <MessageBubble key={m.id} message={m} own={m.sender_id === currentUserId} />)}
        <div ref={scrollRef} />
      </div>
      <form className="composer" onSubmit={submit}>
        <div className="composer-main"><button type="button" className="icon-btn"><i className="bi bi-paperclip" /></button><input value={draft} onChange={e => setDraft(e.target.value)} placeholder={`Message ${conversation.name}...`} /><button type="button" className="icon-btn"><i className="bi bi-emoji-smile" /></button><button className="send-btn" aria-label="Send"><i className="bi bi-send-fill" /></button></div>
        <div className="composer-help"><span><i className="bi bi-stars" /> Type <strong>@orbit</strong> to ask AI</span><span>Enter to send</span></div>
      </form>
    </div>
  )
}
