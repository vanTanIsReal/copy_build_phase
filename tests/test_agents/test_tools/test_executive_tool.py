"""src.agents.tools.executive_tool - reads only already-published WorkspaceBrief records, never
raw Delivery/Quality data."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

import src.db.session as db_session
from src.agents.context_builder import build_agent_context
from src.agents.contracts import (
    AgentContext,
    AgentIntent,
    AgentInvocationRequest,
    AgentProfile,
    BriefType,
    ReleaseReadiness,
    RequestedScope,
    WorkspaceBrief,
)
from src.agents.tools import delivery_tool, executive_tool
from src.db.models import AgentWorkspace, AgentWorkspaceMembership, Task, User, Workspace, WorkspaceMembership
from src.services import workspace_brief_service


async def _publish_quality_brief(context: AgentContext) -> None:
    """Test-local stand-in for the specialist Quality Assurance agent's own brief-producer tool
    (src.agents.tools.quality_tool.build_quality_brief in the source branch this test came from) -
    the real QA vertical slice lives on `develop` with a different (repository-based) design that
    doesn't read Task rows this way, so it can't be called here. This only exercises
    executive_tool's aggregation/matching logic against a real, saved WorkspaceBrief row - same
    contract, same release_target-matching convention (critical open bug -> NOT_READY), nothing
    executive_tool.py itself needs to know is synthetic."""
    workspace_id = context.request.target_agent_workspace_id
    async with db_session.async_session_maker() as db:
        items = list(
            (await db.execute(select(Task).where(Task.agent_workspace_id == workspace_id))).scalars().all()
        )
        blocking = [
            item
            for item in items
            if item.work_item_type == "bug" and item.severity == "critical" and item.quality_status != "passed"
        ]
        readiness = ReleaseReadiness.NOT_READY if blocking else ReleaseReadiness.READY
        release_linked = [item for item in items if item.release_target]

        def _dict(item: Task) -> dict:
            return {
                "id": item.id,
                "title": item.title,
                "work_item_type": item.work_item_type,
                "severity": item.severity,
                "quality_status": item.quality_status,
                "release_target": item.release_target,
            }

        now = datetime.now(UTC)
        brief = WorkspaceBrief(
            brief_id=f"quality-brief-{uuid4()}",
            trace_id=context.trace_id,
            organization_workspace_id=context.actor.organization_workspace_id,
            agent_workspace_id=workspace_id,
            brief_type=BriefType.QUALITY,
            producer_profile=AgentProfile.QUALITY_ASSURANCE,
            period_start=now - timedelta(days=7),
            period_end=now,
            generated_at=now,
            expires_at=now + timedelta(hours=24),
            headline=f"Release {readiness.value}",
            facts=tuple(_dict(item) for item in items),
            dependencies=tuple(_dict(item) for item in release_linked),
            release_readiness=readiness,
        )
        await workspace_brief_service.save_brief(db, brief)


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
        db.add(Task(owner_id=alice.id, workspace_id=org_id, title="Blocked", agent_workspace_id=delivery_id, status="blocked"))
        db.add(
            Task(
                owner_id=alice.id,
                workspace_id=org_id,
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
    await _publish_quality_brief(quality_context)

    executive_context = await _executive_context(bob, org_id)
    async with db_session.async_session_maker() as db:
        result = await executive_tool.build_executive_brief(db, executive_context)

    brief = result.payload["executive_brief"]
    assert len(brief["workspace_brief_ids"]) == 2
    assert any(risk["severity"] == "high" for risk in brief["risks"])  # NOT_READY quality brief -> high risk


@pytest.mark.asyncio
async def test_get_workspace_briefs_alerts_admins_when_a_brief_is_stale(client, auth_headers, other_auth_headers, admin_auth_headers, monkeypatch):
    """Sprint 3 G6 fix: get_workspace_briefs must both report the staleness as a data_gap (already
    covered elsewhere) AND page admins via agent_audit_service.alert_brief_stale - proving the
    real call site is wired, not just the alert function in isolation
    (tests/test_services/test_agent_audit_service.py already covers that function alone)."""
    from datetime import UTC, datetime, timedelta
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from src.agents.contracts import BriefType, WorkspaceBrief
    from src.services import agent_audit_service, workspace_brief_service

    alice = await _user("alice@example.com")
    bob = await _user("bob@example.com")
    org_id, delivery_id, _quality_id = await _make_org_with_delivery_and_quality(alice.id, bob.id)

    generated_at = datetime.now(UTC) - timedelta(hours=48)
    stale_brief = WorkspaceBrief(
        brief_id=f"delivery-brief-{uuid4()}",
        trace_id="trace-stale",
        organization_workspace_id=org_id,
        agent_workspace_id=delivery_id,
        brief_type=BriefType.DELIVERY,
        producer_profile=AgentProfile.PRODUCT_DELIVERY,
        period_start=generated_at - timedelta(days=7),
        period_end=generated_at,
        generated_at=generated_at,
        expires_at=generated_at + timedelta(hours=24),  # 24h ago - already stale
        headline="Old brief",
    )
    async with db_session.async_session_maker() as db:
        await workspace_brief_service.save_brief(db, stale_brief)

    broadcast = AsyncMock()
    monkeypatch.setattr(agent_audit_service.manager, "broadcast_to_users", broadcast)

    executive_context = await _executive_context(bob, org_id)
    async with db_session.async_session_maker() as db:
        result = await executive_tool.get_workspace_briefs(db, executive_context)

    assert any("expired" in gap for gap in result.data_gaps)
    broadcast.assert_awaited_once()
    admin_ids, payload = broadcast.call_args.args
    admin_me = await client.get("/api/v1/auth/me", headers=admin_auth_headers)
    assert admin_me.json()["id"] in admin_ids
    assert payload["type"] == "workspace_brief_stale"
    assert payload["agent_workspace_id"] == delivery_id
    assert payload["brief_type"] == "delivery"


@pytest.mark.asyncio
async def test_get_cross_workspace_dependencies_matches_by_shared_release_target(auth_headers, other_auth_headers):
    alice = await _user("alice@example.com")
    bob = await _user("bob@example.com")
    org_id, delivery_id, quality_id = await _make_org_with_delivery_and_quality(alice.id, bob.id)

    async with db_session.async_session_maker() as db:
        db.add(Task(owner_id=alice.id, workspace_id=org_id, title="Ship login page", agent_workspace_id=delivery_id, status="in_progress", release_target="R1"))
        db.add(
            Task(
                owner_id=alice.id,
                workspace_id=org_id,
                title="Crash on save",
                agent_workspace_id=quality_id,
                work_item_type="bug",
                severity="critical",
                quality_status="open",
                release_target="R1",
            )
        )
        # A second, unrelated Quality bug with no release_target - must not match anything.
        db.add(Task(owner_id=alice.id, workspace_id=org_id, title="Unrelated bug", agent_workspace_id=quality_id, work_item_type="bug", severity="low", quality_status="open"))
        await db.commit()

    delivery_context = await _workspace_context(alice, org_id, delivery_id, AgentProfile.PRODUCT_DELIVERY, AgentIntent.DELIVERY_BRIEF)
    quality_context = await _workspace_context(alice, org_id, quality_id, AgentProfile.QUALITY_ASSURANCE, AgentIntent.QUALITY_READINESS)
    async with db_session.async_session_maker() as db:
        await delivery_tool.build_delivery_brief(db, delivery_context)
    await _publish_quality_brief(quality_context)

    executive_context = await _executive_context(bob, org_id)
    async with db_session.async_session_maker() as db:
        deps_result = await executive_tool.get_cross_workspace_dependencies(db, executive_context)

    deps = deps_result.payload["dependencies"]
    assert len(deps) == 1
    assert deps[0]["release_target"] == "R1"
    assert deps[0]["delivery_task_title"] == "Ship login page"
    assert deps[0]["quality_item_title"] == "Crash on save"
    assert deps[0]["quality_release_readiness"] == "NOT_READY"


@pytest.mark.asyncio
async def test_executive_brief_names_the_specific_delivery_item_at_risk(auth_headers, other_auth_headers):
    """The design brief's own example: "QA báo NOT_READY do critical bug, ảnh hưởng trực tiếp đến
    Delivery Milestone X" - not just a generic "release is NOT_READY" risk."""
    alice = await _user("alice@example.com")
    bob = await _user("bob@example.com")
    org_id, delivery_id, quality_id = await _make_org_with_delivery_and_quality(alice.id, bob.id)

    async with db_session.async_session_maker() as db:
        db.add(Task(owner_id=alice.id, workspace_id=org_id, title="Ship login page", agent_workspace_id=delivery_id, status="in_progress", release_target="R1"))
        db.add(
            Task(
                owner_id=alice.id,
                workspace_id=org_id,
                title="Crash on save",
                agent_workspace_id=quality_id,
                work_item_type="bug",
                severity="critical",
                quality_status="open",
                release_target="R1",
            )
        )
        await db.commit()

    delivery_context = await _workspace_context(alice, org_id, delivery_id, AgentProfile.PRODUCT_DELIVERY, AgentIntent.DELIVERY_BRIEF)
    quality_context = await _workspace_context(alice, org_id, quality_id, AgentProfile.QUALITY_ASSURANCE, AgentIntent.QUALITY_READINESS)
    async with db_session.async_session_maker() as db:
        await delivery_tool.build_delivery_brief(db, delivery_context)
    await _publish_quality_brief(quality_context)

    executive_context = await _executive_context(bob, org_id)
    async with db_session.async_session_maker() as db:
        result = await executive_tool.build_executive_brief(db, executive_context)

    brief = result.payload["executive_brief"]
    named_risks = [r for r in brief["risks"] if r.get("delivery_task_id")]
    assert len(named_risks) == 1
    assert "Crash on save" in named_risks[0]["text"]
    assert "Ship login page" in named_risks[0]["text"]
    assert "NOT_READY" in named_risks[0]["text"]
    assert named_risks[0]["severity"] == "high"
    # Only the specific, named risk - the generic per-brief fallback must not also fire for the
    # same quality brief (would double-report the same NOT_READY release).
    assert len(brief["risks"]) == 1
    assert len(brief["cross_workspace_dependencies"]) == 1


@pytest.mark.asyncio
async def test_non_executive_viewer_is_denied_aggregate_scope(auth_headers, other_auth_headers):
    """alice is only a lead (member/lead role), never granted executive_viewer anywhere - the
    AGGREGATE route must deny her, not silently show her own workspaces' briefs."""
    alice = await _user("alice@example.com")
    bob = await _user("bob@example.com")
    org_id, _delivery_id, _quality_id = await _make_org_with_delivery_and_quality(alice.id, bob.id)

    context = await _executive_context(alice, org_id)
    assert context.authorization.decision.value == "DENY"
