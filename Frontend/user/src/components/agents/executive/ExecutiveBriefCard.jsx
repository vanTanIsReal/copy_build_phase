const EXECUTIVE_BRIEF_FIXTURE = {
  headline: 'Tiến độ tuần này ổn, nhưng cần chốt hai rủi ro trước thứ Sáu.',
  facts: [
    { text: '8/10 hạng mục trong kế hoạch đã hoàn tất.', source_ids: ['delivery-summary'] },
    { text: 'Hai hạng mục còn lại đang phụ thuộc vào dữ liệu từ đối tác.', source_ids: ['delivery-summary', 'partner-update'] },
  ],
  risks: [
    { text: 'Thiếu xác nhận ETA từ đối tác có thể đẩy lịch phát hành.', severity: 'high', evidence_ids: ['partner-update'] },
    { text: 'Nhóm chưa có người dự phòng cho phần kiểm thử cuối.', severity: 'medium', evidence_ids: ['team-plan'] },
  ],
  decisions_needed: [
    { decision: 'Có chấp nhận phát hành với hai hạng mục đang chờ dữ liệu không?', owner: 'Sếp dự án', due_at: '2026-08-28T17:00:00+07:00' },
    { decision: 'Chỉ định người dự phòng cho kiểm thử cuối.', owner: null, due_at: null },
  ],
  data_gaps: [
    'Chưa có ETA chính thức từ đối tác cho hai hạng mục đang chờ dữ liệu.',
    'Chưa có số liệu chất lượng sau vòng kiểm thử cuối.',
  ],
}

const listOrEmpty = (value) => (Array.isArray(value) ? value : [])

function formatDueAt(value) {
  if (!value) return 'Chưa có hạn'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium' }).format(date)
}

function severityLabel(value) {
  const normalized = String(value || 'medium').toLowerCase()
  return ['low', 'medium', 'high'].includes(normalized) ? normalized : 'medium'
}

export { EXECUTIVE_BRIEF_FIXTURE }

export default function ExecutiveBriefCard({ brief = EXECUTIVE_BRIEF_FIXTURE }) {
  const facts = listOrEmpty(brief?.facts)
  const risks = listOrEmpty(brief?.risks)
  const decisions = listOrEmpty(brief?.decisions_needed)
  const dataGaps = listOrEmpty(brief?.data_gaps)

  return <article className="executive-brief-card" aria-labelledby="executive-brief-headline" data-testid="executive-brief-card">
    <header className="executive-brief-header">
      <div>
        <span className="executive-brief-kicker"><i className="bi bi-bar-chart-line" /> Executive brief</span>
        <p className="executive-brief-source">Fixture · chưa nối B/C thật</p>
      </div>
      <span className="executive-brief-status"><i className="bi bi-flask" /> Demo data</span>
    </header>

    <h2 id="executive-brief-headline">{brief?.headline || 'Chưa có headline'}</h2>

    <div className="executive-brief-grid">
      <section className="executive-brief-section" aria-labelledby="executive-brief-facts">
        <div className="executive-brief-section-title">
          <h3 id="executive-brief-facts"><i className="bi bi-check2-circle" /> Facts</h3>
          <span>{facts.length}</span>
        </div>
        {facts.length > 0 ? <ul>{facts.map((fact, index) => <li key={`${fact.text}-${index}`}>
          <span>{fact.text}</span>
          {fact.source_ids?.length > 0 && <small>Source: {fact.source_ids.join(', ')}</small>}
        </li>)}</ul> : <p className="executive-brief-empty">Chưa có facts.</p>}
      </section>

      <section className="executive-brief-section" aria-labelledby="executive-brief-risks">
        <div className="executive-brief-section-title">
          <h3 id="executive-brief-risks"><i className="bi bi-exclamation-triangle" /> Risks</h3>
          <span>{risks.length}</span>
        </div>
        {risks.length > 0 ? <ul>{risks.map((risk, index) => {
          const severity = severityLabel(risk.severity)
          return <li className={`executive-brief-risk ${severity}`} key={`${risk.text}-${index}`}>
            <span>{risk.text}</span>
            <small><b>{severity}</b>{risk.evidence_ids?.length > 0 && ` · Evidence: ${risk.evidence_ids.join(', ')}`}</small>
          </li>
        })}</ul> : <p className="executive-brief-empty">Chưa có risks.</p>}
      </section>

      <section className="executive-brief-section" aria-labelledby="executive-brief-decisions">
        <div className="executive-brief-section-title">
          <h3 id="executive-brief-decisions"><i className="bi bi-signpost-split" /> Decisions needed</h3>
          <span>{decisions.length}</span>
        </div>
        {decisions.length > 0 ? <ul>{decisions.map((item, index) => <li key={`${item.decision}-${index}`}>
          <span>{item.decision}</span>
          <small>{item.owner || 'Chưa có owner'} · {formatDueAt(item.due_at)}</small>
        </li>)}</ul> : <p className="executive-brief-empty">Chưa có decisions needed.</p>}
      </section>
    </div>

    {dataGaps.length > 0 && <section className="executive-brief-data-gaps" aria-labelledby="executive-brief-data-gaps" data-testid="executive-brief-data-gaps">
      <div className="executive-brief-data-gaps-title">
        <i className="bi bi-database-exclamation" />
        <div>
          <h3 id="executive-brief-data-gaps">DATA GAPS — dữ liệu còn thiếu</h3>
          <p>Không suy đoán từ các phần dữ liệu chưa có.</p>
        </div>
      </div>
      <ul>{dataGaps.map((gap, index) => <li key={`${gap}-${index}`}>{gap}</li>)}</ul>
    </section>}
  </article>
}
