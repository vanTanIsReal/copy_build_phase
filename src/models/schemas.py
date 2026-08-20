from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.agents.contracts import RequestedScope


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"] = "user"
    sender: str | None = None
    content: str
    timestamp: str | None = Field(default=None, description="ISO 8601 datetime, optional")


class MessageScope(BaseModel):
    """How much of a real conversation's history to hand the agent, resolved server-side against
    the DB (see chat_service.get_scoped_messages) - the client only says WHAT it wants, never
    supplies the actual messages for this path, unlike the older `ChatRequest.messages` field."""

    kind: Literal["latest_n", "unread", "today", "yesterday", "this_week", "rolling_hours", "custom_range"]
    count: int | None = Field(default=None, ge=1, le=500, description="latest_n: how many, newest first")
    hours: int | None = Field(default=None, ge=1, le=24, description="rolling_hours: size of the trailing window")
    since: str | None = Field(default=None, description="custom_range: ISO datetime, naive = calendar_timezone")
    until: str | None = Field(default=None, description="custom_range: ISO datetime, naive = calendar_timezone")


class SpecialistActionRequest(BaseModel):
    """Which side-effecting specialist tool to propose, and its draft payload. `kind` picks the
    tool deterministically (never inferred by an LLM - MULTI_AGENT_IMPLEMENTATION_PLAN.md G3 "LLM
    chỉ phân loại intent và tổng hợp trong scope; router/policy không giao cho LLM quyết định")."""

    kind: Literal["propose_reminder", "propose_meeting"]
    title: str = Field(min_length=1, max_length=200)
    due_at: str | None = Field(default=None, description="ISO datetime - required for kind=propose_reminder")
    message: str = Field(default="", max_length=2000)
    starts_at: str | None = Field(default=None, description="ISO datetime - required for kind=propose_meeting")
    attendee_ids: list[str] = Field(default_factory=list, description="Internal user ids - kind=propose_meeting only")

    @model_validator(mode="after")
    def required_field_matches_kind(self) -> "SpecialistActionRequest":
        if self.kind == "propose_reminder" and not self.due_at:
            raise ValueError("due_at is required when kind=propose_reminder")
        if self.kind == "propose_meeting" and not self.starts_at:
            raise ValueError("starts_at is required when kind=propose_meeting")
        return self


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")
    thread_id: str | None = Field(default=None, description="Conversation thread id; generated if omitted")
    quick_action: Literal["summarize", "extract_tasks"] | None = Field(
        default=None,
        description=(
            "Set by AIPanel's deterministic Quick Actions (Summarize/Extract tasks) so the server "
            "skips the planner's LLM call and the whole LangGraph run - the planner always routes "
            "these two to the same tool anyway. `message` is still required (kept for display/"
            "backwards compat) but is ignored when this is set."
        ),
    )
    messages: list[ChatMessage] | None = Field(
        default=None,
        description="Raw message history to summarize (read by summarize_conversation via state)",
    )
    conversation_id: str | None = Field(
        default=None,
        description=(
            "If `messages` come from a real 1-1/group chat conversation, its id - the server "
            "verifies the caller is actually a participant before letting the agent see them, "
            "rather than trusting whatever `messages` the client attached."
        ),
    )
    scope: MessageScope | None = Field(
        default=None,
        description=(
            "When set together with conversation_id, the server re-derives the message history "
            "from the DB according to this scope instead of trusting the client-supplied "
            "`messages` array - takes priority over `messages` when both are present."
        ),
    )
    requested_scope: RequestedScope = Field(
        default=RequestedScope.PERSONAL,
        description=(
            "PERSONAL (default) keeps the existing LangGraph Personal-agent flow untouched. "
            "WORKSPACE/AGGREGATE instead route through the deterministic Router to the "
            "product_delivery/quality_assurance/executive agent profiles (read-only brief only "
            "today - see src.api.routes._run_specialist_chat). A REQUEST, never a grant: real "
            "entitlement is still resolved server-side against the caller's own membership."
        ),
    )
    target_agent_workspace_id: str | None = Field(
        default=None,
        description="Required when requested_scope=WORKSPACE; must be omitted otherwise.",
    )
    specialist_action: SpecialistActionRequest | None = Field(
        default=None,
        description=(
            "Only meaningful together with requested_scope WORKSPACE/AGGREGATE. Omitted (default) "
            "-> read-only brief, same as before. Set -> route to the matching propose_*_reminder/"
            "propose_*_meeting tool instead, which returns status=interrupted for the caller to "
            "confirm/reject via POST /chat/resume, exactly like the Personal agent's existing "
            "calendar/reminder HITL flow (src.api.routes._run_specialist_chat)."
        ),
    )


class InterruptPayload(BaseModel):
    type: Literal[
        "calendar_event",
        "calendar_event_update",
        "calendar_event_delete",
        "reminder",
        "delivery_reminder",
        "delivery_meeting",
        "quality_reminder",
        "quality_meeting",
        "executive_meeting",
    ]
    draft: dict


class ChatResponse(BaseModel):
    response: str = Field(default="", description="Phản hồi từ agent")
    analysis: str = Field(default="", description="Phân tích nội bộ")
    thread_id: str
    status: Literal["completed", "interrupted", "error"] = "completed"
    interrupt: InterruptPayload | None = None


class ResumeRequest(BaseModel):
    thread_id: str
    approved: bool
    edits: dict | None = None
