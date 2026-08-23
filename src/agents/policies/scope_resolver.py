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


class InvalidAttendeeError(ValueError):
    """Raised by validate_attendee_ids - one or more attendee_ids do not resolve to an active
    member of the proposing agent's own organization. Callers turn this into a clean
    ToolResult(status=ERROR) / ActionProposalRejectedError, never let it become a raw 500."""

    def __init__(self, missing_ids: tuple[str, ...]):
        super().__init__(f"attendee_ids outside this organization: {', '.join(missing_ids)}")
        self.missing_ids = missing_ids


async def validate_attendee_ids(
    db: AsyncSession,
    *,
    organization_workspace_id: str,
    attendee_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """A specialist meeting proposal (propose_delivery_meeting/propose_executive_meeting/the
    future propose_quality_meeting) must never be able to invite an arbitrary User.id - only an
    active member of the SAME organization (Company Root boundary, docs/BRIEF.md #6 "server tự
    xác định... không tin các trường quyền do client gửi") the proposing agent's own context
    belongs to. Cross-department invites (e.g. a Delivery meeting inviting a QA lead) are
    legitimate and allowed - the boundary enforced here is the company, not the single
    AgentWorkspace, matching how a real meeting invite works.

    Returns the attendees' emails in `attendee_ids` order (deduplicated) - never a partial list;
    raises InvalidAttendeeError if even one id doesn't resolve to an active org member, so the
    caller can reject the whole proposal rather than silently drop invalid invitees."""
    if not attendee_ids:
        return ()
    rows = (
        await db.execute(
            select(User.id, User.email)
            .join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
            .where(
                WorkspaceMembership.workspace_id == organization_workspace_id,
                WorkspaceMembership.status == "active",
                User.id.in_(attendee_ids),
                User.is_active.is_(True),
            )
        )
    ).all()
    emails_by_id = {row.id: row.email for row in rows}
    missing = tuple(attendee_id for attendee_id in attendee_ids if attendee_id not in emails_by_id)
    if missing:
        raise InvalidAttendeeError(missing)
    return tuple(emails_by_id[attendee_id] for attendee_id in dict.fromkeys(attendee_ids))


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
        # `allowed` only proves active *membership* (status=="active"); a member can still have
        # opted their own AI access out separately (consent_status) without leaving the workspace.
        # If the executive_viewer has consented in at least one, aggregate over those; a total
        # revoke across every executive_viewer membership is reported distinctly from NOT_MEMBER.
        consented_ids = (
            await db.execute(
                select(AgentWorkspaceMembership.agent_workspace_id).where(
                    AgentWorkspaceMembership.agent_workspace_id.in_([w.id for w in allowed]),
                    AgentWorkspaceMembership.user_id == user_id,
                    AgentWorkspaceMembership.status == "active",
                    AgentWorkspaceMembership.consent_status == "active",
                )
            )
        ).scalars().all()
        if not consented_ids:
            return _denied(PolicyReason.WORKSPACE_CONSENT_REVOKED)
        allowed = tuple(w for w in allowed if w.id in set(consented_ids))
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
    if membership.consent_status != "active":
        return _denied(PolicyReason.WORKSPACE_CONSENT_REVOKED)
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
