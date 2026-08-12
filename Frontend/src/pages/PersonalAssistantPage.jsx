import { useState } from 'react'
import AssistantSessionList from '../components/ai/AssistantSessionList'
import PersonalAIChat from '../components/ai/PersonalAIChat'
import AssistantContextPanel from '../components/ai/AssistantContextPanel'

export default function PersonalAssistantPage(){const [contextOpen,setContextOpen]=useState(false);return <div className="personal-assistant-layout"><AssistantSessionList/><PersonalAIChat onContext={()=>setContextOpen(true)}/><AssistantContextPanel open={contextOpen} onClose={()=>setContextOpen(false)}/></div>}
