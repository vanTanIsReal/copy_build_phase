"""One-off migration: add reminders.updated_at.

Same story as scripts/migrate_add_task_updated_at.py - this project doesn't use a migration tool
(Base.metadata.create_all() only creates tables that don't exist yet, it never ALTERs an existing
one). `updated_at` was added to the Reminder model (src/db/models.py) to match a column that
already exists NOT NULL on the shared dev Supabase `reminders` table (a leftover from an earlier,
later-reverted branch, same as tasks.updated_at) - every reminder INSERT that doesn't set it
currently fails with a NotNullViolationError, silently swallowed inside the best-effort
try/except in task_routes.py::_add_to_calendar_and_reminder (an Accepted task's Reminder never
actually gets created) and surfacing as a visible 500 from POST /reminders otherwise. A fresh
environment whose `reminders` table doesn't have this column yet (or doesn't have a `reminders`
table at all) needs it added by hand, exactly once. Idempotent (IF NOT EXISTS / backfill-before
touching NOT NULL) so running it again is a no-op, not an error.

Test DB is unaffected: tests/conftest.py's _test_database fixture drops and recreates the whole
schema from the current models every session, so it always gets this column for free.

Usage:
    python scripts/migrate_add_reminder_updated_at.py
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
    "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NULL",
    "UPDATE reminders SET updated_at = created_at WHERE updated_at IS NULL",
]


async def main() -> None:
    async with engine.begin() as conn:
        for statement in DDL_STATEMENTS:
            await conn.execute(text(statement))
    print("reminders.updated_at is present and backfilled.")


if __name__ == "__main__":
    asyncio.run(main())
