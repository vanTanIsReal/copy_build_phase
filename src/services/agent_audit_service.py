"""G6 audit/monitor alerts for the multi-agent workspace feature (MULTI_AGENT_IMPLEMENTATION_
PLAN.md §5.3: "Alert khi denial tăng bất thường, tool lỗi, brief stale, latency/cost vượt ngưỡng
hoặc có output validation failure"). Sprint 3 covers the two most actionable, cheaply-detectable
signals for real: an abnormal run of denials from one actor (possible probing/misconfiguration),
and an executive read hitting a stale/missing WorkspaceBrief. Reuses the exact same WebSocket
channel/shape as usage_service._maybe_alert_budget (BudgetAlertToast.jsx already renders arbitrary
`{"type": ..., ...}` admin broadcasts) rather than opening a second, parallel notification path -
CLAUDE.md's "tái sử dụng kênh/pattern trong websocket/ thay vì tạo kết nối WebSocket song song mới".

Both alerts are best-effort: a failure here must never break the agent turn that triggered it
(same principle as usage_service.log_usage).
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AgentRun, User
from src.websocket.manager import manager

logger = logging.getLogger(__name__)

# Edge-triggered (fires once when the count first reaches this many denials in the window, not on
# every subsequent one) - same "one push per crossing" idea as usage_service's budget alert.
_DENIAL_SPIKE_THRESHOLD = 5
_DENIAL_SPIKE_WINDOW = timedelta(minutes=10)


async def maybe_alert_denial_spike(db: AsyncSession, *, actor_user_id: str, organization_workspace_id: str) -> None:
    """Call after recording one denied AgentRun. Counts this actor's denied runs in the trailing
    window; alerts admins the moment the count first reaches _DENIAL_SPIKE_THRESHOLD."""
    try:
        since = datetime.now(UTC) - _DENIAL_SPIKE_WINDOW
        count = (
            await db.execute(
                select(func.count(AgentRun.id)).where(
                    AgentRun.actor_user_id == actor_user_id,
                    AgentRun.organization_workspace_id == organization_workspace_id,
                    AgentRun.status == "denied",
                    AgentRun.created_at >= since,
                )
            )
        ).scalar_one()
        if count != _DENIAL_SPIKE_THRESHOLD:
            return
        admin_ids = (await db.execute(select(User.id).where(User.role == "admin"))).scalars().all()
        if not admin_ids:
            return
        await manager.broadcast_to_users(
            list(admin_ids),
            {
                "type": "agent_denial_spike",
                "actor_user_id": actor_user_id,
                "organization_workspace_id": organization_workspace_id,
                "denied_count": count,
                "window_minutes": int(_DENIAL_SPIKE_WINDOW.total_seconds() // 60),
            },
        )
    except Exception:  # noqa: BLE001 - audit alerting must never break the agent turn
        logger.exception("Failed to check/send agent_denial_spike alert")


async def alert_brief_stale(
    db: AsyncSession, *, agent_workspace_id: str, agent_workspace_name: str, brief_type: str, organization_workspace_id: str
) -> None:
    """Call when an Executive read finds a stale/expired WorkspaceBrief (executive_tool.py's
    get_workspace_briefs). Not edge-triggered (unlike the two alerts above): a stale brief just
    means nobody has refreshed it, so re-alerting on every subsequent Executive read is correct,
    not noisy - there is no natural "crossing" to debounce against."""
    try:
        admin_ids = (await db.execute(select(User.id).where(User.role == "admin"))).scalars().all()
        if not admin_ids:
            return
        await manager.broadcast_to_users(
            list(admin_ids),
            {
                "type": "workspace_brief_stale",
                "agent_workspace_id": agent_workspace_id,
                "agent_workspace_name": agent_workspace_name,
                "brief_type": brief_type,
                "organization_workspace_id": organization_workspace_id,
            },
        )
    except Exception:  # noqa: BLE001 - audit alerting must never break the agent turn
        logger.exception("Failed to send workspace_brief_stale alert")
