from unittest.mock import AsyncMock

import pytest

from src.agents.tools import summarize_tool


@pytest.mark.asyncio
async def test_summarize_conversation_reads_context_from_state(monkeypatch):
    fake_llm = AsyncMock()
    fake_llm.ainvoke.return_value = AsyncMock(content="A short summary.", usage_metadata=None)
    monkeypatch.setattr(summarize_tool, "get_llm", lambda: fake_llm)

    state = {"context": "Alice: hi\nBob: let's meet tomorrow"}
    result = await summarize_tool.summarize_conversation.coroutine(style="brief", state=state)

    assert result == "A short summary."
    fake_llm.ainvoke.assert_awaited_once()
    prompt = fake_llm.ainvoke.await_args.args[0]
    assert "Alice: hi" in prompt
    assert "brief" in prompt


@pytest.mark.asyncio
async def test_summarize_conversation_no_context(monkeypatch):
    fake_llm = AsyncMock()
    monkeypatch.setattr(summarize_tool, "get_llm", lambda: fake_llm)

    result = await summarize_tool.summarize_conversation.coroutine(style="brief", state={})

    assert "No conversation text" in result
    fake_llm.ainvoke.assert_not_awaited()


def test_state_hidden_from_llm_tool_schema():
    assert list(summarize_tool.summarize_conversation.args.keys()) == ["style"]


@pytest.mark.asyncio
async def test_generate_summary_logs_usage(monkeypatch):
    """★ fix: generate_summary tự gọi LLM riêng nhưng trước đây không log usage - budget tracking
    tính thiếu lượt này. Xác nhận log_usage được gọi đúng với usage_metadata thật của LLM."""
    fake_llm = AsyncMock()
    fake_llm.ainvoke.return_value = AsyncMock(
        content="A short summary.",
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )
    monkeypatch.setattr(summarize_tool, "get_llm", lambda: fake_llm)

    logged = {}

    async def fake_log_usage(**kwargs):
        logged.update(kwargs)

    monkeypatch.setattr(summarize_tool.usage_service, "log_usage", fake_log_usage)

    result = await summarize_tool.generate_summary("Alice: hi\nBob: hello")

    assert result == "A short summary."
    assert logged["usage_metadata"]["total_tokens"] == 15
