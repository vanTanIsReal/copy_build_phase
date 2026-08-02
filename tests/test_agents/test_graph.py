from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from src.agents.graph import agent


def _config():
    return {"configurable": {"thread_id": str(uuid4())}}


@pytest.mark.asyncio
async def test_agent_basic_flow_no_tool_call(monkeypatch, fake_llm_factory):
    reply = AIMessage(content="Just a plain reply, no tools needed.")
    llm = fake_llm_factory([reply])
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    result = await agent.ainvoke({"messages": [HumanMessage(content="Hello")]}, _config())

    assert "__interrupt__" not in result
    assert result["messages"][-1].content == "Just a plain reply, no tools needed."


@pytest.mark.asyncio
async def test_agent_interrupt_then_resume_round_trip(monkeypatch, fake_llm_factory):
    """Drive the full interrupt -> resume round trip through the compiled graph,
    using create_calendar_event as the tool that pauses for confirmation."""

    def _final_message(state):
        last = state["messages"][-1]
        assert isinstance(last, ToolMessage)
        return AIMessage(content=f"final:{last.content}")

    responses = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "create_calendar_event",
                    "args": {
                        "summary": "Sync",
                        "start_iso": "2026-08-01T10:00:00",
                        "end_iso": "2026-08-01T10:30:00",
                    },
                    "id": "call_1",
                }
            ],
        )
    ]
    llm = fake_llm_factory(responses)
    real_ainvoke = llm.ainvoke

    async def ainvoke(messages):
        if llm._responses:
            return await real_ainvoke(messages)
        return _final_message({"messages": messages})

    llm.ainvoke = ainvoke
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    fake_service = None
    from unittest.mock import MagicMock

    from src.agents.tools import calendar_tool

    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt-1"}
    monkeypatch.setattr(calendar_tool, "_get_calendar_service", lambda: fake_service)

    config = _config()
    result = await agent.ainvoke({"messages": [HumanMessage(content="book a sync")]}, config)
    assert result["__interrupt__"][0].value["type"] == "calendar_event"

    result2 = await agent.ainvoke(Command(resume={"approved": True}), config)
    assert "Event created" in result2["messages"][-1].content
