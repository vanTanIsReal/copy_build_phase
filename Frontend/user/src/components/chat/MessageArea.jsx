import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import MessageBubble from './MessageBubble'
import PulseWave from '../fx/PulseWave'
import { springs } from '../fx/springs'

export default function MessageArea({ conversation, messages, currentUserId, onSend, loading, firstUnreadMessageId, unreadCount, aiBusy = false }) {
  const [draft, setDraft] = useState('')
  const [attachments, setAttachments] = useState([])
  const [emojiOpen, setEmojiOpen] = useState(false)
  const fileInputRef = useRef(null)
  const scrollRef = useRef(null)
  const [unreadDismissed, setUnreadDismissed] = useState(false)

  useEffect(() => { scrollRef.current?.scrollIntoView({ block: 'end' }) }, [messages])
  // New unread marker (new conversation, or same conversation reopened) - show the button again.
  useEffect(() => { setUnreadDismissed(false) }, [firstUnreadMessageId])

  const submit = (e) => { e.preventDefault(); if (!draft.trim() && !attachments.length) return; const attachmentText = attachments.map(file => 📎 ).join('\\n'); onSend([draft.trim(), attachmentText].filter(Boolean).join('\\n')); setDraft(''); setAttachments([]); setEmojiOpen(false) }
  const addEmoji = (emoji) => { setDraft(value => value + emoji); setEmojiOpen(false) }
  const onFiles = (event) => { setAttachments(files => [...files, ...Array.from(event.target.files || [])].slice(0, 5)); event.target.value = '' }

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
    // Faint dot-matrix texture on the central canvas (pillar 1) - a Tailwind arbitrary
    // background-image so the panel doesn't read as an empty flat void, kept subtle (2% opacity
    // dots) so it never competes with the actual messages on top of it.
    <div className="message-area bg-[radial-gradient(circle,rgba(255,255,255,0.05)_1px,transparent_1px)] bg-[length:22px_22px]">
      {unreadTargetLoaded && !unreadDismissed && (
        <button type="button" className="jump-to-unread-btn" onClick={jumpToUnread}>
          <i className="bi bi-arrow-up" /> {unreadCount} tin nhắn mới
        </button>
      )}
      <div className="messages-scroll">
        <div className="date-divider"><span>Today</span></div>
        {loading && <p className="text-muted small text-center mt-3">Đang tải tin nhắn...</p>}
        <AnimatePresence initial={false}>
          {!loading && messages.map(m => (
            // Pillar 4: message overshoot entrance - slides up and slightly overshoots before
            // settling, spring-driven (never linear easing).
            <motion.div
              key={m.id} id={`msg-${m.id}`} layout
              initial={{ opacity: 0, y: 18, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={springs.messageEnter}
            >
              {m.id === firstUnreadMessageId && <div className="unread-divider"><span>{unreadCount} tin nhắn mới</span></div>}
              <MessageBubble message={m} own={m.sender_id === currentUserId} />
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={scrollRef} />
      </div>
      <form className="composer" onSubmit={submit}>
        <div className="composer-main">
          <input ref={fileInputRef} type="file" hidden multiple onChange={onFiles} />
          <button type="button" className="icon-btn" aria-label="Attach files" title="Attach files" onClick={() => fileInputRef.current?.click()}><i className="bi bi-paperclip" /></button>
          <input value={draft} onChange={e => setDraft(e.target.value)} placeholder={`Message ${conversation.name}...`} />
          <button type="button" className="icon-btn" aria-label="Choose emoji" title="Choose emoji" onClick={() => setEmojiOpen(open => !open)}><i className="bi bi-emoji-smile" /></button>
          <button className="send-btn" aria-label="Send"><i className="bi bi-send-fill" /></button>
        </div>
        {attachments.length > 0 && <div className="composer-attachments">{attachments.map((file, index) => <span key={`${file.name}-${index}`}><i className="bi bi-paperclip" />{file.name}<button type="button" aria-label={`Remove ${file.name}`} onClick={() => setAttachments(files => files.filter((_, i) => i !== index))}>×</button></span>)}</div>}
        {emojiOpen && <div className="emoji-picker" role="listbox" aria-label="Emoji picker">{['😀','😂','😍','👍','👏','🎉','✅','🔥','💡','🙏','😊','🤝','🚀','❤️','😅','🎯'].map(emoji => <button type="button" key={emoji} onClick={() => addEmoji(emoji)}>{emoji}</button>)}</div>}
        <PulseWave active={aiBusy} />
        <div className="composer-help"><span><i className="bi bi-stars" /> Type <strong>@orbit</strong> to ask AI</span><span>Enter to send</span></div>
      </form>
    </div>
  )
}
