from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from src.agents import graph as agent_graph
from src.services import calendar_service

_USER_ID = "test-user-calendar-tool"


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


def _mock_service(monkeypatch, fake_service):
    async def _fake(user_id):
        return fake_service

    monkeypatch.setattr(calendar_service, "_service", _fake)


@pytest.mark.asyncio
async def test_create_calendar_event_interrupts_then_creates(monkeypatch, fake_llm_factory):
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-abc",
        "htmlLink": "https://calendar.google.com/event?eid=abc",
    }
    fake_service.events.return_value.list.return_value.execute.return_value = {"items": []}
    _mock_service(monkeypatch, fake_service)

    llm = _script_tool_call(
        fake_llm_factory,
        "create_calendar_event",
        {"summary": "Launch review", "start_iso": "2026-08-01T11:00:00", "end_iso": "2026-08-01T12:00:00"},
    )
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    config = _config()
    result = await agent_graph.agent.ainvoke(
        {"messages": [HumanMessage(content="schedule the review")], "user_id": _USER_ID}, config
    )

    interrupts = result.get("__interrupt__")
    assert interrupts is not None
    assert interrupts[0].value["type"] == "calendar_event"
    assert interrupts[0].value["draft"]["summary"] == "Launch review"
    fake_service.events.return_value.insert.assert_not_called()

    result2 = await agent_graph.agent.ainvoke(Command(resume={"approved": True}), config)
    final = result2["messages"][-1]
    assert "Event created" in final.content
    fake_service.events.return_value.insert.assert_called_once()


@pytest.mark.asyncio
async def test_create_calendar_event_declined(monkeypatch, fake_llm_factory):
    fake_service = MagicMock()
    fake_service.events.return_value.list.return_value.execute.return_value = {"items": []}
    _mock_service(monkeypatch, fake_service)

    llm = _script_tool_call(
        fake_llm_factory,
        "create_calendar_event",
        {"summary": "Launch review", "start_iso": "2026-08-01T11:00:00", "end_iso": "2026-08-01T12:00:00"},
    )
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    config = _config()
    await agent_graph.agent.ainvoke(
        {"messages": [HumanMessage(content="schedule the review")], "user_id": _USER_ID}, config
    )

    result2 = await agent_graph.agent.ainvoke(Command(resume={"approved": False}), config)
    final = result2["messages"][-1]
    assert "not created" in final.content
    fake_service.events.return_value.insert.assert_not_called()


@pytest.mark.asyncio
async def test_create_calendar_event_not_connected(monkeypatch, fake_llm_factory):
    """No GoogleCalendarCredential row for this user - real (unmocked) credential-resolution path
    should surface as a friendly tool message, not a crash. The conflict check now runs before the
    confirmation interrupt, so a not-connected account fails fast in the very first turn - there's
    no draft worth confirming if we already know saving it would fail, and no interrupt is left
    pending to resume."""
    llm = _script_tool_call(
        fake_llm_factory,
        "create_calendar_event",
        {"summary": "Launch review", "start_iso": "2026-08-01T11:00:00", "end_iso": "2026-08-01T12:00:00"},
    )
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    config = _config()
    result = await agent_graph.agent.ainvoke(
        {"messages": [HumanMessage(content="schedule the review")], "user_id": "user-with-no-calendar"}, config
    )

    assert result.get("__interrupt__") is None
    final = result["messages"][-1]
    assert "hasn't connected Google Calendar" in final.content


