"""src.agents.context_builder.build_agent_context and AgentRunRecorder (G0 input boundary + G1 scope
resolution assembled into one AgentContext, plus the G6 agent_runs audit trail)."""

import pytest
from sqlalchemy import select

import src.db.session as db_session
from src.agents.context_builder import AgentRunRecorder, build_agent_context
from src.agents.contracts import (
    AgentIntent,
    AgentInvocationRequest,
    AgentProfile,
    PolicyDecision,
    PolicyReason,
    RequestedScope,
)
from src.db.models import (
    AgentRun,
    AgentWorkspace,
    AgentWorkspaceMembership,
    User,
    Workspace,
    WorkspaceMembership,
)


async def _user(email: str) -> User:
    async with db_session.async_session_maker() as db:
        return (await db.execute(select(User).where(User.email == email))).scalar_one()


async def _make_org_with_delivery_workspace_and_lead(user_id: str) -> tuple[str, str]:
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
        await db.commit()
        return org.id, workspace.id


@pytest.mark.asyncio
async def test_build_agent_context_allows_a_real_workspace_lead(auth_headers):
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_org_with_delivery_workspace_and_lead(alice.id)

    async with db_session.async_session_maker() as db:
        context = await build_agent_context(
            db,
            user=alice,
            organization_workspace_id=org_id,
            invocation=AgentInvocationRequest(
                message="what's blocked?",
                requested_scope=RequestedScope.WORKSPACE,
                target_agent_workspace_id=workspace_id,
            ),
            intent=AgentIntent.DELIVERY_BRIEF,
            agent_profile=AgentProfile.PRODUCT_DELIVERY,
        )

    assert context.authorization.decision == PolicyDecision.ALLOW
    assert context.actor.user_id == alice.id
    assert workspace_id in context.authorization.allowed_agent_workspace_ids
    assert workspace_id in context.actor.agent_workspace_ids
    # G0: nothing client-controlled leaks unchecked into the trusted envelope's identity fields.
    assert context.request.text == "what's blocked?"


@pytest.mark.asyncio
async def test_build_agent_context_denies_a_non_member_without_raising(auth_headers, other_auth_headers):
    """bob has no membership anywhere - build_agent_context must still return a *context* (with
    decision=DENY), not raise, so the denial itself can be uniformly logged by AgentRunRecorder."""
    alice = await _user("alice@example.com")
    bob = await _user("bob@example.com")
    org_id, workspace_id = await _make_org_with_delivery_workspace_and_lead(alice.id)

    async with db_session.async_session_maker() as db:
        context = await build_agent_context(
            db,
            user=bob,
            organization_workspace_id=org_id,
            invocation=AgentInvocationRequest(
                message="what's blocked?",
                requested_scope=RequestedScope.WORKSPACE,
                target_agent_workspace_id=workspace_id,
            ),
            intent=AgentIntent.DELIVERY_BRIEF,
            agent_profile=AgentProfile.PRODUCT_DELIVERY,
        )

    assert context.authorization.decision == PolicyDecision.DENY
    assert context.authorization.reason == PolicyReason.NOT_MEMBER
    assert context.authorization.allowed_resource_ids == ()


@pytest.mark.asyncio
async def test_agent_run_recorder_writes_success_row(auth_headers):
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_org_with_delivery_workspace_and_lead(alice.id)

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
        async with AgentRunRecorder(db, context) as recorder:
            recorder.model = "gemini-test"
            recorder.token_usage = 42

    async with db_session.async_session_maker() as db:
        run = (
            await db.execute(select(AgentRun).where(AgentRun.trace_id == context.trace_id))
        ).scalar_one()
    assert run.status == "success"
    assert run.model == "gemini-test"
    assert run.token_usage == 42
    assert run.agent_profile == "product_delivery"


@pytest.mark.asyncio
async def test_agent_run_recorder_records_denied_status_and_never_swallows_exceptions(auth_headers, other_auth_headers):
    alice = await _user("alice@example.com")
    bob = await _user("bob@example.com")
    org_id, workspace_id = await _make_org_with_delivery_workspace_and_lead(alice.id)

    async with db_session.async_session_maker() as db:
        context = await build_agent_context(
            db,
            user=bob,
            organization_workspace_id=org_id,
            invocation=AgentInvocationRequest(
                message="brief",
                requested_scope=RequestedScope.WORKSPACE,
                target_agent_workspace_id=workspace_id,
            ),
            intent=AgentIntent.DELIVERY_BRIEF,
            agent_profile=AgentProfile.PRODUCT_DELIVERY,
        )
        with pytest.raises(ValueError, match="boom"):
            async with AgentRunRecorder(db, context):
                raise ValueError("boom")

    async with db_session.async_session_maker() as db:
        run = (
            await db.execute(select(AgentRun).where(AgentRun.trace_id == context.trace_id))
        ).scalar_one()
    # denied takes precedence over the exception in the recorded status - both are true, but
    # "denied" is the more actionable signal for G6 monitoring (an exception on an already-denied
    # call is expected/harmless, unlike one on an ALLOWed call).
    assert run.status == "denied"
