from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage


@pytest.fixture(autouse=True)
def _no_live_llm(monkeypatch, fake_llm_factory):
    """Every route test gets a fake LLM by default so nothing hits a live OpenAI key."""
    reply = AIMessage(content="Mocked agent reply.")
    llm = fake_llm_factory([reply])
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)
    return llm


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_empty_message(client):
    response = await client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_chat_completed_response(client):
    response = await client.post("/api/v1/chat", json={"message": "hello"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["response"] == "Mocked agent reply."
    assert data["thread_id"]


@pytest.mark.asyncio
async def test_chat_uses_provided_messages_as_context(client, monkeypatch, fake_llm_factory):
    captured = {}
    reply = AIMessage(content="Summary done.")
    llm = fake_llm_factory([reply])

    async def ainvoke(messages):
        captured["messages"] = messages
        return reply

    llm.ainvoke = ainvoke
    monkeypatch.setattr("src.agents.nodes.planner_node.get_llm", lambda: llm)

    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "Summarize this",
            "messages": [
                {"role": "user", "sender": "Alice", "content": "hi"},
                {"role": "user", "sender": "Bob", "content": "let's meet tomorrow"},
            ],
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_interrupts_and_resume_completes(client, monkeypatch, fake_llm_factory):
    from src.agents.tools import calendar_tool

    fake_service = MagicMock()
    fake_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt-1"}
    monkeypatch.setattr(calendar_tool, "_get_calendar_service", lambda: fake_service)

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

    response = await client.post("/api/v1/chat", json={"message": "book a sync"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "interrupted"
    assert data["interrupt"]["type"] == "calendar_event"
    thread_id = data["thread_id"]

    resume_response = await client.post("/api/v1/chat/resume", json={"thread_id": thread_id, "approved": True})
    assert resume_response.status_code == 200
    resume_data = resume_response.json()
    assert resume_data["status"] == "completed"
    assert "Event created" in resume_data["response"]


@pytest.mark.asyncio
async def test_agent_status(client):
    response = await client.get("/api/v1/status")
    assert response.status_code == 200
