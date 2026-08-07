import { useState } from 'react'
import AssistantSessionList, { INITIAL_SESSIONS } from '../components/ai/AssistantSessionList'
import PersonalAIChat from '../components/ai/PersonalAIChat'
import AssistantContextPanel from '../components/ai/AssistantContextPanel'

export default function PersonalAssistantPage() {
  const [contextOpen, setContextOpen] = useState(false)
  const [activeSessionId, setActiveSessionId] = useState(1)
  const [messages, setMessages] = useState(INITIAL_SESSIONS[0].messages)
  const [threadId, setThreadId] = useState(null)

  const handleSelectSession = (session) => {
    setActiveSessionId(session.id)
    setMessages(session.messages || [])
    setThreadId(null)
  }

  const handleNewSession = () => {
    setActiveSessionId(null)
    setMessages([])
    setThreadId(null)
  }

  return (
    <div className="personal-assistant-layout">
      <AssistantSessionList
        activeId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
      />
      <PersonalAIChat
        messages={messages}
        setMessages={setMessages}
        threadId={threadId}
        setThreadId={setThreadId}
        onContext={() => setContextOpen(true)}
        onNewSession={handleNewSession}
      />
      <AssistantContextPanel open={contextOpen} onClose={() => setContextOpen(false)} />
    </div>
  )
}

