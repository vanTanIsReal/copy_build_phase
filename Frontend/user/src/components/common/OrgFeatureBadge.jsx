// Small header pill marking a page as an optional org-gated add-on (Workspaces/Briefs) rather
// than a core personal feature - most accounts are never assigned a company workspace, so an
// empty page here is expected, not broken. Shown in PageHeader's `action` slot, visible even
// while the page is still loading. Inline-styled (not a shared CSS class) so it renders correctly
// regardless of which page's stylesheet cascade it's dropped into.
export default function OrgFeatureBadge({ text }) {
  return (
    <span
      className="d-inline-flex align-items-center gap-1 rounded-pill"
      style={{
        padding: '4px 12px',
        background: 'rgba(124,108,242,0.12)',
        border: '1px solid rgba(124,108,242,0.35)',
        color: '#b9b3f7',
        fontSize: 12,
        fontWeight: 600,
        whiteSpace: 'nowrap',
      }}
    >
      <i className="bi bi-diagram-3" />
      {text}
    </span>
  )
}
