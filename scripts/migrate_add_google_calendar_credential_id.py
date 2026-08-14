"""Add the surrogate id column to an older google_calendar_credentials table.

Older databases used user_id as the row identifier.  The current SQLAlchemy model has a
separate string id column, and create_all() cannot alter an existing table.  This migration is
idempotent and preserves all encrypted Google tokens already stored in the table.

Usage:
    python scripts/migrate_add_google_calendar_credential_id.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.db.session import engine  # noqa: E402


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE google_calendar_credentials ADD COLUMN IF NOT EXISTS id VARCHAR"))
        # Produce the same 32-character shape as uuid.uuid4().hex without requiring an extension.
        await conn.execute(
            text(
                "UPDATE google_calendar_credentials "
                "SET id = md5(random()::text || clock_timestamp()::text || user_id) "
                "WHERE id IS NULL"
            )
        )
        await conn.execute(text("ALTER TABLE google_calendar_credentials ALTER COLUMN id SET NOT NULL"))
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ix_google_calendar_credentials_id ON google_calendar_credentials (id)"
            )
        )
    await engine.dispose()
    print("google_calendar_credentials.id is present and populated.")


if __name__ == "__main__":
    asyncio.run(main())
