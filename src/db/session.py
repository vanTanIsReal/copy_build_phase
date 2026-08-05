from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings
from src.db.base import Base

settings = get_settings()


def _async_url(url: str) -> str:
    if url.startswith("sqlite:///") and "+aiosqlite" not in url:
        db_path = url.removeprefix("sqlite:///")
        if db_path not in (":memory:", ""):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


_is_sqlite = settings.database_url.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
engine = create_async_engine(_async_url(settings.database_url), connect_args=_connect_args)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session


async def _add_missing_user_columns(conn) -> None:
    """`create_all` only creates missing tables, it never ALTERs an existing one.

    The repo has no Alembic migrations, so patch the `users` table in place when an
    existing SQLite file predates the `role`/`is_active` columns.
    """
    result = await conn.execute(text("PRAGMA table_info(users)"))
    existing_columns = {row[1] for row in result.fetchall()}
    if "role" not in existing_columns:
        await conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR NOT NULL DEFAULT 'user'"))
    if "is_active" not in existing_columns:
        await conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
    if "job_title" not in existing_columns:
        await conn.execute(text("ALTER TABLE users ADD COLUMN job_title VARCHAR NOT NULL DEFAULT ''"))
    if "timezone" not in existing_columns:
        await conn.execute(text("ALTER TABLE users ADD COLUMN timezone VARCHAR NOT NULL DEFAULT 'Asia/Ho_Chi_Minh'"))
    if "preferences" not in existing_columns:
        await conn.execute(text("ALTER TABLE users ADD COLUMN preferences JSON NOT NULL DEFAULT '{}'"))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if _is_sqlite:
            await _add_missing_user_columns(conn)
