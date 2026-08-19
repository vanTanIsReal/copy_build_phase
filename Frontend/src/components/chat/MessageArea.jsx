import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'

const readFile = file => new Promise((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => resolve(reader.result)
  reader.onerror = reject
  reader.readAsDataURL(file)
})

export default function MessageArea({ conversation, messages, currentUserId, onSend }) {
  const [draft, setDraft] = useState('')
  const [attachment, setAttachment] = useState(null)
  const [showEmoji, setShowEmoji] = useState(false)
  const [mentionQuery, setMentionQuery] = useState(null)
  const scrollRef = useRef(null)
  const fileRef = useRef(null)
  const emojis = ['😀', '😂', '😍', '👍', '🎉', '🔥', '✅', '🙏', '😅', '🚀', '💡', '❤️']

  useEffect(() => { scrollRef.current?.scrollIntoView({ block: 'end' }) }, [messages])

  const submit = (e) => {
    e.preventDefault()
    if (!draft.trim() && !attachment) return
    const send = async () => {
      let file = null
      if (attachment) {
        if (attachment.size > 2 * 1024 * 1024) { window.alert('File must be smaller than 2 MB.'); return }
        file = { name: attachment.name, type: attachment.type || 'application/octet-stream', data: await readFile(attachment) }
      }
      onSend({ content: draft.trim(), file })
    }
    send()
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
            <input value={draft} onChange={e => {
              const value = e.target.value; setDraft(value)
              const match = value.match(/(?:^|\s)@([^\s@]*)$/)
              setMentionQuery(match ? match[1].toLowerCase() : null)
            }} placeholder={`Message ${conversation.name}...`} />
            {mentionQuery !== null && <div className="mention-menu">{conversation.participants.filter(p => p.display_name.toLowerCase().includes(mentionQuery)).slice(0, 6).map(p => <button type="button" key={p.id} onClick={() => { setDraft(v => v.replace(/@[^\s@]*$/, `@${p.display_name} `)); setMentionQuery(null) }}><span className="mention-avatar">{p.display_name.slice(0, 1).toUpperCase()}</span>{p.display_name}</button>)}</div>}
          </div>
          <div className="emoji-picker-wrap"><button type="button" className="icon-btn" aria-label="Choose emoji" title="Choose emoji" onClick={() => setShowEmoji(v => !v)}><i className="bi bi-emoji-smile" /></button>{showEmoji && <div className="emoji-picker">{emojis.map(emoji => <button type="button" key={emoji} onClick={() => { setDraft(v => `${v}${emoji}`); setShowEmoji(false) }}>{emoji}</button>)}</div>}</div>
          <button className="send-btn" aria-label="Send"><i className="bi bi-send-fill" /></button>
        </div>
        <div className="composer-help"><span><i className="bi bi-stars" /> Type <strong>@orbit</strong> to ask AI</span><span>Enter to send</span></div>
      </form>
    </div>
  )
}
