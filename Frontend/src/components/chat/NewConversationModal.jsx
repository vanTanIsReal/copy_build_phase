import { useEffect, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { listUsers, listGroups, createConversation, joinConversation } from '../../api/chat'
import Avatar from '../common/Avatar'
import { getInitials, getColor } from '../../utils/avatar'

export default function NewConversationModal({ open, onClose, onCreated }) {
  const { token } = useAuth()
  const [mode, setMode] = useState('people')
  const [users, setUsers] = useState([])
  const [groups, setGroups] = useState([])
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState([])
  const [groupName, setGroupName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    if (mode === 'people') {
      listUsers(token, search).then(setUsers).catch(() => setUsers([]))
    } else {
      listGroups(token, search).then(data => setGroups(data.groups)).catch(() => setGroups([]))
    }
  }, [open, search, mode, token])

  useEffect(() => { if (!open) { setMode('people'); setSelected([]); setGroupName(''); setSearch(''); setError('') } }, [open])

  if (!open) return null

  const toggle = (id) => setSelected(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])

  const submit = async (e) => {
    e.preventDefault()
    if (!selected.length) return
    if (selected.length > 1 && !groupName.trim()) { setError('Group name is required'); return }
    setSubmitting(true); setError('')
    try {
      const conv = await createConversation(token, {
        type: selected.length > 1 ? 'group' : 'direct',
        participant_ids: selected,
        name: selected.length > 1 ? groupName.trim() : undefined,
      })
      onCreated(conv)
      onClose()
    } catch (err) { setError(err.detail || 'Could not start conversation') }
    finally { setSubmitting(false) }
  }

  const switchMode = (nextMode) => {
    setMode(nextMode)
    setSelected([])
    setGroupName('')
    setSearch('')
    setError('')
  }

  const openGroup = (group) => {
    onCreated(group)
    onClose()
  }

  const joinGroup = async (group) => {
    setSubmitting(true)
    setError('')
    try {
      const conversation = await joinConversation(token, group.id)
      openGroup(conversation)
    } catch (err) { setError(err.detail || 'Could not join group') }
    finally { setSubmitting(false) }
  }

  return (
    <div className="modal show d-block" tabIndex="-1" style={{ background: 'rgba(20,30,50,.32)' }} onClick={onClose}>
      <div className="modal-dialog modal-dialog-centered" onClick={e => e.stopPropagation()}>
        <div className="modal-content">
          <div className="modal-header"><h5 className="modal-title">Find people or groups</h5><button className="btn-close" onClick={onClose} /></div>
          <form onSubmit={submit}>
            <div className="modal-body">
              {error && <div className="auth-error">{error}</div>}
              <div className="directory-tabs" role="tablist" aria-label="Search directory">
                <button type="button" className={mode === 'people' ? 'active' : ''} onClick={() => switchMode('people')}><i className="bi bi-person" />People</button>
                <button type="button" className={mode === 'groups' ? 'active' : ''} onClick={() => switchMode('groups')}><i className="bi bi-people" />Groups</button>
              </div>
              <input className="form-control mb-3" placeholder={mode === 'people' ? 'Search people...' : 'Search groups...'} value={search} onChange={e => setSearch(e.target.value)} />
              {mode === 'people' ? <>
                {selected.length > 1 && (
                  <input className="form-control mb-3" placeholder="Group name" value={groupName} onChange={e => setGroupName(e.target.value)} />
                )}
                <div className="d-flex flex-column gap-2" style={{ maxHeight: 260, overflowY: 'auto' }}>
                  {users.map(u => (
                    <label key={u.id} className="d-flex align-items-center gap-2" style={{ cursor: 'pointer' }}>
                      <input type="checkbox" checked={selected.includes(u.id)} onChange={() => toggle(u.id)} />
                      <Avatar initials={getInitials(u.display_name)} color={getColor(u.id)} size={32} />
                      <span>{u.display_name}<small className="d-block text-muted">{u.email}</small></span>
                    </label>
                  ))}
                  {!users.length && <p className="text-muted small mb-0">No users found.</p>}
                </div>
              </> : (
                <div className="directory-group-list">
                  {groups.map(group => (
                    <div className="directory-group" key={group.id}>
                      <Avatar initials={getInitials(group.name)} color={getColor(group.id)} size={36} />
                      <span className="directory-group-info"><strong>{group.name}</strong><small>{group.member_count} members{group.is_member ? ' · Joined' : ''}</small><span>{group.last_message?.content || 'No messages yet'}</span></span>
                      <button type="button" className={`btn btn-sm ${group.is_member ? 'btn-light' : 'btn-primary'}`} disabled={submitting} onClick={() => joinGroup(group)}>{group.is_member ? 'Open' : 'Join'}</button>
                    </div>
                  ))}
                  {!groups.length && <p className="text-muted small mb-0">No groups found.</p>}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-light" onClick={onClose}>Cancel</button>
              {mode === 'people' && <button type="submit" className="btn btn-primary" disabled={submitting || !selected.length}>
                {submitting ? 'Starting...' : 'Start conversation'}
              </button>}
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
