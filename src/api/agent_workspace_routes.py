from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.contracts import PolicyDecision
from src.auth.dependencies import get_current_user
from src.db.models import User
from src.db.session import get_db
from src.models.agent_workspace_schemas import (
    AgentWorkspaceConversationCreate,
    AgentWorkspaceConversationOut,
    AgentWorkspaceCreate,
    AgentWorkspaceMemberCreate,
    AgentWorkspaceMemberOut,
    AgentWorkspaceOut,
    MyAgentWorkspaceConsentIn,
    MyAgentWorkspaceConsentOut,
    MyAgentWorkspaceMembershipOut,
)
from src.services.agent_workspace_service import (
    add_agent_workspace_member_by_email,
    create_agent_workspace,
    link_agent_workspace_conversation,
    list_agent_workspace_conversations,
    list_agent_workspace_members,
    list_agent_workspaces,
    list_my_agent_workspaces_out,
    resolve_my_agent_workspace_membership,
    revoke_agent_workspace_member,
    set_my_agent_workspace_consent,
    unlink_agent_workspace_conversation,
)
from src.services.audit_service import record_audit_event
from src.services.authorization_service import require_workspace_role

# Admin CRUD (create/list/member/conversation-link management), mounted at
# /api/v1/workspaces/{workspace_id}/agent-workspaces/... - every route here requires the caller
# be an owner/admin of the ORGANIZATION workspace (_require_agent_workspace_admin below).
router = APIRouter()

# Self-service, mounted separately at /api/v1/agent-workspaces/... (see src/main.py) - for any
# authenticated user asking about THEIR OWN agent-workspace membership, no organization-admin
# role required. Deliberately a second router: reusing `router` above would also re-expose every
# admin CRUD route a second time under this prefix.
my_router = APIRouter()


async def _require_agent_workspace_admin(
    db: AsyncSession,
    current_user: User,
    workspace_id: str,
) -> None:
    await require_workspace_role(db, current_user, workspace_id, {"owner", "admin"})


