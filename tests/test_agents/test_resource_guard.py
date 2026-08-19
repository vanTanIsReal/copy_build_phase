"""src.agents.policies.resource_guard.enforce_agent_resource_access - G2 tool-boundary re-check.

Exercises the "stale HITL" scenario for specialist agents: membership/consent revoked *between*
build_agent_context (start of turn) and a tool call later in the same turn must be caught here, not
silently allowed because the AgentContext snapshot still says ALLOW.
"""

import pytest
from sqlalchemy import select

import src.db.session as db_session
from src.agents.context_builder import build_agent_context
from src.agents.contracts import AgentIntent, AgentInvocationRequest, AgentProfile, RequestedScope
from src.agents.policies.resource_guard import AgentResourceDeniedError, enforce_agent_resource_access
from src.db.models import (
    AgentWorkspace,
    AgentWorkspaceConversation,
    AgentWorkspaceMembership,
    Conversation,
    User,
    Workspace,
    WorkspaceMembership,
)


async def _user(email: str) -> User:
    async with db_session.async_session_maker() as db:
        return (await db.execute(select(User).where(User.email == email))).scalar_one()


async def _make_org_workspace_lead_and_linked_conversation(user_id: str) -> tuple[str, str, str]:
    async with db_session.async_session_maker() as db:
        org = Workspace(type="organization", name="Orbit Demo Org")
        db.add(org)
        await db.flush()
        db.add(WorkspaceMembership(workspace_id=org.id, user_id=user_id, role="member"))
        workspace = AgentWorkspace(
            organization_workspace_id=org.id, key="delivery", name="Delivery", agent_profile="product_delivery"
        )
        db.add(workspace)
        await db.flush()
        db.add(AgentWorkspaceMembership(agent_workspace_id=workspace.id, user_id=user_id, business_role="lead"))
        conversation = Conversation(
            type="group", name="Delivery standup", created_by=user_id, workspace_id=org.id, ai_enabled=True
        )
        db.add(conversation)
        await db.flush()
        db.add(
            AgentWorkspaceConversation(
                agent_workspace_id=workspace.id,
                conversation_id=conversation.id,
                classification="delivery",
                linked_by_user_id=user_id,
            )
        )
        await db.commit()
        return org.id, workspace.id, conversation.id


@pytest.mark.asyncio
async def test_enforce_resource_access_allows_a_currently_authorized_resource(auth_headers):
    alice = await _user("alice@example.com")
    org_id, workspace_id, conversation_id = await _make_org_workspace_lead_and_linked_conversation(alice.id)

    async with db_session.async_session_maker() as db:
        context = await build_agent_context(
            db,
            user=alice,
            organization_workspace_id=org_id,
            invocation=AgentInvocationRequest(
                message="brief",
                requested_scope=RequestedScope.WORKSPACE,
                target_agent_workspace_id=workspace_id,
            ),
            intent=AgentIntent.DELIVERY_BRIEF,
            agent_profile=AgentProfile.PRODUCT_DELIVERY,
        )
        # Must not raise.
        await enforce_agent_resource_access(db, context=context, resource_id=conversation_id)


@pytest.mark.asyncio
async def test_enforce_resource_access_denies_a_resource_outside_the_allowed_set(auth_headers):
    alice = await _user("alice@example.com")
    org_id, workspace_id, _conversation_id = await _make_org_workspace_lead_and_linked_conversation(alice.id)

    async with db_session.async_session_maker() as db:
        context = await build_agent_context(
            db,
            user=alice,
            organization_workspace_id=org_id,
            invocation=AgentInvocationRequest(
                message="brief",
                requested_scope=RequestedScope.WORKSPACE,
                target_agent_workspace_id=workspace_id,
            ),
            intent=AgentIntent.DELIVERY_BRIEF,
            agent_profile=AgentProfile.PRODUCT_DELIVERY,
        )
        with pytest.raises(AgentResourceDeniedError):
            await enforce_agent_resource_access(db, context=context, resource_id="some-other-conversation")


@pytest.mark.asyncio
async def test_enforce_resource_access_denies_when_membership_is_revoked_mid_turn(auth_headers):
    """The AgentContext built at the start of the turn still says ALLOW (it's an immutable
    snapshot) - the guard must re-query membership live and catch the revoke, not trust the
    snapshot. This is what makes G2 more than "check the context and move on"."""
    alice = await _user("alice@example.com")
    org_id, workspace_id, conversation_id = await _make_org_workspace_lead_and_linked_conversation(alice.id)

    async with db_session.async_session_maker() as db:
        context = await build_agent_context(
            db,
            user=alice,
            organization_workspace_id=org_id,
            invocation=AgentInvocationRequest(
                message="brief",
                requested_scope=RequestedScope.WORKSPACE,
                target_agent_workspace_id=workspace_id,
            ),
            intent=AgentIntent.DELIVERY_BRIEF,
            agent_profile=AgentProfile.PRODUCT_DELIVERY,
        )

    # Revoke mid-turn, in a separate session/commit - simulates a concurrent admin action between
    # this turn's context build and the tool call that uses it.
    async with db_session.async_session_maker() as db:
        membership = (
            await db.execute(
                select(AgentWorkspaceMembership).where(
                    AgentWorkspaceMembership.agent_workspace_id == workspace_id,
                    AgentWorkspaceMembership.user_id == alice.id,
                )
            )
        ).scalar_one()
        membership.status = "revoked"
        await db.commit()

    async with db_session.async_session_maker() as db:
        with pytest.raises(AgentResourceDeniedError):
            await enforce_agent_resource_access(db, context=context, resource_id=conversation_id)


@pytest.mark.asyncio
async def test_enforce_resource_access_denies_when_group_ai_policy_changes_mid_turn(auth_headers):
    """Same "stale HITL" principle, but via consent_scope_hash instead of membership: the group's
    ai_enabled/ai_policy_version changing mid-turn changes the hash, which must be caught even
    though the workspace membership itself is unchanged."""
    alice = await _user("alice@example.com")
    org_id, workspace_id, conversation_id = await _make_org_workspace_lead_and_linked_conversation(alice.id)

    async with db_session.async_session_maker() as db:
        context = await build_agent_context(
            db,
            user=alice,
            organization_workspace_id=org_id,
            invocation=AgentInvocationRequest(
                message="brief",
                requested_scope=RequestedScope.WORKSPACE,
                target_agent_workspace_id=workspace_id,
            ),
            intent=AgentIntent.DELIVERY_BRIEF,
            agent_profile=AgentProfile.PRODUCT_DELIVERY,
        )
    assert context.authorization.consent_scope_hash is not None

    async with db_session.async_session_maker() as db:
        conversation = await db.get(Conversation, conversation_id)
        conversation.ai_enabled = False
        await db.commit()

    async with db_session.async_session_maker() as db:
        with pytest.raises(AgentResourceDeniedError):
            await enforce_agent_resource_access(db, context=context, resource_id=conversation_id)
