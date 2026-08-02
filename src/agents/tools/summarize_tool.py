from typing import Annotated, Literal

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from src.agents.state import AgentState
from src.services.llm import get_llm


@tool
async def summarize_conversation(
    style: Literal["brief", "detailed", "bullet_points"] = "brief",
    state: Annotated[AgentState, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """Summarize the conversation the user is currently asking about.

    Args:
        style: Level of detail for the summary - "brief", "detailed", or "bullet_points".
    """
    text = (state or {}).get("context", "")
    if not text.strip():
        return "No conversation text was provided to summarize."

    llm = get_llm()
    prompt = f"Summarize the following conversation in a {style.replace('_', ' ')} style:\n\n{text}"
    result = await llm.ainvoke(prompt)
    return result.content
