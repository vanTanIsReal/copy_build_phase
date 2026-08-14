import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import ConversationList from '../components/chat/ConversationList'
import ConversationHeader from '../components/chat/ConversationHeader'
import MessageArea from '../components/chat/MessageArea'
import AIPanel from '../components/chat/AIPanel'
import NewConversationModal from '../components/chat/NewConversationModal'
import AddMembersModal from '../components/chat/AddMembersModal'
import { useAuth } from '../context/AuthContext'
import { useConversations } from '../hooks/useConversations'
import { useMessages } from '../hooks/useMessages'
import { deleteConversation, getAiPermission, leaveConversation, markRead, setAiPermission } from '../api/chat'

export default function ChatPage() {
  const { token, user } = useAuth()
  const { sendJson, subscribe } = useOutletContext()
  const [mobileChat, setMobileChat] = useState(false)
  const [aiOpen, setAiOpen] = useState(false)
  const [newConvoOpen, setNewConvoOpen] = useState(false)
  const [addMembersOpen, setAddMembersOpen] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const [aiGranted, setAiGranted] = useState(false)
  const { conversations, setConversations } = useConversations(token)
  const { messages, setMessages } = useMessages(token, selectedId)

  // AI permission is per (conversation, user) on the backend - shared here so the header badge
  // and the AI panel's Grant/Revoke buttons always agree, instead of each fetching/toggling it
  // independently.
  useEffect(() => {
    if (!selectedId) { setAiGranted(false); return }
    let cancelled = false
    getAiPermission(token, selectedId).then(res => { if (!cancelled) setAiGranted(res.granted) }).catch(() => {})
    return () => { cancelled = true }
  }, [selectedId, token])

  const onToggleAi = (next) =>
    setAiPermission(token, selectedId, next).then(res => { setAiGranted(res.granted); return res })

  const stateRef = useRef({ selectedId, userId: user?.id })
  stateRef.current = { selectedId, userId: user?.id }

  useEffect(() => subscribe((data) => {
    if (data.type === 'new_message') {
      const { selectedId, userId } = stateRef.current
      const msg = data.message
      if (msg.conversation_id === selectedId) setMessages(prev => [...prev, msg])
      setConversations(prev => {
        const idx = prev.findIndex(c => c.id === msg.conversation_id)
        if (idx === -1) return prev
        const bumpUnread = msg.conversation_id !== selectedId && msg.sender_id !== userId
        const updated = { ...prev[idx], last_message: msg, updated_at: msg.created_at, unread_count: bumpUnread ? (prev[idx].unread_count || 0) + 1 : prev[idx].unread_count }
        return [updated, ...prev.slice(0, idx), ...prev.slice(idx + 1)]
      })
    }
    // Someone else left a group we're still in - keep the member count/roster in the header and
    // "N members" line accurate without a manual refresh.
    if (data.type === 'conversation_member_left') {
      setConversations(prev => prev.map(c => c.id === data.conversation_id
        ? { ...c, participants: c.participants.filter(p => p.id !== data.user_id) }
        : c))
    }
    if (data.type === 'conversation_members_added') {
      setConversations(prev => {
        const idx = prev.findIndex(c => c.id === data.conversation.id)
        if (idx === -1) return [data.conversation, ...prev]
        return prev.map(c => c.id === data.conversation.id
          ? { ...c, participants: data.conversation.participants }
          : c)
      })
    }
  }), [subscribe, setMessages, setConversations])

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

  const onMembersAdded = conv => setConversations(prev => prev.map(c => c.id === conv.id ? conv : c))

  // Shared by delete (hide-for-me) and leave (real membership removal) - both end the same way on
  // this side: the conversation drops out of the list and, if it was open, the chat pane closes.
  const closeConversation = (id) => {
    setConversations(prev => prev.filter(c => c.id !== id))
    if (id === selectedId) { setSelectedId(null); setMobileChat(false) }
  }

  const onDeleteConversation = () => {
    if (!selectedId) return
    const id = selectedId
    deleteConversation(token, id).then(() => closeConversation(id))
      .catch(err => alert(err.detail || 'Could not delete this conversation.'))
  }

  const onLeaveConversation = () => {
    if (!selectedId) return
    const id = selectedId
    leaveConversation(token, id).then(() => closeConversation(id))
      .catch(err => alert(err.detail || 'Could not leave this group.'))
  }

  return (
    <div className={`chat-layout ${mobileChat ? 'show-chat' : ''}`}>
      <ConversationList conversations={conversations} selectedId={selectedId} onSelect={onSelect} onNewConversation={() => setNewConvoOpen(true)} />
      <section className="conversation-pane">
        {selectedConversation ? (
          <>
            <ConversationHeader conversation={selectedConversation} onBack={() => setMobileChat(false)} onAI={() => setAiOpen(true)} aiGranted={aiGranted} onToggleAi={onToggleAi} onDelete={onDeleteConversation} onLeave={onLeaveConversation} onAddMembers={() => setAddMembersOpen(true)} />
            <MessageArea conversation={selectedConversation} messages={messages} currentUserId={user?.id} onSend={onSend} />
          </>
        ) : (
          <div className="chat-empty-state"><i className="bi bi-chat-dots" /><p>Select a conversation or start a new one</p></div>
        )}
      </section>
      <AIPanel open={aiOpen} onClose={() => setAiOpen(false)} messages={messages} conversationId={selectedId} granted={aiGranted} onToggleGrant={onToggleAi} />
      <NewConversationModal open={newConvoOpen} onClose={() => setNewConvoOpen(false)} onCreated={onCreated} />
      <AddMembersModal conversation={addMembersOpen ? selectedConversation : null} onClose={() => setAddMembersOpen(false)} onAdded={onMembersAdded} />
    </div>
  )
}
