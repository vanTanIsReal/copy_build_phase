from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts import AgentProfile, PolicyDecision, PolicyReason, RequestedScope
from src.agents.policies.scope_resolver import ResolvedAgentScope, list_my_agent_workspaces, resolve_agent_scope
from src.db.models import (
    AgentWorkspace,
    AgentWorkspaceConversation,
    AgentWorkspaceMembership,
    Conversation,
    User,
    Workspace,
    WorkspaceMembership,
)

SPECIALIST_PROFILES = {
    AgentProfile.PRODUCT_DELIVERY,
    AgentProfile.QUALITY_ASSURANCE,
}
AGENT_WORKSPACE_ROLES = {"member", "lead", "executive_viewer"}
PROFILE_CLASSIFICATION = {
    AgentProfile.PRODUCT_DELIVERY: "delivery",
    AgentProfile.QUALITY_ASSURANCE: "quality",
}


async def require_agent_workspace(
    db: AsyncSession,
    organization_workspace_id: str,
    agent_workspace_id: str,
) -> AgentWorkspace:
    workspace = await db.get(AgentWorkspace, agent_workspace_id)
    if (
        workspace is None
        or workspace.organization_workspace_id != organization_workspace_id
        or workspace.status == "archived"
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent workspace not found")
    return workspace


async def list_agent_workspaces(
    db: AsyncSession,
    organization_workspace_id: str,
) -> list[AgentWorkspace]:
    return list(
        (
            await db.execute(
                select(AgentWorkspace)
                .where(
                    AgentWorkspace.organization_workspace_id == organization_workspace_id,
                    AgentWorkspace.status != "archived",
                )
                .order_by(AgentWorkspace.key.asc())
            )
        )
        .scalars()
        .all()
    )


async def create_agent_workspace(
    db: AsyncSession,
    organization_workspace_id: str,
    key: str,
    name: str,
    agent_profile: AgentProfile,
) -> AgentWorkspace:
    organization = await db.get(Workspace, organization_workspace_id)
    if organization is None or organization.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization workspace not found")
    if organization.type != "organization":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent workspaces require an organization workspace",
        )
    if agent_profile not in SPECIALIST_PROFILES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Agent workspace requires a specialist profile",
        )
    normalized_key = key.strip().lower().replace(" ", "-")
    normalized_name = name.strip()
    if not normalized_key or not normalized_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Key and name are required")

    workspace = AgentWorkspace(
        organization_workspace_id=organization_workspace_id,
        key=normalized_key,
        name=normalized_name,
        agent_profile=agent_profile.value,
    )
    db.add(workspace)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent workspace key already exists") from exc
    return workspace


