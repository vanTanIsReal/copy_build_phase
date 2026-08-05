import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from src.config import get_settings
from src.db import session as db_session
from src.db.models import UsageLog

logger = logging.getLogger(__name__)


async def log_usage(*, provider: str, model: str, usage_metadata: dict | None) -> None:
    """Best-effort token usage logging. Never lets a logging failure break the chat turn."""
    if not usage_metadata:
        return
    try:
        async with db_session.async_session_maker() as db:
            db.add(
                UsageLog(
                    provider=provider,
                    model=model,
                    prompt_tokens=usage_metadata.get("input_tokens", 0),
                    completion_tokens=usage_metadata.get("output_tokens", 0),
                    total_tokens=usage_metadata.get("total_tokens", 0),
                )
            )
            await db.commit()
    except Exception:  # noqa: BLE001 - usage tracking must never break the agent turn
        logger.exception("Failed to log LLM usage")


async def get_usage_today() -> dict:
    tz = ZoneInfo(get_settings().calendar_timezone)
    midnight_local = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    since = midnight_local.astimezone(UTC)
    async with db_session.async_session_maker() as db:
        result = await db.execute(
            select(func.coalesce(func.sum(UsageLog.total_tokens), 0), func.count(UsageLog.id)).where(
                UsageLog.created_at >= since
            )
        )
        total_tokens, request_count = result.one()
    return {"total_tokens": total_tokens, "request_count": request_count, "since": since}
