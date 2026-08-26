from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from src.config import get_settings
from src.db import session as db_session
from src.db.models import Task
from src.services import calendar_service, reminder_service


async def _create_proactive_task(client, auth_headers, *, title, due_at=None):
    created = (
        await client.post(
            "/api/v1/tasks",
            json={"title": title, "due_at": due_at, "source": "manual"},
            headers=auth_headers,
        )
    ).json()
    async with db_session.async_session_maker() as db:
        task = (await db.execute(select(Task).where(Task.id == created["id"]))).scalar_one()
        task.source = "proactive"
        task.status = "suggested"
        await db.commit()
    tasks = (await client.get("/api/v1/tasks", headers=auth_headers)).json()
    return next(task for task in tasks if task["id"] == created["id"])


@pytest.mark.asyncio
async def test_create_and_list_task(client, auth_headers):
    resp = await client.post(
        "/api/v1/tasks", json={"title": "Send report", "priority": "High"}, headers=auth_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Send report"
    assert body["priority"] == "High"
    assert body["status"] == "pending"
    assert body["source"] == "manual"
    assert body["source"] == "manual"

    resp = await client.get("/api/v1/tasks", headers=auth_headers)
    assert resp.status_code == 200
    titles = [t["title"] for t in resp.json()]
    assert "Send report" in titles


@pytest.mark.asyncio
async def test_tasks_require_auth(client):
    resp = await client.get("/api/v1/tasks")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_update_task_status(client, auth_headers):
    created = (
        await client.post("/api/v1/tasks", json={"title": "Book flight"}, headers=auth_headers)
    ).json()

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_delete_task(client, auth_headers):
    created = (
        await client.post("/api/v1/tasks", json={"title": "Throwaway"}, headers=auth_headers)
    ).json()

    resp = await client.delete(f"/api/v1/tasks/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get("/api/v1/tasks", headers=auth_headers)
    assert created["id"] not in [t["id"] for t in resp.json()]


@pytest.mark.asyncio
async def test_task_not_visible_to_other_user(client, auth_headers, other_auth_headers):
    created = (
        await client.post("/api/v1/tasks", json={"title": "Private task"}, headers=auth_headers)
    ).json()

    resp = await client.get("/api/v1/tasks", headers=other_auth_headers)
    assert created["id"] not in [t["id"] for t in resp.json()]

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "dismissed"}, headers=other_auth_headers
    )
    assert resp.status_code == 404

    resp = await client.delete(f"/api/v1/tasks/{created['id']}", headers=other_auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_task_with_naive_due_at_is_localized_to_calendar_timezone(client, auth_headers):
    """A due_at with no UTC offset (what the LLM emits, e.g. via AIPanel's "Extract tasks" posting
    it straight to this endpoint) must be interpreted as calendar_timezone - not left for
    Postgres/asyncpg to guess from the DB server's own session timezone, which only happens to
    match by coincidence on any given machine. Regression test for task_routes.py::create_task."""
    resp = await client.post(
        "/api/v1/tasks",
        json={"title": "Naive due date", "due_at": "2026-08-10T15:00:00", "priority": "Medium"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    due_at = datetime.fromisoformat(resp.json()["due_at"])
    assert due_at.tzinfo is not None
    assert due_at == datetime(2026, 8, 10, 15, 0, tzinfo=ZoneInfo(get_settings().calendar_timezone))


@pytest.mark.asyncio
async def test_create_task_with_offset_due_at_is_kept_as_is(client, auth_headers):
    """A due_at that already carries an explicit UTC offset must not be re-localized/shifted."""
    resp = await client.post(
        "/api/v1/tasks",
        json={"title": "Explicit offset due date", "due_at": "2026-08-10T15:00:00+00:00", "priority": "Medium"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    due_at = datetime.fromisoformat(resp.json()["due_at"])
    assert due_at == datetime(2026, 8, 10, 15, 0, tzinfo=ZoneInfo("UTC"))


@pytest.mark.asyncio
async def test_tasks_sorted_by_due_date_then_priority(client, auth_headers):
    await client.post(
        "/api/v1/tasks",
        json={"title": "No due date", "priority": "High"},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/tasks",
        json={"title": "Due soon", "due_at": "2026-01-01T00:00:00Z", "priority": "Low"},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/tasks",
        json={"title": "Due later", "due_at": "2026-06-01T00:00:00Z", "priority": "High"},
        headers=auth_headers,
    )

    resp = await client.get("/api/v1/tasks", headers=auth_headers)
    titles = [t["title"] for t in resp.json()]
    assert titles == ["Due soon", "Due later", "No due date"]


@pytest.mark.asyncio
async def test_accepting_proactive_task_auto_syncs_calendar_and_reminder(
    client, auth_headers, monkeypatch
):
    """Product decision: Accept on an AI-suggested task IS the human confirmation to both write
    the matching Google Calendar event AND schedule a Reminder for the same due_at - no separate
    dialog for either. (Reminders created this way still fire through the normal reminder flow;
    this only skips the confirmation step, matching the same "Accept = confirm" reasoning already
    applied to Calendar sync.)"""
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-1", "htmlLink": "https://calendar.google.com/event?eid=evt1",
    }
    monkeypatch.setattr(calendar_service, "get_calendar_service", lambda: fake_service)

    created = await _create_proactive_task(
        client, auth_headers, title="Product launch call", due_at="2026-12-10T15:00:00"
    )
    assert created["status"] == "suggested"

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["calendar_event_id"] == "evt-1"
    assert body["reminder_id"] is not None

    fake_service.events.return_value.insert.assert_called_once()
    call_kwargs = fake_service.events.return_value.insert.call_args.kwargs
    assert call_kwargs["body"]["summary"] == "Product launch call"
    assert call_kwargs["body"]["start"]["dateTime"] == "2026-12-10T15:00:00+07:00"
    assert call_kwargs["body"]["end"]["dateTime"] == "2026-12-10T15:30:00+07:00"

    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    reminder = next(r for r in reminders if r["title"] == "Product launch call")
    assert reminder["id"] == body["reminder_id"]
    assert reminder["due_at"].startswith("2026-12-10T15:00:00")
    assert reminder["source"] == "proactive"


@pytest.mark.asyncio
async def test_accepting_manual_task_does_not_touch_calendar_or_reminder(client, auth_headers, monkeypatch):
    fake_service = MagicMock()
    monkeypatch.setattr(calendar_service, "get_calendar_service", lambda: fake_service)

    created = (
        await client.post(
            "/api/v1/tasks",
            json={"title": "Manual with due date", "due_at": "2026-08-10T15:00:00", "source": "manual"},
            headers=auth_headers,
        )
    ).json()

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200
    fake_service.events.return_value.insert.assert_not_called()
    assert resp.json()["reminder_id"] is None
    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    assert not any(r["title"] == "Manual with due date" for r in reminders)


@pytest.mark.asyncio
async def test_accepting_proactive_task_without_due_date_does_not_touch_calendar_or_reminder(
    client, auth_headers, monkeypatch
):
    fake_service = MagicMock()
    monkeypatch.setattr(calendar_service, "get_calendar_service", lambda: fake_service)

    created = await _create_proactive_task(client, auth_headers, title="No due date")
    assert created["due_at"] is None

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200
    fake_service.events.return_value.insert.assert_not_called()
    assert resp.json()["reminder_id"] is None
    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    assert not any(r["title"] == "No due date" for r in reminders)


@pytest.mark.asyncio
async def test_accepting_proactive_task_survives_calendar_sync_failure(client, auth_headers, monkeypatch):
    """Calendar and Reminder sync on Accept are independent, best-effort actions: a broken Google
    API must not stop Accept from succeeding, and must not stop the Reminder sync from still
    happening."""

    def _broken_get_calendar_service():
        raise RuntimeError("Google API unreachable")

    monkeypatch.setattr(calendar_service, "get_calendar_service", _broken_get_calendar_service)

    created = await _create_proactive_task(
        client, auth_headers, title="Flaky calendar", due_at="2026-12-10T15:00:00"
    )

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["calendar_event_id"] is None
    assert body["reminder_id"] is not None

    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    assert any(r["title"] == "Flaky calendar" for r in reminders)


@pytest.mark.asyncio
async def test_accepting_proactive_task_survives_reminder_sync_failure(client, auth_headers, monkeypatch):
    """Same independence the other direction: a broken Reminder sync must not stop Accept from
    succeeding, and must not stop the Calendar sync from still happening."""
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-2", "htmlLink": "https://calendar.google.com/event?eid=evt2",
    }
    monkeypatch.setattr(calendar_service, "get_calendar_service", lambda: fake_service)

    async def _broken_schedule_reminder(**kwargs):
        raise RuntimeError("Reminder scheduler unreachable")

    monkeypatch.setattr(reminder_service, "schedule_reminder", _broken_schedule_reminder)

    created = await _create_proactive_task(
        client, auth_headers, title="Flaky reminder", due_at="2026-12-10T15:00:00"
    )

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["calendar_event_id"] == "evt-2"
    assert body["reminder_id"] is None

    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    assert not any(r["title"] == "Flaky reminder" for r in reminders)


@pytest.mark.asyncio
async def test_accepting_proactive_task_with_past_due_date_skips_reminder_sync(
    client, auth_headers, monkeypatch
):
    """schedule_reminder rejects a due_at too close to (or past) now - this must be silently
    skipped, same as any other reminder-sync failure, never surfaced as a failed Accept."""
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-3", "htmlLink": "https://calendar.google.com/event?eid=evt3",
    }
    monkeypatch.setattr(calendar_service, "get_calendar_service", lambda: fake_service)

    created = await _create_proactive_task(
        client, auth_headers, title="Already due", due_at="2026-01-01T09:00:00"
    )

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["calendar_event_id"] == "evt-3"
    assert body["reminder_id"] is None


@pytest.mark.asyncio
async def test_accepting_proactive_task_due_soon_still_gets_a_reminder(client, auth_headers, monkeypatch):
    """A due_at only minutes away must not lose its reminder just because the default 30-minute
    lead would push the notification time into the past - the lead should shrink instead of the
    reminder disappearing. Uses a due_at relative to real now (not a fixed date) since this test is
    specifically about that near-term boundary."""
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-4", "htmlLink": "https://calendar.google.com/event?eid=evt4",
    }
    monkeypatch.setattr(calendar_service, "get_calendar_service", lambda: fake_service)

    # Naive, no explicit offset - same convention as every other due_at fixture in this file
    # (matching how a real AI-extracted due_at arrives, per create_task's own comment); it's
    # interpreted as calendar_timezone (Asia/Ho_Chi_Minh) wall-clock time.
    due_at_local = datetime.now(ZoneInfo(get_settings().calendar_timezone)) + timedelta(minutes=10)
    due_at_local = due_at_local.replace(microsecond=0)
    created = await _create_proactive_task(
        client, auth_headers, title="Ăn tối", due_at=due_at_local.replace(tzinfo=None).isoformat()
    )

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["calendar_event_id"] == "evt-4"
    assert body["reminder_id"] is not None

    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    reminder = next(r for r in reminders if r["title"] == "Ăn tối")
    # SQLite (this test DB) doesn't reliably round-trip tzinfo on DateTime(timezone=True) columns -
    # a naive result here means "Asia/Ho_Chi_Minh wall clock", same assumption applied to due_at
    # above and throughout this codebase's own naive-datetime handling.
    tz = ZoneInfo(get_settings().calendar_timezone)

    def _aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=tz)

    fire_at = _aware(datetime.fromisoformat(reminder["fire_at"]))
    due_at_aware = _aware(due_at_local)
    assert datetime.now(UTC) < fire_at < due_at_aware


