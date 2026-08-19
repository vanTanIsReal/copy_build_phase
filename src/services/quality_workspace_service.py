"""Real (Postgres-backed) reads for the Quality Assurance Agent - the QA counterpart of
src.services.delivery_workspace_service. Work items (bug/test_case/release_check) are Task rows
with agent_workspace_id + work_item_type/severity/quality_status set (MULTI_AGENT_IMPLEMENTATION_
PLAN.md #6.2: "không xây test-management system riêng"). Every query is bound to
agent_workspace_id (G2) - callers must already have run
resource_guard.enforce_agent_workspace_access.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AgentWorkspaceConversation, AgentWorkspaceMembership, Message, Task, User


def _escape_ilike(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_work_items(
    db: AsyncSession,
    agent_workspace_id: str,
    *,
    work_item_type: str | None = None,
) -> list[Task]:
    stmt = select(Task).where(Task.agent_workspace_id == agent_workspace_id).order_by(Task.due_at.asc().nulls_last())
    if work_item_type is not None:
        stmt = stmt.where(Task.work_item_type == work_item_type)
    return list((await db.execute(stmt)).scalars().all())


async def list_members(db: AsyncSession, agent_workspace_id: str) -> list[tuple[User, str]]:
    stmt = (
        select(User, AgentWorkspaceMembership.business_role)
        .join(AgentWorkspaceMembership, AgentWorkspaceMembership.user_id == User.id)
        .where(
            AgentWorkspaceMembership.agent_workspace_id == agent_workspace_id,
            AgentWorkspaceMembership.status == "active",
        )
        .order_by(User.display_name.asc())
    )
    return [(row.User, row.business_role) for row in (await db.execute(stmt)).all()]


async def search_messages(
    db: AsyncSession, agent_workspace_id: str, query: str, *, limit: int = 10
) -> list[tuple[Message, User]]:
    limit = max(1, min(limit, 50))
    stmt = (
        select(Message, User)
        .join(User, User.id == Message.sender_id)
        .join(AgentWorkspaceConversation, AgentWorkspaceConversation.conversation_id == Message.conversation_id)
        .where(AgentWorkspaceConversation.agent_workspace_id == agent_workspace_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    if query.strip():
        stmt = stmt.where(Message.content.ilike(f"%{_escape_ilike(query)}%", escape="\\"))
    rows = list(reversed((await db.execute(stmt)).all()))
    return [(row.Message, row.User) for row in rows]


def compute_release_readiness(work_items: list[Task]) -> tuple[str, list[Task]]:
    """MULTI_AGENT_IMPLEMENTATION_PLAN.md #6.2's hard rule, enforced in code (not left to the
    LLM to decide, per hard-constraint #1): any open critical bug -> NOT_READY. Otherwise any
    failed/blocked test -> AT_RISK. Otherwise READY."""
    critical_open = [
        item
        for item in work_items
        if item.work_item_type == "bug" and item.severity == "critical" and item.quality_status != "passed"
    ]
    if critical_open:
        return "NOT_READY", critical_open
    at_risk = [item for item in work_items if item.quality_status in ("failed", "blocked")]
    if at_risk:
        return "AT_RISK", at_risk
    return "READY", []
