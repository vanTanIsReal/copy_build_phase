from sqlalchemy import select

from src.db import session as db_session
from src.db.models import Memory


async def list_memories_for_owner(owner_id: str | None) -> list[Memory]:
    """All memory notes for a user, newest first. Shared by memory_routes.py's `GET /memories` and
    the agent's `list_memories` tool (src/agents/tools/memory_tool.py)."""
    async with db_session.async_session_maker() as db:
        memories = (
            await db.execute(
                select(Memory).where(Memory.owner_id == owner_id).order_by(Memory.created_at.desc())
            )
        ).scalars().all()
    return list(memories)
