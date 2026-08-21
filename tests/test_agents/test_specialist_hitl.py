"""End-to-end HITL flow for the specialist (product_delivery/quality_assurance/executive) agents'
propose_*_reminder/propose_*_meeting tools - Sprint 3's real interrupt()/resume wiring
(src.api.routes._run_specialist_chat + _resume_specialist_action), reusing the exact same
reminder_service.schedule_reminder/calendar_service.create_event services the Personal agent's own
already-shipped calendar/reminder HITL flow calls, never a parallel implementation."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

import src.db.session as db_session
from src.db.models import AgentWorkspace, AgentWorkspaceMembership, Reminder, User, Workspace, WorkspaceMembership

_ORG_ID = "hitl-test-org"
_DELIVERY_WS_ID = "hitl-test-delivery"


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
