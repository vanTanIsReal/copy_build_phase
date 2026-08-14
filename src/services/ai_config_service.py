import logging

from src.config import get_settings
from src.db import session as db_session
from src.db.models import SystemConfig

logger = logging.getLogger(__name__)

_SYSTEM_CONFIG_ID = "default"

# Keep this list intentionally limited to text/chat models suitable for the app's LangChain
# planner and tool-calling flow. Model identifiers are sent to the provider unchanged.
MODEL_OPTIONS: dict[str, list[dict[str, str]]] = {
    "google": [
        {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
        {"id": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash-Lite"},
    ],
    "openai": [
        {"id": "gpt-4.1-mini", "label": "GPT-4.1 mini"},
        {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
        {"id": "o4-mini", "label": "o4-mini"},
    ],
    "groq": [
        {"id": "openai/gpt-oss-120b", "label": "GPT-OSS 120B"},
        {"id": "openai/gpt-oss-20b", "label": "GPT-OSS 20B"},
        {"id": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B Versatile"},
        {"id": "llama-3.1-8b-instant", "label": "Llama 3.1 8B Instant"},
    ],
}


def configured_providers() -> list[str]:
    settings = get_settings()
    keys = {"google": settings.google_api_key, "openai": settings.openai_api_key, "groq": settings.groq_api_key}
    return [provider for provider, api_key in keys.items() if api_key]


def is_supported_model(provider: str, model: str) -> bool:
    return any(option["id"] == model for option in MODEL_OPTIONS.get(provider, []))


def apply_ai_configuration(provider: str, model: str, temperature: float) -> None:
    """Update the cached Settings object (get_settings() is @lru_cache'd - this mutates the one
    shared instance) so get_llm() picks up the new provider/model/temperature on the very next
    call, no restart needed."""
    settings = get_settings()
    settings.llm_provider = provider
    settings.model_name = model
    settings.llm_temperature = temperature


async def load_saved_ai_configuration() -> None:
    """Restore the admin-selected model at process startup (src/main.py lifespan), same as
    usage_service's SystemConfig-backed daily_token_budget override. Silently keeps the .env
    defaults if nothing was ever saved, or if the saved value fails to validate - startup must
    never fail because of a bad persisted setting."""
    try:
        async with db_session.async_session_maker() as db:
            config = await db.get(SystemConfig, _SYSTEM_CONFIG_ID)
        if config is None or config.llm_provider is None or config.model_name is None:
            return
        provider, model = config.llm_provider, config.model_name
        temperature = config.llm_temperature if config.llm_temperature is not None else get_settings().llm_temperature
        if provider in MODEL_OPTIONS and is_supported_model(provider, model):
            apply_ai_configuration(provider, model, float(temperature))
        else:
            logger.warning("Ignored unsupported saved AI configuration: %s / %s", provider, model)
    except Exception:  # noqa: BLE001 - startup should retain environment defaults if persistence fails
        logger.exception("Could not load saved AI configuration; using environment defaults")
