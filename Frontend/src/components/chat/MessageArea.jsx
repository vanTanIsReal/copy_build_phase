import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'

export default function MessageArea({ conversation, messages, currentUserId, onSend }) {
  const [draft, setDraft] = useState('')
  const [attachment, setAttachment] = useState(null)
  const [showEmoji, setShowEmoji] = useState(false)
  const scrollRef = useRef(null)
  const fileRef = useRef(null)
  const emojis = ['😀', '😂', '😍', '👍', '🎉', '🔥', '✅', '🙏', '😅', '🚀', '💡', '❤️']

  useEffect(() => { scrollRef.current?.scrollIntoView({ block: 'end' }) }, [messages])

  const submit = (e) => {
    e.preventDefault()
    if (!draft.trim() && !attachment) return
    const fileNote = attachment ? `📎 ${attachment.name}\n` : ''
    onSend(`${fileNote}${draft.trim()}`.trim())
    setDraft(''); setAttachment(null); setShowEmoji(false)
  }

  return (
    <div className="message-area">
      <div className="messages-scroll">
        <div className="date-divider"><span>Today</span></div>
        {messages.map(m => <MessageBubble key={m.id} message={m} own={m.sender_id === currentUserId} />)}
        <div ref={scrollRef} />
      </div>
      <form className="composer" onSubmit={submit}>
        <div className="composer-main">
          <input ref={fileRef} type="file" hidden onChange={e => setAttachment(e.target.files?.[0] || null)} />
          <button type="button" className="icon-btn" aria-label="Attach file" title="Attach file" onClick={() => fileRef.current?.click()}><i className="bi bi-paperclip" /></button>
          <div className="composer-input-wrap">
            {attachment && <small className="attachment-chip"><i className="bi bi-file-earmark" /> {attachment.name}<button type="button" onClick={() => setAttachment(null)} aria-label="Remove attachment">×</button></small>}
            <input value={draft} onChange={e => setDraft(e.target.value)} placeholder={`Message ${conversation.name}...`} />
          </div>
          <div className="emoji-picker-wrap"><button type="button" className="icon-btn" aria-label="Choose emoji" title="Choose emoji" onClick={() => setShowEmoji(v => !v)}><i className="bi bi-emoji-smile" /></button>{showEmoji && <div className="emoji-picker">{emojis.map(emoji => <button type="button" key={emoji} onClick={() => { setDraft(v => `${v}${emoji}`); setShowEmoji(false) }}>{emoji}</button>)}</div>}</div>
          <button className="send-btn" aria-label="Send"><i className="bi bi-send-fill" /></button>
        </div>
        <div className="composer-help"><span><i className="bi bi-stars" /> Type <strong>@orbit</strong> to ask AI</span><span>Enter to send</span></div>
      </form>
    </div>
  )
}
