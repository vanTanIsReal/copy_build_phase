import { useEffect, useState } from 'react'
import PageHeader from '../../src/components/common/PageHeader'
import UserTable from './UserTable'
import { useAuth } from '../../src/context/AuthContext'
import { useToast } from '../../src/context/ToastContext'
import { listUsers, updateUserRole, updateUserStatus } from '../../src/api/admin'
import TableRowsSkeleton from '../../src/components/common/TableRowsSkeleton'

export default function AdminUsersPage() {
  const { token, user } = useAuth()
  const { pushToast } = useToast()
  const [users, setUsers] = useState([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  // Which user row currently has a Promote/Demote/Lock/Unlock request in flight - disables that
  // row's buttons so an admin can't fire the same security-sensitive action twice while waiting.
  const [pendingId, setPendingId] = useState(null)

  const refresh = () => {
    setLoading(true)
    listUsers(token, search).then(setUsers).finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [token, search])

  const toggleRole = async (u) => {
    setPendingId(u.id)
    try {
      const updated = await updateUserRole(token, u.id, u.role === 'admin' ? 'user' : 'admin')
      setUsers(list => list.map(x => x.id === updated.id ? updated : x))
    } catch (err) {
      pushToast(err.detail || 'Could not change this user\'s role.')
    } finally {
      setPendingId(null)
    }
  }

  const toggleStatus = async (u) => {
    setPendingId(u.id)
    try {
      const updated = await updateUserStatus(token, u.id, !u.is_active)
      setUsers(list => list.map(x => x.id === updated.id ? updated : x))
    } catch (err) {
      pushToast(err.detail || 'Could not change this user\'s status.')
    } finally {
      setPendingId(null)
    }
  }

  return (
    <div className="page-container">
      <PageHeader eyebrow="Admin" title="User management" description="Promote/demote accounts and lock or unlock access." />
      <section className="content-card">
        <div className="card-toolbar">
          <div><h3>All users</h3><span>{users.length} accounts</span></div>
          <div className="toolbar-actions">
            <div className="mini-search"><i className="bi bi-search" /><input placeholder="Search by name or email" value={search} onChange={e => setSearch(e.target.value)} /></div>
          </div>
        </div>
        {loading ? <TableRowsSkeleton cols={5} /> : (
          <UserTable users={users} currentUserId={user?.id} pendingId={pendingId} onToggleRole={toggleRole} onToggleStatus={toggleStatus} />
        )}
      </section>
    </div>
  )
}
