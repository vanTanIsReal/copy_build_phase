from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint
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


class Workspace(Base):
    """An organization-level container for the (currently foundation-only, not user-facing)
    multi-agent workspace feature - see docs/MULTI_AGENT_PROGRESS.md. Ported narrowly from the
    G19-T132-Lương-Trí-Tuệ branch's Agent Workspace foundation to unblock that work; this is NOT a
    reintroduction of the general multi-tenant "workspace" concept the team deliberately removed
    from the product on 2026-08-13 (commit 13e41c3, "remove workspace authorization model") - no
    other part of the app (chat, tasks, calendar, admin) reads or writes this table."""

    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint("type IN ('personal', 'organization')", name="ck_workspace_type"),
        CheckConstraint("status IN ('active', 'suspended', 'deleting')", name="ck_workspace_status"),
    )

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    type: Mapped[str]
    name: Mapped[str]
    status: Mapped[str] = mapped_column(default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_membership_user"),
        CheckConstraint("role IN ('owner', 'admin', 'member', 'guest')", name="ck_workspace_membership_role"),
        CheckConstraint(
            "status IN ('active', 'invited', 'suspended', 'revoked')",
            name="ck_workspace_membership_status",
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str]
    status: Mapped[str] = mapped_column(default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    type: Mapped[str]  # "direct" | "group"
    name: Mapped[str | None] = mapped_column(default=None)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    # workspace_id/ai_policy_version/ai_enabled below are used ONLY by the agent-workspace
    # foundation's scope_resolver (which group conversations feed a Delivery/Quality brief) - they
    # are NOT the app's real AI-consent mechanism and nothing else reads them. The actual, shipped
    # per-user AI consent for chat is the AIPermission table (conversation_id, user_id, granted)
    # below; ai_enabled here defaults False and stays that way for every real conversation unless
    # something explicitly links it via agent_workspace_service.link_agent_workspace_conversation.
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), default=None, index=True)
    ai_policy_version: Mapped[str] = mapped_column(default="v0")
    ai_enabled: Mapped[bool] = mapped_column(default=False)
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


