from unittest.mock import MagicMock

import pytest

from src.services import calendar_service

_USER_ID = "test-user-calendar-service"


def _mock_service(monkeypatch, fake_service):
    async def _fake(user_id):
        return fake_service

    monkeypatch.setattr(calendar_service, "_service", _fake)


def _with_items(items: list[dict]) -> MagicMock:
    fake_service = MagicMock()
    fake_service.events.return_value.list.return_value.execute.return_value = {"items": items}
    return fake_service


@pytest.mark.asyncio
async def test_find_conflicts_empty_when_no_events(monkeypatch):
    _mock_service(monkeypatch, _with_items([]))

    conflicts = await calendar_service.find_conflicts(_USER_ID, "2026-08-01T11:00:00", "2026-08-01T12:00:00")

    assert conflicts == []


@pytest.mark.asyncio
async def test_find_conflicts_returns_overlapping_events(monkeypatch):
    items = [
        {"id": "evt-1", "summary": "Standup", "start": {"dateTime": "2026-08-01T11:00:00"}, "end": {"dateTime": "2026-08-01T11:30:00"}},
        {"id": "evt-2", "summary": "1:1", "start": {"dateTime": "2026-08-01T11:45:00"}, "end": {"dateTime": "2026-08-01T12:15:00"}},
    ]
    _mock_service(monkeypatch, _with_items(items))

    conflicts = await calendar_service.find_conflicts(_USER_ID, "2026-08-01T11:00:00", "2026-08-01T12:00:00")

    assert conflicts == items


@pytest.mark.asyncio
async def test_suggest_alternative_slots_starts_right_after_busy_event(monkeypatch):
    """One 30-minute conflict right at the requested start: the first alternative should pick up
    exactly where it ends, and a second alternative should still be found (next working day, since
    the rest of the requested day is free)."""
    items = [
        {"id": "evt-1", "summary": "Standup", "start": {"dateTime": "2026-08-01T11:00:00"}, "end": {"dateTime": "2026-08-01T11:30:00"}},
    ]
    _mock_service(monkeypatch, _with_items(items))

    slots = await calendar_service.suggest_alternative_slots(_USER_ID, "2026-08-01T11:00:00", "2026-08-01T12:00:00")

    assert slots[0] == {"start": "2026-08-01T11:30:00", "end": "2026-08-01T12:30:00"}
    assert len(slots) == 2


@pytest.mark.asyncio
async def test_suggest_alternative_slots_respects_count(monkeypatch):
    _mock_service(monkeypatch, _with_items([]))

    slots = await calendar_service.suggest_alternative_slots(
        _USER_ID, "2026-08-01T11:00:00", "2026-08-01T12:00:00", count=1
    )

    assert len(slots) == 1
    assert slots[0] == {"start": "2026-08-01T11:00:00", "end": "2026-08-01T12:00:00"}


@pytest.mark.asyncio
async def test_suggest_alternative_slots_returns_fewer_when_window_is_full(monkeypatch):
    """A single busy block spanning the entire search window leaves no free gap anywhere in it -
    best-effort means returning what was found (nothing here), never raising."""
    items = [
        {"id": "evt-1", "summary": "Offsite", "start": {"dateTime": "2026-08-01T00:00:00"}, "end": {"dateTime": "2026-08-04T00:00:00"}},
    ]
    _mock_service(monkeypatch, _with_items(items))

    slots = await calendar_service.suggest_alternative_slots(_USER_ID, "2026-08-01T11:00:00", "2026-08-01T12:00:00")

    assert slots == []
