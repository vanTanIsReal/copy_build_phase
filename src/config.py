from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"

    # LLM
    llm_provider: Literal["google", "groq", "openai"] = "google"
    google_api_key: str = ""
    groq_api_key: str = ""
    openai_api_key: str = ""
    model_name: str = "gemini-2.5-flash"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    daily_token_budget: int = Field(default=200_000, ge=0)

    # Database — PostgreSQL only, no SQLite fallback. Required: no default, so a missing/misconfigured
    # DATABASE_URL fails fast at startup instead of silently falling back to a file-based DB.
    database_url: str

    # Auth
    secret_key: str = "dev-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    initial_admin_email: str = ""
    # Web application OAuth Client ID used for both identity login and per-user Calendar consent.
    google_oauth_client_id: str = ""

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"

    # Google Calendar
    google_credentials_path: str = "./secrets/credentials.json"
    # OAuth client configuration only. User Calendar tokens are stored per-user in PostgreSQL.
    google_token_path: str = "./secrets/token.json"  # legacy setting; no longer read by the app
    google_calendar_id: str = "primary"
    google_calendar_client_id: str = ""
    google_calendar_client_secret: str = ""
    google_calendar_redirect_uri: str = "http://localhost:8000/api/v1/calendar/oauth/callback"
    credential_encryption_key: str = ""
    frontend_origin: str = "http://localhost:5173"
    calendar_timezone: str = "Asia/Ho_Chi_Minh"

    # Reminders / scheduler
    scheduler_timezone: str = "Asia/Ho_Chi_Minh"

    # Calendar polling (no public HTTPS URL yet for Google's real push/webhook channels, so
    # changes made directly in Google Calendar are picked up by polling with a syncToken instead)
    calendar_poll_interval_seconds: int = Field(default=20, ge=5)

    # Request rate limits. Kept in-memory for the current single-instance deployment.
    rate_limit_enabled: bool = True
    rate_limit_auth: str = "10/minute"
    rate_limit_register: str = "5/minute"
    rate_limit_chat: str = "15/minute"
    rate_limit_crud: str = "60/minute"


@lru_cache
def get_settings() -> Settings:
    return Settings()
