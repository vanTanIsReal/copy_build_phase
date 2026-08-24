import { useState } from 'react'

// Renders one src.agents.contracts.ActionProposal (a specialist agent's draft side effect,
// awaiting human confirmation - the HITL step required for every propose_* tool, see
// src/agents/hitl_executor.py). Reads ChatResponse.proposal (action/expires_at/proposal_id -
// InterruptPayload.draft alone doesn't carry these). onConfirm/onReject are caller-supplied - this
// component only renders the proposal and reports the decision, it never calls /chat/resume itself.
export default function ActionProposalCard({ proposal, onConfirm, onReject }) {
  const [decision, setDecision] = useState(null) // null | 'confirmed' | 'rejected'
  const expired = new Date(proposal.expires_at) <= new Date()

  const confirm = () => { setDecision('confirmed'); onConfirm?.(proposal) }
  const reject = () => { setDecision('rejected'); onReject?.(proposal) }

  return (
    <article className="suggestion-card mb-3">
      <div className="flex-grow-1">
        <div className="d-flex justify-content-between align-items-start gap-2 mb-2">
          <span className="soft-badge warning"><i />Chờ xác nhận</span>
          <small className="text-secondary">Hết hạn: {new Date(proposal.expires_at).toLocaleTimeString('vi-VN')}</small>
        </div>
        <h4 className="mb-2">{proposal.action}</h4>
        <pre className="brief-payload-preview mb-3">{JSON.stringify(proposal.payload, null, 2)}</pre>

        {decision === null && !expired && (
          <div className="suggestion-actions">
            <button className="btn btn-sm btn-primary" onClick={confirm}>Approve</button>
            <button className="btn btn-sm btn-light" onClick={reject}>Reject</button>
          </div>
        )}
        {decision === 'confirmed' && <span className="status-badge success">Đã xác nhận</span>}
        {decision === 'rejected' && <span className="status-badge secondary">Đã từ chối</span>}
        {decision === null && expired && <span className="status-badge danger">Đã hết hạn</span>}
      </div>
    </article>
  )
}
