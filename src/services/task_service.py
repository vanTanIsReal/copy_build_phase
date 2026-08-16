from sqlalchemy import select

from src.db import session as db_session
from src.db.models import Task

_PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}


def _sort_key(t: Task) -> tuple[bool, float, int]:
    # .timestamp() gives a plain float to sort by - fine for a relative sort ordering.
    return (t.due_at is None, t.due_at.timestamp() if t.due_at else 0.0, _PRIORITY_RANK.get(t.priority, 1))


async def list_tasks_for_owner(owner_id: str | None) -> list[Task]:
    """All tasks for a user (any status), sorted the same way `/tasks` shows them: soonest due_at
    first, priority as tiebreaker, no-due-date tasks last. Shared by task_routes.py's `GET /tasks`
    and the agent's `list_tasks` tool (src/agents/tools/task_tool.py) - one sort order, not two
    that could drift apart."""
    async with db_session.async_session_maker() as db:
        tasks = (await db.execute(select(Task).where(Task.owner_id == owner_id))).scalars().all()
    tasks = list(tasks)
    tasks.sort(key=_sort_key)
    return tasks
