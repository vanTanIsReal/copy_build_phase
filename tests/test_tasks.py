from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from src.config import get_settings
from src.db import session as db_session
from src.db.models import Task
from src.services import calendar_service


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
async def test_accepting_proactive_task_only_accepts_task_without_hidden_side_effects(
    client, auth_headers, monkeypatch
):
    """A button labelled Accept task cannot silently confirm calendar/reminder writes too."""
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-1", "htmlLink": "https://calendar.google.com/event?eid=evt1",
    }
    monkeypatch.setattr(calendar_service, "get_calendar_service", lambda: fake_service)

    created = await _create_proactive_task(
        client, auth_headers, title="Product launch call", due_at="2026-08-10T15:00:00"
    )
    assert created["status"] == "suggested"

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    fake_service.events.return_value.insert.assert_not_called()

    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    assert not any(r["title"] == "Product launch call" for r in reminders)


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


@pytest.mark.asyncio
async def test_accepting_proactive_task_never_calls_calendar(client, auth_headers, monkeypatch):

    def _broken_get_calendar_service():
        raise RuntimeError("Google API unreachable")

    monkeypatch.setattr(calendar_service, "get_calendar_service", _broken_get_calendar_service)

    created = await _create_proactive_task(
        client, auth_headers, title="Flaky calendar", due_at="2026-08-10T15:00:00"
    )

    resp = await client.patch(
        f"/api/v1/tasks/{created['id']}/status", json={"status": "pending"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    reminders = (await client.get("/api/v1/reminders", headers=auth_headers)).json()
    assert not any(r["title"] == "Flaky calendar" for r in reminders)
