from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import llm as llm_service


@pytest.mark.asyncio
async def test_invoke_with_fallback_uses_next_configured_provider(monkeypatch):
    primary = AsyncMock()
    primary.ainvoke.side_effect = RuntimeError("primary unavailable")
    fallback = AsyncMock()
    fallback.ainvoke.return_value = SimpleNamespace(content="ok")

    monkeypatch.setattr(
        llm_service,
        "get_settings",
        lambda: SimpleNamespace(llm_provider="google", model_name="primary-model"),
    )
    monkeypatch.setattr(
        llm_service,
        "_candidates",
        lambda: [("google", "primary-model"), ("openai", "fallback-model")],
    )
    monkeypatch.setattr(
        llm_service,
        "_build_llm",
        lambda provider, model, *, temperature=None: fallback,
    )

    result = await llm_service.invoke_with_fallback("hello", primary_llm=primary)

    assert result.message.content == "ok"
    assert (result.provider, result.model) == ("openai", "fallback-model")
    primary.ainvoke.assert_awaited_once_with("hello")
    fallback.ainvoke.assert_awaited_once_with("hello")