@pytest.mark.asyncio
async def test_create_calendar_event_conflict_offers_alternatives(monkeypatch, fake_llm_factory):
    """Propose & Verify: an overlapping event turns up in the draft's `conflicts`, and up to 2
    free alternative slots are computed and attached - all before the user is ever asked to
    confirm. Picking an alternative via `edits` creates the event at that time, not the original."""
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-abc",
        "htmlLink": "https://calendar.google.com/event?eid=abc",
    }
    fake_service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "evt-standup",
                "summary": "Standup",
                "start": {"dateTime": "2026-08-01T11:00:00"},
                "end": {"dateTime": "2026-08-01T11:30:00"},
            }
        ]
    }
    _mock_service(monkeypatch, fake_service)

    llm = _script_tool_call(
        fake_llm_factory,
        "create_calendar_event",
        {"summary": "Launch review", "start_iso": "2026-08-01T11:00:00", "end_iso": "2026-08-01T12:00:00"},
    )
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    config = _config()
    result = await agent_graph.agent.ainvoke(
        {"messages": [HumanMessage(content="schedule the review")], "user_id": _USER_ID}, config
    )

    draft = result["__interrupt__"][0].value["draft"]
    assert [c["title"] for c in draft["conflicts"]] == ["Standup"]
    assert draft["alternatives"][0] == {"start": "2026-08-01T11:30:00", "end": "2026-08-01T12:30:00"}
    assert len(draft["alternatives"]) == 2

    alt = draft["alternatives"][0]
    result2 = await agent_graph.agent.ainvoke(
        Command(resume={"approved": True, "edits": {"start": alt["start"], "end": alt["end"]}}), config
    )
    assert "Event created" in result2["messages"][-1].content
    body = fake_service.events.return_value.insert.call_args.kwargs["body"]
    assert body["start"]["dateTime"] == alt["start"]


@pytest.mark.asyncio
async def test_create_calendar_event_conflict_confirmed_anyway(monkeypatch, fake_llm_factory):
    """Alternatives are offers, not a block - confirming without picking one still books the
    originally requested (conflicting) time, same as today's double-booking-allowed behavior."""
    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-abc",
        "htmlLink": "https://calendar.google.com/event?eid=abc",
    }
    fake_service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "evt-standup",
                "summary": "Standup",
                "start": {"dateTime": "2026-08-01T11:00:00"},
                "end": {"dateTime": "2026-08-01T11:30:00"},
            }
        ]
    }
    _mock_service(monkeypatch, fake_service)

    llm = _script_tool_call(
        fake_llm_factory,
        "create_calendar_event",
        {"summary": "Launch review", "start_iso": "2026-08-01T11:00:00", "end_iso": "2026-08-01T12:00:00"},
    )
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    config = _config()
    await agent_graph.agent.ainvoke(
        {"messages": [HumanMessage(content="schedule the review")], "user_id": _USER_ID}, config
    )

    result2 = await agent_graph.agent.ainvoke(Command(resume={"approved": True}), config)
    assert "Event created" in result2["messages"][-1].content
    body = fake_service.events.return_value.insert.call_args.kwargs["body"]
    assert body["start"]["dateTime"] == "2026-08-01T11:00:00"


@pytest.mark.asyncio
async def test_update_calendar_event_interrupts_then_updates(monkeypatch, fake_llm_factory):
    fake_service = MagicMock()
    fake_service.events.return_value.get.return_value.execute.return_value = {
        "id": "evt-1", "start": {"dateTime": "2026-08-01T11:00:00"}, "end": {"dateTime": "2026-08-01T12:00:00"},
    }
    fake_service.events.return_value.list.return_value.execute.return_value = {"items": []}
    fake_service.events.return_value.patch.return_value.execute.return_value = {
        "id": "evt-1", "summary": "Launch review (moved)", "htmlLink": "https://calendar.google.com/event?eid=evt1",
    }
    _mock_service(monkeypatch, fake_service)

    llm = _script_tool_call(
        fake_llm_factory, "update_calendar_event", {"event_id": "evt-1", "start_iso": "2026-08-01T15:00:00"}
    )
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    config = _config()
    result = await agent_graph.agent.ainvoke(
        {"messages": [HumanMessage(content="move the review")], "user_id": _USER_ID}, config
    )

    interrupts = result.get("__interrupt__")
    assert interrupts is not None
    assert interrupts[0].value["type"] == "calendar_event_update"
    assert interrupts[0].value["draft"].get("conflicts") is None
    fake_service.events.return_value.patch.assert_not_called()

    result2 = await agent_graph.agent.ainvoke(Command(resume={"approved": True}), config)
    final = result2["messages"][-1]
    assert "Event updated" in final.content
    fake_service.events.return_value.patch.assert_called_once()


