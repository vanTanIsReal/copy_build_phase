import { useEffect, useState } from 'react'
import PageHeader from '../../components/common/PageHeader'
import StatCard from '../../components/common/StatCard'
import { useAuth } from '../../context/AuthContext'
import { getStats } from '../../api/admin'

export default function AdminDashboardPage() {
  const { token } = useAuth()
  const [stats, setStats] = useState(null)

  useEffect(() => { getStats(token).then(setStats).catch(() => setStats(null)) }, [token])

  return (
    <div className="page-container">
      <PageHeader eyebrow="Admin" title="Dashboard" description="Overview of accounts and messaging activity across Orbit." />
      <div className="stats-grid">
        <StatCard label="Total users" value={stats?.total_users ?? '—'} icon="bi-people" />
        <StatCard label="New users (7d)" value={stats?.new_users_last_7_days ?? '—'} icon="bi-person-plus" color="success" />
        <StatCard label="Conversations" value={stats?.total_conversations ?? '—'} icon="bi-chat-dots" color="info" />
        <StatCard label="Messages" value={stats?.total_messages ?? '—'} icon="bi-envelope" color="warning" />
      </div>
    </div>
  )
}
