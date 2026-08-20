import { useEffect, useMemo, useState } from 'react'
import PageHeader from '../components/common/PageHeader'
import { useAuth } from '../context/AuthContext'
import { useWorkspace } from '../context/WorkspaceContext'
import { listAvailableAgentWorkspaces } from '../api/workspaces'

const profileName = profile => (
  ({
    product_delivery: 'Product Delivery Agent',
    quality_assurance: 'Quality Assurance Agent',
    executive: 'Executive Agent',
  }[profile] || profile)
)

export default function WorkspaceManagementPage() {
  const { token } = useAuth()
  const { workspaces } = useWorkspace()
  const company = useMemo(
    () => workspaces.find(item => item.type === 'organization' && item.slug === 'company-root'),
    [workspaces],
  )
  const [assignedWorkspaces, setAssignedWorkspaces] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!company?.id) {
      setAssignedWorkspaces([])
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    listAvailableAgentWorkspaces(token, company.id)
      .then(setAssignedWorkspaces)
      .catch(err => setError(err.detail || 'Could not load your assigned workspaces.'))
      .finally(() => setLoading(false))
  }, [token, company?.id])

  return <div className="container-fluid py-4 px-3 px-lg-4">
    <PageHeader
      eyebrow="Company workspaces"
      title="My workspaces"
      description="Workspaces assigned to you, each with its dedicated supporting agent."
    />
    {error && <div className="alert alert-danger mt-3">{error}</div>}
    {!company && !loading && <div className="workspace-panel mt-4"><h3>No workspace assigned</h3><p className="text-secondary mb-0">Ask an administrator to assign you to a company workspace.</p></div>}
    {company && <>
      <div className="workspace-grid mt-4">{assignedWorkspaces.map(workspace => <article className="workspace-card" key={workspace.id}><div className="workspace-card-head"><div><h3>{workspace.name}</h3><small>{workspace.key} · {profileName(workspace.agent_profile)}</small></div><span className="workspace-role">{workspace.current_user_business_role}</span></div><div className="mt-3 small text-secondary">Workspace lead: {workspace.lead_display_name || workspace.lead_email}</div></article>)}</div>
      {!loading && !assignedWorkspaces.length && <div className="workspace-panel mt-4"><h3>No workspace assigned</h3><p className="text-secondary mb-0">An administrator must assign you as a workspace lead or member.</p></div>}
      {loading && <div className="workspace-panel mt-4"><span className="spinner-border spinner-border-sm me-2" />Loading workspaces…</div>}
    </>}
  </div>
}
