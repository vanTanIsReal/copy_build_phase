import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from src.config import get_settings
from src.db import session as db_session
from src.db.models import SystemConfig, UsageLog, User
from src.websocket.manager import manager

_SYSTEM_CONFIG_ID = "default"

logger = logging.getLogger(__name__)

# Edge-triggered alert thresholds (percent of daily_token_budget). "Edge-triggered" so admins get
# one push per crossing per day, not one on every single request once already over the line.
_WARNING_PCT = 80
_EXCEEDED_PCT = 100

# Standard paid-tier text-token prices in USD per one million tokens, for the "AI Usage" admin
# page's cost estimate. These are ballpark figures for the models this project documents in
# .env.example - provider invoices remain the source of truth for actual billing. A model not in
# this table stays explicitly unpriced (see _estimate_cost) rather than silently inheriting a
# possibly-wrong rate.
_PRICING_PER_MILLION: dict[tuple[str, str], tuple[float, float]] = {
    ("google", "gemini-2.5-flash"): (0.30, 2.50),
    ("google", "gemini-2.5-flash-lite"): (0.10, 0.40),
    ("openai", "gpt-4o-mini"): (0.15, 0.60),
    ("openai", "gpt-4.1-mini"): (0.40, 1.60),
    ("groq", "openai/gpt-oss-20b"): (0.075, 0.30),
    ("groq", "llama-3.1-8b-instant"): (0.05, 0.08),
}


def _estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> tuple[float, int]:
    """Returns (estimated_cost_usd, unpriced_tokens) - unpriced_tokens is either 0 (a price was
    found) or total_tokens (nothing charged, all of it called out as unpriced instead)."""
    normalized_model = model.lower().removeprefix("models/")
    prices = _PRICING_PER_MILLION.get((provider.lower(), normalized_model))
    if prices is None:
        return 0.0, total_tokens
    input_price, output_price = prices
    cost = prompt_tokens / 1_000_000 * input_price + completion_tokens / 1_000_000 * output_price
    return cost, 0


def _midnight_local_as_utc() -> datetime:
    tz = ZoneInfo(get_settings().calendar_timezone)
    return datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


async def log_usage(*, provider: str, model: str, usage_metadata: dict | None) -> None:
    """Best-effort token usage logging. Never lets a logging failure break the chat turn."""
    if not usage_metadata:
        return
    try:
        tokens = usage_metadata.get("total_tokens", 0)
        async with db_session.async_session_maker() as db:
            before_result = await db.execute(
                select(func.coalesce(func.sum(UsageLog.total_tokens), 0)).where(
                    UsageLog.created_at >= _midnight_local_as_utc()
                )
            )
            before_tokens = before_result.scalar_one()
            db.add(
                UsageLog(
                    provider=provider,
                    model=model,
                    prompt_tokens=usage_metadata.get("input_tokens", 0),
                    completion_tokens=usage_metadata.get("output_tokens", 0),
                    total_tokens=tokens,
                )
            )
            await db.commit()
        await _maybe_alert_budget(before_tokens=before_tokens, after_tokens=before_tokens + tokens)
    except Exception:  # noqa: BLE001 - usage tracking must never break the agent turn
        logger.exception("Failed to log LLM usage")


async def get_daily_token_budget() -> int:
    """The effective daily token budget: an admin-set override (SystemConfig, PATCH
    /admin/settings/budget) if one exists, otherwise the .env default (Settings.daily_token_budget)
    - a deployment that never touches the Admin dashboard keeps working exactly as before."""
    async with db_session.async_session_maker() as db:
        config = await db.get(SystemConfig, _SYSTEM_CONFIG_ID)
    if config is not None and config.daily_token_budget is not None:
        return config.daily_token_budget
    return get_settings().daily_token_budget


async def set_daily_token_budget(value: int, *, updated_by: str | None) -> int:
    """Admin-only write path (src/api/admin_routes.py) - upserts the single SystemConfig row."""
    async with db_session.async_session_maker() as db:
        config = await db.get(SystemConfig, _SYSTEM_CONFIG_ID)
        if config is None:
            config = SystemConfig(id=_SYSTEM_CONFIG_ID)
            db.add(config)
        config.daily_token_budget = value
        config.updated_by = updated_by
        await db.commit()
    return value


async def _maybe_alert_budget(*, before_tokens: int, after_tokens: int) -> None:
    """Push a WebSocket alert to every connected admin the moment today's usage crosses 80% or
    100% of daily_token_budget - so it surfaces wherever an admin already is in the app, not only
    when they happen to open the Admin dashboard (see ROADMAP.md, mục 'Cảnh báo token/chi phí')."""
    budget = await get_daily_token_budget()
    if not budget:
        return
    before_pct = before_tokens / budget * 100
    after_pct = after_tokens / budget * 100
    if before_pct < _EXCEEDED_PCT <= after_pct:
        level = "exceeded"
    elif before_pct < _WARNING_PCT <= after_pct:
        level = "warning"
    else:
        return

    async with db_session.async_session_maker() as db:
        admin_ids = (await db.execute(select(User.id).where(User.role == "admin"))).scalars().all()
    if not admin_ids:
        return
    await manager.broadcast_to_users(
        list(admin_ids),
        {
            "type": "usage_budget_alert",
            "level": level,
            "tokens_used_today": after_tokens,
            "daily_token_budget": budget,
            "used_pct": round(after_pct, 1),
        },
    )


