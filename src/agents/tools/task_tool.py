from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from src.agents.state import AgentState
from src.config import get_settings
from src.services import chat_service, task_service, usage_service
from src.services.llm import get_llm


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
    llm = get_llm()
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
    result = await llm.ainvoke(prompt)
    await usage_service.log_usage(
        provider=settings.llm_provider, model=settings.model_name, usage_metadata=result.usage_metadata
    )
    return result.content


@tool
async def extract_tasks(
    state: Annotated[AgentState, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """Extract action items, tasks, and appointments mentioned in the conversation the user is
    currently asking about, as a JSON array."""
    return await generate_tasks_json((state or {}).get("context", ""))


@tool
async def list_tasks(state: Annotated[AgentState, InjectedState] = None) -> str:  # type: ignore[assignment]
    """List the current user's own tasks (from /tasks - manually created, or previously accepted
    from an AI suggestion), sorted soonest-due first. Use this to answer questions about their
    deadlines, to-do list, or what's overdue/upcoming - it is NOT the same as extract_tasks, which
    only reads the conversation currently open in the chat panel and never touches saved tasks.
    Read-only, no confirmation needed."""
    tasks = await task_service.list_tasks_for_owner((state or {}).get("user_id"))
    if not tasks:
        return "The user has no tasks saved."
    lines = []
    for t in tasks:
        due = chat_service.format_local_timestamp(t.due_at.isoformat()) if t.due_at else "no due date"
        lines.append(f"- {t.title} (status: {t.status}, priority: {t.priority}, due: {due})")
    return "\n".join(lines)
