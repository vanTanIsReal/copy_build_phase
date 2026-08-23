from datetime import UTC, datetime, timedelta

import pytest

from src.db import session as db_session
from src.db.models import Task
from src.services import task_service


async def _get_user_id(client, auth_headers) -> str:
    return (await client.get("/api/v1/auth/me", headers=auth_headers)).json()["id"]


async def _seed_task(owner_id: str, title: str, due_at=None, priority: str = "Medium") -> None:
    async with db_session.async_session_maker() as db:
        db.add(Task(owner_id=owner_id, title=title, due_at=due_at, priority=priority))
        await db.commit()


@pytest.mark.asyncio
async def test_list_tasks_for_owner_sorts_by_due_date_no_due_date_last(client, auth_headers):
    owner_id = await _get_user_id(client, auth_headers)
    now = datetime.now(UTC)
    await _seed_task(owner_id, "No due date task")
    await _seed_task(owner_id, "Later task", due_at=now + timedelta(days=5))
    await _seed_task(owner_id, "Soonest task", due_at=now + timedelta(hours=1))

    tasks = await task_service.list_tasks_for_owner(owner_id)

    assert [t.title for t in tasks] == ["Soonest task", "Later task", "No due date task"]


@pytest.mark.asyncio
async def test_list_tasks_for_owner_priority_tiebreaks_same_due_date(client, auth_headers):
    owner_id = await _get_user_id(client, auth_headers)
    due = datetime.now(UTC) + timedelta(days=1)
    await _seed_task(owner_id, "Low prio", due_at=due, priority="Low")
    await _seed_task(owner_id, "High prio", due_at=due, priority="High")

    tasks = await task_service.list_tasks_for_owner(owner_id)

    assert [t.title for t in tasks] == ["High prio", "Low prio"]


@pytest.mark.asyncio
async def test_list_tasks_for_owner_scoped_to_owner(client, auth_headers, other_auth_headers):
    owner_id = await _get_user_id(client, auth_headers)
    other_id = await _get_user_id(client, other_auth_headers)
    await _seed_task(owner_id, "Mine")
    await _seed_task(other_id, "Not mine")

    tasks = await task_service.list_tasks_for_owner(owner_id)

    assert [t.title for t in tasks] == ["Mine"]


@pytest.mark.asyncio
async def test_list_tasks_for_owner_no_tasks():
    tasks = await task_service.list_tasks_for_owner("no-such-user")
    assert tasks == []
