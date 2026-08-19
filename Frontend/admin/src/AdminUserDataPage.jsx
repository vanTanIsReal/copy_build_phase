import { useEffect, useState } from 'react'
import PageHeader from '../../src/components/common/PageHeader'
import AdminTaskTable from './AdminTaskTable'
import AdminReminderTable from './AdminReminderTable'
import AdminMemoryTable from './AdminMemoryTable'
import ConfirmDialog from '../../src/components/common/ConfirmDialog'
import { useAuth } from '../../src/context/AuthContext'
import { useToast } from '../../src/context/ToastContext'
import {
  listUsers,
  listTasks, deleteTask,
  listReminders, deleteReminder,
  listMemories, deleteMemory,
} from '../../src/api/admin'
import TableRowsSkeleton from '../../src/components/common/TableRowsSkeleton'

const TABS = [
  { key: 'tasks', label: 'Tasks' },
  { key: 'reminders', label: 'Reminders' },
  { key: 'memories', label: 'Memories' },
]

const listFor = { tasks: listTasks, reminders: listReminders, memories: listMemories }
const deleteFor = { tasks: deleteTask, reminders: deleteReminder, memories: deleteMemory }
const confirmLabel = { tasks: 'task', reminders: 'reminder', memories: 'memory' }

export default function AdminUserDataPage() {
  const { token } = useAuth()
  const { pushToast } = useToast()
  const [tab, setTab] = useState('tasks')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [users, setUsers] = useState([])
  const [ownerFilter, setOwnerFilter] = useState('')
  const [pendingDelete, setPendingDelete] = useState(null)

  useEffect(() => { listUsers(token).then(setUsers).catch(() => setUsers([])) }, [token])

  const refresh = () => {
    setLoading(true)
    listFor[tab](token, ownerFilter || undefined).then(setItems).finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [token, tab, ownerFilter])

  const confirmDelete = async () => {
    const item = pendingDelete
    setPendingDelete(null)
    try {
      await deleteFor[tab](token, item.id)
      setItems(list => list.filter(x => x.id !== item.id))
    } catch (err) {
      pushToast(err.detail || 'Could not delete this item.')
    }
  }

  return (
    <div className="page-container">
      <PageHeader eyebrow="Admin" title="User data" description="View and manage any user's tasks, reminders, and memories." />
      <section className="content-card">
        <div className="card-toolbar">
          <div className="btn-group">
            {TABS.map(t => (
              <button key={t.key} className={`btn btn-sm ${tab === t.key ? 'btn-primary' : 'btn-light'}`} onClick={() => setTab(t.key)}>{t.label}</button>
            ))}
          </div>
          <div className="toolbar-actions">
            <select className="form-select form-select-sm" value={ownerFilter} onChange={e => setOwnerFilter(e.target.value)}>
              <option value="">All users</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.display_name} ({u.email})</option>)}
            </select>
          </div>
        </div>
        {loading ? <TableRowsSkeleton /> : (
          <>
            {tab === 'tasks' && <AdminTaskTable tasks={items} onDelete={setPendingDelete} />}
            {tab === 'reminders' && <AdminReminderTable reminders={items} onDelete={setPendingDelete} />}
            {tab === 'memories' && <AdminMemoryTable memories={items} onDelete={setPendingDelete} />}
          </>
        )}
      </section>
      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete item"
        message={`Delete this ${confirmLabel[tab]}? This cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
