from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from src.config import get_settings
from src.services import calendar_service


@pytest.mark.asyncio
async def test_create_and_list_task(client, auth_headers):
    resp = await client.post(
        "/api/v1/tasks", json={"title": "Send report", "priority": "High"}, headers=auth_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Send report"
    assert body["priority"] == "High"
    assert body["status"] == "suggested"
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
async def test_accepting_proactive_task_with_due_date_creates_calendar_event_and_reminder(
    client, auth_headers, monkeypatch
):
    """Accept is the human confirmation - a proactively-suggested task with a due date, once
    accepted, also becomes a real Calendar event and a real Reminder without a separate interrupt()
    step for either."""
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-1", "htmlLink": "https://calendar.google.com/event?eid=evt1",
    }
    monkeypatch.setattr(calendar_service, "_service", AsyncMock(return_value=fake_service))

    created = (
        await client.post(
            "/api/v1/tasks",
            json={"title": "Product launch call", "due_at": "2026-08-10T15:00:00", "source": "proactive"},
            headers=auth_headers,
        )
    ).json()
    assert created["status"] == "suggested"

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    fake_service.events.return_value.insert.assert_called_once()
    call_body = fake_service.events.return_value.insert.call_args.kwargs["body"]
    assert call_body["summary"] == "Product launch call"

    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    assert any(r["title"] == "Product launch call" and r["source"] == "proactive" for r in reminders)


@pytest.mark.asyncio
async def test_accepting_manual_task_does_not_touch_calendar_or_reminder(client, auth_headers, monkeypatch):
    fake_service = MagicMock()
    monkeypatch.setattr(calendar_service, "_service", AsyncMock(return_value=fake_service))

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


@pytest.mark.asyncio
async def test_accepting_proactive_task_without_due_date_does_not_touch_calendar_or_reminder(
    client, auth_headers, monkeypatch
):
    fake_service = MagicMock()
    monkeypatch.setattr(calendar_service, "_service", AsyncMock(return_value=fake_service))

    created = (
        await client.post(
            "/api/v1/tasks", json={"title": "No due date", "source": "proactive"}, headers=auth_headers
        )
    ).json()
    assert created["due_at"] is None

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200
    fake_service.events.return_value.insert.assert_not_called()


@pytest.mark.asyncio
async def test_accepting_proactive_task_survives_calendar_failure(client, auth_headers, monkeypatch):
    """Best-effort: a Google Calendar failure must not block the task itself from being accepted."""

    monkeypatch.setattr(
        calendar_service, "_service", AsyncMock(side_effect=RuntimeError("Google API unreachable"))
    )

    created = (
        await client.post(
            "/api/v1/tasks",
            json={"title": "Flaky calendar", "due_at": "2026-08-10T15:00:00", "source": "proactive"},
            headers=auth_headers,
        )
    ).json()

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    assert any(r["title"] == "Flaky calendar" for r in reminders)


# ---------------------------------------------------------------- POST /tasks/{id}/accept


def _fake_calendar_service(monkeypatch, *, existing_events: list[dict] | None = None) -> MagicMock:
    """A fake Google Calendar client: events().list().execute() returns `existing_events` (for
    find_conflicts/suggest_alternative_slots), events().insert().execute() returns a fake created
    event (for create_event) - independent mocks on the same events() return value, same pattern
    as the calendar-accept tests above."""
    fake_service = MagicMock()
    fake_service.events.return_value.list.return_value.execute.return_value = {"items": existing_events or []}
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-1", "htmlLink": "https://calendar.google.com/event?eid=evt1",
    }
    monkeypatch.setattr(calendar_service, "_service", AsyncMock(return_value=fake_service))
    return fake_service


