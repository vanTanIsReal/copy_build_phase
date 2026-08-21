import pytest

from src.services import quick_action_service


@pytest.mark.asyncio
async def test_run_quick_action_summarize_calls_generate_summary(monkeypatch):
    called = {}

    async def fake_generate_summary(context):
        called["context"] = context
        return "summary text"

    monkeypatch.setattr(quick_action_service, "generate_summary", fake_generate_summary)

    result = await quick_action_service.run_quick_action("summarize", "ctx")

    assert result == "summary text"
    assert called["context"] == "ctx"


@pytest.mark.asyncio
async def test_run_quick_action_extract_tasks_calls_generate_tasks_json(monkeypatch):
    called = {}

    async def fake_generate_tasks_json(context):
        called["context"] = context
        return "[]"

    monkeypatch.setattr(quick_action_service, "generate_tasks_json", fake_generate_tasks_json)

    result = await quick_action_service.run_quick_action("extract_tasks", "ctx")

    assert result == "[]"
    assert called["context"] == "ctx"
