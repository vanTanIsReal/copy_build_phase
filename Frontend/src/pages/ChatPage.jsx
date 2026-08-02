import { useState } from 'react'
import ConversationList from '../components/chat/ConversationList'
import ConversationHeader from '../components/chat/ConversationHeader'
import MessageArea from '../components/chat/MessageArea'
import AIPanel from '../components/chat/AIPanel'
import NewConversationModal from '../components/chat/NewConversationModal'
import { useAuth } from '../context/AuthContext'
import { useConversations } from '../hooks/useConversations'
import { useMessages } from '../hooks/useMessages'
import { useChatSocket } from '../api/useWebSocket'
import { markRead } from '../api/chat'

export default function ChatPage() {
  const { token, user } = useAuth()
  const [mobileChat, setMobileChat] = useState(false)
  const [aiOpen, setAiOpen] = useState(false)
  const [newConvoOpen, setNewConvoOpen] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const { conversations, setConversations } = useConversations(token)
  const { messages, setMessages } = useMessages(token, selectedId)

  const { sendJson } = useChatSocket(token, (data) => {
    if (data.type !== 'new_message') return
    const msg = data.message
    if (msg.conversation_id === selectedId) setMessages(prev => [...prev, msg])
    setConversations(prev => {
      const idx = prev.findIndex(c => c.id === msg.conversation_id)
      if (idx === -1) return prev
      const bumpUnread = msg.conversation_id !== selectedId && msg.sender_id !== user?.id
      const updated = { ...prev[idx], last_message: msg, updated_at: msg.created_at, unread_count: bumpUnread ? (prev[idx].unread_count || 0) + 1 : prev[idx].unread_count }
      return [updated, ...prev.slice(0, idx), ...prev.slice(idx + 1)]
    })
  })

  const selectedConversation = conversations.find(c => c.id === selectedId) || null

  const onSelect = (id) => {
    setSelectedId(id)
    setMobileChat(true)
    setConversations(prev => prev.map(c => c.id === id ? { ...c, unread_count: 0 } : c))
    markRead(token, id).catch(() => {})
  }

  const onSend = (content) => { if (selectedId) sendJson({ type: 'send_message', conversation_id: selectedId, content }) }

  const onCreated = (conv) => {
    setConversations(prev => [conv, ...prev.filter(c => c.id !== conv.id)])
    setSelectedId(conv.id)
    setMobileChat(true)
  }

  return (
    <div className={`chat-layout ${mobileChat ? 'show-chat' : ''}`}>
      <ConversationList conversations={conversations} selectedId={selectedId} onSelect={onSelect} onNewConversation={() => setNewConvoOpen(true)} />
      <section className="conversation-pane">
        {selectedConversation ? (
          <>
            <ConversationHeader conversation={selectedConversation} onBack={() => setMobileChat(false)} onAI={() => setAiOpen(true)} />
            <MessageArea conversation={selectedConversation} messages={messages} currentUserId={user?.id} onSend={onSend} />
          </>
        ) : (
          <div className="chat-empty-state"><i className="bi bi-chat-dots" /><p>Select a conversation or start a new one</p></div>
        )}
      </section>
      <AIPanel open={aiOpen} onClose={() => setAiOpen(false)} />
      <NewConversationModal open={newConvoOpen} onClose={() => setNewConvoOpen(false)} onCreated={onCreated} />
    </div>
  )
}