@router.post(
    "/{workspace_id}/agent-workspaces",
    response_model=AgentWorkspaceOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace_agent(
    workspace_id: str,
    request: AgentWorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentWorkspaceOut:
    await _require_agent_workspace_admin(db, current_user, workspace_id)
    agent_workspace = await create_agent_workspace(
        db,
        workspace_id,
        request.key,
        request.name,
        request.agent_profile,
    )
    await record_audit_event(
        db,
        actor=current_user,
        action="agent_workspace.created",
        target_type="agent_workspace",
        target_id=agent_workspace.id,
        metadata={
            "organization_workspace_id": workspace_id,
            "agent_profile": agent_workspace.agent_profile,
            "key": agent_workspace.key,
        },
    )
    await db.commit()
    await db.refresh(agent_workspace)
    return AgentWorkspaceOut.model_validate(agent_workspace)


@router.get("/{workspace_id}/agent-workspaces", response_model=list[AgentWorkspaceOut])
async def get_workspace_agents(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentWorkspaceOut]:
    await _require_agent_workspace_admin(db, current_user, workspace_id)
    workspaces = await list_agent_workspaces(db, workspace_id)
    return [AgentWorkspaceOut.model_validate(workspace) for workspace in workspaces]


@router.post(
    "/{workspace_id}/agent-workspaces/{agent_workspace_id}/members",
    response_model=AgentWorkspaceMemberOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_workspace_agent_member(
    workspace_id: str,
    agent_workspace_id: str,
    request: AgentWorkspaceMemberCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentWorkspaceMemberOut:
    await _require_agent_workspace_admin(db, current_user, workspace_id)
    membership = await add_agent_workspace_member_by_email(
        db,
        workspace_id,
        agent_workspace_id,
        str(request.email),
        request.business_role,
    )
    user = await db.get(User, membership.user_id)
    await record_audit_event(
        db,
        actor=current_user,
        action="agent_workspace.member_upserted",
        target_type="agent_workspace_membership",
        target_id=membership.id,
        metadata={
            "organization_workspace_id": workspace_id,
            "member_user_id": membership.user_id,
            "business_role": membership.business_role,
        },
    )
    await db.commit()
    await db.refresh(membership)
    return AgentWorkspaceMemberOut(
        id=membership.id,
        agent_workspace_id=membership.agent_workspace_id,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        business_role=membership.business_role,
        status=membership.status,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


@router.get(
    "/{workspace_id}/agent-workspaces/{agent_workspace_id}/members",
    response_model=list[AgentWorkspaceMemberOut],
)
async def get_workspace_agent_members(
    workspace_id: str,
    agent_workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentWorkspaceMemberOut]:
    await _require_agent_workspace_admin(db, current_user, workspace_id)
    rows = await list_agent_workspace_members(db, workspace_id, agent_workspace_id)
    return [
        AgentWorkspaceMemberOut(
            id=membership.id,
            agent_workspace_id=membership.agent_workspace_id,
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            business_role=membership.business_role,
            status=membership.status,
            created_at=membership.created_at,
            updated_at=membership.updated_at,
        )
        for membership, user in rows
    ]


@router.delete(
    "/{workspace_id}/agent-workspaces/{agent_workspace_id}/members/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_workspace_agent_member(
    workspace_id: str,
    agent_workspace_id: str,
    membership_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _require_agent_workspace_admin(db, current_user, workspace_id)
    membership = await revoke_agent_workspace_member(db, workspace_id, agent_workspace_id, membership_id)
    await record_audit_event(
        db,
        actor=current_user,
        action="agent_workspace.member_revoked",
        target_type="agent_workspace_membership",
        target_id=membership.id,
        metadata={"organization_workspace_id": workspace_id, "member_user_id": membership.user_id},
    )
    await db.commit()


@router.post(
    "/{workspace_id}/agent-workspaces/{agent_workspace_id}/conversations",
    response_model=AgentWorkspaceConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def link_workspace_agent_conversation(
    workspace_id: str,
    agent_workspace_id: str,
    request: AgentWorkspaceConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentWorkspaceConversationOut:
    await _require_agent_workspace_admin(db, current_user, workspace_id)
    mapping = await link_agent_workspace_conversation(
        db,
        organization_workspace_id=workspace_id,
        agent_workspace_id=agent_workspace_id,
        conversation_id=request.conversation_id,
        classification=request.classification,
        linked_by_user_id=current_user.id,
    )
    await record_audit_event(
        db,
        actor=current_user,
        action="agent_workspace.conversation_linked",
        target_type="agent_workspace_conversation",
        target_id=mapping.id,
        metadata={
            "organization_workspace_id": workspace_id,
            "agent_workspace_id": agent_workspace_id,
            "conversation_id": mapping.conversation_id,
            "classification": mapping.classification,
        },
    )
    await db.commit()
    await db.refresh(mapping)
    return AgentWorkspaceConversationOut.model_validate(mapping)


@router.get(
    "/{workspace_id}/agent-workspaces/{agent_workspace_id}/conversations",
    response_model=list[AgentWorkspaceConversationOut],
)
async def get_workspace_agent_conversations(
    workspace_id: str,
    agent_workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentWorkspaceConversationOut]:
    await _require_agent_workspace_admin(db, current_user, workspace_id)
    mappings = await list_agent_workspace_conversations(db, workspace_id, agent_workspace_id)
    return [AgentWorkspaceConversationOut.model_validate(mapping) for mapping in mappings]


@router.delete(
    "/{workspace_id}/agent-workspaces/{agent_workspace_id}/conversations/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_workspace_agent_conversation(
    workspace_id: str,
    agent_workspace_id: str,
    mapping_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _require_agent_workspace_admin(db, current_user, workspace_id)
    mapping = await unlink_agent_workspace_conversation(db, workspace_id, agent_workspace_id, mapping_id)
    await record_audit_event(
        db,
        actor=current_user,
        action="agent_workspace.conversation_unlinked",
        target_type="agent_workspace_conversation",
        target_id=mapping.id,
        metadata={
            "organization_workspace_id": workspace_id,
            "agent_workspace_id": agent_workspace_id,
            "conversation_id": mapping.conversation_id,
        },
    )
    await db.commit()


@my_router.get("/{agent_workspace_id}/my-membership", response_model=MyAgentWorkspaceMembershipOut)
async def get_my_agent_workspace_membership(
    agent_workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyAgentWorkspaceMembershipOut:
    result = await resolve_my_agent_workspace_membership(
        db,
        user_id=current_user.id,
        agent_workspace_id=agent_workspace_id,
    )
    if result.decision != PolicyDecision.ALLOW or result.business_role is None:
        # Same 403, same detail, whether agent_workspace_id doesn't exist, is archived, or exists
        # but the caller was never a member - never lets a caller learn which of those is true.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this agent workspace")
    return MyAgentWorkspaceMembershipOut(
        agent_workspace_id=agent_workspace_id,
        business_role=result.business_role.value,
    )


@my_router.put("/{agent_workspace_id}/my-consent", response_model=MyAgentWorkspaceConsentOut)
async def set_my_agent_workspace_consent_route(
    agent_workspace_id: str,
    request: MyAgentWorkspaceConsentIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyAgentWorkspaceConsentOut:
    """Self-service Grant/Revoke for this Agent Workspace's AI consent - same idea as the existing
    per-conversation AI permission toggle, applied to specialist agent workspaces (Sprint 3
    consent-gap fix). Revoking does not remove membership; it only stops a specialist agent from
    reading/acting on this member's behalf here on the caller's very next request."""
    membership = await set_my_agent_workspace_consent(
        db, user_id=current_user.id, agent_workspace_id=agent_workspace_id, granted=request.granted
    )
    await record_audit_event(
        db,
        actor=current_user,
        action="agent_workspace.consent_changed",
        target_type="agent_workspace_membership",
        target_id=membership.id,
        metadata={"agent_workspace_id": agent_workspace_id, "consent_status": membership.consent_status},
    )
    await db.commit()
    return MyAgentWorkspaceConsentOut(agent_workspace_id=agent_workspace_id, consent_status=membership.consent_status)


@my_router.get("", response_model=list[AgentWorkspaceOut])
async def get_my_agent_workspaces(
    mine: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentWorkspaceOut]:
    if not mine:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mine=true is required")
    workspaces = await list_my_agent_workspaces_out(db, user_id=current_user.id)
    return [AgentWorkspaceOut.model_validate(workspace) for workspace in workspaces]
