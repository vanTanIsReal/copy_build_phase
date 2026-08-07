from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from src.agents.state import AgentState
from src.services.llm import get_llm


@tool
async def extract_tasks(
    state: Annotated[AgentState, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """Extract action items, tasks, and appointments mentioned in the conversation the user is
    currently asking about, as a JSON array."""
    text = (state or {}).get("context", "")
    if not text.strip():
        return "[]"

    llm = get_llm()
    prompt = (
        "Extract action items, tasks, and appointments mentioned in the following conversation. "
        "Output ONLY a JSON array, no prose, no markdown code fence. Each item must be an object "
        'with exactly these keys: "title" (string, written in Vietnamese - tiếng Việt), "due_at" '
        '(ISO 8601 datetime string, or null if no date/time was mentioned), "priority" (one of '
        '"High", "Medium", "Low" - keep these three values exactly as-is, in English). If nothing '
        "is found, output [].\n\n"
        f"{text}"
    )
    result = await llm.ainvoke(prompt)
    return result.content
