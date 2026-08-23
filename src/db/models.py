from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


def _uuid() -> str:
    return uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    password_hash: Mapped[str]
    display_name: Mapped[str]
    role: Mapped[str] = mapped_column(default="user")  # "user" | "admin"
    is_active: Mapped[bool] = mapped_column(default=True)
    job_title: Mapped[str] = mapped_column(default="")
    timezone: Mapped[str] = mapped_column(default="Asia/Ho_Chi_Minh")
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class GoogleIdentity(Base):
    """Links a User to the Google account they signed in with (Sign in with Google) - kept as its
    own table rather than columns on User so this feature needs no ALTER on the existing users
    table (this repo has no Alembic; Base.metadata.create_all() only creates missing tables).

    Unrelated to the app's other Google integration (Calendar sync, src/services/calendar_service.py) -
    that's one shared service-account token for the whole app, not a per-user login identity."""

    __tablename__ = "google_identities"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    google_sub: Mapped[str] = mapped_column(unique=True, index=True)  # Google's stable subject id
    email: Mapped[str] = mapped_column(default="")  # snapshot at link time, for audit only
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship()


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    type: Mapped[str]  # "direct" | "group"
    name: Mapped[str | None] = mapped_column(default=None)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    participants: Mapped[list["ConversationParticipant"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # "Delete conversation" (for me) - hides it from THIS participant's own conversation list only,
    # never touches the conversation/messages themselves (those still exist for every other
    # participant). Cleared back to NULL the moment any new message lands in the conversation - see
    # chat_service.create_message - so a re-activated thread reappears automatically instead of
    # staying hidden forever. Distinct from actually leaving a group (row gets deleted, not hidden).
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    conversation: Mapped["Conversation"] = relationship(back_populates="participants")
    user: Mapped["User"] = relationship()


class AIPermission(Base):
    """Per (conversation, user) consent for the AI agent to read that conversation's messages.

    Keyed per-user rather than per-conversation: each participant grants/revokes independently for
    themselves, no consensus from other members required."""

    __tablename__ = "ai_permissions"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    granted: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    sender: Mapped["User"] = relationship()


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id"), default=None)
    title: Mapped[str]
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    priority: Mapped[str] = mapped_column(default="Medium")  # "High" | "Medium" | "Low"
    status: Mapped[str] = mapped_column(default="suggested")
    # "suggested" | "pending" | "in_progress" | "completed" | "dismissed"
    source: Mapped[str] = mapped_column(default="manual")  # "manual" | "proactive"
    # id of the Message that proposed this commitment (proactive_service) - anchors dedup (an
    # overlapping re-scan of the same window doesn't duplicate) and retraction (a later "huỷ nhé"/
    # rescheduling message can find and dismiss every Task it spawned). NULL for source="manual".
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), default=None, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    owner: Mapped["User"] = relationship()
    conversation: Mapped["Conversation | None"] = relationship()


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    provider: Mapped[str]
    model: Mapped[str]
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    total_tokens: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class SystemConfig(Base):
    """Single-row table (fixed id) for runtime-editable settings that would otherwise only live in
    .env - daily_token_budget, and (as of the AI Management admin page) which LLM provider/model/
    temperature every new AI call uses. NULL on any of these means "no override yet" - callers
    fall back to the matching Settings.* field (the .env default), so a deployment that never
    touches this stays on exactly the old behavior."""

    __tablename__ = "system_config"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: "default")
    daily_token_budget: Mapped[int | None] = mapped_column(default=None)
    # AI Management overrides - see ai_config_service.py. Applied to the cached Settings object at
    # startup (load_saved_ai_configuration) and immediately on every admin update
    # (apply_ai_configuration), so a running process never needs a restart to pick these up.
    llm_provider: Mapped[str | None] = mapped_column(default=None)
    model_name: Mapped[str | None] = mapped_column(default=None)
    llm_temperature: Mapped[float | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), default=None)


class AuditLog(Base):
    """Append-only record of notable admin-triggered actions (role/status/budget/model changes,
    moderation deletes) for the Admin "Audit Log" page - who did what, to what, when. Deliberately
    does NOT record message/memory content or anything from _SENSITIVE_METADATA_KEYS (see
    audit_service.record_audit_event) - it's an activity trail, not a content log. No workspace_id:
    this app has no multi-tenant workspace concept, unlike the branch this feature was ported from."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True)
    actor_type: Mapped[str]  # "admin" | "system" - who/what performed the action
    action: Mapped[str]
    target_type: Mapped[str]
    target_id: Mapped[str | None] = mapped_column(default=None)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(default="Preference")  # "Work" | "Preference" | "People" | ...
    title: Mapped[str]
    detail: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    owner: Mapped["User"] = relationship()


class AssistantThread(Base):
    """One row per Personal AI Assistant chat session (/assistant page) - lets a user browse past
    sessions ("Gần đây" sidebar). Distinct from Conversation (1-1/group human chat) and from the
    LangGraph checkpointer's own Postgres tables: those hold the full message state per thread_id
    but have no owner_id column and no title/preview concept, so they can't answer "which threads
    belong to this user" on their own - this table is the missing owner_id -> thread_id index, kept
    in sync from src/api/routes.py (chat()/resume_chat()) whenever a turn completes. Only chat()
    calls with conversation_id=None create a row here - AIPanel's embedded quick actions/Ask Orbit
    (always conversation_id-scoped) are a different, unrelated flow and must not show up in this
    list."""

    __tablename__ = "assistant_threads"

    thread_id: Mapped[str] = mapped_column(primary_key=True)  # same thread_id used by the checkpointer
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str]  # fixed at creation from the first message - like a conversation name, never edited after
    preview: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    owner: Mapped["User"] = relationship()


class GoogleCalendarCredential(Base):
    """Per-user Google Calendar OAuth credential (authorization-code flow, access_type=offline).
    A row existing = this user has connected their own Google Calendar; no row = Calendar features
    are unavailable to them - there is no shared/fallback calendar under the per-user model.

    Different from GoogleIdentity: that table only records "this user signed in with this Google
    account" (ID token, can't call any API with it). This table holds a real refresh token that
    can act on the user's Calendar on their behalf. A user can have a GoogleIdentity without this
    (logged in with Google, never connected Calendar) or this without a GoogleIdentity (logged in
    with a password, connected Calendar separately) - the two are unrelated.

    refresh_token_enc/access_token_enc are Fernet-encrypted (src/auth/crypto.py) - a Calendar
    refresh token is a long-lived secret; leaking it means indefinite read/write access to the
    user's calendar until they manually revoke it, unlike e.g. a password hash which is one-way.

    sync_token lives on this same row (not a separate table) since it's 1:1 with the credential -
    replaces the old single-row app-wide calendar_sync_state from when Calendar was one shared
    account for everyone."""

    __tablename__ = "google_calendar_credentials"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    google_email: Mapped[str] = mapped_column(default="")  # connected account, for display only
    refresh_token_enc: Mapped[str] = mapped_column(Text)
    access_token_enc: Mapped[str | None] = mapped_column(Text, default=None)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    scopes: Mapped[str] = mapped_column(default="")  # space-separated
    sync_token: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped["User"] = relationship()


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), default=None, index=True)
    title: Mapped[str]
    message: Mapped[str] = mapped_column(default="")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(default="scheduled")  # "scheduled" | "fired" | "cancelled"
    source: Mapped[str] = mapped_column(default="manual")  # "manual" | "agent" | "proactive"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    owner: Mapped["User | None"] = relationship()
