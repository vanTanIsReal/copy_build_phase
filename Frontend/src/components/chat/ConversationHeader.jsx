import Avatar from '../common/Avatar'
import { getInitials, getColor } from '../../utils/avatar'

export default function ConversationHeader({ conversation, aiAllowed, onAiConsentChange, onBack, onAI }) {
  return (
    <header className="conversation-header">
      <button className="icon-btn chat-back" onClick={onBack}><i className="bi bi-arrow-left" /></button>
      <Avatar initials={getInitials(conversation.name)} color={getColor(conversation.id)} size={44} />
      <div className="conversation-meta"><div><h3>{conversation.name}</h3><span>{conversation.type === 'group' ? `${conversation.participants.length} members` : 'Direct message'}</span></div></div>
      <label className={`ai-consent-toggle ${aiAllowed ? 'enabled' : ''}`} title="Control whether AI can read this conversation">
        <span className="ai-consent-copy"><i className={`bi ${aiAllowed ? 'bi-shield-check' : 'bi-shield-lock'}`} /><span><strong>AI access</strong><small>{aiAllowed ? 'AI can read this chat' : 'Allow AI to read'}</small></span></span>
        <input type="checkbox" checked={aiAllowed} onChange={e => onAiConsentChange(e.target.checked)} aria-label="Allow AI to read this conversation" />
        <span className="ai-consent-track" aria-hidden="true"><span /></span>
      </label>
      <div className="header-actions"><button className="icon-btn"><i className="bi bi-telephone" /></button><button className="icon-btn"><i className="bi bi-camera-video" /></button><button className="icon-btn ai-mobile-btn" onClick={onAI}><i className="bi bi-stars" /></button><button className="icon-btn"><i className="bi bi-three-dots-vertical" /></button></div>
    </header>
  )
}
