from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from langgraph.types import interrupt

from src.agents.state import AgentState
from src.services import reminder_service


def _agent_identity(state: AgentState | None) -> tuple[str, str]:
    user_id = (state or {}).get("user_id")
    workspace_id = (state or {}).get("workspace_id")
    if not user_id or not workspace_id:
        raise ValueError("Authenticated user and workspace context are required")
    return user_id, workspace_id


@tool
async def create_reminder(
    title: str,
    due_at_iso: str,
    lead_minutes: int = 30,
    message: str = "",
    state: Annotated[AgentState, InjectedState] = None,  # type: ignore[assignment]
) -> str:
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
    user_id, workspace_id = _agent_identity(state)
    reminder = await reminder_service.schedule_reminder(
        workspace_id=workspace_id,
        owner_id=user_id,
        title=draft["title"],
        due_at_iso=draft["due_at"],
        lead_minutes=draft["lead_minutes"],
        message=draft["message"],
        source="agent",
    )
    return f"Reminder '{draft['title']}' scheduled to fire at {reminder.fire_at.isoformat()}."


@tool
async def list_reminders(
    state: Annotated[AgentState, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """List currently scheduled reminders. Read-only, no confirmation needed."""
    user_id, workspace_id = _agent_identity(state)
    reminders = await reminder_service.list_reminders(owner_id=user_id, workspace_id=workspace_id)
    if not reminders:
        return "No reminders scheduled."
    return "\n".join(f"- {r.title} ({r.status}, due {r.due_at.isoformat()})" for r in reminders)