@pytest.mark.asyncio
async def test_update_calendar_event_conflict_offers_alternatives(monkeypatch, fake_llm_factory):
    """Moving an event onto a time another event already occupies surfaces `conflicts` +
    `alternatives` in the draft, same Propose & Verify treatment create_calendar_event gets - and
    the event being moved is excluded from its own conflict list even if the old and new time
    happen to overlap."""
    fake_service = MagicMock()
    fake_service.events.return_value.get.return_value.execute.return_value = {
        "id": "evt-1", "start": {"dateTime": "2026-08-01T09:00:00"}, "end": {"dateTime": "2026-08-01T09:30:00"},
    }
    fake_service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "evt-standup",
                "summary": "Standup",
                "start": {"dateTime": "2026-08-01T11:00:00"},
                "end": {"dateTime": "2026-08-01T11:30:00"},
            }
        ]
    }
    fake_service.events.return_value.patch.return_value.execute.return_value = {
        "id": "evt-1", "htmlLink": "https://calendar.google.com/event?eid=evt1",
    }
    _mock_service(monkeypatch, fake_service)

    llm = _script_tool_call(
        fake_llm_factory, "update_calendar_event",
        {"event_id": "evt-1", "start_iso": "2026-08-01T11:00:00", "end_iso": "2026-08-01T11:30:00"},
    )
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    config = _config()
    result = await agent_graph.agent.ainvoke(
        {"messages": [HumanMessage(content="move the review to 11am")], "user_id": _USER_ID}, config
    )

    draft = result["__interrupt__"][0].value["draft"]
    assert [c["title"] for c in draft["conflicts"]] == ["Standup"]
    assert len(draft["alternatives"]) == 2

    result2 = await agent_graph.agent.ainvoke(Command(resume={"approved": True}), config)
    assert "Event updated" in result2["messages"][-1].content


@pytest.mark.asyncio
async def test_update_calendar_event_only_one_bound_merges_the_other_from_current_event(monkeypatch, fake_llm_factory):
    """Only start_iso is being changed - the conflict check must use the *current* end time, not
    leave the range half-open, so it actually checks against the real resulting time instead of
    silently skipping the check (which is what happens when only one bound is given and nothing
    is merged in)."""
    fake_service = MagicMock()
    fake_service.events.return_value.get.return_value.execute.return_value = {
        "id": "evt-1", "start": {"dateTime": "2026-08-01T09:00:00"}, "end": {"dateTime": "2026-08-01T09:30:00"},
    }
    fake_service.events.return_value.list.return_value.execute.return_value = {"items": []}
    fake_service.events.return_value.patch.return_value.execute.return_value = {"id": "evt-1"}
    _mock_service(monkeypatch, fake_service)

    # Only start_iso given (no end_iso) - the merged end used for the conflict check must be the
    # current event's end (09:30), captured via the mocked list() call args below. With no
    # merging, the check would have been skipped entirely (check_end would stay None).
    llm = _script_tool_call(
        fake_llm_factory, "update_calendar_event", {"event_id": "evt-1", "start_iso": "2026-08-01T11:00:00"}
    )
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    await agent_graph.agent.ainvoke(
        {"messages": [HumanMessage(content="move the review to 11am")], "user_id": _USER_ID}, _config()
    )

    fake_service.events.return_value.get.assert_called_once()
    kwargs = fake_service.events.return_value.list.call_args.kwargs
    assert kwargs["timeMin"] == "2026-08-01T11:00:00"
    assert kwargs["timeMax"] == "2026-08-01T09:30:00"


@pytest.mark.asyncio
async def test_delete_calendar_event_interrupts_then_deletes(monkeypatch, fake_llm_factory):
    fake_service = MagicMock()
    fake_service.events.return_value.delete.return_value.execute.return_value = {}
    _mock_service(monkeypatch, fake_service)

    llm = _script_tool_call(fake_llm_factory, "delete_calendar_event", {"event_id": "evt-1"})
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    config = _config()
    result = await agent_graph.agent.ainvoke(
        {"messages": [HumanMessage(content="cancel the review")], "user_id": _USER_ID}, config
    )

    interrupts = result.get("__interrupt__")
    assert interrupts is not None
    assert interrupts[0].value["type"] == "calendar_event_delete"
    fake_service.events.return_value.delete.assert_not_called()

    result2 = await agent_graph.agent.ainvoke(Command(resume={"approved": True}), config)
    final = result2["messages"][-1]
    assert "deleted" in final.content.lower()
    fake_service.events.return_value.delete.assert_called_once()


