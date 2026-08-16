from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from src.agents.state import AgentState
from src.services import memory_service


@tool
async def list_memories(state: Annotated[AgentState, InjectedState] = None) -> str:  # type: ignore[assignment]
    """List things the user has explicitly asked Orbit to remember about them (preferences,
    habits, people they work with, etc. - from the /memory page). This is long-term personal
    memory the user manages themselves, distinct from this conversation's own chat history. Use it
    to answer questions like "what do you remember about how I work" or to personalize an answer.
    Read-only, no confirmation needed."""
    memories = await memory_service.list_memories_for_owner((state or {}).get("user_id"))
    if not memories:
        return "The user has no saved memories yet."
    return "\n".join(f"- [{m.category}] {m.title}: {m.detail}" if m.detail else f"- [{m.category}] {m.title}" for m in memories)
