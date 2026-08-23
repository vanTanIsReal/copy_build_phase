"""One-off migration: add conversation_participants.hidden_at.

Why a hand-written script instead of Alembic: this project doesn't use a migration tool -
Base.metadata.create_all() (src/db/session.py::init_db, run on every app startup) only creates
tables that don't exist yet, it never ALTERs an existing table. A new column on an already-live
`conversation_participants` table (dev DB, and Supabase in production if deployed) therefore has to
be applied by hand, exactly once. Idempotent (IF NOT EXISTS) so running it again is a no-op, not an
error. Same pattern as scripts/migrate_add_task_source_message.py.

Test DB is unaffected: tests/conftest.py's _test_database fixture drops and recreates the whole
schema from the current models every session, so it always gets this column for free.

Usage:
    python scripts/migrate_add_conversation_hidden_at.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.db.session import engine  # noqa: E402

DDL_STATEMENT = "ALTER TABLE conversation_participants ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMPTZ NULL"


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text(DDL_STATEMENT))
    print("conversation_participants.hidden_at is present.")


if __name__ == "__main__":
    asyncio.run(main())
