import PageHeader from '../components/common/PageHeader'
import StatCard from '../components/common/StatCard'
import WorkspaceBriefCard from '../components/agents/WorkspaceBriefCard'
import ActionProposalCard from '../components/agents/ActionProposalCard'

// UI shell for the multi-agent workspace foundation (MULTI_AGENT_IMPLEMENTATION_PLAN.md #12,
// Ngày 3 "WorkspaceBrief và UI skeleton"). Deliberately renders SAMPLE data matching the real
// backend contract shapes (src.agents.contracts.WorkspaceBrief/ExecutiveBrief/ActionProposal),
// not a live API call: the Product Delivery/Quality Assurance/Executive agents are not wired into
// any HTTP route yet (see docs/MULTI_AGENT_PROGRESS.md) - this page exists to prove the render
// states (status cards, brief cards, data-gap warnings, stale badge, HITL approve/reject) work
// against the real contract shape, ready to be pointed at a real endpoint once one exists. Not
// linked from Sidebar - reachable only by URL - so it doesn't present as a finished feature to
// real users.

const SAMPLE_DELIVERY_BRIEF = {
  brief_type: 'delivery',
  headline: 'Delivery: 1 task đang blocked, cần xử lý trước khi tiếp tục.',
  generated_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 24 * 3600 * 1000).toISOString(),
  facts: [{ id: 't1' }],
  decisions_needed: [],
  data_gaps: ['Milestone tracking is not yet modeled beyond Task.', 'Cross-workspace dependency tracking is not yet modeled.'],
  sources: [{ resource_id: 't1' }],
}

const SAMPLE_QUALITY_BRIEF = {
  brief_type: 'quality',
  release_readiness: 'NOT_READY',
  headline: 'Release NOT_READY: 1 critical bug còn mở.',
  generated_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 24 * 3600 * 1000).toISOString(),
  facts: [{ id: 'bug-1' }],
  decisions_needed: [],
  data_gaps: [],
  sources: [{ resource_id: 'bug-1' }],
}

const SAMPLE_PROPOSAL = {
  action: 'preview_delivery_reminder',
  payload: { title: 'Nhắc team xử lý blocker trước 5h chiều', due_at: new Date(Date.now() + 3 * 3600 * 1000).toISOString() },
  expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
}

export default function WorkspaceBriefsPage() {
  return (
    <div className="page-section">
      <PageHeader
        eyebrow="Multi-agent workspace (demo)"
        title="Delivery / Quality / Executive briefs"
        description="Bản demo render shape thật của WorkspaceBrief/ActionProposal - chưa nối API thật (xem docs/MULTI_AGENT_PROGRESS.md)."
      />

      <div className="stat-grid mb-4">
        <StatCard label="Delivery brief" value="1" icon="bi-kanban" color="primary" note="last 7 ngày" />
        <StatCard label="Quality brief" value="1" icon="bi-shield-check" color="danger" note="NOT_READY" />
        <StatCard label="Pending HITL" value="1" icon="bi-hourglass-split" color="warning" />
      </div>

      <div className="row g-4">
        <div className="col-lg-6">
          <h2 className="h6 text-uppercase text-muted">Workspace briefs</h2>
          <WorkspaceBriefCard brief={SAMPLE_DELIVERY_BRIEF} />
          <WorkspaceBriefCard brief={SAMPLE_QUALITY_BRIEF} />
        </div>
        <div className="col-lg-6">
          <h2 className="h6 text-uppercase text-muted">Chờ xác nhận (HITL)</h2>
          <ActionProposalCard
            proposal={SAMPLE_PROPOSAL}
            onConfirm={(p) => console.info('confirmed (demo, no live executor call)', p)}
            onReject={(p) => console.info('rejected (demo, no live executor call)', p)}
          />
        </div>
      </div>
    </div>
  )
}
