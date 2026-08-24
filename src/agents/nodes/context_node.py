from __future__ import annotations

from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages

from src.agents.state import AgentState
from src.config import get_settings
from src.services import guardrail_service, memory_service

# Adapted from the guardrail/agent-memory design in copy_build_phase's old snapshot (see
# WORKLOG/ARCHITECTURE for context) - trimmed to what src/services/memory_service.py actually
# supports today. The old version also injected a retrieved "episodic_context" built from
# MemoryEpisode rows produced by a separate memory_maintenance_service consolidation job; neither
# that table nor that job exist in this codebase yet, so episodic_context is intentionally left
# out rather than half-built. memory_context below only covers the user's own saved Memory notes
# (src/services/memory_service.py's list_memories_for_owner), same data the list_memories tool
# already exposes to the planner - this just also surfaces it as ambient context so the planner
# doesn't need to call the tool for something already relevant to the current turn.


def _last_user_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage) and isinstance(message.content, str):
            return message.content
    return state.get("query", "")


def _fit(text: str, token_budget: int) -> str:
    # Conservative provider-independent approximation; count_tokens_approximately is used for
    # message objects below. Never split beyond the budget just because a source is large.
    char_budget = max(0, token_budget * 4)
    if len(text) <= char_budget:
        return text
    return text[:char_budget].rsplit("\n", 1)[0] + "\n[context trimmed]"


def budgeted_messages(state: AgentState):
    settings = get_settings()
    max_tokens = max(512, int(settings.agent_context_window_tokens * settings.memory_short_term_fraction))
    return trim_messages(
        state.get("messages", []),
        max_tokens=max_tokens,
        token_counter=count_tokens_approximately,
        strategy="last",
        include_system=False,
        allow_partial=False,
    )


async def context_node(state: AgentState) -> dict:
    """Build the token-budgeted prompt context: recent turns + the user's saved memories.

    Runs after input_guardrail (so a blocked/clarification-needed request never reaches this far)
    and before planner. Never raises - a failure here must not break the turn, just fall back to
    an empty memory_context (planner_node.py already handles that as "no memory context").
    """
    settings = get_settings()
    owner_id = state.get("user_id")

    memory_lines: list[str] = []
    try:
        memories = await memory_service.list_memories_for_owner(owner_id) if owner_id else []
    except Exception:  # noqa: BLE001 - context enrichment must never break the agent turn
        memories = []
    for memory in memories:
        line = f"[{memory.category}] {memory.title}"
        if memory.detail:
            line += f": {memory.detail}"
        memory_lines.append(guardrail_service.sanitize_untrusted_text(line))

    long_budget = int(settings.agent_context_window_tokens * settings.memory_long_term_fraction)
    trimmed = list(budgeted_messages(state))
    return {
        "memory_context": _fit("\n".join(memory_lines), long_budget),
        "prompt_messages": trimmed,
        "context_metadata": {
            "short_term_tokens": sum(count_tokens_approximately([m]) for m in trimmed),
            "long_term_memories": len(memories),
        },
    }
