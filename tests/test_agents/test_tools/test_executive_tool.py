"""src.agents.tools.executive_tool - reads only already-published WorkspaceBrief records, never
raw Delivery/Quality data."""

import pytest
from sqlalchemy import select

import src.db.session as db_session
from src.agents.context_builder import build_agent_context
from src.agents.contracts import AgentIntent, AgentInvocationRequest, AgentProfile, RequestedScope
from src.agents.tools import delivery_tool, executive_tool, quality_tool
from src.db.models import AgentWorkspace, AgentWorkspaceMembership, Task, User, Workspace, WorkspaceMembership


async def _user(email: str) -> User:
    async with db_session.async_session_maker() as db:
        return (await db.execute(select(User).where(User.email == email))).scalar_one()


async def _make_org_with_delivery_and_quality(lead_id: str, executive_id: str) -> tuple[str, str, str]:
    """One org with a Delivery workspace (lead_id as lead) and a Quality workspace (lead_id as
    lead too, to keep the fixture small), both with executive_id as executive_viewer on both."""
    async with db_session.async_session_maker() as db:
        org = Workspace(type="organization", name="Org")
        db.add(org)
        await db.flush()
        for user_id in {lead_id, executive_id}:
            db.add(WorkspaceMembership(workspace_id=org.id, user_id=user_id, role="member"))

        delivery = AgentWorkspace(organization_workspace_id=org.id, key="delivery", name="Delivery", agent_profile="product_delivery")
        quality = AgentWorkspace(organization_workspace_id=org.id, key="quality", name="Quality", agent_profile="quality_assurance")
        db.add(delivery)
        db.add(quality)
        await db.flush()

        db.add(AgentWorkspaceMembership(agent_workspace_id=delivery.id, user_id=lead_id, business_role="lead"))
        db.add(AgentWorkspaceMembership(agent_workspace_id=quality.id, user_id=lead_id, business_role="lead"))
        db.add(AgentWorkspaceMembership(agent_workspace_id=delivery.id, user_id=executive_id, business_role="executive_viewer"))
        db.add(AgentWorkspaceMembership(agent_workspace_id=quality.id, user_id=executive_id, business_role="executive_viewer"))
        await db.commit()
        return org.id, delivery.id, quality.id


async def _workspace_context(user: User, org_id: str, workspace_id: str, profile: AgentProfile, intent: AgentIntent):
    async with db_session.async_session_maker() as db:
        return await build_agent_context(
            db,
            user=user,
            organization_workspace_id=org_id,
            invocation=AgentInvocationRequest(
                message="brief", requested_scope=RequestedScope.WORKSPACE, target_agent_workspace_id=workspace_id
            ),
            intent=intent,
            agent_profile=profile,
        )


async def _executive_context(user: User, org_id: str):
    async with db_session.async_session_maker() as db:
        return await build_agent_context(
            db,
            user=user,
            organization_workspace_id=org_id,
            invocation=AgentInvocationRequest(message="status?", requested_scope=RequestedScope.AGGREGATE),
            intent=AgentIntent.EXECUTIVE_BRIEF,
            agent_profile=AgentProfile.EXECUTIVE,
        )


@pytest.mark.asyncio
async def test_executive_sees_no_briefs_yet_reports_data_gaps_not_fabricated_content(auth_headers, other_auth_headers):
    alice = await _user("alice@example.com")  # lead
    bob = await _user("bob@example.com")  # executive
    org_id, _delivery_id, _quality_id = await _make_org_with_delivery_and_quality(alice.id, bob.id)

    context = await _executive_context(bob, org_id)
    async with db_session.async_session_maker() as db:
        result = await executive_tool.get_workspace_briefs(db, context)

    assert result.payload["briefs"] == []
    assert len(result.data_gaps) == 2  # one per workspace, neither has published a brief yet


@pytest.mark.asyncio
async def test_executive_brief_aggregates_real_published_delivery_and_quality_briefs(auth_headers, other_auth_headers):
    alice = await _user("alice@example.com")
    bob = await _user("bob@example.com")
    org_id, delivery_id, quality_id = await _make_org_with_delivery_and_quality(alice.id, bob.id)

    async with db_session.async_session_maker() as db:
        db.add(Task(owner_id=alice.id, title="Blocked", agent_workspace_id=delivery_id, status="blocked"))
        db.add(
            Task(
                owner_id=alice.id,
                title="Crash",
                agent_workspace_id=quality_id,
                work_item_type="bug",
                severity="critical",
                quality_status="open",
            )
        )
        await db.commit()

    delivery_context = await _workspace_context(alice, org_id, delivery_id, AgentProfile.PRODUCT_DELIVERY, AgentIntent.DELIVERY_BRIEF)
    quality_context = await _workspace_context(alice, org_id, quality_id, AgentProfile.QUALITY_ASSURANCE, AgentIntent.QUALITY_READINESS)
    async with db_session.async_session_maker() as db:
        await delivery_tool.build_delivery_brief(db, delivery_context)
    async with db_session.async_session_maker() as db:
        await quality_tool.build_quality_brief(db, quality_context)

    executive_context = await _executive_context(bob, org_id)
    async with db_session.async_session_maker() as db:
        result = await executive_tool.build_executive_brief(db, executive_context)

    brief = result.payload["executive_brief"]
    assert len(brief["workspace_brief_ids"]) == 2
    assert any(risk["severity"] == "high" for risk in brief["risks"])  # NOT_READY quality brief -> high risk


@pytest.mark.asyncio
async def test_non_executive_viewer_is_denied_aggregate_scope(auth_headers, other_auth_headers):
    """alice is only a lead (member/lead role), never granted executive_viewer anywhere - the
    AGGREGATE route must deny her, not silently show her own workspaces' briefs."""
    alice = await _user("alice@example.com")
    bob = await _user("bob@example.com")
    org_id, _delivery_id, _quality_id = await _make_org_with_delivery_and_quality(alice.id, bob.id)

    context = await _executive_context(alice, org_id)
    assert context.authorization.decision.value == "DENY"
