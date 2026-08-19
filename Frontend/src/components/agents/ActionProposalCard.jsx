import { useState } from 'react'

// Renders one src.agents.contracts.ActionProposal (a specialist agent's draft side effect,
// awaiting human confirmation - the HITL step required for every propose_* tool, see
// src/agents/hitl_executor.py). onConfirm/onReject are caller-supplied - this component only
// renders the proposal and reports the decision, it never calls the executor itself.
export default function ActionProposalCard({ proposal, onConfirm, onReject }) {
  const [decision, setDecision] = useState(null) // null | 'confirmed' | 'rejected'
  const expired = new Date(proposal.expires_at) <= new Date()

  const confirm = () => { setDecision('confirmed'); onConfirm?.(proposal) }
  const reject = () => { setDecision('rejected'); onReject?.(proposal) }

  return (
    <div className="card mb-3 border-warning-subtle">
      <div className="card-body">
        <div className="d-flex justify-content-between align-items-start">
          <span className="badge text-bg-warning-subtle text-warning-emphasis mb-2">Chờ xác nhận</span>
          <small className="text-muted">Hết hạn: {new Date(proposal.expires_at).toLocaleTimeString('vi-VN')}</small>
        </div>
        <p className="mb-2"><strong>{proposal.action}</strong></p>
        <pre className="small bg-light-subtle p-2 rounded mb-3">{JSON.stringify(proposal.payload, null, 2)}</pre>

        {decision === null && !expired && (
          <div className="d-flex gap-2">
            <button className="btn btn-success btn-sm" onClick={confirm}>Approve</button>
            <button className="btn btn-outline-danger btn-sm" onClick={reject}>Reject</button>
          </div>
        )}
        {decision === 'confirmed' && <span className="badge text-bg-success">Đã xác nhận</span>}
        {decision === 'rejected' && <span className="badge text-bg-secondary">Đã từ chối</span>}
        {decision === null && expired && <span className="badge text-bg-danger">Đã hết hạn</span>}
      </div>
    </div>
  )
}
