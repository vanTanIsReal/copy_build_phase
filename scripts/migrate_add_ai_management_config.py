"""One-off migration: add system_config.llm_provider / model_name / llm_temperature.

Why a hand-written script instead of Alembic: this project doesn't use a migration tool -
Base.metadata.create_all() (src/db/session.py::init_db, run on every app startup) only creates
tables that don't exist yet, it never ALTERs an existing table. New columns on an already-live
`system_config` table (dev DB, and Supabase in production if deployed) therefore have to be
applied by hand, exactly once. Idempotent (IF NOT EXISTS everywhere) so running it again is a
no-op, not an error. Same pattern as scripts/migrate_add_task_source_message.py.

`audit_logs` (the other new table this feature needs) does NOT need a script here - it's a
brand-new table, so create_all() picks it up automatically on next backend startup.

Test DB is unaffected: tests/conftest.py's _test_database fixture drops and recreates the whole
schema from the current models every session, so it always gets these columns for free.

Usage:
    python scripts/migrate_add_ai_management_config.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.db.session import engine  # noqa: E402

DDL_STATEMENTS = [
    "ALTER TABLE system_config ADD COLUMN IF NOT EXISTS llm_provider VARCHAR NULL",
    "ALTER TABLE system_config ADD COLUMN IF NOT EXISTS model_name VARCHAR NULL",
    "ALTER TABLE system_config ADD COLUMN IF NOT EXISTS llm_temperature DOUBLE PRECISION NULL",
]


async def main() -> None:
    async with engine.begin() as conn:
        for statement in DDL_STATEMENTS:
            await conn.execute(text(statement))
    print("system_config.llm_provider / model_name / llm_temperature are present.")


if __name__ == "__main__":
    asyncio.run(main())
