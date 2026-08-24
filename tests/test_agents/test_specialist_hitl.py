"""End-to-end HITL flow for the specialist (product_delivery/quality_assurance/executive) agents'
propose_*_reminder/propose_*_meeting tools - Sprint 3's real interrupt()/resume wiring
(src.api.routes._run_specialist_chat + _resume_specialist_action), reusing the exact same
reminder_service.schedule_reminder/calendar_service.create_event services the Personal agent's own
already-shipped calendar/reminder HITL flow calls, never a parallel implementation."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

import src.db.session as db_session
from src.db.models import (
    AgentActionProposal,
    AgentWorkspace,
    AgentWorkspaceMembership,
    Reminder,
    Task,
    User,
    Workspace,
    WorkspaceMembership,
)

_ORG_ID = "hitl-test-org"
_DELIVERY_WS_ID = "hitl-test-delivery"
_QUALITY_WS_ID = "hitl-test-quality"


def _enable_flags(monkeypatch) -> None:
    from src.api import routes

    settings = routes.get_settings().model_copy(
        update={"multi_agent_enabled": True, "product_delivery_agent_enabled": True}
    )
    monkeypatch.setattr(routes, "get_settings", lambda: settings)


async def _seed_delivery_lead() -> str:
    async with db_session.async_session_maker() as db:
        alice = (await db.execute(select(User).where(User.email == "alice@example.com"))).scalar_one()
        db.add(Workspace(id=_ORG_ID, type="organization", name="HITL Test Org"))
        await db.flush()
        db.add(WorkspaceMembership(workspace_id=_ORG_ID, user_id=alice.id, role="member", status="active"))
        db.add(
            AgentWorkspace(
                id=_DELIVERY_WS_ID, organization_workspace_id=_ORG_ID, key="delivery", name="Delivery", agent_profile="product_delivery"
            )
        )
        await db.flush()
        db.add(AgentWorkspaceMembership(agent_workspace_id=_DELIVERY_WS_ID, user_id=alice.id, business_role="lead", status="active"))
        await db.commit()
        return alice.id


@pytest.mark.asyncio
async def test_propose_reminder_then_confirm_creates_a_real_reminder(client, auth_headers, monkeypatch):
    _enable_flags(monkeypatch)
    await _seed_delivery_lead()

    propose_resp = await client.post(
        "/api/v1/chat",
        json={
            "message": "Nhắc tôi follow up",
            "requested_scope": "workspace",
            "target_agent_workspace_id": _DELIVERY_WS_ID,
            "specialist_action": {"kind": "propose_reminder", "title": "Follow up blocked task", "due_at": "2026-09-01T09:00:00+07:00"},
        },
        headers=auth_headers,
    )
    assert propose_resp.status_code == 200
    propose_data = propose_resp.json()
    assert propose_data["status"] == "interrupted"
    assert propose_data["interrupt"]["type"] == "delivery_reminder"
    assert propose_data["interrupt"]["draft"]["title"] == "Follow up blocked task"
    thread_id = propose_data["thread_id"]

    async with db_session.async_session_maker() as db:
        assert (await db.execute(select(Reminder))).scalars().all() == []  # nothing created before confirm

    resume_resp = await client.post("/api/v1/chat/resume", json={"thread_id": thread_id, "approved": True}, headers=auth_headers)
    assert resume_resp.status_code == 200
    resume_data = resume_resp.json()
    assert resume_data["status"] == "completed"
    assert "Follow up blocked task" in resume_data["response"]

    async with db_session.async_session_maker() as db:
        reminders = (await db.execute(select(Reminder))).scalars().all()
    assert len(reminders) == 1
    assert reminders[0].title == "Follow up blocked task"
    assert reminders[0].source == "agent"


async def _seed_quality_lead() -> str:
    async with db_session.async_session_maker() as db:
        alice = (await db.execute(select(User).where(User.email == "alice@example.com"))).scalar_one()
        db.add(Workspace(id=_ORG_ID, type="organization", name="HITL Test Org"))
        await db.flush()
        db.add(WorkspaceMembership(workspace_id=_ORG_ID, user_id=alice.id, role="member", status="active"))
        db.add(
            AgentWorkspace(
                id=_QUALITY_WS_ID, organization_workspace_id=_ORG_ID, key="quality", name="Quality", agent_profile="quality_assurance"
            )
        )
        await db.flush()
        db.add(AgentWorkspaceMembership(agent_workspace_id=_QUALITY_WS_ID, user_id=alice.id, business_role="lead", status="active"))
        db.add(
            Task(
                owner_id=alice.id, workspace_id=_ORG_ID, agent_workspace_id=_QUALITY_WS_ID,
                title="Login crashes", work_item_type="bug", severity="critical", quality_status="open",
            )
        )
        await db.commit()
        return alice.id


@pytest.mark.asyncio
async def test_quality_brief_read_via_chat_returns_not_ready(client, auth_headers, monkeypatch):
    """Proves Quality Assurance is actually wired into _SPECIALIST_BRIEF_TOOL - previously this
    request unconditionally returned status="error" with "chưa sẵn sàng cho luồng chat này."
    regardless of the feature flag (see src.api.routes._run_specialist_chat's now-removed QA
    special case)."""
    from src.api import routes

    settings = routes.get_settings().model_copy(
        update={"multi_agent_enabled": True, "quality_assurance_agent_enabled": True}
    )
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    await _seed_quality_lead()

    resp = await client.post(
        "/api/v1/chat",
        json={"message": "Release đã sẵn sàng chưa?", "requested_scope": "workspace", "target_agent_workspace_id": _QUALITY_WS_ID},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "NOT_READY" in data["response"]
    assert data["workspace_brief"]["brief_type"] == "quality"
    assert data["workspace_brief"]["release_readiness"] == "NOT_READY"


@pytest.mark.asyncio
async def test_quality_propose_reminder_then_confirm_creates_a_real_reminder(client, auth_headers, monkeypatch):
    from src.api import routes

    settings = routes.get_settings().model_copy(
        update={"multi_agent_enabled": True, "quality_assurance_agent_enabled": True}
    )
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    await _seed_quality_lead()

    propose_resp = await client.post(
        "/api/v1/chat",
        json={
            "message": "Nhắc tôi",
            "requested_scope": "workspace",
            "target_agent_workspace_id": _QUALITY_WS_ID,
            "specialist_action": {"kind": "propose_reminder", "title": "Chase critical bug", "due_at": "2026-09-01T09:00:00+07:00"},
        },
        headers=auth_headers,
    )
    assert propose_resp.status_code == 200
    propose_data = propose_resp.json()
    assert propose_data["status"] == "interrupted"
    assert propose_data["interrupt"]["type"] == "quality_reminder"
    assert propose_data["proposal"]["action"] == "preview_quality_reminder"
    thread_id = propose_data["thread_id"]

    resume_resp = await client.post("/api/v1/chat/resume", json={"thread_id": thread_id, "approved": True}, headers=auth_headers)
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "completed"

    async with db_session.async_session_maker() as db:
        reminders = (await db.execute(select(Reminder))).scalars().all()
    assert len(reminders) == 1
    assert reminders[0].title == "Chase critical bug"


@pytest.mark.asyncio
async def test_reject_creates_nothing(client, auth_headers, monkeypatch):
    _enable_flags(monkeypatch)
    await _seed_delivery_lead()

    propose_resp = await client.post(
        "/api/v1/chat",
        json={
            "message": "Nhắc tôi",
            "requested_scope": "workspace",
            "target_agent_workspace_id": _DELIVERY_WS_ID,
            "specialist_action": {"kind": "propose_reminder", "title": "Something", "due_at": "2026-09-01T09:00:00+07:00"},
        },
        headers=auth_headers,
    )
    thread_id = propose_resp.json()["thread_id"]

    resume_resp = await client.post("/api/v1/chat/resume", json={"thread_id": thread_id, "approved": False}, headers=auth_headers)
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "completed"
    assert "huỷ" in resume_resp.json()["response"]

    async with db_session.async_session_maker() as db:
        assert (await db.execute(select(Reminder))).scalars().all() == []


@pytest.mark.asyncio
async def test_double_confirm_does_not_create_a_second_reminder(client, auth_headers, monkeypatch):
    """A double-click on "Xác nhận" (or a retried request after a dropped response) must not
    create two reminders - hitl_executor's own idempotency_key check makes the second confirm a
    no-op that replays the same result, proving _resume_specialist_action's deliberate choice not
    to pop the proposal on a successful approve (see its own docstring)."""
    _enable_flags(monkeypatch)
    await _seed_delivery_lead()

    propose_resp = await client.post(
        "/api/v1/chat",
        json={
            "message": "Nhắc tôi",
            "requested_scope": "workspace",
            "target_agent_workspace_id": _DELIVERY_WS_ID,
            "specialist_action": {"kind": "propose_reminder", "title": "Only once", "due_at": "2026-09-01T09:00:00+07:00"},
        },
        headers=auth_headers,
    )
    thread_id = propose_resp.json()["thread_id"]

    first = await client.post("/api/v1/chat/resume", json={"thread_id": thread_id, "approved": True}, headers=auth_headers)
    second = await client.post("/api/v1/chat/resume", json={"thread_id": thread_id, "approved": True}, headers=auth_headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["response"] == second.json()["response"]

    async with db_session.async_session_maker() as db:
        reminders = (await db.execute(select(Reminder))).scalars().all()
    assert len(reminders) == 1


@pytest.mark.asyncio
async def test_a_different_user_cannot_confirm_someone_elses_proposal(client, auth_headers, other_auth_headers, monkeypatch):
    _enable_flags(monkeypatch)
    await _seed_delivery_lead()

    propose_resp = await client.post(
        "/api/v1/chat",
        json={
            "message": "Nhắc tôi",
            "requested_scope": "workspace",
            "target_agent_workspace_id": _DELIVERY_WS_ID,
            "specialist_action": {"kind": "propose_reminder", "title": "Alice's reminder", "due_at": "2026-09-01T09:00:00+07:00"},
        },
        headers=auth_headers,
    )
    thread_id = propose_resp.json()["thread_id"]

    resp = await client.post("/api/v1/chat/resume", json={"thread_id": thread_id, "approved": True}, headers=other_auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_propose_meeting_then_confirm_creates_a_real_calendar_event(client, auth_headers, monkeypatch):
    from src.services import calendar_service

    _enable_flags(monkeypatch)
    await _seed_delivery_lead()

    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt-hitl-1"}
    monkeypatch.setattr(calendar_service, "_service", AsyncMock(return_value=fake_service))

    propose_resp = await client.post(
        "/api/v1/chat",
        json={
            "message": "Đặt lịch họp",
            "requested_scope": "workspace",
            "target_agent_workspace_id": _DELIVERY_WS_ID,
            "specialist_action": {"kind": "propose_meeting", "title": "Release sync", "starts_at": "2026-09-01T10:00:00+07:00"},
        },
        headers=auth_headers,
    )
    assert propose_resp.status_code == 200
    propose_data = propose_resp.json()
    assert propose_data["status"] == "interrupted"
    assert propose_data["interrupt"]["type"] == "delivery_meeting"
    thread_id = propose_data["thread_id"]

    resume_resp = await client.post("/api/v1/chat/resume", json={"thread_id": thread_id, "approved": True}, headers=auth_headers)
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "completed"
    assert "Release sync" in resume_resp.json()["response"]
    fake_service.events.return_value.insert.assert_called_once()


@pytest.mark.asyncio
async def test_executive_profile_rejects_propose_reminder_cleanly(client, auth_headers, monkeypatch):
    """Executive has no propose_*_reminder tool (only propose_executive_meeting) - must be a clean
    error, not a crash or a silently-wrong brief. Caught before any AgentWorkspace membership
    check even runs (_run_specialist_chat validates (profile, action.kind) before calling
    route_agent_request) - alice only needs the plain org membership _seed_delivery_lead already
    gives her, nothing executive_viewer-specific."""
    from src.api import routes

    settings = routes.get_settings().model_copy(update={"multi_agent_enabled": True, "executive_agent_enabled": True})
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    await _seed_delivery_lead()

    resp = await client.post(
        "/api/v1/chat",
        json={
            "message": "Nhắc tôi",
            "requested_scope": "aggregate",
            "specialist_action": {"kind": "propose_reminder", "title": "x", "due_at": "2026-09-01T09:00:00+07:00"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


@pytest.mark.asyncio
async def test_pending_proposal_is_persisted_to_the_database(client, auth_headers, monkeypatch):
    """The 3 hardening fixes below all depend on a pending proposal being real, queryable DB
    state (src.db.models.AgentActionProposal) instead of the old in-memory dict - this proves the
    write actually happens and carries the routing metadata resume-time re-auth needs."""
    _enable_flags(monkeypatch)
    await _seed_delivery_lead()

    propose_resp = await client.post(
        "/api/v1/chat",
        json={
            "message": "Nhắc tôi",
            "requested_scope": "workspace",
            "target_agent_workspace_id": _DELIVERY_WS_ID,
            "specialist_action": {"kind": "propose_reminder", "title": "Durable", "due_at": "2026-09-01T09:00:00+07:00"},
        },
        headers=auth_headers,
    )
    thread_id = propose_resp.json()["thread_id"]

    async with db_session.async_session_maker() as db:
        row = await db.get(AgentActionProposal, thread_id)
    assert row is not None
    assert row.status == "pending"
    assert row.organization_workspace_id == _ORG_ID
    assert row.agent_profile == "product_delivery"
    assert row.requested_scope == "workspace"
    assert row.target_agent_workspace_id == _DELIVERY_WS_ID


@pytest.mark.asyncio
async def test_revoked_membership_between_propose_and_confirm_is_rejected(client, auth_headers, monkeypatch):
    """Re-authorization at resume (not just at propose time): alice's AgentWorkspace membership is
    revoked *after* the proposal was drafted but *before* she confirms it - the confirm must be
    denied and must not create the reminder, proving _resume_specialist_action re-resolves scope
    instead of trusting the snapshot from when the proposal was drafted."""
    _enable_flags(monkeypatch)
    await _seed_delivery_lead()

    propose_resp = await client.post(
        "/api/v1/chat",
        json={
            "message": "Nhắc tôi",
            "requested_scope": "workspace",
            "target_agent_workspace_id": _DELIVERY_WS_ID,
            "specialist_action": {"kind": "propose_reminder", "title": "Revoke me", "due_at": "2026-09-01T09:00:00+07:00"},
        },
        headers=auth_headers,
    )
    thread_id = propose_resp.json()["thread_id"]

    async with db_session.async_session_maker() as db:
        membership = (
            await db.execute(
                select(AgentWorkspaceMembership).where(AgentWorkspaceMembership.agent_workspace_id == _DELIVERY_WS_ID)
            )
        ).scalar_one()
        membership.status = "revoked"
        await db.commit()

    resume_resp = await client.post("/api/v1/chat/resume", json={"thread_id": thread_id, "approved": True}, headers=auth_headers)
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "error"

    async with db_session.async_session_maker() as db:
        assert (await db.execute(select(Reminder))).scalars().all() == []
        row = await db.get(AgentActionProposal, thread_id)
    assert row.status == "rejected"  # closed, not left "pending" for a retry to slip through

    # A retry against the same (now-closed) thread_id must not resurrect it either.
    retry_resp = await client.post("/api/v1/chat/resume", json={"thread_id": thread_id, "approved": True}, headers=auth_headers)
    assert retry_resp.status_code == 404


@pytest.mark.asyncio
async def test_propose_meeting_rejects_attendee_outside_the_organization(client, auth_headers, other_auth_headers, monkeypatch):
    """attendee_ids must be restricted to active members of the SAME organization - bob is never
    added to _ORG_ID, so inviting him must fail the proposal outright (not silently drop him, and
    not create a calendar event with an unscoped invitee)."""
    from src.services import calendar_service

    _enable_flags(monkeypatch)
    await _seed_delivery_lead()
    # other_auth_headers registers bob's account without adding him to _ORG_ID - that's the point.
    _ = other_auth_headers
    async with db_session.async_session_maker() as db:
        bob_id = (await db.execute(select(User.id).where(User.email == "bob@example.com"))).scalar_one()

    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt-should-not-happen"}
    monkeypatch.setattr(calendar_service, "_service", AsyncMock(return_value=fake_service))

    propose_resp = await client.post(
        "/api/v1/chat",
        json={
            "message": "Đặt lịch họp",
            "requested_scope": "workspace",
            "target_agent_workspace_id": _DELIVERY_WS_ID,
            "specialist_action": {
                "kind": "propose_meeting",
                "title": "Should be blocked",
                "starts_at": "2026-09-01T10:00:00+07:00",
                "attendee_ids": [bob_id],
            },
        },
        headers=auth_headers,
    )
    assert propose_resp.status_code == 200
    body = propose_resp.json()
    assert body["status"] == "error"
    fake_service.events.return_value.insert.assert_not_called()


@pytest.mark.asyncio
async def test_propose_meeting_allows_attendee_inside_the_organization(client, auth_headers, other_auth_headers, monkeypatch):
    """Positive case for the same scoping rule - once bob is a real active member of _ORG_ID
    (cross-department invites are legitimate, see validate_attendee_ids's own docstring), inviting
    him must succeed end-to-end."""
    from src.services import calendar_service

    _enable_flags(monkeypatch)
    await _seed_delivery_lead()
    _ = other_auth_headers
    async with db_session.async_session_maker() as db:
        bob_id = (await db.execute(select(User.id).where(User.email == "bob@example.com"))).scalar_one()
        db.add(WorkspaceMembership(workspace_id=_ORG_ID, user_id=bob_id, role="member", status="active"))
        await db.commit()

    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt-attendee-ok"}
    monkeypatch.setattr(calendar_service, "_service", AsyncMock(return_value=fake_service))

    propose_resp = await client.post(
        "/api/v1/chat",
        json={
            "message": "Đặt lịch họp",
            "requested_scope": "workspace",
            "target_agent_workspace_id": _DELIVERY_WS_ID,
            "specialist_action": {
                "kind": "propose_meeting",
                "title": "Cross-team sync",
                "starts_at": "2026-09-01T10:00:00+07:00",
                "attendee_ids": [bob_id],
            },
        },
        headers=auth_headers,
    )
    assert propose_resp.status_code == 200
    thread_id = propose_resp.json()["thread_id"]
    assert propose_resp.json()["status"] == "interrupted"

    resume_resp = await client.post("/api/v1/chat/resume", json={"thread_id": thread_id, "approved": True}, headers=auth_headers)
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "completed"
    fake_service.events.return_value.insert.assert_called_once()
