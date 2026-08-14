import { useEffect, useState } from 'react'
import { addConversationMembers, listUsers } from '../../api/chat'
import { useAuth } from '../../context/AuthContext'
import Avatar from '../common/Avatar'
import { getColor, getInitials } from '../../utils/avatar'

export default function AddMembersModal({ conversation, onClose, onAdded }) {
  const { token } = useAuth()
  const [users, setUsers] = useState([])
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const memberIds = new Set(conversation?.participants.map(p => p.id) || [])

  useEffect(() => {
    if (!conversation) return
    listUsers(token, search).then(items => setUsers(items.filter(u => !memberIds.has(u.id)))).catch(() => setUsers([]))
  }, [conversation, search, token])

  if (!conversation) return null
  const toggle = id => setSelected(value => value.includes(id) ? value.filter(item => item !== id) : [...value, id])
  const submit = async e => {
    e.preventDefault()
    if (!selected.length) return
    setSubmitting(true); setError('')
    try {
      const updated = await addConversationMembers(token, conversation.id, selected)
      onAdded(updated)
      onClose()
    } catch (err) { setError(err.detail || 'Could not add members') }
    finally { setSubmitting(false) }
  }

  return <div className="modal show d-block" tabIndex="-1" style={{ background: 'rgba(20,30,50,.32)' }} onClick={onClose}>
    <div className="modal-dialog modal-dialog-centered" onClick={e => e.stopPropagation()}><div className="modal-content">
      <div className="modal-header"><h5 className="modal-title">Add members to {conversation.name}</h5><button className="btn-close" onClick={onClose} /></div>
      <form onSubmit={submit}><div className="modal-body">
        {error && <div className="auth-error">{error}</div>}
        <input className="form-control mb-3" placeholder="Search people..." value={search} onChange={e => setSearch(e.target.value)} autoFocus />
        <div className="d-flex flex-column gap-2" style={{ maxHeight: 260, overflowY: 'auto' }}>
          {users.map(u => <label key={u.id} className="d-flex align-items-center gap-2" style={{ cursor: 'pointer' }}>
            <input type="checkbox" checked={selected.includes(u.id)} onChange={() => toggle(u.id)} />
            <Avatar initials={getInitials(u.display_name)} color={getColor(u.id)} size={32} />
            <span>{u.display_name}<small className="d-block text-muted">{u.email}</small></span>
          </label>)}
          {!users.length && <p className="text-muted small mb-0">Everyone is already in this group, or no user matched.</p>}
        </div>
      </div><div className="modal-footer">
        <button type="button" className="btn btn-light" onClick={onClose}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={submitting || !selected.length}>{submitting ? 'Adding...' : 'Add members'}</button>
      </div></form>
    </div></div>
  </div>
}
