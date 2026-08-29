import pytest

from src.config import get_settings
from src.db import session as db_session
from src.db.models import SystemConfig
from src.services import ai_config_service


@pytest.fixture(autouse=True)
def _restore_settings_after():
    """apply_ai_configuration mutates the @lru_cache'd Settings singleton in place - every test in
    this file must leave it exactly as it found it, or a later test elsewhere in the same pytest
    session (same process, same singleton) would silently run against the wrong provider/model."""
    settings = get_settings()
    original = (settings.llm_provider, settings.model_name, settings.llm_temperature)
    yield
    settings.llm_provider, settings.model_name, settings.llm_temperature = original


def test_configured_providers_reflects_settings_api_keys():
    settings = get_settings()
    expected = {
        provider
        for provider, api_key in [
            ("google", settings.google_api_key),
            ("openai", settings.openai_api_key),
            ("groq", settings.groq_api_key),
            ("openrouter", settings.openrouter_api_key),
        ]
        if api_key
    }
    assert set(ai_config_service.configured_providers()) == expected


def test_is_supported_model():
    assert ai_config_service.is_supported_model("google", "gemini-2.5-flash") is True
    assert ai_config_service.is_supported_model("openrouter", "openai/gpt-4.1-mini") is True
    assert ai_config_service.is_supported_model("google", "not-a-real-model") is False
    assert ai_config_service.is_supported_model("not-a-real-provider", "anything") is False


def test_apply_ai_configuration_mutates_the_shared_settings_object():
    ai_config_service.apply_ai_configuration("groq", "llama-3.1-8b-instant", 1.2)
    settings = get_settings()
    assert settings.llm_provider == "groq"
    assert settings.model_name == "llama-3.1-8b-instant"
    assert settings.llm_temperature == 1.2


@pytest.mark.asyncio
async def test_load_saved_ai_configuration_is_noop_when_nothing_saved():
    before = (get_settings().llm_provider, get_settings().model_name, get_settings().llm_temperature)
    await ai_config_service.load_saved_ai_configuration()
    after = (get_settings().llm_provider, get_settings().model_name, get_settings().llm_temperature)
    assert before == after


@pytest.mark.asyncio
async def test_load_saved_ai_configuration_applies_a_valid_saved_choice(client):
    # `client` is here purely for the truncate-after-test isolation its fixture teardown provides
    # (see conftest.py) - both this test and the one below write a SystemConfig row with the same
    # fixed id="default" primary key, which would collide without truncation in between.
    async with db_session.async_session_maker() as db:
        db.add(SystemConfig(id="default", llm_provider="google", model_name="gemini-2.5-flash-lite", llm_temperature=0.3))
        await db.commit()

    await ai_config_service.load_saved_ai_configuration()

    settings = get_settings()
    assert settings.llm_provider == "google"
    assert settings.model_name == "gemini-2.5-flash-lite"
    assert settings.llm_temperature == 0.3


@pytest.mark.asyncio
async def test_load_saved_ai_configuration_ignores_unsupported_saved_model(client):
    async with db_session.async_session_maker() as db:
        db.add(SystemConfig(id="default", llm_provider="google", model_name="not-a-real-model", llm_temperature=0.5))
        await db.commit()

    before = (get_settings().llm_provider, get_settings().model_name)
    await ai_config_service.load_saved_ai_configuration()
    after = (get_settings().llm_provider, get_settings().model_name)
    assert before == after  # bad saved value discarded, .env defaults kept - no crash either
