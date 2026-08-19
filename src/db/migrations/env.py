"""Alembic environment - runs migrations with a plain sync psycopg (v3) connection, deliberately
separate from src.db.session's async asyncpg engine (Alembic's autogenerate/offline machinery is
sync-only). Reads the same DATABASE_URL the app itself uses via src.config.get_settings(), so
`alembic upgrade head` always targets whatever database the current environment is configured for -
with one override: ALEMBIC_DATABASE_URL, used only to point a one-off `alembic revision
--autogenerate` at a scratch database when validating a new migration (see WORKLOG.md/PR notes for
today's baseline migration) without touching .env."""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `import src...` resolve when Alembic runs from the repo root (alembic.ini sets
# prepend_sys_path = . for the same reason; this is a belt-and-suspenders fallback for anyone
# invoking `python -m alembic` from a different working directory).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.config import get_settings  # noqa: E402
from src.db import models  # noqa: E402,F401 - import registers every table on Base.metadata
from src.db.base import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    override = os.environ.get("ALEMBIC_DATABASE_URL")
    if override:
        return override
    url = get_settings().database_url
    # Alembic's sync engine needs the psycopg (v3) dialect, not asyncpg - src.db.session does the
    # opposite conversion (-> +asyncpg) for the app's own async engine from this same plain url.
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