class AgentWorkspace(Base):
    """A business-scoped agent area (Product Delivery or Quality Assurance) inside one
    organization Workspace - part of the not-yet-wired multi-agent foundation, see
    docs/MULTI_AGENT_PROGRESS.md. agent_profile mirrors src.agents.contracts.AgentProfile."""

    __tablename__ = "agent_workspaces"
    __table_args__ = (
        UniqueConstraint("organization_workspace_id", "key", name="uq_agent_workspace_organization_key"),
        CheckConstraint(
            "agent_profile IN ('product_delivery', 'quality_assurance')",
            name="ck_agent_workspace_profile",
        ),
        CheckConstraint("status IN ('active', 'suspended', 'archived')", name="ck_agent_workspace_status"),
        Index("ix_agent_workspaces_organization_status", "organization_workspace_id", "status"),
    )

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    organization_workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    key: Mapped[str]
    name: Mapped[str]
    agent_profile: Mapped[str]
    status: Mapped[str] = mapped_column(default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AgentWorkspaceMembership(Base):
    __tablename__ = "agent_workspace_memberships"
    __table_args__ = (
        UniqueConstraint("agent_workspace_id", "user_id", name="uq_agent_workspace_membership_user"),
        CheckConstraint(
            "business_role IN ('member', 'lead', 'executive_viewer')",
            name="ck_agent_workspace_membership_role",
        ),
        CheckConstraint(
            "status IN ('active', 'invited', 'suspended', 'revoked')",
            name="ck_agent_workspace_membership_status",
        ),
        Index("ix_agent_workspace_memberships_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    agent_workspace_id: Mapped[str] = mapped_column(ForeignKey("agent_workspaces.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    business_role: Mapped[str]
    status: Mapped[str] = mapped_column(default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AgentWorkspaceConversation(Base):
    __tablename__ = "agent_workspace_conversations"
    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_agent_workspace_conversation"),
        CheckConstraint(
            "classification IN ('delivery', 'quality')",
            name="ck_agent_workspace_conversation_classification",
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    agent_workspace_id: Mapped[str] = mapped_column(ForeignKey("agent_workspaces.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    classification: Mapped[str]
    linked_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    # "suggested" | "pending" | "in_progress" | "blocked" | "completed" | "dismissed"
    # "blocked" added for the Product Delivery Agent (MULTI_AGENT_IMPLEMENTATION_PLAN.md #6.1) - no
    # CHECK constraint on this column, so this is additive and doesn't require a migration of its own.
    source: Mapped[str] = mapped_column(default="manual")  # "manual" | "proactive"
    # id of the Message that proposed this commitment (proactive_service) - anchors dedup (an
    # overlapping re-scan of the same window doesn't duplicate) and retraction (a later "huỷ nhé"/
    # rescheduling message can find and dismiss every Task it spawned). NULL for source="manual".
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), default=None, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # --- Agent Workspace fields (MULTI_AGENT_IMPLEMENTATION_PLAN.md #7.2) ---
    # NULL for every personal Task (proactive/manual) - this app's existing, shipped behaviour is
    # completely unaffected. Set only when a work item belongs to a Product Delivery or Quality
    # Assurance Agent Workspace, per Product/Quality Agent tools (src/agents/tools/delivery_tool.py /
    # quality_tool.py). Deliberately reuses Task instead of a parallel work-item table - the plan
    # explicitly says QA metadata should not become "a separate test-management system".
    agent_workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_workspaces.id"), default=None, index=True
    )
    confidence: Mapped[float | None] = mapped_column(default=None)
    needs_clarification: Mapped[bool] = mapped_column(default=False)
    # Quality Assurance work-item metadata (MULTI_AGENT_IMPLEMENTATION_PLAN.md #6.2) - only ever set
    # when agent_workspace_id points at a quality_assurance workspace.
    work_item_type: Mapped[str | None] = mapped_column(default=None)  # "bug" | "test_case" | "release_check"
    severity: Mapped[str | None] = mapped_column(default=None)  # "low" | "medium" | "high" | "critical"
    quality_status: Mapped[str | None] = mapped_column(default=None)
    # "open" | "testing" | "passed" | "failed" | "blocked"
    # Free-text release/milestone tag (MULTI_AGENT_IMPLEMENTATION_PLAN.md Ngày 4 "cross-workspace
    # scenario") - a Delivery task and a Quality work item that share the same release_target are
    # the cross-workspace dependency executive_tool.get_cross_workspace_dependencies resolves.
    # Deliberately a plain string, not a foreign key to a Milestone table - there is no Milestone
    # model (see delivery_tool.py's own data-gap note); this is the same "no parallel tracking
    # system" reuse decision already made for QA metadata above, applied to release tagging too.
    release_target: Mapped[str | None] = mapped_column(default=None, index=True)

    owner: Mapped["User"] = relationship()
    conversation: Mapped["Conversation | None"] = relationship()
    agent_workspace: Mapped["AgentWorkspace | None"] = relationship()


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


class WorkspaceBriefRecord(Base):
    """Persisted copy of a published src.agents.contracts.WorkspaceBrief (named *Record* to avoid
    a same-name clash with that Pydantic contract). One row per generated Delivery/Quality brief -
    lets the Executive Agent (and the UI) list/replay past briefs instead of only ever seeing the
    single most-recent one held in memory. brief_json stores the full validated contract payload
    (already schema-versioned/source-checked by WorkspaceBrief itself); the flat columns below exist
    only so common queries (latest non-stale brief per workspace, per type) don't need to unpack
    JSON."""

    __tablename__ = "workspace_briefs"
    __table_args__ = (
        CheckConstraint("brief_type IN ('delivery', 'quality')", name="ck_workspace_brief_type"),
        Index("ix_workspace_briefs_workspace_type_generated", "agent_workspace_id", "brief_type", "generated_at"),
    )

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    organization_workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    agent_workspace_id: Mapped[str] = mapped_column(ForeignKey("agent_workspaces.id"), index=True)
    brief_type: Mapped[str]
    trace_id: Mapped[str] = mapped_column(index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    headline: Mapped[str]
    brief_json: Mapped[dict] = mapped_column(JSON)


class AgentRun(Base):
    """One row per agent invocation - the trace/audit record MULTI_AGENT_IMPLEMENTATION_PLAN.md #7.1
    and #13 (Versioning và eval) require: agent_profile, prompt_version, model, policy_decision,
    latency, token usage and outcome for every run, with no raw message/PII content (G6). Deliberately
    separate from AuditLog (admin-triggered actions only, no workspace/profile/latency/token concept)
    and UsageLog (token totals only, no per-run trace/policy outcome) - neither fits this shape."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "policy_decision IN ('ALLOW', 'DENY', 'MASK', 'REQUIRE_APPROVAL')",
            name="ck_agent_run_policy_decision",
        ),
        CheckConstraint("status IN ('success', 'partial', 'error', 'denied')", name="ck_agent_run_status"),
        Index("ix_agent_runs_actor_created", "actor_user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    trace_id: Mapped[str] = mapped_column(index=True)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), default=None)
    agent_workspace_id: Mapped[str | None] = mapped_column(ForeignKey("agent_workspaces.id"), default=None)
    agent_profile: Mapped[str]
    intent: Mapped[str]
    requested_scope: Mapped[str]
    policy_decision: Mapped[str]
    policy_reason: Mapped[str]
    prompt_version: Mapped[str]
    model: Mapped[str] = mapped_column(default="")
    status: Mapped[str]
    latency_ms: Mapped[int] = mapped_column(default=0)
    token_usage: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class AgentActionExecution(Base):
    """Idempotency ledger for the shared HITL executor (src/agents/hitl_executor.py). One row per
    ActionProposal.idempotency_key that has actually been executed - a resume/confirm replayed with
    the same key (double-click, retry after a dropped response) short-circuits to the stored result
    instead of re-running a non-idempotent side effect twice. Deliberately keyed on idempotency_key
    alone (not proposal_id) since that's the field ActionProposal itself defines as the replay key."""

    __tablename__ = "agent_action_executions"

    idempotency_key: Mapped[str] = mapped_column(primary_key=True)
    proposal_id: Mapped[str] = mapped_column(index=True)
    trace_id: Mapped[str] = mapped_column(index=True)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str]
    status: Mapped[str]  # "success" | "error"
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
