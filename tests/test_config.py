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


def test_multi_agent_feature_flags_default_to_disabled(monkeypatch):
    for name in (
        "MULTI_AGENT_ENABLED",
        "PRODUCT_DELIVERY_AGENT_ENABLED",
        "QUALITY_ASSURANCE_AGENT_ENABLED",
        "EXECUTIVE_AGENT_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)

    assert settings.multi_agent_enabled is False
    assert settings.product_delivery_agent_enabled is False
    assert settings.quality_assurance_agent_enabled is False
    assert settings.executive_agent_enabled is False


def test_multi_agent_feature_flags_can_be_enabled_explicitly():
    settings = Settings(
        _env_file=None,
        multi_agent_enabled=True,
        product_delivery_agent_enabled=True,
        quality_assurance_agent_enabled=True,
        executive_agent_enabled=True,
    )

    assert settings.multi_agent_enabled is True
    assert settings.product_delivery_agent_enabled is True
    assert settings.quality_assurance_agent_enabled is True
    assert settings.executive_agent_enabled is True


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
