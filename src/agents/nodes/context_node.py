from __future__ import annotations

from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages

from src.agents.state import AgentState
from src.config import get_settings
from src.services import guardrail_service, memory_service


def _last_user_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage) and isinstance(message.content, str):
            return message.content
    return state.get("query", "")


def _fit(text: str, token_budget: int) -> str:
    # Conservative provider-independent approximation; count_tokens_approximately is used for
    # message objects below. Never split beyond the budget just because a retrieval source is big.
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
    """Build the optional context layers: query-ranked recall from the user's saved Memory notes
    and from MemoryEpisode summaries (memory_maintenance_service.py's background consolidation of
    past assistant threads), each token-budgeted as a fraction of agent_context_window_tokens.

    Runs once per turn, after input_guardrail (so a blocked/clarification-needed request never
    reaches this far) and before planner - NOT on every planner<->tools loop iteration, so its
    output (memory_context/episodic_context/prompt_messages) reflects the turn's opening state,
    not anything a tool call produces later in the same turn. planner_node.py accounts for this:
    it uses memory_context/episodic_context (safe - just extra text) but always the real, live
    `messages` rather than this node's prompt_messages for the actual LLM call. Never raises - a
    failure here must not break the turn, just fall back to empty context (planner_node.py already
    treats that as "no memory/episode context").
    """
    settings = get_settings()
    query = _last_user_text(state)
    owner_id = state.get("user_id")

    try:
        memories = await memory_service.retrieve_memories(owner_id, query)
    except Exception:  # noqa: BLE001 - context enrichment must never break the agent turn
        memories = []
    try:
        episodes = await memory_service.retrieve_episodes(owner_id, query)
    except Exception:  # noqa: BLE001
        episodes = []

    memory_lines = []
    for memory in memories:
        line = f"[{memory.memory_type}/{memory.category}] {memory.title}"
        if memory.detail:
            line += f": {memory.detail}"
        memory_lines.append(guardrail_service.sanitize_untrusted_text(line))

    episode_lines = []
    for episode in episodes:
        line = episode.summary
        if episode.decisions:
            line += " | decisions: " + "; ".join(map(str, episode.decisions))
        if episode.open_loops:
            line += " | open loops: " + "; ".join(map(str, episode.open_loops))
        episode_lines.append(guardrail_service.sanitize_untrusted_text(line))

    long_budget = int(settings.agent_context_window_tokens * settings.memory_long_term_fraction)
    episode_budget = int(settings.agent_context_window_tokens * settings.memory_episodic_fraction)
    trimmed = list(budgeted_messages(state))
    return {
        "memory_context": _fit("\n".join(memory_lines), long_budget),
        "episodic_context": _fit("\n".join(episode_lines), episode_budget),
        # Deliberately does NOT touch state["context"] (the real 1-1/group conversation excerpt,
        # set upstream in routes.py before the graph runs): summarize_conversation/extract_tasks
        # (src/agents/tools/summarize_tool.py, task_tool.py) read it straight from state via
        # InjectedState and need it verbatim/unabridged - budgeting it here to
        # memory_retrieval_fraction's tiny share of the window would silently truncate what they
        # summarize/extract from on any conversation longer than a few hundred tokens.
        "prompt_messages": trimmed,
        "context_metadata": {
            "short_term_tokens": sum(count_tokens_approximately([m]) for m in trimmed),
            "long_term_memories": len(memories),
            "episodes": len(episodes),
        },
    }
