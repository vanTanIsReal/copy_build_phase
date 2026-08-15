import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import ConversationList from '../components/chat/ConversationList'
import ConversationHeader from '../components/chat/ConversationHeader'
import MessageArea from '../components/chat/MessageArea'
import AIPanel from '../components/chat/AIPanel'
import NewConversationModal from '../components/chat/NewConversationModal'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { useConversations } from '../hooks/useConversations'
import { useMessages } from '../hooks/useMessages'
import { deleteConversation, getAiPermission, leaveConversation, markRead, setAiPermission } from '../api/chat'

export default function ChatPage() {
  const { token, user } = useAuth()
  const { pushToast } = useToast()
  const { sendJson, subscribe } = useOutletContext()
  const [mobileChat, setMobileChat] = useState(false)
  const [aiOpen, setAiOpen] = useState(false)
  const [newConvoOpen, setNewConvoOpen] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const [aiGranted, setAiGranted] = useState(false)
  // Snapshot of the selected conversation's unread_count, taken in onSelect BEFORE it's zeroed
  // locally below - sizes useMessages's initial fetch so the "jump to unread" boundary is covered.
  const [unreadHint, setUnreadHint] = useState(0)
  const { conversations, setConversations } = useConversations(token)
  const { messages, setMessages, loading: messagesLoading, firstUnreadMessageId, unreadCount } = useMessages(token, selectedId, unreadHint)

  // AI permission is per (conversation, user) on the backend - shared here so the header badge
  // and the AI panel's Grant/Revoke buttons always agree, instead of each fetching/toggling it
  // independently.
  useEffect(() => {
    if (!selectedId) { setAiGranted(false); return }
    let cancelled = false
    getAiPermission(token, selectedId).then(res => { if (!cancelled) setAiGranted(res.granted) }).catch(() => {})
    return () => { cancelled = true }
  }, [selectedId, token])

  // Shared by the header pill, the AI panel's Grant/Revoke button, AND the new per-row toggle in
  // ConversationList - one place updates both the open conversation's aiGranted and the matching
  // row in `conversations`, so all three stay in sync no matter which one triggered the change.
  const toggleAiPermission = (id, next) =>
    setAiPermission(token, id, next).then(res => {
      setConversations(prev => prev.map(c => c.id === id ? { ...c, ai_permission_granted: res.granted } : c))
      if (id === selectedId) setAiGranted(res.granted)
      return res
    })

  const onToggleAi = (next) => toggleAiPermission(selectedId, next)
  const onToggleAiInList = (id, next) =>
    toggleAiPermission(id, next).catch(err => pushToast(err.detail || 'Could not update AI permission.'))

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
  }), [subscribe, setMessages, setConversations])

  const selectedConversation = conversations.find(c => c.id === selectedId) || null

  const onSelect = (id) => {
    setSelectedId(id)
    setMobileChat(true)
    setUnreadHint(conversations.find(c => c.id === id)?.unread_count || 0)
    setConversations(prev => prev.map(c => c.id === id ? { ...c, unread_count: 0 } : c))
    // markRead is called once messages (and the first-unread marker) have actually loaded for
    // this conversation - see the effect below. Calling it here, immediately, would race the
    // GET /messages call that reads the same last_read_at this is about to overwrite.
  }

  // Marks the conversation read only after its messages have finished loading - not in onSelect
  // above - so GET /messages's first_unread_message_id (computed from last_read_at) is guaranteed
  // to reflect the state from *before* this call overwrites it, no race either way.
  const markedReadRef = useRef(null)
  useEffect(() => {
    if (!selectedId || messagesLoading) return
    if (markedReadRef.current === selectedId) return
    markedReadRef.current = selectedId
    markRead(token, selectedId).catch(() => {})
  }, [selectedId, messagesLoading, token])

  const onSend = (content) => { if (selectedId) sendJson({ type: 'send_message', conversation_id: selectedId, content }) }

  const onCreated = (conv) => {
    setConversations(prev => [conv, ...prev.filter(c => c.id !== conv.id)])
    setSelectedId(conv.id)
    setMobileChat(true)
  }

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
      .catch(err => pushToast(err.detail || 'Could not delete this conversation.'))
  }

  const onLeaveConversation = () => {
    if (!selectedId) return
    const id = selectedId
    leaveConversation(token, id).then(() => closeConversation(id))
      .catch(err => pushToast(err.detail || 'Could not leave this group.'))
  }

  return (
    <div className={`chat-layout ${mobileChat ? 'show-chat' : ''}`}>
      <ConversationList conversations={conversations} selectedId={selectedId} onSelect={onSelect} onNewConversation={() => setNewConvoOpen(true)} onToggleAi={onToggleAiInList} />
      <section className="conversation-pane">
        {selectedConversation ? (
          <>
            <ConversationHeader conversation={selectedConversation} onBack={() => setMobileChat(false)} onAI={() => setAiOpen(true)} aiGranted={aiGranted} onToggleAi={onToggleAi} onDelete={onDeleteConversation} onLeave={onLeaveConversation} />
            <MessageArea conversation={selectedConversation} messages={messages} currentUserId={user?.id} onSend={onSend} loading={messagesLoading} firstUnreadMessageId={firstUnreadMessageId} unreadCount={unreadCount} />
          </>
        ) : (
          <div className="chat-empty-state"><i className="bi bi-chat-dots" /><p>Select a conversation or start a new one</p></div>
        )}
      </section>
      <AIPanel open={aiOpen} onClose={() => setAiOpen(false)} messages={messages} conversationId={selectedId} granted={aiGranted} onToggleGrant={onToggleAi} />
      <NewConversationModal open={newConvoOpen} onClose={() => setNewConvoOpen(false)} onCreated={onCreated} />
    </div>
  )
}
