import { useState } from 'react'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Drawer, DrawerContent, DrawerDescription, DrawerFooter, DrawerHeader, DrawerTitle } from '../ui/drawer'

const fieldLabel = (key) => key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

const formatValue = (value) => {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—'
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    try { return new Date(value).toLocaleString('vi-VN') } catch { return value }
  }
  return String(value)
}

// Human-in-the-loop confirmation surface for a src.agents.contracts.ActionProposal (design brief
// Phase 4) - replaces the small ActionProposalCard for any action a specialist agent proposes.
// `beforePayload` is optional: an update-style action (e.g. changing a bug's status) passes the
// record's current field values for a real diff; a create-style action (e.g. a brand-new
// reminder/meeting - what every propose_* tool in this repo currently drafts, see
// src/agents/tools/delivery_tool.py etc.) has no prior state, so the "Trước" column reads "—"
// for every field rather than fabricating one.
export default function HitlDrawer({ proposal, beforePayload = null, open, onOpenChange, onApprove, onReject }) {
  const [decision, setDecision] = useState(null) // null | 'approving' | 'rejecting'
  if (!proposal) return null

  const fields = Object.keys(proposal.payload)
  const expired = new Date(proposal.expires_at) <= new Date()

  const approve = async () => {
    setDecision('approving')
    try { await onApprove?.(proposal) } finally { setDecision(null); onOpenChange?.(false) }
  }
  const reject = async () => {
    setDecision('rejecting')
    try { await onReject?.(proposal) } finally { setDecision(null); onOpenChange?.(false) }
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <div className="flex items-center gap-2">
            <Badge variant="warning">Chờ xác nhận</Badge>
            {expired && <Badge variant="destructive">Hết hạn</Badge>}
          </div>
          <DrawerTitle>{proposal.action}</DrawerTitle>
          <DrawerDescription>
            AI đề xuất hành động này — không có gì thay đổi thật cho tới khi bạn bấm Approve.
          </DrawerDescription>
        </DrawerHeader>

        <div className="flex-1 overflow-y-auto px-6 py-2">
          <div className="grid grid-cols-2 gap-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <span>Trước</span>
            <span>Sau</span>
          </div>
          <div className="mt-2 divide-y divide-white/10 rounded-lg border border-white/10">
            {fields.map((key) => {
              const before = beforePayload ? formatValue(beforePayload[key]) : '—'
              const after = formatValue(proposal.payload[key])
              const changed = before !== after
              return (
                <div key={key} className="grid grid-cols-2 gap-3 p-3 text-sm">
                  <div className="min-w-0">
                    <div className="text-[11px] text-muted-foreground">{fieldLabel(key)}</div>
                    <div className="truncate text-muted-foreground/80 line-through decoration-white/20">{before}</div>
                  </div>
                  <div className="min-w-0">
                    <div className="text-[11px] text-muted-foreground">{fieldLabel(key)}</div>
                    <div className={`truncate font-medium ${changed ? 'text-primary' : 'text-foreground'}`}>{after}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <DrawerFooter>
          <Button size="lg" onClick={approve} disabled={expired || decision !== null}>
            {decision === 'approving' ? 'Đang xử lý...' : 'Approve'}
          </Button>
          <Button variant="outline" size="lg" onClick={reject} disabled={decision !== null}>
            {decision === 'rejecting' ? 'Đang xử lý...' : 'Reject'}
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  )
}
