"""Persists/retrieves published src.agents.contracts.WorkspaceBrief envelopes
(src.db.models.WorkspaceBriefRecord) - the durable store the Executive Agent reads from, so
"read validated briefs" means "read what Delivery/Quality actually published", not an in-memory
value that only exists for the lifetime of one tool call.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts import WorkspaceBrief
from src.db.models import WorkspaceBriefRecord


async def save_brief(db: AsyncSession, brief: WorkspaceBrief) -> WorkspaceBriefRecord:
    record = WorkspaceBriefRecord(
        id=brief.brief_id,
        organization_workspace_id=brief.organization_workspace_id,
        agent_workspace_id=brief.agent_workspace_id,
        brief_type=brief.brief_type.value,
        trace_id=brief.trace_id,
        period_start=brief.period_start,
        period_end=brief.period_end,
        generated_at=brief.generated_at,
        expires_at=brief.expires_at,
        headline=brief.headline,
        brief_json=brief.model_dump(mode="json"),
    )
    db.add(record)
    await db.commit()
    return record


async def get_latest_brief(db: AsyncSession, agent_workspace_id: str, brief_type: str) -> WorkspaceBrief | None:
    """Most recently generated brief for one workspace/type - may be stale (caller must check
    `.is_stale()`), never filtered out here so a stale brief can still be reported as a data gap
    rather than silently disappearing."""
    stmt = (
        select(WorkspaceBriefRecord)
        .where(
            WorkspaceBriefRecord.agent_workspace_id == agent_workspace_id,
            WorkspaceBriefRecord.brief_type == brief_type,
        )
        .order_by(WorkspaceBriefRecord.generated_at.desc())
        .limit(1)
    )
    record = (await db.execute(stmt)).scalar_one_or_none()
    if record is None:
        return None
    return WorkspaceBrief.model_validate(record.brief_json)
