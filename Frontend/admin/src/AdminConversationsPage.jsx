import { useEffect, useState } from 'react'
import PageHeader from '../../src/components/common/PageHeader'
import ConversationTable from './ConversationTable'
import ConversationMessagesModal from './ConversationMessagesModal'
import ConfirmDialog from '../../src/components/common/ConfirmDialog'
import { useAuth } from '../../src/context/AuthContext'
import { useToast } from '../../src/context/ToastContext'
import { listConversations, deleteConversation } from '../../src/api/admin'
import TableRowsSkeleton from '../../src/components/common/TableRowsSkeleton'

export default function AdminConversationsPage() {
  const { token } = useAuth()
  const { pushToast } = useToast()
  const [conversations, setConversations] = useState([])
  const [loading, setLoading] = useState(true)
  const [viewing, setViewing] = useState(null)
  const [pendingDelete, setPendingDelete] = useState(null)

  const refresh = () => {
    setLoading(true)
    listConversations(token).then(setConversations).finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [token])

  const confirmDelete = async () => {
    const c = pendingDelete
    setPendingDelete(null)
    try {
      await deleteConversation(token, c.id)
      setConversations(list => list.filter(x => x.id !== c.id))
    } catch (err) {
      pushToast(err.detail || 'Could not delete this conversation.')
    }
  }

  return (
    <div className="page-container">
      <PageHeader eyebrow="Admin" title="Conversations" description="Review and moderate 1-1 and group conversations." />
      <section className="content-card">
        <div className="card-toolbar"><div><h3>All conversations</h3><span>{conversations.length} conversations</span></div></div>
        {loading ? <TableRowsSkeleton /> : (
          <ConversationTable conversations={conversations} onView={setViewing} onDelete={setPendingDelete} />
        )}
      </section>
      <ConversationMessagesModal conversation={viewing} onClose={() => setViewing(null)} />
      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete conversation"
        message="Delete this conversation? This removes all its messages permanently."
        confirmLabel="Delete"
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
