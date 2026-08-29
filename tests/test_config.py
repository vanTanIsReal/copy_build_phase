import pytest
from pydantic import ValidationError

from src.config import Settings


def _production_settings(**overrides):
    values = {
        "app_env": "production",
        "secret_key": "x" * 32,
        "database_url": "postgresql://orbit:secret@db/orbit",
        "cors_origins": "https://app.example.com",
        "cors_origin_regex": "",
        "llm_provider": "google",
        "google_api_key": "test-api-key",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_valid_production_settings_are_accepted():
    settings = _production_settings()
    assert settings.app_env == "production"


def test_openrouter_production_settings_require_their_api_key():
    with pytest.raises(ValidationError):
        _production_settings(
            llm_provider="openrouter",
            google_api_key="",
            openrouter_api_key="",
        )

    settings = _production_settings(
        llm_provider="openrouter",
        google_api_key="",
        openrouter_api_key="test-openrouter-key",
        model_name="openai/gpt-4.1-mini",
    )
    assert settings.llm_provider == "openrouter"


@pytest.mark.parametrize(
    "override",
    [
        {"secret_key": "too-short"},
        {"database_url": "sqlite:///./data/app.db"},
        {"cors_origins": "*"},
        {"google_api_key": ""},
    ],
)
def test_unsafe_production_settings_are_rejected(override):
    with pytest.raises(ValidationError):
        _production_settings(**override)
