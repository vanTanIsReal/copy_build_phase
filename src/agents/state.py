from __future__ import annotations

from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """State schema cho LangGraph agent.

    Mỗi node đọc và ghi vào state này.
    total=False cho phép tất cả fields là optional.
    """

    query: str
    context: str
    analysis: str
    response: str
    error: str
    metadata: dict
    guardrail_blocked: bool
    guardrail_requires_clarification: bool
    user_id: str | None  # id of the user driving this run, for tools that push WS updates to them
    workspace_id: str | None  # active workspace for tenant-scoped tools
    conversation_id: str | None
    consent_scope_hash: str | None
    source_message_ids: list[str]
    thread_summary: str
    thread_id: str | None
    user_context: dict
    memory_context: str
    episodic_context: str
    conversation_summary_context: str
    prompt_messages: list[AnyMessage]
    context_metadata: dict

    # Tool-calling planner loop (messages, ToolNode, tools_condition all require this).
    messages: Annotated[list[AnyMessage], add_messages]

    # Structured outputs of the summarize/calendar/reminder tools.
    summary: str
    calendar_event_draft: dict | None
    reminder_draft: dict | None
