from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from src.agents.state import AgentState
from src.config import get_settings
from src.services import usage_service
from src.services.llm import invoke_with_fallback


async def generate_tasks_json(context: str) -> str:
    """Build the prompt, call the LLM once, log usage, and return the raw JSON array text. This is
    the real logic - `extract_tasks` below is a thin @tool wrapper around it for the LangGraph
    path; `quick_action_service` calls this directly for AIPanel's Extract tasks button (routes.py
    bypasses the planner entirely there, see ROADMAP.md "batch LLM call")."""
    text = context or ""
    if not text.strip():
        return "[]"

    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.calendar_timezone))
    prompt = (
        "Extract action items, tasks, and appointments mentioned in the following conversation. "
        "Output ONLY a JSON array, no prose, no markdown code fence. Each item must be an object "
        'with exactly these keys: "title" (string, written in Vietnamese - tiếng Việt), "due_at" '
        '(ISO 8601 datetime string, or null if no date/time was mentioned), "priority" (one of '
        '"High", "Medium", "Low" - keep these three values exactly as-is, in English). Resolve '
        "relative dates/times (\"tomorrow\", \"next Monday\", \"in an hour\") against the current "
        f"date and time, which is {now.strftime('%A, %Y-%m-%d %H:%M')} ({settings.calendar_timezone}). "
        "If nothing is found, output [].\n\n"
        f"{text}"
    )
    call = await invoke_with_fallback(prompt)
    result = call.message
    await usage_service.log_usage(
        provider=call.provider, model=call.model, usage_metadata=result.usage_metadata
    )
    return result.content


@tool
async def extract_tasks(
    state: Annotated[AgentState, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """Extract action items, tasks, and appointments mentioned in the conversation the user is
    currently asking about, as a JSON array."""
    return await generate_tasks_json((state or {}).get("context", ""))
