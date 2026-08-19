"""src.agents.tools.quality_tool - real DB-backed Quality Assurance Agent vertical slice, with
the hard-coded (not LLM-decided) release-readiness rule as the centerpiece."""

import pytest
from sqlalchemy import select

import src.db.session as db_session
from src.agents.context_builder import build_agent_context
from src.agents.contracts import AgentIntent, AgentInvocationRequest, AgentProfile, RequestedScope
from src.agents.tools import quality_tool
from src.db.models import AgentWorkspace, AgentWorkspaceMembership, Task, User, Workspace, WorkspaceMembership


async def _user(email: str) -> User:
    async with db_session.async_session_maker() as db:
        return (await db.execute(select(User).where(User.email == email))).scalar_one()


async def _make_quality_workspace_with_lead(user_id: str) -> tuple[str, str]:
    async with db_session.async_session_maker() as db:
        org = Workspace(type="organization", name="Orbit Demo Org")
        db.add(org)
        await db.flush()
        db.add(WorkspaceMembership(workspace_id=org.id, user_id=user_id, role="member"))
        workspace = AgentWorkspace(
            organization_workspace_id=org.id, key="quality", name="Quality", agent_profile="quality_assurance"
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
                message="ready?", requested_scope=RequestedScope.WORKSPACE, target_agent_workspace_id=workspace_id
            ),
            intent=AgentIntent.QUALITY_READINESS,
            agent_profile=AgentProfile.QUALITY_ASSURANCE,
        )


@pytest.mark.asyncio
async def test_release_is_ready_with_no_blocking_work_items(auth_headers):
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_quality_workspace_with_lead(alice.id)
    async with db_session.async_session_maker() as db:
        db.add(
            Task(
                owner_id=alice.id,
                title="Login test",
                agent_workspace_id=workspace_id,
                work_item_type="test_case",
                quality_status="passed",
            )
        )
        await db.commit()

    context = await _context(alice, org_id, workspace_id)
    async with db_session.async_session_maker() as db:
        result = await quality_tool.get_release_test_status(db, context)
    assert result.payload["release_readiness"] == "READY"


@pytest.mark.asyncio
async def test_one_open_critical_bug_forces_not_ready_even_with_other_passing_tests(auth_headers):
    """The centerpiece rule: no amount of passing tests overrides one open critical bug."""
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_quality_workspace_with_lead(alice.id)
    async with db_session.async_session_maker() as db:
        db.add(
            Task(
                owner_id=alice.id,
                title="Crash on save",
                agent_workspace_id=workspace_id,
                work_item_type="bug",
                severity="critical",
                quality_status="open",
            )
        )
        for i in range(5):
            db.add(
                Task(
                    owner_id=alice.id,
                    title=f"Passing test {i}",
                    agent_workspace_id=workspace_id,
                    work_item_type="test_case",
                    quality_status="passed",
                )
            )
        await db.commit()

    context = await _context(alice, org_id, workspace_id)
    async with db_session.async_session_maker() as db:
        result = await quality_tool.get_release_test_status(db, context)

    assert result.payload["release_readiness"] == "NOT_READY"
    assert len(result.payload["blocking_items"]) == 1
    assert result.payload["blocking_items"][0]["title"] == "Crash on save"


@pytest.mark.asyncio
async def test_a_resolved_critical_bug_no_longer_blocks_readiness(auth_headers):
    """A critical bug whose quality_status is already "passed" (fixed and verified) is not an
    open critical bug - the rule is about *open* critical bugs, not "any bug ever marked critical"."""
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_quality_workspace_with_lead(alice.id)
    async with db_session.async_session_maker() as db:
        db.add(
            Task(
                owner_id=alice.id,
                title="Fixed crash",
                agent_workspace_id=workspace_id,
                work_item_type="bug",
                severity="critical",
                quality_status="passed",
            )
        )
        await db.commit()

    context = await _context(alice, org_id, workspace_id)
    async with db_session.async_session_maker() as db:
        result = await quality_tool.get_release_test_status(db, context)
    assert result.payload["release_readiness"] == "READY"


@pytest.mark.asyncio
async def test_failed_test_without_critical_bug_is_at_risk_not_not_ready(auth_headers):
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_quality_workspace_with_lead(alice.id)
    async with db_session.async_session_maker() as db:
        db.add(
            Task(
                owner_id=alice.id,
                title="Flaky test",
                agent_workspace_id=workspace_id,
                work_item_type="test_case",
                quality_status="failed",
            )
        )
        await db.commit()

    context = await _context(alice, org_id, workspace_id)
    async with db_session.async_session_maker() as db:
        result = await quality_tool.get_release_test_status(db, context)
    assert result.payload["release_readiness"] == "AT_RISK"


@pytest.mark.asyncio
async def test_build_quality_brief_sets_release_readiness_on_the_workspace_brief(auth_headers):
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_quality_workspace_with_lead(alice.id)
    async with db_session.async_session_maker() as db:
        db.add(
            Task(
                owner_id=alice.id,
                title="Crash",
                agent_workspace_id=workspace_id,
                work_item_type="bug",
                severity="critical",
                quality_status="open",
            )
        )
        await db.commit()

    context = await _context(alice, org_id, workspace_id)
    async with db_session.async_session_maker() as db:
        result = await quality_tool.build_quality_brief(db, context)

    assert result.payload["workspace_brief"]["brief_type"] == "quality"
    assert result.payload["workspace_brief"]["release_readiness"] == "NOT_READY"
    assert "NOT_READY" in result.payload["quality_brief"]["headline"]
