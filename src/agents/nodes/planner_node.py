from langchain_core.messages import AIMessage, SystemMessage

from src.agents.state import AgentState
from src.agents.tools import ALL_TOOLS
from src.services.llm import get_llm

SYSTEM_PROMPT = (
    "You are a personal assistant embedded in a chat app. You can summarize conversations, "
    "draft Google Calendar events, and schedule reminders. Use the available tools when the "
    "user's request calls for it. Calendar and reminder actions always require the user's "
    "explicit confirmation before they take effect; summarization does not."
)


async def planner_node(state: AgentState) -> dict:
    """Bind tools to the LLM and decide the next action (respond or call a tool)."""
    try:
        llm = get_llm().bind_tools(ALL_TOOLS)
        messages = state.get("messages", [])
        ai_message: AIMessage = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), *messages])
        return {"messages": [ai_message]}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
