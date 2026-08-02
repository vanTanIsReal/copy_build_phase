import logging
from datetime import datetime, timedelta
from uuid import uuid4

from langchain_core.tools import tool
from langgraph.types import interrupt

from src.services.scheduler import scheduler

logger = logging.getLogger(__name__)

# In-memory reminder store. Lost on server restart - no DB is wired up for this yet.
_reminders: dict[str, dict] = {}
_fired_reminders: list[dict] = []


def _fire_reminder(reminder_id: str) -> None:
    """Job callback executed by APScheduler when a reminder's lead time elapses.

    Scoping simplification: firing today just logs and records the reminder as fired.
    Real delivery (e.g. WebSocket push to the client) is a separate, later piece of work.
    """
    record = _reminders.get(reminder_id)
    if not record:
        return
    record["status"] = "fired"
    _fired_reminders.append(record)
    logger.info("Reminder fired: %s", record)


@tool
async def create_reminder(title: str, due_at_iso: str, lead_minutes: int = 30, message: str = "") -> str:
    """Draft a reminder that fires lead_minutes before due_at_iso. Requires the user's
    explicit confirmation before it is actually scheduled.

    Args:
        title: Short title of the reminder.
        due_at_iso: When the reminded-about thing is due, as an ISO 8601 datetime string.
        lead_minutes: How many minutes before due_at_iso to fire the reminder.
        message: Optional extra detail to show alongside the reminder.
    """
    draft = {"title": title, "due_at": due_at_iso, "lead_minutes": lead_minutes, "message": message}
    decision = interrupt({"type": "reminder", "draft": draft})
    if not decision or not decision.get("approved"):
        return "Reminder was not scheduled (user declined)."

    draft.update(decision.get("edits") or {})
    reminder_id = str(uuid4())
    fire_at = datetime.fromisoformat(draft["due_at"]) - timedelta(minutes=draft["lead_minutes"])
    _reminders[reminder_id] = {**draft, "id": reminder_id, "status": "scheduled"}
    scheduler.add_job(_fire_reminder, "date", run_date=fire_at, args=[reminder_id], id=reminder_id)
    return f"Reminder '{draft['title']}' scheduled to fire at {fire_at.isoformat()}."


@tool
async def list_reminders() -> str:
    """List currently scheduled reminders. Read-only, no confirmation needed."""
    if not _reminders:
        return "No reminders scheduled."
    return "\n".join(f"- {r['title']} ({r['status']}, due {r['due_at']})" for r in _reminders.values())
