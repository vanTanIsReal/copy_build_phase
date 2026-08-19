// Renders one src.agents.contracts.WorkspaceBrief / ExecutiveBrief (already-validated JSON shape
// from the backend contract - not a free-form object). Pure presentational component: no fetch,
// no state - the caller decides where the brief data comes from. See WorkspaceBriefsPage.jsx for
// why this only renders sample data today (no /chat wiring yet for the specialist agents).

const readinessTone = { READY: 'success', AT_RISK: 'warning', NOT_READY: 'danger' }

export default function WorkspaceBriefCard({ brief }) {
  const isQuality = brief.brief_type === 'quality'
  const isStale = brief.expires_at && new Date(brief.expires_at) <= new Date()

  return (
    <div className="card mb-3">
      <div className="card-body">
        <div className="d-flex justify-content-between align-items-start gap-2 mb-2">
          <div>
            <span className="badge text-bg-secondary text-uppercase me-2">{brief.brief_type}</span>
            {isQuality && brief.release_readiness && (
              <span className={`badge text-bg-${readinessTone[brief.release_readiness] || 'secondary'} me-2`}>
                {brief.release_readiness}
              </span>
            )}
            {isStale && <span className="badge text-bg-warning">Stale</span>}
          </div>
          <small className="text-muted">{new Date(brief.generated_at).toLocaleString('vi-VN')}</small>
        </div>

        <h5 className="card-title">{brief.headline}</h5>

        {brief.data_gaps?.length > 0 && (
          <div className="alert alert-warning py-2 px-3 small mb-2">
            <strong>Data gaps:</strong>
            <ul className="mb-0 ps-3">
              {brief.data_gaps.map((gap, i) => <li key={i}>{gap}</li>)}
            </ul>
          </div>
        )}

        {(brief.facts?.length > 0 || brief.blocked_items?.length > 0) && (
          <div className="small text-muted mb-1">
            {brief.facts?.length || 0} fact(s) · {brief.decisions_needed?.length || 0} decision(s) cần chốt ·{' '}
            {brief.sources?.length || 0} source
          </div>
        )}
      </div>
    </div>
  )
}
