import { useState } from 'react'
import { motion } from 'framer-motion'
import { useAuth } from '../../context/AuthContext'
import { chatWithAgent } from '../../api/agent'

const actions = [
  ['bi-text-paragraph', 'Summarize', 'Get the key points', '#526ff5'],
  ['bi-check2-square', 'Extract tasks', 'Find action items', '#8b5cf6'],
  ['bi-calendar-event', 'Find schedule', 'Detect events', '#10b981'],
  ['bi-alarm', 'Deadlines', 'Spot due dates', '#f59e0b'],
]

const scopeToCount = { '20 latest messages': 20, '50 latest messages': 50 }

export default function AIPanel({ open, onClose, messages = [] }) {
  const { token } = useAuth()
  const [granted, setGranted] = useState(true)
  const [scope, setScope] = useState('20 latest messages')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState('')
  const [error, setError] = useState('')

  const runSummarize = async () => {
    if (!messages.length) { setError('No messages in this conversation yet.'); setResult(''); return }
    const count = scopeToCount[scope]
    const scoped = count ? messages.slice(-count) : messages
    setRunning(true); setError(''); setResult('')
    try {
      const res = await chatWithAgent(token, {
        message: 'Summarize this conversation.',
        messages: scoped.map(m => ({ role: 'user', sender: m.sender_name, content: m.content, timestamp: m.created_at })),
      })
      setResult(res.response)
    } catch (err) { setError(err.detail || 'Could not summarize this conversation.') }
    finally { setRunning(false) }
  }

  return (
    <><div className={`ai-backdrop ${open ? 'show' : ''}`} onClick={onClose}/><aside className={`ai-panel ${open ? 'open' : ''}`}>
      <div className="ai-panel-header"><div className="ai-title-icon"><i className="bi bi-stars"/></div><div><h3>AI Assistant</h3><span>Context-aware help</span></div><button className="icon-btn ai-close" onClick={onClose}><i className="bi bi-x-lg"/></button></div>
      <div className={`permission-card ${granted ? 'granted' : ''}`}>
        <div className="permission-top"><div><i className={`bi ${granted ? 'bi-shield-check' : 'bi-shield-lock'}`}/></div><span><strong>{granted ? 'Permission granted' : 'Permission required'}</strong><small>{granted ? 'AI can read selected messages' : 'Allow AI to read this conversation'}</small></span>{granted && <span className="live-badge">Active</span>}</div>
        {granted ? <><label>Permission scope</label><select value={scope} onChange={e=>setScope(e.target.value)} className="form-select"><option>20 latest messages</option><option>50 latest messages</option><option>Unread messages</option><option>Today's messages</option><option>Custom time range</option></select><button className="revoke-btn" onClick={()=>setGranted(false)}>Revoke permission</button></> : <button className="btn btn-primary w-100 mt-3" onClick={()=>setGranted(true)}><i className="bi bi-shield-check me-2"/>Grant Permission</button>}
      </div>
      <div className="ai-section-title"><span>Quick actions</span><i className="bi bi-lightning-charge-fill"/></div>
      <div className="quick-grid">{actions.map(([icon,title,sub,color])=><motion.button key={title} whileHover={{y:-2}} whileTap={{scale:.98}} disabled={title==='Summarize' && (!granted || running)} onClick={title==='Summarize' ? runSummarize : undefined}><span style={{color,background:`${color}12`}}><i className={`bi ${title==='Summarize' && running ? 'bi-hourglass-split' : icon}`}/></span><strong>{title}</strong><small>{title==='Summarize' && running ? 'Summarizing...' : sub}</small></motion.button>)}</div>
      {error && <div className="auth-error">{error}</div>}
      {result && <div className="border rounded-3 p-3 mt-2 small"><strong className="d-block mb-1">Summary</strong>{result}</div>}
      <div className="ask-card"><div className="ask-title"><span><i className="bi bi-stars"/></span><div><strong>Ask Orbit</strong><small>About this conversation</small></div></div><textarea placeholder="Ask anything about this conversation..."/><div className="ask-footer"><span>AI may make mistakes</span><button><i className="bi bi-arrow-up"/></button></div></div>
      <div className="suggested-prompts"><span>Try asking</span><button>“What decisions were made today?”</button><button>“Who assigned me tasks?”</button></div>
    </aside></>
  )
}
