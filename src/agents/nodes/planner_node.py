from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, SystemMessage

from src.agents.state import AgentState
from src.agents.tools import ALL_TOOLS
from src.config import get_settings
from src.services import usage_service
from src.services.llm import get_llm

SYSTEM_PROMPT_TEMPLATE = (
    "You are a personal assistant embedded in a chat app. You can summarize conversations, "
    "extract action items/tasks from a conversation, and manage Google Calendar events (list, "
    "create, update, delete) and reminders (list, create). Use list_calendar_events first to find "
    "an event's id before updating or deleting it. Use the available tools when the user's request "
    "calls for it. Calendar and reminder actions that change something (create/update/delete) "
    "always require the user's explicit confirmation before they take effect; listing, "
    "summarization, and task extraction do not. "
    "The current date and time is {current_datetime} ({timezone}). Use this as the reference "
    "point for resolving relative dates/times such as 'tomorrow', 'next Monday', or 'in an hour' "
    "when drafting calendar events or reminders. "
    "When a tool returns a result, relay it to the user as-is — do not re-summarize it, "
    "expand it, add extra formats, or add commentary before/after it. "
    "Always reply in Vietnamese (tiếng Việt), regardless of what language the user or the "
    "conversation being analyzed is in."
)


def _build_system_prompt() -> str:
    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.calendar_timezone))
    return SYSTEM_PROMPT_TEMPLATE.format(
        current_datetime=now.strftime("%A, %Y-%m-%d %H:%M"),
        timezone=settings.calendar_timezone,
    )


async def planner_node(state: AgentState) -> dict:
    """Bind tools to the LLM and decide the next action (respond or call a tool)."""
    settings = get_settings()
    try:
        llm = get_llm().bind_tools(ALL_TOOLS)
        messages = state.get("messages", [])
        ai_message: AIMessage = await llm.ainvoke([SystemMessage(content=_build_system_prompt()), *messages])
        await usage_service.log_usage(
            provider=settings.llm_provider,
            model=settings.model_name,
            usage_metadata=ai_message.usage_metadata,
        )
        return {"messages": [ai_message]}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
