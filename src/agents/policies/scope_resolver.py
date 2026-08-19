"""Agent-workspace scope resolution: turns (user, organization workspace, requested profile/scope)
into what that user is actually allowed to see. Ported narrowly from the G19-T132-Lương-Trí-Tuệ
branch's foundation - see docs/MULTI_AGENT_PROGRESS.md. Nothing here is wired into `/chat` yet.
"""

import hashlib

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts import (
    AgentProfile,
    BusinessRole,
    PolicyDecision,
    PolicyReason,
    RequestedScope,
)
from src.db.models import (
    AgentWorkspace,
    AgentWorkspaceConversation,
    AgentWorkspaceMembership,
    Conversation,
    User,
    Workspace,
    WorkspaceMembership,
)


class ResolvedAgentScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: PolicyDecision
    reason: PolicyReason
    business_role: BusinessRole | None = None
    allowed_agent_workspace_ids: tuple[str, ...] = ()
    allowed_resource_ids: tuple[str, ...] = ()
    consent_scope_hash: str | None = None


def _denied(reason: PolicyReason) -> ResolvedAgentScope:
    return ResolvedAgentScope(decision=PolicyDecision.DENY, reason=reason)


async def _has_organization_access(db: AsyncSession, user_id: str, workspace_id: str) -> bool:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or workspace.type != "organization" or workspace.status != "active":
        return False
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        return False
    return (
        await db.execute(
            select(WorkspaceMembership.id).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.status == "active",
            )
        )
    ).scalar_one_or_none() is not None


async def list_active_agent_workspace_memberships(
    db: AsyncSession,
    *,
    user_id: str,
    organization_workspace_id: str | None = None,
    business_roles: tuple[str, ...] | None = None,
) -> tuple[AgentWorkspace, ...]:
    """Every active AgentWorkspace the user has an active membership in.

    Shared by the EXECUTIVE branch of resolve_agent_scope below (organization- and
    executive_viewer-scoped) and by the self-service "my agent workspaces" listing (unscoped,
    any active role) - one query, two callers, so the membership-filtering logic lives in exactly
    one place.
    """
    stmt = (
        select(AgentWorkspace)
        .join(AgentWorkspaceMembership, AgentWorkspaceMembership.agent_workspace_id == AgentWorkspace.id)
        .where(
            AgentWorkspace.status == "active",
            AgentWorkspaceMembership.user_id == user_id,
            AgentWorkspaceMembership.status == "active",
        )
        .order_by(AgentWorkspace.key.asc())
    )
    if organization_workspace_id is not None:
        stmt = stmt.where(AgentWorkspace.organization_workspace_id == organization_workspace_id)
    if business_roles is not None:
        stmt = stmt.where(AgentWorkspaceMembership.business_role.in_(business_roles))
    return tuple((await db.execute(stmt)).scalars().all())


async def list_my_agent_workspaces(db: AsyncSession, *, user_id: str) -> tuple[AgentWorkspace, ...]:
    """Agent workspaces the user has ANY active membership in (member/lead/executive_viewer),
    across every organization workspace - backs GET /api/v1/agent-workspaces?mine=true."""
    return await list_active_agent_workspace_memberships(db, user_id=user_id)


async def _resolve_conversation_resources(
    db: AsyncSession,
    organization_workspace_id: str,
    agent_workspace_id: str,
) -> tuple[tuple[str, ...], str | None]:
    rows = (
        await db.execute(
            select(Conversation.id, Conversation.ai_policy_version)
            .join(
                AgentWorkspaceConversation,
                AgentWorkspaceConversation.conversation_id == Conversation.id,
            )
            .where(
                AgentWorkspaceConversation.agent_workspace_id == agent_workspace_id,
                Conversation.workspace_id == organization_workspace_id,
                Conversation.type == "group",
                Conversation.ai_enabled.is_(True),
            )
            .order_by(Conversation.id.asc())
        )
    ).all()
    if not rows:
        return (), None
    resource_ids = tuple(row.id for row in rows)
    scope_material = "|".join(f"{row.id}:{row.ai_policy_version}" for row in rows)
    consent_scope_hash = hashlib.sha256(scope_material.encode("utf-8")).hexdigest()
    return resource_ids, consent_scope_hash


async def resolve_agent_scope(
    db: AsyncSession,
    *,
    user_id: str,
    organization_workspace_id: str,
    agent_profile: AgentProfile,
    requested_scope: RequestedScope,
    target_agent_workspace_id: str | None = None,
) -> ResolvedAgentScope:
    if not await _has_organization_access(db, user_id, organization_workspace_id):
        return _denied(PolicyReason.NOT_MEMBER)

    if agent_profile == AgentProfile.EXECUTIVE:
        if requested_scope != RequestedScope.AGGREGATE or target_agent_workspace_id is not None:
            return _denied(PolicyReason.INVALID_SCOPE)
        allowed = await list_active_agent_workspace_memberships(
            db,
            user_id=user_id,
            organization_workspace_id=organization_workspace_id,
            business_roles=("executive_viewer",),
        )
        if not allowed:
            return _denied(PolicyReason.NOT_MEMBER)
        return ResolvedAgentScope(
            decision=PolicyDecision.ALLOW,
            reason=PolicyReason.ALLOWED,
            business_role=BusinessRole.EXECUTIVE,
            allowed_agent_workspace_ids=tuple(workspace.id for workspace in allowed),
        )

    if agent_profile not in {AgentProfile.PRODUCT_DELIVERY, AgentProfile.QUALITY_ASSURANCE}:
        return _denied(PolicyReason.PROFILE_MISMATCH)
    if requested_scope != RequestedScope.WORKSPACE or target_agent_workspace_id is None:
        return _denied(PolicyReason.INVALID_SCOPE)

    agent_workspace = await db.get(AgentWorkspace, target_agent_workspace_id)
    if (
        agent_workspace is None
        or agent_workspace.status != "active"
        or agent_workspace.organization_workspace_id != organization_workspace_id
    ):
        return _denied(PolicyReason.WRONG_WORKSPACE)
    if agent_workspace.agent_profile != agent_profile.value:
        return _denied(PolicyReason.PROFILE_MISMATCH)

    membership = (
        await db.execute(
            select(AgentWorkspaceMembership).where(
                AgentWorkspaceMembership.agent_workspace_id == target_agent_workspace_id,
                AgentWorkspaceMembership.user_id == user_id,
                AgentWorkspaceMembership.status == "active",
                AgentWorkspaceMembership.business_role.in_(("member", "lead")),
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        return _denied(PolicyReason.NOT_MEMBER)
    role = BusinessRole.LEAD if membership.business_role == "lead" else BusinessRole.MEMBER
    allowed_resource_ids, consent_scope_hash = await _resolve_conversation_resources(
        db,
        organization_workspace_id,
        agent_workspace.id,
    )
    return ResolvedAgentScope(
        decision=PolicyDecision.ALLOW,
        reason=PolicyReason.ALLOWED,
        business_role=role,
        allowed_agent_workspace_ids=(agent_workspace.id,),
        allowed_resource_ids=allowed_resource_ids,
        consent_scope_hash=consent_scope_hash,
    )
