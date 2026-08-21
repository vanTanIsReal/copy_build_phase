"""src.agents.tools.delivery_tool - real DB-backed Product Delivery Agent vertical slice."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import src.db.session as db_session
from src.agents.context_builder import build_agent_context
from src.agents.contracts import (
    ActorContext,
    AgentContext,
    AgentIntent,
    AgentInvocationRequest,
    AgentProfile,
    AgentRequestContext,
    AgentRuntimeContext,
    AuthorizationContext,
    BusinessRole,
    PolicyDecision,
    PolicyReason,
    RequestedScope,
)
from src.agents.policies.resource_guard import AgentResourceDeniedError
from src.agents.tools import delivery_tool
from src.db.models import AgentWorkspace, AgentWorkspaceMembership, Task, User, Workspace, WorkspaceMembership


async def _user(email: str) -> User:
    async with db_session.async_session_maker() as db:
        return (await db.execute(select(User).where(User.email == email))).scalar_one()


async def _make_delivery_workspace_with_lead(user_id: str) -> tuple[str, str]:
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


async def _context(user: User, org_id: str, workspace_id: str):
    async with db_session.async_session_maker() as db:
        return await build_agent_context(
            db,
            user=user,
            organization_workspace_id=org_id,
            invocation=AgentInvocationRequest(
                message="status?", requested_scope=RequestedScope.WORKSPACE, target_agent_workspace_id=workspace_id
            ),
            intent=AgentIntent.DELIVERY_BRIEF,
            agent_profile=AgentProfile.PRODUCT_DELIVERY,
        )


@pytest.mark.asyncio
async def test_get_delivery_tasks_returns_only_this_workspace_tasks(auth_headers):
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_delivery_workspace_with_lead(alice.id)

    async with db_session.async_session_maker() as db:
        db.add(Task(owner_id=alice.id, workspace_id=org_id, title="In scope", agent_workspace_id=workspace_id, status="pending"))
        db.add(Task(owner_id=alice.id, workspace_id=org_id, title="Personal task, no workspace"))  # agent_workspace_id=None
        await db.commit()

    context = await _context(alice, org_id, workspace_id)
    async with db_session.async_session_maker() as db:
        result = await delivery_tool.get_delivery_tasks(db, context)

    titles = [task["title"] for task in result.payload["tasks"]]
    assert titles == ["In scope"]


@pytest.mark.asyncio
async def test_delivery_tools_deny_a_non_member(auth_headers, other_auth_headers):
    alice = await _user("alice@example.com")
    bob = await _user("bob@example.com")
    org_id, workspace_id = await _make_delivery_workspace_with_lead(alice.id)

    async with db_session.async_session_maker() as db:
        bob_context = await build_agent_context(
            db,
            user=bob,
            organization_workspace_id=org_id,
            invocation=AgentInvocationRequest(
                message="status?", requested_scope=RequestedScope.WORKSPACE, target_agent_workspace_id=workspace_id
            ),
            intent=AgentIntent.DELIVERY_BRIEF,
            agent_profile=AgentProfile.PRODUCT_DELIVERY,
        )
        with pytest.raises(AgentResourceDeniedError):
            await delivery_tool.get_delivery_tasks(db, bob_context)


@pytest.mark.asyncio
async def test_quality_lead_cannot_use_delivery_tools_on_their_own_workspace(client):
    """Cross-profile boundary: a QA workspace's own context (requested via QUALITY_READINESS)
    can never satisfy a Delivery tool's target_agent_workspace_id check for a Delivery workspace -
    routing already prevents this shape, but the tool-level guard must independently hold too."""
    async with db_session.async_session_maker() as db:
        org = Workspace(type="organization", name="Org")
        db.add(org)
        await db.flush()
        qa_workspace = AgentWorkspace(
            organization_workspace_id=org.id, key="quality", name="Quality", agent_profile="quality_assurance"
        )
        db.add(qa_workspace)
        await db.commit()
        qa_workspace_id = qa_workspace.id

    # A context built for a nonexistent/foreign delivery workspace id must not let a tool proceed.
    forged_context = AgentContext(
        trace_id="trace-forged",
        actor=ActorContext(user_id="someone", organization_workspace_id=org.id, business_role=BusinessRole.MEMBER),
        request=AgentRequestContext(
            text="hi",
            intent=AgentIntent.DELIVERY_BRIEF,
            requested_scope=RequestedScope.WORKSPACE,
            target_agent_workspace_id=qa_workspace_id,
        ),
        authorization=AuthorizationContext(
            decision=PolicyDecision.ALLOW,
            reason=PolicyReason.ALLOWED,
            allowed_agent_workspace_ids=(qa_workspace_id,),
        ),
        runtime=AgentRuntimeContext(agent_profile=AgentProfile.PRODUCT_DELIVERY, prompt_version="product-delivery-v1"),
    )
    async with db_session.async_session_maker() as db:
        with pytest.raises(AgentResourceDeniedError):
            await delivery_tool.get_delivery_tasks(db, forged_context)


@pytest.mark.asyncio
async def test_build_delivery_brief_reports_blocked_tasks_and_data_gaps(auth_headers):
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_delivery_workspace_with_lead(alice.id)

    async with db_session.async_session_maker() as db:
        db.add(Task(owner_id=alice.id, workspace_id=org_id, title="Blocked task", agent_workspace_id=workspace_id, status="blocked"))
        db.add(Task(owner_id=alice.id, workspace_id=org_id, title="Fine task", agent_workspace_id=workspace_id, status="pending"))
        await db.commit()

    context = await _context(alice, org_id, workspace_id)
    async with db_session.async_session_maker() as db:
        result = await delivery_tool.build_delivery_brief(db, context)

    assert "1 task đang blocked" in result.payload["delivery_brief"]["headline"]
    assert len(result.payload["delivery_brief"]["blocked_items"]) == 1
    assert result.data_gaps  # honest about milestones/dependencies not being modeled yet
    assert result.payload["workspace_brief"]["brief_type"] == "delivery"


@pytest.mark.asyncio
async def test_propose_delivery_reminder_never_persists_anything(auth_headers):
    """Preview-only: no Reminder row should exist afterwards - only a human confirming via the
    (Phase 4) HITL executor may create one."""
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_delivery_workspace_with_lead(alice.id)
    context = await _context(alice, org_id, workspace_id)

    async with db_session.async_session_maker() as db:
        result = await delivery_tool.propose_delivery_reminder(
            db, context, title="Ping team", due_at=datetime.now(UTC) + timedelta(days=1)
        )

    assert result.payload["requires_confirmation"] is True
    assert result.payload["proposal"]["actor_user_id"] == alice.id

    from src.db.models import Reminder

    async with db_session.async_session_maker() as db:
        count = len((await db.execute(select(Reminder))).scalars().all())
    assert count == 0