async def get_usage_today() -> dict:
    since = _midnight_local_as_utc()
    async with db_session.async_session_maker() as db:
        rows = (
            await db.execute(
                select(
                    UsageLog.provider,
                    UsageLog.model,
                    func.coalesce(func.sum(UsageLog.prompt_tokens), 0),
                    func.coalesce(func.sum(UsageLog.completion_tokens), 0),
                    func.coalesce(func.sum(UsageLog.total_tokens), 0),
                    func.count(UsageLog.id),
                )
                .where(UsageLog.created_at >= since)
                .group_by(UsageLog.provider, UsageLog.model)
            )
        ).all()

    estimated_cost_usd = 0.0
    unpriced_tokens = 0
    for provider, model, prompt, completion, total, _requests in rows:
        cost, unpriced = _estimate_cost(provider, model, prompt, completion, total)
        estimated_cost_usd += cost
        unpriced_tokens += unpriced

    return {
        "prompt_tokens": sum(row[2] for row in rows),
        "completion_tokens": sum(row[3] for row in rows),
        "total_tokens": sum(row[4] for row in rows),
        "request_count": sum(row[5] for row in rows),
        "estimated_cost_usd": round(estimated_cost_usd, 6),
        "unpriced_tokens": unpriced_tokens,
        "since": since,
    }


async def get_usage_summary() -> dict:
    """Non-admin-safe subset of today's usage - just enough for a "% of today's shared AI budget
    used" indicator (Sidebar.jsx's widget, via GET /api/v1/usage/status). Deliberately excludes
    estimated_cost_usd and per-provider/model data that get_usage_today()/get_usage_report() expose
    - those stay admin-only (GET /admin/stats, /admin/ai-usage)."""
    budget = await get_daily_token_budget()
    usage = await get_usage_today()
    used_pct = round(usage["total_tokens"] / budget * 100, 1) if budget else 0.0
    return {
        "tokens_used_today": usage["total_tokens"],
        "daily_token_budget": budget,
        "used_pct": used_pct,
    }


async def get_usage_report(days: int = 7) -> dict:
    """Powers the "AI Usage" admin page: per-day totals for a trend chart, plus a per-model
    breakdown, over the trailing `days` days (including today)."""
    settings = get_settings()
    tz = ZoneInfo(settings.calendar_timezone)
    today = datetime.now(tz).date()
    since_local = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    since = since_local.astimezone(UTC)
    async with db_session.async_session_maker() as db:
        rows = (
            await db.execute(
                select(
                    UsageLog.provider,
                    UsageLog.model,
                    UsageLog.prompt_tokens,
                    UsageLog.completion_tokens,
                    UsageLog.total_tokens,
                    UsageLog.created_at,
                ).where(UsageLog.created_at >= since)
            )
        ).all()

    daily = {
        (today - timedelta(days=offset)).isoformat(): {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "request_count": 0,
            "estimated_cost_usd": 0.0,
            "unpriced_tokens": 0,
        }
        for offset in range(days - 1, -1, -1)
    }
    models: dict[tuple[str, str], dict] = {}
    for provider, model, prompt, completion, total, created_at in rows:
        timestamp = created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at
        day_key = timestamp.astimezone(tz).date().isoformat()
        if day_key not in daily:
            continue
        cost, unpriced = _estimate_cost(provider, model, prompt, completion, total)

        day = daily[day_key]
        day["prompt_tokens"] += prompt
        day["completion_tokens"] += completion
        day["total_tokens"] += total
        day["request_count"] += 1
        day["estimated_cost_usd"] += cost
        day["unpriced_tokens"] += unpriced

        model_usage = models.setdefault(
            (provider, model),
            {
                "provider": provider, "model": model, "prompt_tokens": 0, "completion_tokens": 0,
                "total_tokens": 0, "request_count": 0, "estimated_cost_usd": 0.0, "unpriced_tokens": 0,
            },
        )
        model_usage["prompt_tokens"] += prompt
        model_usage["completion_tokens"] += completion
        model_usage["total_tokens"] += total
        model_usage["request_count"] += 1
        model_usage["estimated_cost_usd"] += cost
        model_usage["unpriced_tokens"] += unpriced

    daily_rows = []
    for day_key, values in daily.items():
        values["estimated_cost_usd"] = round(values["estimated_cost_usd"], 6)
        daily_rows.append({"date": day_key, **values})
    model_rows = sorted(models.values(), key=lambda item: item["total_tokens"], reverse=True)
    for values in model_rows:
        values["estimated_cost_usd"] = round(values["estimated_cost_usd"], 6)

    totals = {
        key: sum(row[key] for row in daily_rows)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "request_count", "estimated_cost_usd", "unpriced_tokens")
    }
    totals["estimated_cost_usd"] = round(totals["estimated_cost_usd"], 6)
    return {"days": days, "since": since, "totals": totals, "daily": daily_rows, "models": model_rows}


async def is_over_budget() -> bool:
    """True once today's usage has reached (not just approached) daily_token_budget. Used to
    block *new* LLM calls - never to interrupt one already in flight or a human-approved action
    that's just completing (see routes.py::resume_chat for why resume is exempt)."""
    budget = await get_daily_token_budget()
    if not budget:
        return False
    usage = await get_usage_today()
    return usage["total_tokens"] >= budget
