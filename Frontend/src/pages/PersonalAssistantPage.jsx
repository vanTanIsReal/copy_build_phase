import { useState } from 'react'
import AssistantSessionList from '../components/ai/AssistantSessionList'
import PersonalAIChat from '../components/ai/PersonalAIChat'
import AssistantContextPanel from '../components/ai/AssistantContextPanel'
import ExecutiveBriefCard from '../../user/src/components/agents/executive/ExecutiveBriefCard'

export default function PersonalAssistantPage(){
  const [contextOpen,setContextOpen]=useState(false)
  // Lifted here (not owned by PersonalAIChat) so the left "Gần đây" sidebar and the chat panel stay
  // in sync: clicking a past session sets this, which the chat panel then loads history for.
  const [activeThreadId,setActiveThreadId]=useState(null)
  // Bumped after every completed chat turn so AssistantSessionList re-fetches - a new/updated
  // thread should show up (or move to the top) without a manual page refresh.
  const [threadsVersion,setThreadsVersion]=useState(0)

  return <div className="personal-assistant-layout">
    <AssistantSessionList
      activeThreadId={activeThreadId}
      onSelectThread={setActiveThreadId}
      onNewThread={()=>setActiveThreadId(null)}
      refreshSignal={threadsVersion}
    />
    <main className="personal-assistant-center">
      <ExecutiveBriefCard />
      <PersonalAIChat
        onContext={()=>setContextOpen(true)}
        threadId={activeThreadId}
        onThreadIdChange={setActiveThreadId}
        onActivity={()=>setThreadsVersion(v=>v+1)}
      />
    </main>
    <AssistantContextPanel open={contextOpen} onClose={()=>setContextOpen(false)}/>
  </div>
}
