"""One-off migration: add tasks.calendar_event_id and tasks.reminder_id.

Same story as the other scripts/migrate_add_task_*.py scripts: this project doesn't use a
migration tool - Base.metadata.create_all() (src/db/session.py::init_db, run on every app
startup) only creates tables that don't exist yet, it never ALTERs an existing one. These two new
nullable columns on the Task model (src/db/models.py) link an Accepted task to the real Calendar
event/Reminder auto-created behind it (task_routes.py::_add_to_calendar_and_reminder) - without
them, deleting a Task can't cascade-delete its Calendar event/Reminder, and deleting the Calendar
event (this app, the agent's delete_calendar_event tool, or directly in Google Calendar) can't
find and remove the Task that spawned it (calendar_service.notify_event_deleted). Idempotent (IF
NOT EXISTS everywhere) so running it again is a no-op, not an error.

Test DB is unaffected: tests/conftest.py's _test_database fixture drops and recreates the whole
schema from the current models every session, so it always gets these columns for free.

Usage:
    python scripts/migrate_add_task_calendar_reminder_links.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.db.session import engine  # noqa: E402

# Separate statements, not one multi-statement string - asyncpg (the driver src/db/session.py
# uses for the app's async engine) doesn't reliably support several commands in a single execute().
DDL_STATEMENTS = [
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS calendar_event_id VARCHAR NULL",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS reminder_id VARCHAR NULL",
    "CREATE INDEX IF NOT EXISTS ix_tasks_calendar_event_id ON tasks (calendar_event_id)",
    "CREATE INDEX IF NOT EXISTS ix_tasks_reminder_id ON tasks (reminder_id)",
]


async def main() -> None:
    async with engine.begin() as conn:
        for statement in DDL_STATEMENTS:
            await conn.execute(text(statement))
    print("tasks.calendar_event_id and tasks.reminder_id are present.")


if __name__ == "__main__":
    asyncio.run(main())