@pytest.mark.asyncio
async def test_delete_calendar_event_declined(monkeypatch, fake_llm_factory):
    fake_service = MagicMock()
    _mock_service(monkeypatch, fake_service)

    llm = _script_tool_call(fake_llm_factory, "delete_calendar_event", {"event_id": "evt-1"})
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    config = _config()
    await agent_graph.agent.ainvoke(
        {"messages": [HumanMessage(content="cancel the review")], "user_id": _USER_ID}, config
    )

    result2 = await agent_graph.agent.ainvoke(Command(resume={"approved": False}), config)
    final = result2["messages"][-1]
    assert "not deleted" in final.content
    fake_service.events.return_value.delete.assert_not_called()


@pytest.mark.asyncio
async def test_list_calendar_events_with_scope_resolves_deterministic_range(monkeypatch, fake_llm_factory):
    """The bug this fixes: the LLM used to freehand-compute time_min_iso/time_max_iso for "tuần
    này" and reliably got it wrong (anchoring at "now" instead of the start of the week, missing
    earlier-this-week events already past). scope removes that guesswork - calendar_service.
    resolve_scope() does the date math instead of the LLM."""
    fake_service = MagicMock()
    fake_service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "evt-1", "summary": "Standup", "start": {"dateTime": "2026-08-11T09:00:00"}}]
    }
    _mock_service(monkeypatch, fake_service)
    monkeypatch.setattr(
        calendar_service, "resolve_scope",
        lambda scope: ("2026-08-10T00:00:00+07:00", "2026-08-17T00:00:00+07:00"),
    )

    llm = _script_tool_call(fake_llm_factory, "list_calendar_events", {"scope": "this_week"})
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    result = await agent_graph.agent.ainvoke(
        {"messages": [HumanMessage(content="tuần này tôi có gì")], "user_id": _USER_ID}, _config()
    )

    kwargs = fake_service.events.return_value.list.call_args.kwargs
    assert kwargs["timeMin"] == "2026-08-10T00:00:00+07:00"
    assert kwargs["timeMax"] == "2026-08-17T00:00:00+07:00"
    assert "Standup" in result["messages"][-1].content


@pytest.mark.asyncio
async def test_list_calendar_events_with_explicit_range_still_works(monkeypatch, fake_llm_factory):
    fake_service = MagicMock()
    fake_service.events.return_value.list.return_value.execute.return_value = {"items": []}
    _mock_service(monkeypatch, fake_service)

    llm = _script_tool_call(
        fake_llm_factory, "list_calendar_events",
        {"time_min_iso": "2026-08-01T00:00:00", "time_max_iso": "2026-08-02T00:00:00"},
    )
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    result = await agent_graph.agent.ainvoke(
        {"messages": [HumanMessage(content="events tomorrow")], "user_id": _USER_ID}, _config()
    )

    kwargs = fake_service.events.return_value.list.call_args.kwargs
    assert kwargs["timeMin"] == "2026-08-01T00:00:00"
    assert kwargs["timeMax"] == "2026-08-02T00:00:00"
    assert "No events found" in result["messages"][-1].content


@pytest.mark.asyncio
async def test_list_calendar_events_without_scope_or_range_asks_for_one(monkeypatch, fake_llm_factory):
    fake_service = MagicMock()
    _mock_service(monkeypatch, fake_service)

    llm = _script_tool_call(fake_llm_factory, "list_calendar_events", {})
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    result = await agent_graph.agent.ainvoke(
        {"messages": [HumanMessage(content="list my events")], "user_id": _USER_ID}, _config()
    )

    fake_service.events.return_value.list.assert_not_called()
    assert "khoảng thời gian" in result["messages"][-1].content