@pytest.mark.asyncio
async def test_deleting_synced_calendar_event_dismisses_the_linked_task(client, auth_headers, monkeypatch):
    """Task <-> Calendar sync is two-way: once Accept auto-created a Calendar event for a task
    (see the accept test above), deleting that event - from the app's own Delete event button, or
    detected from Google Calendar itself via poll_calendar_changes - must not leave the task
    looking like it's still awaiting the user's attention."""
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-linked", "htmlLink": "https://calendar.google.com/event?eid=evtlinked",
    }
    monkeypatch.setattr(calendar_service, "get_calendar_service", lambda: fake_service)

    created = await _create_proactive_task(
        client, auth_headers, title="Họp ngày mai", due_at="2026-08-25T09:00:00"
    )
    accepted = (
        await client.patch(
            f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
        )
    ).json()
    assert accepted["calendar_event_id"] == "evt-linked"

    user_id = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()["id"]
    # Exercises exactly what calendar_routes.delete_event and poll_calendar_changes both call once
    # Google confirms the event is gone - no need to re-mock the Google client for this part.
    await calendar_service.broadcast_change(user_id, "calendar_event_deleted", {"event_id": "evt-linked"})

    tasks = (await client.get("/api/v1/tasks", headers=auth_headers)).json()
    task = next(t for t in tasks if t["id"] == created["id"])
    assert task["status"] == "dismissed"
    assert task["calendar_event_id"] is None
