import { useEffect, useState } from 'react'
import PageHeader from '../../src/components/common/PageHeader'
import StatCard from '../../src/components/common/StatCard'
import { useAuth } from '../../src/context/AuthContext'
import { getStats, updateDailyTokenBudget } from '../../src/api/admin'

export default function AdminDashboardPage() {
  const { token } = useAuth()
  const [stats, setStats] = useState(null)
  const [budgetInput, setBudgetInput] = useState('')
  const [savingBudget, setSavingBudget] = useState(false)
  const [budgetError, setBudgetError] = useState('')
  const [budgetSaved, setBudgetSaved] = useState(false)

  const refresh = () => getStats(token).then(s => { setStats(s); setBudgetInput(String(s.daily_token_budget)) }).catch(() => setStats(null))

  useEffect(() => { refresh() }, [token])

  const nearBudget = (stats?.budget_used_pct ?? 0) >= 80

  const saveBudget = async () => {
    const value = Number(budgetInput)
    if (!Number.isInteger(value) || value < 0) { setBudgetError('Enter a whole number ≥ 0 (0 = unlimited).'); return }
    setSavingBudget(true); setBudgetError('')
    try {
      const updated = await updateDailyTokenBudget(token, value)
      setStats(updated)
      setBudgetSaved(true); setTimeout(() => setBudgetSaved(false), 1800)
    } catch (err) { setBudgetError(err.detail || 'Could not update the budget.') }
    finally { setSavingBudget(false) }
  }

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
      <div className="content-card p-3 mt-3">
        <h3 className="h6 mb-1">Daily token budget</h3>
        <p className="text-muted small mb-3">Applies immediately, no server restart needed. 0 means unlimited (never blocks/alerts).</p>
        <div className="d-flex align-items-center gap-2" style={{ maxWidth: 360 }}>
          <input
            type="number" min="0" step="1" className="form-control" value={budgetInput}
            onChange={e => setBudgetInput(e.target.value)} disabled={!stats || savingBudget}
          />
          <button className="btn btn-primary text-nowrap" onClick={saveBudget} disabled={!stats || savingBudget}>
            <i className={`bi ${budgetSaved ? 'bi-check2' : 'bi-floppy'} me-2`}/>{savingBudget ? 'Saving...' : budgetSaved ? 'Saved' : 'Save'}
          </button>
        </div>
        {budgetError && <p className="text-danger small mt-2 mb-0">{budgetError}</p>}
      </div>
    </div>
  )
}
