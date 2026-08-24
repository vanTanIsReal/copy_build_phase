import { useEffect, useMemo, useState } from 'react'
import PageHeader from '../components/common/PageHeader'
import StatCard from '../components/common/StatCard'
import EmptyState from '../components/fx/EmptyState'
import WorkspaceBriefCard from '../components/agents/WorkspaceBriefCard'
import ActionProposalCard from '../components/agents/ActionProposalCard'
import { useAuth } from '../context/AuthContext'
import { useWorkspace } from '../context/WorkspaceContext'
import { listAvailableAgentWorkspaces } from '../api/workspaces'
import { chatWithAgent, resumeAgent } from '../api/agent'

// Real API-backed successor to the old Frontend/src/pages/WorkspaceBriefsPage.jsx sample-data
// shell (never routed/linked, see docs/ARCHITECTURE.md §16.2). Calls the same /chat endpoint
// Delivery/Quality/Executive already use (src.api.routes._run_specialist_chat) with
// requested_scope=workspace|aggregate - one brief request per Agent Workspace the user belongs to.
const BRIEF_PROFILES = new Set(['product_delivery', 'quality_assurance'])

const profileName = profile => (
  { product_delivery: 'Product Delivery', quality_assurance: 'Quality Assurance' }[profile] || profile
)

