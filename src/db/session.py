from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.config import get_settings
from src.db.base import Base

settings = get_settings()


def _async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


# Tests exercise the app from more than one event loop (pytest-asyncio's session loop for the
# httpx-based `client` fixture, plus Starlette TestClient's own background-thread loop for
# websocket tests) - a real asyncpg connection is bound to the loop that created it, so a pooled
# connection checked out from a different loop than the one that opened it breaks with
# "attached to a different loop". NullPool sidesteps this by opening a fresh connection on every
# checkout instead of reusing one across loops; production keeps normal pooling.
# Pool is kept deliberately small (SQLAlchemy's async default is 5 + 10 overflow = 15) because a
# managed Postgres pooler (e.g. Supabase's Session pooler) caps *total* concurrent clients per
# project - this engine is only one of three pools sharing that budget (see graph.py's
# AsyncPostgresSaver pool and scheduler.py's APScheduler jobstore engine).
_engine_kwargs = (
    {"poolclass": NullPool}
    if settings.app_env == "test"
    else {"pool_size": 3, "max_overflow": 2, "pool_pre_ping": True}
)
# asyncpg's connect() takes an `ssl` kwarg, not the libpq-style `sslmode` that psycopg (used by the
# LangGraph checkpointer and the APScheduler jobstore) understands - so SSL can't be configured via
# a query string on DATABASE_URL without breaking one driver or the other. Set it here instead,
# scoped to this engine only. "prefer" negotiates SSL when the server offers it (managed Postgres
# like Supabase) and falls back to plaintext otherwise (local dev, CI's postgres service container).
_engine_kwargs["connect_args"] = {"ssl": "prefer"}
engine = create_async_engine(_async_url(settings.database_url), **_engine_kwargs)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session


# ``create_all`` only creates TABLES that don't exist yet - it never alters an existing table, so
# adding a column to a model (as memory_maintenance_service.py's episodic-memory support did to
# Memory/AssistantThread) needs an explicit, idempotent ALTER TABLE pass here too, or every
# database that already had these tables before this change stays on the old schema forever.
# Postgres's ADD COLUMN IF NOT EXISTS makes each statement safe to run on every startup (fresh
# DB, already-migrated DB, or a DB moved between them) - and safe on data, since every new column
# is nullable or has a default, so no existing row needs to change.
_MEMORY_COLUMNS = (
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS memory_type VARCHAR DEFAULT 'fact' NOT NULL",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'active' NOT NULL",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_type VARCHAR DEFAULT 'manual' NOT NULL",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_id VARCHAR",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_thread_id VARCHAR",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_conversation_id VARCHAR",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS provenance JSON DEFAULT '{}'::json NOT NULL",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION DEFAULT 1.0 NOT NULL",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS importance DOUBLE PRECISION DEFAULT 0.5 NOT NULL",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS sensitivity VARCHAR DEFAULT 'normal' NOT NULL",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS user_confirmed BOOLEAN DEFAULT TRUE NOT NULL",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMP WITH TIME ZONE",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS content_hash VARCHAR DEFAULT '' NOT NULL",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding JSON",
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding_model VARCHAR",
)
_ASSISTANT_THREAD_COLUMNS = (
    "ALTER TABLE assistant_threads ADD COLUMN IF NOT EXISTS session_summary TEXT DEFAULT '' NOT NULL",
    "ALTER TABLE assistant_threads ADD COLUMN IF NOT EXISTS compacted_message_count INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE assistant_threads ADD COLUMN IF NOT EXISTS summary_updated_at TIMESTAMP WITH TIME ZONE",
    "ALTER TABLE assistant_threads ADD COLUMN IF NOT EXISTS last_memory_maintenance_at TIMESTAMP WITH TIME ZONE",
)


async def _apply_memory_schema_compatibility(conn: AsyncConnection) -> None:
    for statement in _MEMORY_COLUMNS + _ASSISTANT_THREAD_COLUMNS:
        await conn.execute(text(statement))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _apply_memory_schema_compatibility(conn)
