"""src.agents.router.route_agent_request - deterministic profile selection (no LLM, no membership
check - that's scope_resolver's job, exercised separately in test_context_builder.py)."""

import pytest

import src.db.session as db_session
from src.agents.contracts import AgentIntent, AgentInvocationRequest, AgentProfile, RequestedScope
from src.agents.router import AgentRouteDeniedError, route_agent_request
from src.db.models import AgentWorkspace, Workspace


async def _make_org() -> str:
    async with db_session.async_session_maker() as db:
        org = Workspace(type="organization", name="Orbit Demo Org")
        db.add(org)
        await db.commit()
        return org.id


async def _make_agent_workspace(org_id: str, *, profile: str, status: str = "active") -> str:
    async with db_session.async_session_maker() as db:
        workspace = AgentWorkspace(
            organization_workspace_id=org_id,
            key=profile,
            name=profile,
            agent_profile=profile,
            status=status,
        )
        db.add(workspace)
        await db.commit()
        return workspace.id


@pytest.mark.asyncio
async def test_personal_scope_routes_to_personal_profile_regardless_of_intent():
    async with db_session.async_session_maker() as db:
        route = await route_agent_request(
            db,
            organization_workspace_id="does-not-matter",
            invocation=AgentInvocationRequest(message="hi", requested_scope=RequestedScope.PERSONAL),
            intent=AgentIntent.SUMMARIZE,
        )
    assert route.profile == AgentProfile.PERSONAL
    assert "summarize_conversation" in route.allowed_tools


@pytest.mark.asyncio
async def test_personal_scope_with_target_workspace_is_denied():
    async with db_session.async_session_maker() as db:
        with pytest.raises(AgentRouteDeniedError):
            await route_agent_request(
                db,
                organization_workspace_id="org-1",
                invocation=AgentInvocationRequest(
                    message="hi",
                    requested_scope=RequestedScope.PERSONAL,
                    target_agent_workspace_id="some-workspace",
                ),
                intent=AgentIntent.SUMMARIZE,
            )


@pytest.mark.asyncio
async def test_aggregate_scope_routes_to_executive_profile():
    async with db_session.async_session_maker() as db:
        route = await route_agent_request(
            db,
            organization_workspace_id="org-1",
            invocation=AgentInvocationRequest(message="brief me", requested_scope=RequestedScope.AGGREGATE),
            intent=AgentIntent.EXECUTIVE_BRIEF,
        )
    assert route.profile == AgentProfile.EXECUTIVE


@pytest.mark.asyncio
async def test_workspace_scope_routes_to_the_agent_workspace_own_profile():
    org_id = await _make_org()
    workspace_id = await _make_agent_workspace(org_id, profile="quality_assurance")

    async with db_session.async_session_maker() as db:
        route = await route_agent_request(
            db,
            organization_workspace_id=org_id,
            invocation=AgentInvocationRequest(
                message="readiness?",
                requested_scope=RequestedScope.WORKSPACE,
                target_agent_workspace_id=workspace_id,
            ),
            intent=AgentIntent.QUALITY_READINESS,
        )
    assert route.profile == AgentProfile.QUALITY_ASSURANCE
    assert route.target_agent_workspace_id == workspace_id


@pytest.mark.asyncio
async def test_workspace_scope_wrong_intent_for_that_profile_is_denied():
    """A Quality Assurance workspace's route can never satisfy a DELIVERY_BRIEF intent - this is the
    "Delivery user không query được Quality" boundary, enforced deterministically, not by the LLM."""
    org_id = await _make_org()
    workspace_id = await _make_agent_workspace(org_id, profile="quality_assurance")

    async with db_session.async_session_maker() as db:
        with pytest.raises(AgentRouteDeniedError):
            await route_agent_request(
                db,
                organization_workspace_id=org_id,
                invocation=AgentInvocationRequest(
                    message="milestones?",
                    requested_scope=RequestedScope.WORKSPACE,
                    target_agent_workspace_id=workspace_id,
                ),
                intent=AgentIntent.DELIVERY_BRIEF,
            )


@pytest.mark.asyncio
async def test_workspace_scope_denies_suspended_agent_workspace():
    org_id = await _make_org()
    workspace_id = await _make_agent_workspace(org_id, profile="product_delivery", status="suspended")

    async with db_session.async_session_maker() as db:
        with pytest.raises(AgentRouteDeniedError):
            await route_agent_request(
                db,
                organization_workspace_id=org_id,
                invocation=AgentInvocationRequest(
                    message="milestones?",
                    requested_scope=RequestedScope.WORKSPACE,
                    target_agent_workspace_id=workspace_id,
                ),
                intent=AgentIntent.DELIVERY_BRIEF,
            )


@pytest.mark.asyncio
async def test_workspace_scope_denies_agent_workspace_from_a_different_organization():
    """A target_agent_workspace_id that's real but belongs to another org must not leak which
    profile it is - denied the same way as "wrong workspace", not treated as a valid Delivery/QA
    route just because the id happens to resolve."""
    org_id = await _make_org()
    other_org_id = await _make_org()
    workspace_id = await _make_agent_workspace(other_org_id, profile="product_delivery")

    async with db_session.async_session_maker() as db:
        with pytest.raises(AgentRouteDeniedError):
            await route_agent_request(
                db,
                organization_workspace_id=org_id,
                invocation=AgentInvocationRequest(
                    message="milestones?",
                    requested_scope=RequestedScope.WORKSPACE,
                    target_agent_workspace_id=workspace_id,
                ),
                intent=AgentIntent.DELIVERY_BRIEF,
            )


@pytest.mark.asyncio
async def test_workspace_scope_without_target_id_is_denied():
    async with db_session.async_session_maker() as db:
        with pytest.raises(AgentRouteDeniedError):
            await route_agent_request(
                db,
                organization_workspace_id="org-1",
                invocation=AgentInvocationRequest(message="hi", requested_scope=RequestedScope.WORKSPACE),
                intent=AgentIntent.DELIVERY_BRIEF,
            )
