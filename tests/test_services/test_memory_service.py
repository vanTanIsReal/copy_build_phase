from datetime import UTC, datetime, timedelta

import pytest

from src.db import session as db_session
from src.db.models import Memory
from src.services import memory_service


async def _get_user_id(client, auth_headers) -> str:
    return (await client.get("/api/v1/auth/me", headers=auth_headers)).json()["id"]


async def _seed_memory(owner_id: str, title: str, created_at, category: str = "Preference") -> None:
    async with db_session.async_session_maker() as db:
        db.add(Memory(owner_id=owner_id, category=category, title=title, created_at=created_at))
        await db.commit()


@pytest.mark.asyncio
async def test_list_memories_for_owner_newest_first(client, auth_headers):
    owner_id = await _get_user_id(client, auth_headers)
    now = datetime.now(UTC)
    await _seed_memory(owner_id, "Older", created_at=now - timedelta(days=1))
    await _seed_memory(owner_id, "Newer", created_at=now)

    memories = await memory_service.list_memories_for_owner(owner_id)

    assert [m.title for m in memories] == ["Newer", "Older"]


@pytest.mark.asyncio
async def test_list_memories_for_owner_scoped_to_owner(client, auth_headers, other_auth_headers):
    owner_id = await _get_user_id(client, auth_headers)
    other_id = await _get_user_id(client, other_auth_headers)
    now = datetime.now(UTC)
    await _seed_memory(owner_id, "Mine", created_at=now)
    await _seed_memory(other_id, "Not mine", created_at=now)

    memories = await memory_service.list_memories_for_owner(owner_id)

    assert [m.title for m in memories] == ["Mine"]


@pytest.mark.asyncio
async def test_list_memories_for_owner_no_memories():
    memories = await memory_service.list_memories_for_owner("no-such-user")
    assert memories == []
