from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from src.agents.graph import agent
from src.agents.tools import reminder_tool


def _config():
    return {"configurable": {"thread_id": str(uuid4())}}


def _script_tool_call(fake_llm_factory, tool_name: str, args: dict):
    def _final_message(state):
        last = state["messages"][-1]
        assert isinstance(last, ToolMessage)
        return AIMessage(content=f"final:{last.content}")

    responses = [AIMessage(content="", tool_calls=[{"name": tool_name, "args": args, "id": "call_1"}])]
    llm = fake_llm_factory(responses)
    real_ainvoke = llm.ainvoke

    async def ainvoke(messages):
        if llm._responses:
            return await real_ainvoke(messages)
        return _final_message({"messages": messages})

    llm.ainvoke = ainvoke
    return llm


@pytest.fixture(autouse=True)
def _clean_reminder_store():
    reminder_tool._reminders.clear()
    reminder_tool._fired_reminders.clear()
    yield
    reminder_tool._reminders.clear()
    reminder_tool._fired_reminders.clear()


@pytest.mark.asyncio
async def test_create_reminder_interrupts_then_schedules(monkeypatch, fake_llm_factory):
    recorded_jobs = []
    monkeypatch.setattr(
        reminder_tool.scheduler,
        "add_job",
        lambda func, trigger, run_date, args, id: recorded_jobs.append({"run_date": run_date, "reminder_id": args[0]}),
    )

    due_at = "2026-08-10T15:00:00"
    llm = _script_tool_call(
        fake_llm_factory,
        "create_reminder",
        {"title": "Product launch call", "due_at_iso": due_at, "lead_minutes": 30},
    )
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    config = _config()
    result = await agent.ainvoke({"messages": [HumanMessage(content="remind me")]}, config)

    interrupts = result.get("__interrupt__")
    assert interrupts is not None
    assert interrupts[0].value["type"] == "reminder"
    assert not recorded_jobs

    result2 = await agent.ainvoke(Command(resume={"approved": True}), config)
    final = result2["messages"][-1]
    assert "scheduled to fire" in final.content
    assert len(recorded_jobs) == 1
    assert recorded_jobs[0]["run_date"] == datetime.fromisoformat(due_at) - timedelta(minutes=30)
    assert len(reminder_tool._reminders) == 1


def test_fire_reminder_marks_status_and_records():
    reminder_tool._reminders["r1"] = {"id": "r1", "title": "Test", "status": "scheduled"}

    reminder_tool._fire_reminder("r1")

    assert reminder_tool._reminders["r1"]["status"] == "fired"
    assert reminder_tool._fired_reminders == [reminder_tool._reminders["r1"]]


def test_fire_reminder_missing_id_is_noop():
    reminder_tool._fire_reminder("does-not-exist")
    assert reminder_tool._fired_reminders == []