async def add_agent_workspace_member(
    db: AsyncSession,
    agent_workspace_id: str,
    user_id: str,
    business_role: str,
) -> AgentWorkspaceMembership:
    if business_role not in AGENT_WORKSPACE_ROLES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid business role")
    agent_workspace = await db.get(AgentWorkspace, agent_workspace_id)
    if agent_workspace is None or agent_workspace.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent workspace not found")
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active user not found")
    organization_membership = (
        await db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == agent_workspace.organization_workspace_id,
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.status == "active",
            )
        )
    ).scalar_one_or_none()
    if organization_membership is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User must be an active organization workspace member",
        )

    existing = (
        await db.execute(
            select(AgentWorkspaceMembership).where(
                AgentWorkspaceMembership.agent_workspace_id == agent_workspace_id,
                AgentWorkspaceMembership.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.business_role = business_role
        existing.status = "active"
        existing.updated_at = datetime.now(UTC)
        await db.flush()
        return existing

    membership = AgentWorkspaceMembership(
        agent_workspace_id=agent_workspace_id,
        user_id=user_id,
        business_role=business_role,
    )
    db.add(membership)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent workspace membership exists") from exc
    return membership


async def add_agent_workspace_member_by_email(
    db: AsyncSession,
    organization_workspace_id: str,
    agent_workspace_id: str,
    email: str,
    business_role: str,
) -> AgentWorkspaceMembership:
    await require_agent_workspace(db, organization_workspace_id, agent_workspace_id)
    user = (
        await db.execute(select(User).where(User.email == email.strip().lower(), User.is_active.is_(True)))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active user not found")
    return await add_agent_workspace_member(db, agent_workspace_id, user.id, business_role)


async def list_agent_workspace_members(
    db: AsyncSession,
    organization_workspace_id: str,
    agent_workspace_id: str,
) -> list[tuple[AgentWorkspaceMembership, User]]:
    await require_agent_workspace(db, organization_workspace_id, agent_workspace_id)
    rows = await db.execute(
        select(AgentWorkspaceMembership, User)
        .join(User, User.id == AgentWorkspaceMembership.user_id)
        .where(
            AgentWorkspaceMembership.agent_workspace_id == agent_workspace_id,
            AgentWorkspaceMembership.status != "revoked",
        )
        .order_by(AgentWorkspaceMembership.business_role.asc(), User.display_name.asc())
    )
    return list(rows.all())


async def revoke_agent_workspace_member(
    db: AsyncSession,
    organization_workspace_id: str,
    agent_workspace_id: str,
    membership_id: str,
) -> AgentWorkspaceMembership:
    await require_agent_workspace(db, organization_workspace_id, agent_workspace_id)
    membership = await db.get(AgentWorkspaceMembership, membership_id)
    if membership is None or membership.agent_workspace_id != agent_workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent workspace membership not found")
    membership.status = "revoked"
    membership.updated_at = datetime.now(UTC)
    await db.flush()
    return membership


async def link_agent_workspace_conversation(
    db: AsyncSession,
    *,
    organization_workspace_id: str,
    agent_workspace_id: str,
    conversation_id: str,
    classification: str,
    linked_by_user_id: str,
) -> AgentWorkspaceConversation:
    agent_workspace = await require_agent_workspace(db, organization_workspace_id, agent_workspace_id)
    expected_classification = PROFILE_CLASSIFICATION[AgentProfile(agent_workspace.agent_profile)]
    if classification != expected_classification:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Conversation classification must match the agent workspace profile",
        )
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.workspace_id != organization_workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if conversation.type != "group":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only group conversations can be linked to an agent workspace",
        )

    existing = (
        await db.execute(
            select(AgentWorkspaceConversation).where(
                AgentWorkspaceConversation.conversation_id == conversation_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.agent_workspace_id == agent_workspace_id:
            return existing
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation is already linked to another agent workspace",
        )

    mapping = AgentWorkspaceConversation(
        agent_workspace_id=agent_workspace_id,
        conversation_id=conversation_id,
        classification=classification,
        linked_by_user_id=linked_by_user_id,
    )
    db.add(mapping)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation is already linked to an agent workspace",
        ) from exc
    return mapping


async def list_agent_workspace_conversations(
    db: AsyncSession,
    organization_workspace_id: str,
    agent_workspace_id: str,
) -> list[AgentWorkspaceConversation]:
    await require_agent_workspace(db, organization_workspace_id, agent_workspace_id)
    return list(
        (
            await db.execute(
                select(AgentWorkspaceConversation)
                .where(AgentWorkspaceConversation.agent_workspace_id == agent_workspace_id)
                .order_by(AgentWorkspaceConversation.created_at.asc())
            )
        )
        .scalars()
        .all()
    )


async def unlink_agent_workspace_conversation(
    db: AsyncSession,
    organization_workspace_id: str,
    agent_workspace_id: str,
    mapping_id: str,
) -> AgentWorkspaceConversation:
    await require_agent_workspace(db, organization_workspace_id, agent_workspace_id)
    mapping = await db.get(AgentWorkspaceConversation, mapping_id)
    if mapping is None or mapping.agent_workspace_id != agent_workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation mapping not found")
    await db.delete(mapping)
    await db.flush()
    return mapping


async def resolve_my_agent_workspace_membership(
    db: AsyncSession,
    *,
    user_id: str,
    agent_workspace_id: str,
) -> ResolvedAgentScope:
    """Backs GET /{agent_workspace_id}/my-membership.

    A missing/archived agent_workspace_id collapses into the exact same DENY/NOT_MEMBER result
    resolve_agent_scope already returns for "exists but you're not a member" - the caller (the
    route) must not be able to tell the two apart, so it never learns whether a given id is real.
    """
    agent_workspace = await db.get(AgentWorkspace, agent_workspace_id)
    if agent_workspace is None or agent_workspace.status == "archived":
        return ResolvedAgentScope(decision=PolicyDecision.DENY, reason=PolicyReason.NOT_MEMBER)
    return await resolve_agent_scope(
        db,
        user_id=user_id,
        organization_workspace_id=agent_workspace.organization_workspace_id,
        agent_profile=AgentProfile(agent_workspace.agent_profile),
        requested_scope=RequestedScope.WORKSPACE,
        target_agent_workspace_id=agent_workspace_id,
    )


async def list_my_agent_workspaces_out(db: AsyncSession, *, user_id: str) -> list[AgentWorkspace]:
    """Backs GET /api/v1/agent-workspaces?mine=true. Thin pass-through to
    scope_resolver.list_my_agent_workspaces - kept here too so routes only ever import from the
    service layer, not from src.agents.policies directly."""
    return list(await list_my_agent_workspaces(db, user_id=user_id))


async def set_my_agent_workspace_consent(
    db: AsyncSession, *, user_id: str, agent_workspace_id: str, granted: bool
) -> AgentWorkspaceMembership:
    """Self-service opt-in/out for a specialist agent acting on this member's behalf in this Agent
    Workspace (Sprint 3 consent-gap fix - AgentWorkspaceMembership.consent_status, independent of
    membership.status). Same idea as the existing per-conversation AIPermission.granted toggle for
    the Personal Agent (AIPanel's Grant/Revoke button), applied to Agent Workspace membership.
    Takes effect on the caller's very next request - resolve_agent_scope reads this column live,
    there is no cache to invalidate."""
    membership = (
        await db.execute(
            select(AgentWorkspaceMembership).where(
                AgentWorkspaceMembership.agent_workspace_id == agent_workspace_id,
                AgentWorkspaceMembership.user_id == user_id,
                AgentWorkspaceMembership.status == "active",
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not an active member of this agent workspace")
    membership.consent_status = "active" if granted else "revoked"
    membership.updated_at = datetime.now(UTC)
    await db.flush()
    return membership
