import { useEffect, useMemo, useState } from 'react'
import PageHeader from '../components/common/PageHeader'
import OrgFeatureBadge from '../components/common/OrgFeatureBadge'
import { useAuth } from '../context/AuthContext'
import { useWorkspace } from '../context/WorkspaceContext'
import { listAvailableAgentWorkspaces } from '../api/workspaces'
import EmptyState from '../components/fx/EmptyState'

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
      .catch(err => setError(err.detail || 'Không thể tải danh sách workspace được gán cho bạn.'))
      .finally(() => setLoading(false))
  }, [token, company?.id])

  return <div className="container-fluid py-4 px-3 px-lg-4">
    <PageHeader
      eyebrow="Workspace công ty"
      title="Workspace của bạn"
      description="Các workspace được gán cho bạn, mỗi workspace có một agent hỗ trợ riêng."
      action={<OrgFeatureBadge text="Tính năng tổ chức · cần admin gán" />}
    />
    {error && <div className="alert alert-danger mt-3">{error}</div>}
    {!company && !loading && <div className="workspace-panel mt-4"><EmptyState variant="radar" icon="bi-diagram-3" title="Tài khoản này chưa được cấu hình cho tính năng này" description="Đây là tiện ích multi-agent tuỳ chọn dành cho các nhóm Product Delivery / Quality Assurance / Executive — không phải tài khoản nào cũng có. Nếu nhóm của bạn cần, hãy nhờ admin gán bạn vào một workspace công ty." /></div>}
    {company && <>
      <div className="workspace-grid mt-4">{assignedWorkspaces.map(workspace => <article className="workspace-card" key={workspace.id}><div className="workspace-card-head"><div><h3>{workspace.name}</h3><small>{workspace.key} · {profileName(workspace.agent_profile)}</small></div><span className="workspace-role">{workspace.current_user_business_role}</span></div><div className="mt-3 small text-secondary">Trưởng workspace: {workspace.lead_display_name || workspace.lead_email}</div></article>)}</div>
      {!loading && !assignedWorkspaces.length && <div className="workspace-panel mt-4"><EmptyState variant="radar" icon="bi-diagram-3" title="Tài khoản này chưa được cấu hình cho tính năng này" description="Đây là tiện ích multi-agent tuỳ chọn — không phải tài khoản nào cũng được gán. Cần admin thêm bạn làm lead hoặc thành viên của workspace nếu nhóm bạn cần." /></div>}
      {loading && <div className="workspace-panel mt-4"><span className="spinner-border spinner-border-sm me-2" />Đang tải workspace…</div>}
    </>}
  </div>
}
