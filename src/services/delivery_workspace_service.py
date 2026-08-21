"""Real (Postgres-backed) reads for the Product Delivery Agent - replaces the fixture data
`src.agents.tools.delivery_tool` shipped with before today's DB work (Task.agent_workspace_id,
AgentWorkspaceConversation) existed. Every query here is bound to `agent_workspace_id` (G2: "Query
phải chứa organization và Agent Workspace predicate") - callers are expected to have already run
`resource_guard.enforce_agent_workspace_access` before calling any function in this module.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    AgentWorkspaceConversation,
    AgentWorkspaceMembership,
    Message,
    Task,
    User,
)


def _escape_ilike(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_tasks(db: AsyncSession, agent_workspace_id: str, *, include_completed: bool = False) -> list[Task]:
    stmt = select(Task).where(Task.agent_workspace_id == agent_workspace_id).order_by(Task.due_at.asc().nulls_last())
    if not include_completed:
        stmt = stmt.where(Task.status.notin_(("completed", "dismissed")))
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
    """Search only messages in conversations explicitly linked to this Agent Workspace
    (AgentWorkspaceConversation) - never every conversation the caller happens to be in. Mirrors
    src.services.chat_service.search_messages' ILIKE convention."""
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
