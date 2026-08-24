"""One-off migration: add tasks.updated_at.

Why a hand-written script instead of Alembic: this project doesn't use a migration tool -
Base.metadata.create_all() (src/db/session.py::init_db, run on every app startup) only creates
tables that don't exist yet, it never ALTERs an existing table. `updated_at` was added to the
Task model (src/db/models.py) to match a column that already exists NOT NULL on the shared dev
Supabase `tasks` table (a leftover from an earlier, later-reverted branch) - every task INSERT
that doesn't set it currently fails with a NotNullViolationError, silently swallowed wherever the
insert happens in a best-effort/background path (proactive_service.maybe_suggest_task) and as a
visible 500 wherever it doesn't (POST /tasks). A fresh environment whose `tasks` table doesn't
have this column yet (or doesn't have a `tasks` table at all) needs it added by hand, exactly
once. Idempotent (IF NOT EXISTS / backfill-before-constrain) so running it again is a no-op, not
an error.

Test DB is unaffected: tests/conftest.py's _test_database fixture drops and recreates the whole
schema from the current models every session, so it always gets this column for free.

Usage:
    python scripts/migrate_add_task_updated_at.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.db.session import engine  # noqa: E402

# Separate statements, not one multi-statement string - asyncpg (the driver src/db/session.py
# uses for the app's async engine) doesn't reliably support several commands in a single execute().
# Backfill from created_at before enforcing NOT NULL, so this is safe to run against a `tasks`
# table that already has rows (this project never sets updated_at via a DB-level DEFAULT - see
# every other *_at column in src/db/models.py - so the column stays nullable at the DB level; the
# ORM's Python-side default/onupdate is what actually populates it going forward).
DDL_STATEMENTS = [
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NULL",
    "UPDATE tasks SET updated_at = created_at WHERE updated_at IS NULL",
]


async def main() -> None:
    async with engine.begin() as conn:
        for statement in DDL_STATEMENTS:
            await conn.execute(text(statement))
    print("tasks.updated_at is present and backfilled.")


if __name__ == "__main__":
    asyncio.run(main())