@pytest.mark.asyncio
async def test_accept_task_no_conflict_creates_calendar_event_and_reminder(client, auth_headers, monkeypatch):
    fake_service = _fake_calendar_service(monkeypatch)
    created = (
        await client.post(
            "/api/v1/tasks",
            json={"title": "Sprint planning", "due_at": "2026-08-10T15:00:00", "source": "proactive"},
            headers=auth_headers,
        )
    ).json()

    resp = await client.post(f"/api/v1/tasks/{created['id']}/accept", json={}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["conflict"] is False
    assert body["task"]["status"] == "pending"
    fake_service.events.return_value.insert.assert_called_once()

    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    assert any(r["title"] == "Sprint planning" for r in reminders)


@pytest.mark.asyncio
async def test_accept_task_reports_conflict_without_changing_anything(client, auth_headers, monkeypatch):
    """A conflicting event at the same time must block the accept - task stays "suggested", no
    Calendar event or Reminder gets created - until the caller resolves it."""
    fake_service = _fake_calendar_service(monkeypatch, existing_events=[{
        "id": "evt-existing", "summary": "Already booked",
        "start": {"dateTime": "2026-08-10T15:00:00+07:00"}, "end": {"dateTime": "2026-08-10T15:30:00+07:00"},
    }])
    created = (
        await client.post(
            "/api/v1/tasks",
            json={"title": "Double-booked meeting", "due_at": "2026-08-10T15:00:00", "source": "proactive"},
            headers=auth_headers,
        )
    ).json()

    resp = await client.post(f"/api/v1/tasks/{created['id']}/accept", json={}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["conflict"] is True
    assert body["task"]["status"] == "suggested"
    assert body["conflicts"][0]["title"] == "Already booked"
    fake_service.events.return_value.insert.assert_not_called()

    # Still "suggested" server-side too, not just in this one response.
    tasks = (await client.get("/api/v1/tasks", headers=auth_headers)).json()
    assert next(t for t in tasks if t["id"] == created["id"])["status"] == "suggested"


@pytest.mark.asyncio
async def test_accept_task_force_keeps_original_time_despite_conflict(client, auth_headers, monkeypatch):
    fake_service = _fake_calendar_service(monkeypatch, existing_events=[{
        "id": "evt-existing", "summary": "Already booked",
        "start": {"dateTime": "2026-08-10T15:00:00+07:00"}, "end": {"dateTime": "2026-08-10T15:30:00+07:00"},
    }])
    created = (
        await client.post(
            "/api/v1/tasks",
            json={"title": "Keep it anyway", "due_at": "2026-08-10T15:00:00", "source": "proactive"},
            headers=auth_headers,
        )
    ).json()

    resp = await client.post(f"/api/v1/tasks/{created['id']}/accept", json={"force": True}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["conflict"] is False
    assert body["task"]["status"] == "pending"
    assert body["task"]["due_at"] == created["due_at"]
    fake_service.events.return_value.insert.assert_called_once()


@pytest.mark.asyncio
async def test_accept_task_due_at_override_syncs_task_calendar_and_reminder(client, auth_headers, monkeypatch):
    """Picking a different date/time (an alternative slot, or a custom pick) must land on the
    Task, the Calendar event AND the Reminder all at once - one value, not three to keep in sync."""
    fake_service = _fake_calendar_service(monkeypatch)
    created = (
        await client.post(
            "/api/v1/tasks",
            json={"title": "Rescheduled sync", "due_at": "2026-08-10T15:00:00", "source": "proactive"},
            headers=auth_headers,
        )
    ).json()

    resp = await client.post(
        f"/api/v1/tasks/{created['id']}/accept", json={"due_at": "2026-08-11T09:30:00"}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["conflict"] is False
    new_due_at = datetime.fromisoformat(body["task"]["due_at"])
    assert new_due_at == datetime(2026, 8, 11, 9, 30, tzinfo=ZoneInfo(get_settings().calendar_timezone))

    call_body = fake_service.events.return_value.insert.call_args.kwargs["body"]
    # Postgres normalizes TIMESTAMPTZ to UTC on read-back, so the offset in the string can differ
    # from what was written (+07:00 vs +00:00) even though it's the exact same instant - compare
    # by value, not by prefix (same reasoning as test_create_task_with_offset_due_at_is_kept_as_is).
    assert datetime.fromisoformat(call_body["start"]["dateTime"]) == new_due_at

    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    reminder = next(r for r in reminders if r["title"] == "Rescheduled sync")
    assert datetime.fromisoformat(reminder["due_at"]) == new_due_at


@pytest.mark.asyncio
async def test_accept_task_rejects_when_not_suggested(client, auth_headers, monkeypatch):
    _fake_calendar_service(monkeypatch)
    created = (
        await client.post("/api/v1/tasks", json={"title": "Already handled"}, headers=auth_headers)
    ).json()
    await client.patch(f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers)

    resp = await client.post(f"/api/v1/tasks/{created['id']}/accept", json={}, headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_accept_manual_task_skips_conflict_check_and_calendar(client, auth_headers, monkeypatch):
    """A manual task never gets an auto-created Calendar event/Reminder (same as the plain PATCH
    .../status path) - so it has nothing to conflict with and the check is skipped entirely."""
    fake_service = _fake_calendar_service(monkeypatch, existing_events=[{
        "id": "evt-existing", "summary": "Already booked",
        "start": {"dateTime": "2026-08-10T15:00:00+07:00"}, "end": {"dateTime": "2026-08-10T15:30:00+07:00"},
    }])
    created = (
        await client.post(
            "/api/v1/tasks",
            json={"title": "Manual overlap", "due_at": "2026-08-10T15:00:00", "source": "manual"},
            headers=auth_headers,
        )
    ).json()

    resp = await client.post(f"/api/v1/tasks/{created['id']}/accept", json={}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["conflict"] is False
    assert body["task"]["status"] == "pending"
    fake_service.events.return_value.insert.assert_not_called()


@pytest.mark.asyncio
async def test_accept_task_twice_creates_only_one_calendar_event(client, auth_headers, monkeypatch):
    """A second Accept on an already-accepted task must not double-book - the early "not pending
    review" guard already rejects a sequential repeat; the conditional UPDATE in accept_task (only
    the request whose UPDATE actually flips a "suggested" row creates the Calendar event/Reminder)
    is what closes the narrower window where two requests race each other's read before either
    commits - not reproducible with sequential awaits, but this still locks in the visible half of
    the guarantee: however many times Accept is called, at most one Calendar event gets created."""
    fake_service = _fake_calendar_service(monkeypatch)
    created = (
        await client.post(
            "/api/v1/tasks",
            json={"title": "Only once", "due_at": "2026-08-10T15:00:00", "source": "proactive"},
            headers=auth_headers,
        )
    ).json()

    first = await client.post(f"/api/v1/tasks/{created['id']}/accept", json={}, headers=auth_headers)
    second = await client.post(f"/api/v1/tasks/{created['id']}/accept", json={}, headers=auth_headers)

    assert first.status_code == 200
    assert first.json()["task"]["status"] == "pending"
    assert second.status_code == 400  # already pending review, not suggested anymore
    fake_service.events.return_value.insert.assert_called_once()


@pytest.mark.asyncio
async def test_accept_task_not_visible_to_other_user(client, auth_headers, other_auth_headers, monkeypatch):
    _fake_calendar_service(monkeypatch)
    created = (
        await client.post("/api/v1/tasks", json={"title": "Private task"}, headers=auth_headers)
    ).json()

    resp = await client.post(f"/api/v1/tasks/{created['id']}/accept", json={}, headers=other_auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------- DELETE /tasks/{id} cascade


@pytest.mark.asyncio
async def test_delete_task_cascades_to_linked_calendar_event_and_reminder(client, auth_headers, monkeypatch):
    """A Task Accepted with a due date gets a real Calendar event + Reminder behind it
    (_add_to_calendar_and_reminder, which links them back via calendar_event_id/reminder_id) -
    deleting the Task must not leave those orphaned on the user's real Calendar/Reminders."""
    fake_service = _fake_calendar_service(monkeypatch)
    created = (
        await client.post(
            "/api/v1/tasks",
            json={"title": "Cascade delete me", "due_at": "2026-08-10T15:00:00", "source": "proactive"},
            headers=auth_headers,
        )
    ).json()
    await client.post(f"/api/v1/tasks/{created['id']}/accept", json={}, headers=auth_headers)

    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    reminder = next(r for r in reminders if r["title"] == "Cascade delete me")
    assert reminder["status"] == "scheduled"

    resp = await client.delete(f"/api/v1/tasks/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204

    fake_service.events.return_value.delete.assert_called_once()
    assert fake_service.events.return_value.delete.call_args.kwargs["eventId"] == "evt-1"

    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    reminder = next(r for r in reminders if r["id"] == reminder["id"])
    assert reminder["status"] == "cancelled"


@pytest.mark.asyncio
async def test_delete_task_without_a_link_does_not_touch_calendar(client, auth_headers, monkeypatch):
    """A task that was never Accepted (still "suggested", or manual/no due date) has no
    calendar_event_id/reminder_id - deleting it must not call the Calendar API at all."""
    fake_service = _fake_calendar_service(monkeypatch)
    created = (
        await client.post("/api/v1/tasks", json={"title": "Never accepted"}, headers=auth_headers)
    ).json()

    resp = await client.delete(f"/api/v1/tasks/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204
    fake_service.events.return_value.delete.assert_not_called()
