"""Workspace-role authorization for the agent-workspace foundation only.

Trimmed on purpose from the G19-T132-Lương-Trí-Tuệ branch's authorization_service.py: that file
also has conversation-access/support-access-grant helpers built on models (ConversationParticipant
principal linking, ExternalContact, SupportAccessGrant) that don't exist here and aren't needed by
src.api.agent_workspace_routes - only require_workspace_role is. Do not grow this file to match the
source branch without also porting those models; see docs/MULTI_AGENT_PROGRESS.md for the actual
foundation scope.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User, Workspace, WorkspaceMembership


async def require_workspace_role(
    db: AsyncSession,
    user: User,
    workspace_id: str,
    allowed_roles: set[str] | frozenset[str],
) -> WorkspaceMembership | None:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or workspace.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    membership = (
        await db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user.id,
                WorkspaceMembership.status == "active",
                WorkspaceMembership.role.in_(allowed_roles),
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied")
    return membership
