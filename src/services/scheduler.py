from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import get_settings

settings = get_settings()

# SQLAlchemyJobStore uses a *sync* engine, so it needs its own driver: psycopg2 (default for
# "postgresql://") isn't installed, but psycopg3 is (already pulled in for the LangGraph
# checkpointer) - point it at that dialect instead of adding another dependency.
_jobstore_url = settings.database_url
if _jobstore_url.startswith("postgresql://"):
    _jobstore_url = _jobstore_url.replace("postgresql://", "postgresql+psycopg://", 1)

# SQLAlchemyJobStore persists scheduled jobs (e.g. reminders) so they survive a server restart -
# without it, a job's row in the DB could say "scheduled" while the actual APScheduler job that
# would fire it is gone, and it would just never fire.
# timezone=... matters even though the datetimes passed in are usually tz-aware already: without
# it, APScheduler falls back to the *system's* local timezone (often UTC on a server) for any
# naive datetime it's given, which would fire reminders up to 7h off from Hanoi time.
# engine_options caps this jobstore's own pool - it's the third of three pools sharing a managed
# Postgres pooler's total-client budget (e.g. Supabase Session pooler caps ~15), alongside
# session.py's engine and graph.py's AsyncPostgresSaver pool. SQLAlchemy's sync default (5 +
# 10 overflow = 15) would exhaust that budget on its own.
scheduler = AsyncIOScheduler(
    jobstores={
        "default": SQLAlchemyJobStore(
            url=_jobstore_url, engine_options={"pool_size": 1, "max_overflow": 1, "pool_pre_ping": True}
        )
    },
    timezone=settings.scheduler_timezone,
)
