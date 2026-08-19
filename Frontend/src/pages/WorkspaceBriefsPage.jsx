import { useState } from 'react'
import PageHeader from '../components/common/PageHeader'
import StatCard from '../components/common/StatCard'
import { Button } from '../components/ui/button'
import WorkspaceBriefCard from '../components/agents/WorkspaceBriefCard'
import HitlDrawer from '../components/agents/HitlDrawer'

// UI shell for the multi-agent workspace foundation (MULTI_AGENT_IMPLEMENTATION_PLAN.md #12,
// Ngày 3 "WorkspaceBrief và UI skeleton" + design brief Phase 4 "HITL Drawer"). Deliberately
// renders SAMPLE data matching the real backend contract shapes
// (src.agents.contracts.WorkspaceBrief/ExecutiveBrief/ActionProposal), not a live API call: the
// Product Delivery/Quality Assurance/Executive agents are not wired into any HTTP route yet (see
// docs/MULTI_AGENT_PROGRESS.md) - this page exists to prove the render states (status cards, brief
// cards, data-gap warnings, stale badge, HITL diff/approve/reject) work against the real contract
// shape, ready to be pointed at a real endpoint once one exists. Not linked from Sidebar -
// reachable only by URL - so it doesn't present as a finished feature to real users.

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

// A create-type proposal (propose_delivery_reminder's real shape) - no prior state, HitlDrawer
// shows "—" on the Trước side for every field.
const SAMPLE_CREATE_PROPOSAL = {
  action: 'preview_delivery_reminder',
  payload: { title: 'Nhắc team xử lý blocker trước 5h chiều', due_at: new Date(Date.now() + 3 * 3600 * 1000).toISOString(), message: '' },
  expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
}

// An update-type proposal (the design brief's own example - "đổi status bug") with a real
// Trước/Sau diff. No propose_* tool in this codebase drafts this shape yet (only create-type
// reminder/meeting previews exist today) - included so HitlDrawer's diff rendering has a real
// case to prove against, not just the all-"—" create case.
const SAMPLE_UPDATE_PROPOSAL = {
  action: 'preview_quality_status_change',
  payload: { title: 'Crash on save', severity: 'critical', quality_status: 'passed' },
  expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
}
const SAMPLE_UPDATE_BEFORE = { title: 'Crash on save', severity: 'critical', quality_status: 'open' }

export default function WorkspaceBriefsPage() {
  const [activeProposal, setActiveProposal] = useState(null)

  const openDrawer = (proposal, beforePayload = null) => setActiveProposal({ proposal, beforePayload })

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
        <StatCard label="Pending HITL" value="2" icon="bi-hourglass-split" color="warning" />
      </div>

      <div className="row g-4">
        <div className="col-lg-6">
          <h2 className="h6 text-uppercase text-muted">Workspace briefs</h2>
          <WorkspaceBriefCard brief={SAMPLE_DELIVERY_BRIEF} />
          <WorkspaceBriefCard brief={SAMPLE_QUALITY_BRIEF} />
        </div>
        <div className="col-lg-6">
          <h2 className="h6 text-uppercase text-muted">Chờ xác nhận (HITL)</h2>
          <p className="text-muted small">
            Mọi hành động có tác dụng phụ mở một Drawer riêng thay vì thẻ nhỏ (design brief Phase 4)
            - có so sánh Trước/Sau trước khi bấm Approve.
          </p>
          <div className="d-flex gap-2 flex-wrap">
            <Button onClick={() => openDrawer(SAMPLE_CREATE_PROPOSAL)}>Xem đề xuất: Nhắc nhở mới</Button>
            <Button variant="outline" onClick={() => openDrawer(SAMPLE_UPDATE_PROPOSAL, SAMPLE_UPDATE_BEFORE)}>
              Xem đề xuất: Đổi status bug
            </Button>
          </div>
        </div>
      </div>

      <HitlDrawer
        proposal={activeProposal?.proposal}
        beforePayload={activeProposal?.beforePayload}
        open={!!activeProposal}
        onOpenChange={(open) => !open && setActiveProposal(null)}
        onApprove={(p) => console.info('approved (demo, no live executor call)', p)}
        onReject={(p) => console.info('rejected (demo, no live executor call)', p)}
      />
    </div>
  )
}
