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

    # Agent context engineering (context_node.py). Fractions are budgets for optional/retrieved
    # layers, not a claim that every model or turn must consume exactly these percentages - system/
    # policy content and the model's own output are unaffected by this and always take priority;
    # lower-value retrieval (episodic > long-term > conversation excerpt) is trimmed first.
    agent_context_window_tokens: int = Field(default=32_768, ge=8_192)
    memory_short_term_fraction: float = Field(default=0.10, ge=0.02, le=0.50)  # recent chat turns
    memory_long_term_fraction: float = Field(default=0.04, ge=0.01, le=0.20)  # saved Memory notes
    memory_episodic_fraction: float = Field(default=0.03, ge=0.0, le=0.20)  # MemoryEpisode summaries

    # memory_maintenance_service.py's periodic consolidation heartbeat (registered in
    # src/main.py's lifespan) - how often it runs, and how it decides a thread is due for
    # compaction: at least this many uncompacted messages, keeping the most recent N verbatim.
    memory_heartbeat_interval_seconds: int = Field(default=900, ge=60)
    memory_compaction_message_threshold: int = Field(default=24, ge=8)
    memory_recent_messages_to_keep: int = Field(default=12, ge=4)

    # Database — PostgreSQL only, no SQLite fallback. Required: no default, so a missing/misconfigured
    # DATABASE_URL fails fast at startup instead of silently falling back to a file-based DB.
    database_url: str

    # Auth
    secret_key: str = "dev-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    initial_admin_email: str = ""
    # Gate for POST /auth/admin/register (the separate Admin frontend's one-time "create the first
    # admin" flow) - empty means the endpoint is disabled (503), so this only needs setting once,
    # at first deploy. Not a replacement for initial_admin_email, which still works the same way;
    # this exists for deployments where nobody wants to pre-decide the admin's email address.
    admin_bootstrap_key: str = ""
    # "Sign in with Google" - Web application OAuth Client ID (audience for ID-token verification
    # only, never an authorization-code exchange, so no client secret needed). Distinct from the
    # Calendar OAuth client below - two separate Google Cloud OAuth Clients on purpose, so a user
    # can log in without ever being asked for Calendar access, and vice versa.
    google_oauth_client_id: str = ""

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"

    # Google Calendar - per-user OAuth (each user connects their own Calendar from the Calendar
    # page via a real redirect + backend callback; there is no shared/fallback calendar). This IS
    # an authorization-code exchange (to get a refresh_token we can use outside the browser), so
    # unlike google_oauth_client_id above, this Client needs a secret. Create a separate "Web
    # application" OAuth Client for this in Google Cloud Console - see .env.example. calendarId is
    # always "primary" now (credential is already the user's own), so no google_calendar_id setting.
    google_calendar_client_id: str = ""
    google_calendar_client_secret: str = ""
    google_calendar_redirect_uri: str = "http://localhost:8000/api/v1/calendar/oauth/callback"
    calendar_timezone: str = "Asia/Ho_Chi_Minh"

    # Fernet key encrypting refresh_token/access_token at rest (src/auth/crypto.py) - a Calendar
    # refresh token is a long-lived secret (unlike a password hash, it's directly usable to read/
    # write someone's calendar until they revoke it), so unlike most other secrets in this app it
    # gets encrypted, not just kept out of git. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Never rotate after users have connected - doing so turns every stored refresh_token into
    # garbage and forces everyone to reconnect.
    credential_encryption_key: str = ""

    # Frontend origin, used as postMessage's targetOrigin on the OAuth callback page so only our
    # own frontend (not an arbitrary embedded/opener page) can receive the "connected" signal.
    frontend_origin: str = "http://localhost:5173"

    # Reminders / scheduler
    scheduler_timezone: str = "Asia/Ho_Chi_Minh"

    # Calendar polling (no public HTTPS URL yet for Google's real push/webhook channels, so
    # changes made directly in Google Calendar are picked up by polling with a syncToken instead)
    calendar_poll_interval_seconds: int = Field(default=20, ge=5)

    # Rate limiting (slowapi, in-memory - single uvicorn worker/single Render instance, no Redis).
    # Complements daily_token_budget above, doesn't replace it: budget caps $ cost across the whole
    # app per day, this caps request burst/abuse per user or IP per minute. See src/api/rate_limit.py.
    # Off by default in tests (tests/conftest.py sets RATE_LIMIT_ENABLED=false before app import) so
    # fixtures that register several users per session don't trip the auth-endpoint limit themselves.
    rate_limit_enabled: bool = True
    rate_limit_auth: str = "10/minute"  # /auth/login, /auth/google - per IP
    rate_limit_register: str = "5/minute"  # /auth/register - per IP, stricter than login
    rate_limit_chat: str = "15/minute"  # POST /chat (fresh turns only, not /chat/resume) - per user
    rate_limit_crud: str = "60/minute"  # everything else authenticated - per user, generous safety net


@lru_cache
def get_settings() -> Settings:
    return Settings()
