import Avatar from '../common/Avatar'
import { getInitials, getColor } from '../../utils/avatar'

export default function ConversationHeader({ conversation, onBack, onAI, aiGranted, onToggleAi, onDelete, onLeave }) {
  const handleToggleAi = () => { onToggleAi(!aiGranted).catch(() => {}) }
  const handleDelete = () => {
    if (window.confirm('Delete this conversation? It will be removed from your list, but other participants keep it.')) onDelete()
  }
  const handleLeave = () => {
    if (window.confirm('Leave this group? You will lose access unless someone adds you back.')) onLeave()
  }
  return (
    <header className="conversation-header">
      <button className="icon-btn chat-back" onClick={onBack}><i className="bi bi-arrow-left" /></button>
      <Avatar initials={getInitials(conversation.name)} color={getColor(conversation.id)} size={44} />
      <div className="conversation-meta">
        <div><h3>{conversation.name}</h3><span>{conversation.type === 'group' ? `${conversation.participants.length} members` : 'Direct message'}</span></div>
        <button
          type="button"
          className={`ai-active${aiGranted ? '' : ' off'}`}
          onClick={handleToggleAi}
          title={aiGranted ? 'AI can read this conversation — click to turn off' : 'AI cannot read this conversation — click to turn on'}
        >
          <i className={`bi ${aiGranted ? 'bi-stars' : 'bi-slash-circle'}`} />{aiGranted ? 'AI enabled' : 'AI disabled'}
        </button>
      </div>
      <div className="header-actions">
        <button className="icon-btn"><i className="bi bi-telephone" /></button>
        <button className="icon-btn"><i className="bi bi-camera-video" /></button>
        <button className="icon-btn ai-mobile-btn" onClick={onAI}><i className="bi bi-stars" /></button>
        <div className="dropdown">
          <button className="icon-btn" data-bs-toggle="dropdown" aria-expanded="false"><i className="bi bi-three-dots-vertical" /></button>
          <ul className="dropdown-menu dropdown-menu-end">
            {conversation.type === 'group' && (
              <li><button className="dropdown-item text-danger" onClick={handleLeave}><i className="bi bi-box-arrow-right me-2" />Leave group</button></li>
            )}
            <li><button className="dropdown-item text-danger" onClick={handleDelete}><i className="bi bi-trash me-2" />Delete conversation</button></li>
          </ul>
        </div>
      </div>
    </header>
  )
}
