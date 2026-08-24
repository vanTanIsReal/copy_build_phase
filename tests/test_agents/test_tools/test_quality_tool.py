"""src.agents.tools.quality_tool - real DB-backed Quality Assurance Agent vertical slice
(completes "Ngày 3 - Runtime và Quality WorkspaceBrief" from
docs/ROLE_C_QUALITY_ASSURANCE_7_DAY_PLAN.md). Mirrors test_delivery_tool.py's structure."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import src.db.session as db_session
from src.agents.context_builder import build_agent_context
from src.agents.contracts import AgentIntent, AgentInvocationRequest, AgentProfile, RequestedScope
from src.agents.policies.resource_guard import AgentResourceDeniedError
from src.agents.tools import quality_tool
from src.db.models import (
    AgentWorkspace,
    AgentWorkspaceMembership,
    Task,
    User,
    Workspace,
    WorkspaceBriefRecord,
    WorkspaceMembership,
)


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
                message="readiness?", requested_scope=RequestedScope.WORKSPACE, target_agent_workspace_id=workspace_id
            ),
            intent=AgentIntent.QUALITY_BRIEF,
            agent_profile=AgentProfile.QUALITY_ASSURANCE,
        )


def _work_item(owner_id: str, org_id: str, workspace_id: str, **kwargs) -> Task:
    defaults = {"work_item_type": "bug", "severity": "low", "quality_status": "open"}
    defaults.update(kwargs)
    return Task(owner_id=owner_id, workspace_id=org_id, agent_workspace_id=workspace_id, **defaults)


@pytest.mark.asyncio
async def test_quality_tools_deny_a_non_member(auth_headers, other_auth_headers):
    alice = await _user("alice@example.com")
    bob = await _user("bob@example.com")
    org_id, workspace_id = await _make_quality_workspace_with_lead(alice.id)

    async with db_session.async_session_maker() as db:
        bob_context = await build_agent_context(
            db,
            user=bob,
            organization_workspace_id=org_id,
            invocation=AgentInvocationRequest(
                message="readiness?", requested_scope=RequestedScope.WORKSPACE, target_agent_workspace_id=workspace_id
            ),
            intent=AgentIntent.QUALITY_BRIEF,
            agent_profile=AgentProfile.QUALITY_ASSURANCE,
        )
        with pytest.raises(AgentResourceDeniedError):
            await quality_tool.build_quality_brief(db, bob_context)


@pytest.mark.asyncio
async def test_build_quality_brief_is_not_ready_with_an_active_critical_bug(auth_headers):
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_quality_workspace_with_lead(alice.id)

    async with db_session.async_session_maker() as db:
        db.add(_work_item(alice.id, org_id, workspace_id, title="Login crashes", severity="critical", quality_status="open"))
        db.add(Task(owner_id=alice.id, workspace_id=org_id, title="Personal task, no workspace"))
        await db.commit()

    context = await _context(alice, org_id, workspace_id)
    async with db_session.async_session_maker() as db:
        result = await quality_tool.build_quality_brief(db, context)

    assert result.payload["quality_brief"]["release_readiness"] == "NOT_READY"
    assert len(result.payload["quality_brief"]["critical_defects"]) == 1
    assert result.payload["workspace_brief"]["brief_type"] == "quality"
    assert result.payload["workspace_brief"]["release_readiness"] == "NOT_READY"

    async with db_session.async_session_maker() as db:
        saved = await db.get(WorkspaceBriefRecord, result.payload["workspace_brief"]["brief_id"])
    assert saved is not None
    assert saved.brief_type == "quality"


@pytest.mark.asyncio
async def test_build_quality_brief_is_ready_when_required_checks_pass_and_nothing_is_open(auth_headers):
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_quality_workspace_with_lead(alice.id)

    async with db_session.async_session_maker() as db:
        db.add(_work_item(alice.id, org_id, workspace_id, title="Regression suite", work_item_type="release_check", quality_status="passed"))
        db.add(_work_item(alice.id, org_id, workspace_id, title="Login test", work_item_type="test_case", quality_status="passed"))
        await db.commit()

    context = await _context(alice, org_id, workspace_id)
    async with db_session.async_session_maker() as db:
        result = await quality_tool.build_quality_brief(db, context)

    assert result.payload["quality_brief"]["release_readiness"] == "READY"
    assert not result.data_gaps


@pytest.mark.asyncio
async def test_build_quality_brief_reports_a_data_gap_for_malformed_work_items(auth_headers):
    """A Task tagged as a QA work item but with an invalid severity/status string is excluded and
    reported, never silently coerced into a fake default (see quality_tool._task_to_work_item)."""
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_quality_workspace_with_lead(alice.id)

    async with db_session.async_session_maker() as db:
        db.add(_work_item(alice.id, org_id, workspace_id, title="Bad severity", severity="urgent"))  # not a real QualitySeverity
        await db.commit()

    context = await _context(alice, org_id, workspace_id)
    async with db_session.async_session_maker() as db:
        result = await quality_tool.build_quality_brief(db, context)

    assert any("excluded" in gap for gap in result.data_gaps)
    assert result.payload["quality_brief"]["release_readiness"] != "READY"


@pytest.mark.asyncio
async def test_propose_quality_reminder_never_persists_anything(auth_headers):
    alice = await _user("alice@example.com")
    org_id, workspace_id = await _make_quality_workspace_with_lead(alice.id)
    context = await _context(alice, org_id, workspace_id)

    async with db_session.async_session_maker() as db:
        result = await quality_tool.propose_quality_reminder(
            db, context, title="Chase failing test", due_at=datetime.now(UTC) + timedelta(days=1)
        )

    assert result.payload["requires_confirmation"] is True
    assert result.payload["proposal"]["actor_user_id"] == alice.id
    assert result.payload["proposal"]["action"] == "preview_quality_reminder"

    from src.db.models import Reminder

    async with db_session.async_session_maker() as db:
        count = len((await db.execute(select(Reminder))).scalars().all())
    assert count == 0
