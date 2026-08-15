import { useState } from 'react'
import Avatar from '../common/Avatar'
import ConfirmDialog from '../common/ConfirmDialog'
import { getInitials, getColor } from '../../utils/avatar'
import { useToast } from '../../context/ToastContext'

export default function ConversationHeader({ conversation, onBack, onAI, aiGranted, onToggleAi, onDelete, onLeave }) {
  const { pushToast } = useToast()
  // 'delete' | 'leave' | null - which ConfirmDialog (if any) is open, replacing raw window.confirm()
  const [confirming, setConfirming] = useState(null)

  const handleToggleAi = () => { onToggleAi(!aiGranted).catch(err => pushToast(err.detail || 'Could not update AI permission.')) }

  const dialogFor = {
    delete: {
      title: 'Delete conversation',
      message: 'Delete this conversation? It will be removed from your list, but other participants keep it.',
      confirmLabel: 'Delete',
      onConfirm: () => { setConfirming(null); onDelete() },
    },
    leave: {
      title: 'Leave group',
      message: 'Leave this group? You will lose access unless someone adds you back.',
      confirmLabel: 'Leave',
      onConfirm: () => { setConfirming(null); onLeave() },
    },
  }

  return (
    <header className="conversation-header">
      <button className="icon-btn chat-back" onClick={onBack} aria-label="Back"><i className="bi bi-arrow-left" /></button>
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
        <button className="icon-btn ai-mobile-btn" onClick={onAI} aria-label="AI panel"><i className="bi bi-stars" /></button>
        <div className="dropdown">
          <button className="icon-btn" data-bs-toggle="dropdown" aria-expanded="false" aria-label="More options"><i className="bi bi-three-dots-vertical" /></button>
          <ul className="dropdown-menu dropdown-menu-end">
            {conversation.type === 'group' && (
              <li><button className="dropdown-item text-danger" onClick={() => setConfirming('leave')}><i className="bi bi-box-arrow-right me-2" />Leave group</button></li>
            )}
            <li><button className="dropdown-item text-danger" onClick={() => setConfirming('delete')}><i className="bi bi-trash me-2" />Delete conversation</button></li>
          </ul>
        </div>
      </div>
      <ConfirmDialog open={!!confirming} onCancel={() => setConfirming(null)} {...(dialogFor[confirming] || {})} />
    </header>
  )
}
