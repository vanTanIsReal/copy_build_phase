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

    # LLM (OpenAI)
    llm_provider: Literal["openai"] = "openai"
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    daily_token_budget: int = Field(default=200_000, ge=0)

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Auth
    secret_key: str = "dev-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    initial_admin_email: str = ""
    password_reset_expire_minutes: int = 30
    frontend_url: str = "http://localhost:5173"

    # Email / password reset
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"

    # Google Calendar
    google_credentials_path: str = "./secrets/credentials.json"
    google_token_path: str = "./secrets/token.json"
    google_calendar_id: str = "primary"
    calendar_timezone: str = "Asia/Ho_Chi_Minh"

    # Reminders / scheduler
    scheduler_timezone: str = "Asia/Ho_Chi_Minh"

    # Calendar polling (no public HTTPS URL yet for Google's real push/webhook channels, so
    # changes made directly in Google Calendar are picked up by polling with a syncToken instead)
    calendar_poll_interval_seconds: int = Field(default=20, ge=5)


@lru_cache
def get_settings() -> Settings:
    return Settings()
