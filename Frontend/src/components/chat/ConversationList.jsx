import { useState } from 'react'
import Avatar from '../common/Avatar'
import { getInitials, getColor, formatTime } from '../../utils/avatar'

export default function ConversationList({ conversations, selectedId, onSelect, onNewConversation }) {
  const [search, setSearch] = useState('')
  const normalized=search.trim().toLowerCase()
  const filtered = conversations.filter(c => [c.name,c.last_message?.content].some(value=>String(value||'').toLowerCase().includes(normalized)))
  return (
    <section className="conversation-list">
      <div className="conversation-title"><div><h2>Messages</h2><span>{conversations.length} conversations</span></div><button className="icon-btn primary-soft" onClick={onNewConversation} title="Find people or groups" aria-label="Find people or groups"><i className="bi bi-pencil-square" /></button></div>
      <div className="conversation-search"><i className="bi bi-search" /><input placeholder="Search messages" value={search} onChange={e => setSearch(e.target.value)} /></div>
      <div className="conversation-items">
        {filtered.map(c => (
          <button key={c.id} className={`chat-item ${c.id === selectedId ? 'active' : ''}`} onClick={() => onSelect(c.id)}>
            <Avatar initials={getInitials(c.name)} color={getColor(c.id)} size={44} />
            <span className="chat-item-body"><span className="chat-item-top"><strong>{c.name}</strong><time>{formatTime(c.last_message?.created_at || c.updated_at)}</time></span><span className="chat-item-bottom"><span>{c.last_message?.content || 'No messages yet'}</span>{c.unread_count > 0 && <b>{c.unread_count}</b>}</span></span>
          </button>
        ))}
        {!filtered.length && <p className="text-muted small text-center mt-4">{search ? 'No matching conversations or messages.' : 'No conversations yet.'}</p>}
      </div>
    </section>
  )
}
