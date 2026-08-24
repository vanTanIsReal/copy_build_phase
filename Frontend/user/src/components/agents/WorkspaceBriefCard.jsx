// Renders one src.agents.contracts.WorkspaceBrief / ExecutiveBrief (already-validated JSON shape
// from ChatResponse.workspace_brief - see src.api.routes._run_specialist_chat). Pure
// presentational component: no fetch, no state - the caller (WorkspaceBriefsPage) decides where
// the brief data comes from.

const readinessTone = { READY: 'success', AT_RISK: 'warning', NOT_READY: 'danger' }

export default function WorkspaceBriefCard({ brief }) {
  const isQuality = brief.brief_type === 'quality'
  const isStale = brief.expires_at && new Date(brief.expires_at) <= new Date()

  return (
    <article className="workspace-card mb-3">
      <div className="d-flex justify-content-between align-items-start gap-2 mb-2">
        <div className="d-flex align-items-center gap-2 flex-wrap">
          <span className="source-pill text-uppercase">{brief.brief_type}</span>
          {isQuality && brief.release_readiness && (
            <span className={`status-badge ${readinessTone[brief.release_readiness] || 'secondary'}`}>
              {brief.release_readiness}
            </span>
          )}
          {isStale && <span className="status-badge secondary">Stale</span>}
        </div>
        <small className="text-secondary">{new Date(brief.generated_at).toLocaleString('vi-VN')}</small>
      </div>

      <h3 className="h6 mb-2">{brief.headline}</h3>

      {brief.data_gaps?.length > 0 && (
        <div className="reminder-tip py-2 px-3 small mb-2">
          <i className="bi bi-exclamation-triangle" />
          <div>
            <strong>Data gaps</strong>
            <ul className="mb-0 ps-3">
              {brief.data_gaps.map((gap, i) => <li key={i}>{gap}</li>)}
            </ul>
          </div>
        </div>
      )}

      {(brief.facts?.length > 0 || brief.blocked_items?.length > 0) && (
        <div className="small text-secondary">
          {brief.facts?.length || 0} fact(s) · {brief.decisions_needed?.length || 0} decision(s) cần chốt ·{' '}
          {brief.sources?.length || 0} source
        </div>
      )}
    </article>
  )
}
