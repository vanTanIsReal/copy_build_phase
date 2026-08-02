from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from src.agents.graph import agent
from src.agents.tools import calendar_tool


def _config():
    return {"configurable": {"thread_id": str(uuid4())}}


def _script_tool_call(fake_llm_factory, tool_name: str, args: dict):
    """First planner turn calls the tool; second turn (after the ToolMessage) replies."""

    def _final_message(state):
        last = state["messages"][-1]
        assert isinstance(last, ToolMessage)
        return AIMessage(content=f"final:{last.content}")

    responses = [
        AIMessage(content="", tool_calls=[{"name": tool_name, "args": args, "id": "call_1"}]),
    ]
    llm = fake_llm_factory(responses)
    real_ainvoke = llm.ainvoke

    async def ainvoke(messages):
        if llm._responses:
            return await real_ainvoke(messages)
        return _final_message({"messages": messages})

    llm.ainvoke = ainvoke
    return llm


@pytest.mark.asyncio
async def test_create_calendar_event_interrupts_then_creates(monkeypatch, fake_llm_factory):
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "htmlLink": "https://calendar.google.com/event?eid=abc"
    }
    monkeypatch.setattr(calendar_tool, "_get_calendar_service", lambda: fake_service)

    llm = _script_tool_call(
        fake_llm_factory,
        "create_calendar_event",
        {"summary": "Launch review", "start_iso": "2026-08-01T11:00:00", "end_iso": "2026-08-01T12:00:00"},
    )
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    config = _config()
    result = await agent.ainvoke({"messages": [HumanMessage(content="schedule the review")]}, config)

    interrupts = result.get("__interrupt__")
    assert interrupts is not None
    assert interrupts[0].value["type"] == "calendar_event"
    assert interrupts[0].value["draft"]["summary"] == "Launch review"
    fake_service.events.return_value.insert.assert_not_called()

    result2 = await agent.ainvoke(Command(resume={"approved": True}), config)
    final = result2["messages"][-1]
    assert "Event created" in final.content
    fake_service.events.return_value.insert.assert_called_once()


@pytest.mark.asyncio
async def test_create_calendar_event_declined(monkeypatch, fake_llm_factory):
    fake_service = MagicMock()
    monkeypatch.setattr(calendar_tool, "_get_calendar_service", lambda: fake_service)

    llm = _script_tool_call(
        fake_llm_factory,
        "create_calendar_event",
        {"summary": "Launch review", "start_iso": "2026-08-01T11:00:00", "end_iso": "2026-08-01T12:00:00"},
    )
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    config = _config()
    await agent.ainvoke({"messages": [HumanMessage(content="schedule the review")]}, config)

    result2 = await agent.ainvoke(Command(resume={"approved": False}), config)
    final = result2["messages"][-1]
    assert "not created" in final.content
    fake_service.events.return_value.insert.assert_not_called()