export default function WorkspaceBriefsPage() {
  const { token } = useAuth()
  const { workspaces } = useWorkspace()
  const company = useMemo(
    () => workspaces.find(item => item.type === 'organization' && item.slug === 'company-root'),
    [workspaces],
  )

  const [agentWorkspaces, setAgentWorkspaces] = useState([])
  const [loadingWorkspaces, setLoadingWorkspaces] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [briefsByWorkspace, setBriefsByWorkspace] = useState({}) // id -> { status, brief, errorText }
  const [executiveBrief, setExecutiveBrief] = useState(null) // { status, brief, errorText }
  const [pendingProposal, setPendingProposal] = useState(null) // { workspaceId, threadId, proposal }

  useEffect(() => {
    if (!company?.id) {
      setAgentWorkspaces([])
      setLoadingWorkspaces(false)
      return
    }
    setLoadingWorkspaces(true)
    setLoadError('')
    listAvailableAgentWorkspaces(token, company.id)
      .then(setAgentWorkspaces)
      .catch(err => setLoadError(err.detail || 'Could not load your assigned workspaces.'))
      .finally(() => setLoadingWorkspaces(false))
  }, [token, company?.id])

  const briefWorkspaces = useMemo(
    () => agentWorkspaces.filter(ws => BRIEF_PROFILES.has(ws.agent_profile)),
    [agentWorkspaces],
  )

  useEffect(() => {
    briefWorkspaces.forEach(ws => {
      setBriefsByWorkspace(prev => ({ ...prev, [ws.id]: { status: 'loading' } }))
      chatWithAgent(token, {
        message: 'Tóm tắt brief mới nhất',
        requested_scope: 'workspace',
        target_agent_workspace_id: ws.id,
      })
        .then(res => {
          setBriefsByWorkspace(prev => ({
            ...prev,
            [ws.id]: res.status === 'error'
              ? { status: 'error', errorText: res.response }
              : { status: 'ready', brief: res.workspace_brief, threadId: res.thread_id },
          }))
        })
        .catch(err => setBriefsByWorkspace(prev => ({ ...prev, [ws.id]: { status: 'error', errorText: err.detail } })))
    })
    // Executive aggregate - independent of briefWorkspaces (an executive_viewer may have zero
    // Delivery/Quality assignments of their own), attempted once per token/company.
    if (token) {
      setExecutiveBrief({ status: 'loading' })
      chatWithAgent(token, { message: 'Tổng hợp tình hình', requested_scope: 'aggregate' })
        .then(res => {
          setExecutiveBrief(
            res.status === 'error' ? { status: 'error', errorText: res.response } : { status: 'ready', brief: res.workspace_brief },
          )
        })
        .catch(() => setExecutiveBrief(null))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, briefWorkspaces.map(ws => ws.id).join(',')])

  const proposeFollowUpReminder = (ws) => {
    const dueAt = new Date(Date.now() + 24 * 3600 * 1000).toISOString()
    chatWithAgent(token, {
      message: 'Nhắc tôi theo dõi',
      requested_scope: 'workspace',
      target_agent_workspace_id: ws.id,
      specialist_action: { kind: 'propose_reminder', title: `Theo dõi ${ws.name}`, due_at: dueAt },
    }).then(res => {
      if (res.status === 'interrupted' && res.proposal) {
        setPendingProposal({ workspaceId: ws.id, threadId: res.thread_id, proposal: res.proposal })
      }
    })
  }

  const confirmProposal = (approved) => {
    if (!pendingProposal) return
    resumeAgent(token, { thread_id: pendingProposal.threadId, approved }).finally(() => setPendingProposal(null))
  }

  const readyBriefs = Object.values(briefsByWorkspace).filter(entry => entry.status === 'ready')
  const notReadyCount = readyBriefs.filter(entry => entry.brief?.release_readiness === 'NOT_READY').length

  return (
    <div className="page-container">
      <PageHeader
        eyebrow="Multi-agent"
        title="Workspace Briefs"
        description="Delivery, Quality Assurance và Executive brief - dựng từ dữ liệu thật, tôn trọng human-in-the-loop trước mọi hành động."
      />

      {loadError && <div className="auth-error mb-3">{loadError}</div>}

      <div className="stats-grid mb-4">
        <StatCard label="Workspace của bạn" value={briefWorkspaces.length} icon="bi-diagram-3" color="primary" />
        <StatCard label="Brief đã tải" value={readyBriefs.length} icon="bi-file-earmark-bar-graph" color="primary" />
        <StatCard label="Release NOT_READY" value={notReadyCount} icon="bi-exclamation-circle" color={notReadyCount ? 'danger' : 'success'} />
      </div>

      {!loadingWorkspaces && !briefWorkspaces.length && (
        <div className="content-card p-4">
          <EmptyState
            variant="radar"
            icon="bi-diagram-3"
            title="Chưa có workspace nào"
            description="Một admin cần gán bạn vào Product Delivery hoặc Quality Assurance workspace trước."
          />
        </div>
      )}

      <div className="row g-4">
        <div className="col-lg-7">
          <h2 className="h6 text-uppercase text-secondary">Workspace briefs</h2>
          {briefWorkspaces.map(ws => {
            const entry = briefsByWorkspace[ws.id] || { status: 'loading' }
            return (
              <div key={ws.id} className="mb-3">
                <div className="d-flex justify-content-between align-items-center mb-1">
                  <strong>{ws.name}</strong>
                  <small className="text-secondary">{profileName(ws.agent_profile)}</small>
                </div>
                {entry.status === 'loading' && <p className="text-secondary small">Đang tải...</p>}
                {entry.status === 'error' && <div className="auth-error small">{entry.errorText}</div>}
                {entry.status === 'ready' && <>
                  <WorkspaceBriefCard brief={entry.brief} />
                  <button className="btn btn-sm btn-light mb-3" onClick={() => proposeFollowUpReminder(ws)}>
                    <i className="bi bi-bell me-1" />Đề xuất nhắc theo dõi
                  </button>
                </>}
              </div>
            )
          })}

          {executiveBrief?.status === 'ready' && (
            <>
              <h2 className="h6 text-uppercase text-secondary mt-4">Executive</h2>
              <WorkspaceBriefCard brief={executiveBrief.brief} />
            </>
          )}
        </div>

        <div className="col-lg-5">
          <h2 className="h6 text-uppercase text-secondary">Chờ xác nhận (HITL)</h2>
          {pendingProposal
            ? <ActionProposalCard proposal={pendingProposal.proposal} onConfirm={() => confirmProposal(true)} onReject={() => confirmProposal(false)} />
            : <p className="text-secondary small">Không có đề xuất nào đang chờ xác nhận.</p>}
        </div>
      </div>
    </div>
  )
}
