import { useEffect, useState } from 'react'
import PageHeader from '../../components/common/PageHeader'
import StatCard from '../../components/common/StatCard'
import { useAuth } from '../../context/AuthContext'
import { getStats } from '../../api/admin'

export default function AdminDashboardPage() {
  const { token } = useAuth()
  const [stats, setStats] = useState(null)

  useEffect(() => { getStats(token).then(setStats).catch(() => setStats(null)) }, [token])

  const nearBudget = (stats?.budget_used_pct ?? 0) >= 80

  return (
    <div className="page-container">
      <PageHeader eyebrow="Admin" title="Dashboard" description="Overview of accounts and messaging activity across Orbit." />
      {nearBudget && <div className="auth-error mb-3"><i className="bi bi-exclamation-triangle me-2"/>AI token usage today is at {stats.budget_used_pct}% of the daily budget ({stats.tokens_used_today.toLocaleString()} / {stats.daily_token_budget.toLocaleString()} tokens).</div>}
      <div className="stats-grid">
        <StatCard label="Total users" value={stats?.total_users ?? '—'} icon="bi-people" />
        <StatCard label="New users (7d)" value={stats?.new_users_last_7_days ?? '—'} icon="bi-person-plus" color="success" />
        <StatCard label="Conversations" value={stats?.total_conversations ?? '—'} icon="bi-chat-dots" color="info" />
        <StatCard label="Messages" value={stats?.total_messages ?? '—'} icon="bi-envelope" color="warning" />
        <StatCard label="AI tokens used today" value={stats?.tokens_used_today?.toLocaleString() ?? '—'} icon="bi-cpu" color={nearBudget ? 'danger' : 'primary'} note={stats ? `${stats.budget_used_pct}% of ${stats.daily_token_budget.toLocaleString()} budget` : ''} />
        <StatCard label="AI requests today" value={stats?.requests_today ?? '—'} icon="bi-stars" color="info" />
      </div>
    </div>
  )
}
