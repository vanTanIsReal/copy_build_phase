from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import graph as agent_graph
from src.agents import router as agent_router
from src.agents.context_builder import AgentRunRecorder, build_agent_context
from src.agents.contracts import (
    ActionProposal,
    AgentContext,
    AgentIntent,
    AgentInvocationRequest,
    AgentProfile,
    PolicyDecision,
    PolicyReason,
    RequestedScope,
    ToolResult,
    ToolResultStatus,
)
from src.agents.hitl_executor import ActionProposalRejectedError, execute_action_proposal
from src.agents.tools import delivery_tool, executive_tool
from src.auth.dependencies import get_current_user
from src.config import get_settings
from src.db.models import AgentWorkspace, Conversation, User, Workspace, WorkspaceMembership
from src.db.session import get_db
from src.models.schemas import (
    AuthorizedContextMetadata,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    InterruptPayload,
    ResumeRequest,
    SpecialistActionRequest,
)
from src.models.usage_schemas import UsageStatusOut
from src.services import (
    assistant_thread_service,
    calendar_service,
    chat_service,
    consent_service,
    reminder_service,
    thread_memory_service,
    usage_service,
)
from src.services.authorization_service import require_conversation_access
from src.services.google_credentials import CalendarNotConnectedError
from src.services.workspace_service import resolve_workspace_for_user

router = APIRouter()

# Ngày 6-7 hookup (MULTI_AGENT_IMPLEMENTATION_PLAN.md): which specialist tool builds the read-only
# brief for a resolved route.profile. quality_assurance is intentionally absent - that profile's
# real vertical slice (src.services.quality_workspace_service) is still under active development
# on its own repository-based design (see that module's docstring); dispatch below degrades to a
# clear "not available yet" response for it instead of guessing at an incompatible API.
_SPECIALIST_BRIEF_TOOL = {
    AgentProfile.PRODUCT_DELIVERY: delivery_tool.build_delivery_brief,
    AgentProfile.EXECUTIVE: executive_tool.build_executive_brief,
}

# (profile, SpecialistActionRequest.kind) -> the intent route_agent_request/registry.py must
# resolve for that (profile, action) pair to be allowed - see registry.py's allowed_intents.
_SPECIALIST_ACTION_INTENT = {
    (AgentProfile.PRODUCT_DELIVERY, "propose_reminder"): AgentIntent.DELIVERY_PROPOSE_REMINDER,
    (AgentProfile.PRODUCT_DELIVERY, "propose_meeting"): AgentIntent.DELIVERY_PROPOSE_MEETING,
    (AgentProfile.EXECUTIVE, "propose_meeting"): AgentIntent.EXECUTIVE_PROPOSE_MEETING,
}

# proposal.action (set by delivery_tool.py/executive_tool.py's propose_* functions) -> the
# InterruptPayload.type the frontend receives - stable, short names distinct from the Personal
# agent's own calendar_event/reminder types so a future UI can tell them apart.
_INTERRUPT_TYPE_BY_PROPOSAL_ACTION = {
    "preview_delivery_reminder": "delivery_reminder",
    "preview_delivery_meeting": "delivery_meeting",
    "preview_executive_meeting": "executive_meeting",
}

_DEFAULT_MEETING_DURATION = timedelta(minutes=30)

_PROFILE_ENABLED_FLAG = {
    AgentProfile.PRODUCT_DELIVERY: "product_delivery_agent_enabled",
    AgentProfile.QUALITY_ASSURANCE: "quality_assurance_agent_enabled",
    AgentProfile.EXECUTIVE: "executive_agent_enabled",
}

_SPECIALIST_DENY_TEXT = {
    PolicyReason.NOT_MEMBER: "Bạn chưa là thành viên của agent workspace này.",
    PolicyReason.WRONG_WORKSPACE: "Không tìm thấy agent workspace này trong tổ chức của bạn.",
    PolicyReason.PROFILE_MISMATCH: "Agent workspace này không khớp với loại yêu cầu.",
    PolicyReason.INVALID_SCOPE: "Yêu cầu không hợp lệ cho phạm vi này.",
    PolicyReason.RESOURCE_NOT_ALLOWED: "Bạn không có quyền truy cập dữ liệu này.",
    PolicyReason.CONSENT_CHANGED: "Quyền chia sẻ dữ liệu đã thay đổi, vui lòng thử lại.",
    PolicyReason.FEATURE_DISABLED: "Tính năng này hiện chưa được bật.",
    PolicyReason.WORKSPACE_CONSENT_REVOKED: (
        "Bạn đã tắt quyền AI cho agent workspace này - bật lại trong cài đặt workspace để tiếp tục."
    ),
}

# thread_id -> the ActionProposal a specialist propose_* tool drafted, awaiting confirm/reject via
# POST /chat/resume (src.agents.hitl_executor.execute_action_proposal does the actual binding/
# expiry/idempotency checks at confirm time - this dict is only "where do we find the proposal
# again", the LangGraph checkpointer's equivalent role for the Personal agent's own interrupt()).
# In-memory only - bounded by ActionProposal's own 15-minute expires_at, so losing this on a
# restart just means "ask the agent again", not silent data loss.
_pending_specialist_proposals: dict[str, ActionProposal] = {}


def _format_messages(messages: list[ChatMessage]) -> str:
    return "\n".join(f"{m.sender or m.role}: {m.content}" for m in messages)


async def _user_organization_workspace_ids(db: AsyncSession, user_id: str) -> tuple[str, ...]:
    """Real (if today mostly empty - see Workspace's own docstring in src/db/models.py) active
    organization memberships for this user. Never fabricated: a user with no row here simply gets
    denied below, same as any other real authorization failure."""
    rows = (
        await db.execute(
            select(WorkspaceMembership.workspace_id)
            .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
            .where(
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.status == "active",
                Workspace.type == "organization",
                Workspace.status == "active",
            )
        )
    ).scalars().all()
    return tuple(rows)


_BRIEF_INTENT_BY_PROFILE = {
    AgentProfile.PRODUCT_DELIVERY: AgentIntent.DELIVERY_BRIEF,
    AgentProfile.QUALITY_ASSURANCE: AgentIntent.QUALITY_BRIEF,
    AgentProfile.EXECUTIVE: AgentIntent.EXECUTIVE_BRIEF,
}


async def _guess_target_profile(
    db: AsyncSession, requested_scope: RequestedScope, target_agent_workspace_id: str | None
) -> AgentProfile:
    """Which profile intent to ask for BEFORE calling route_agent_request - intent alone doesn't
    determine profile (route_agent_request derives profile from the real AgentWorkspace.
    agent_profile column, never from the client), but route_agent_request also requires the intent
    it's given to already be valid for whatever profile it resolves, so the caller must guess
    right. A wrong guess here is still safe: when target_agent_workspace_id doesn't resolve to a
    real, same-org, active workspace, route_agent_request's own lookup denies WRONG_WORKSPACE
    before it ever reaches the intent check, regardless of this guess."""
    if requested_scope == RequestedScope.AGGREGATE:
        return AgentProfile.EXECUTIVE
    if target_agent_workspace_id:
        workspace = await db.get(AgentWorkspace, target_agent_workspace_id)
        if workspace is not None and workspace.agent_profile == AgentProfile.QUALITY_ASSURANCE.value:
            return AgentProfile.QUALITY_ASSURANCE
    return AgentProfile.PRODUCT_DELIVERY


def _format_workspace_brief_text(brief: dict) -> str:
    lines = [brief["headline"]]
    if brief.get("release_readiness"):
        lines.append(f"Release readiness: {brief['release_readiness']}")
    if brief.get("risks"):
        lines.append(f"Rủi ro ({len(brief['risks'])}):")
        lines.extend(f"- {risk.get('text', risk)}" for risk in brief["risks"][:5])
    if brief.get("dependencies"):
        lines.append(f"Liên quan release chung với workspace khác: {len(brief['dependencies'])} mục.")
    if brief.get("data_gaps"):
        lines.append("Thiếu dữ liệu: " + "; ".join(brief["data_gaps"]))
    return "\n".join(lines)


def _format_executive_brief_text(brief: dict) -> str:
    lines = [brief["headline"]]
    if brief.get("risks"):
        lines.append(f"Rủi ro ({len(brief['risks'])}):")
        lines.extend(f"- {risk.get('text', risk)}" for risk in brief["risks"][:5])
    if brief.get("cross_workspace_dependencies"):
        lines.append(f"Phụ thuộc chéo workspace: {len(brief['cross_workspace_dependencies'])} mục.")
    if brief.get("data_gaps"):
        lines.append("Thiếu dữ liệu: " + "; ".join(brief["data_gaps"]))
    return "\n".join(lines)


async def _run_specialist_chat(body: ChatRequest, current_user: User, db: AsyncSession, thread_id: str) -> ChatResponse:
    """Ngày 6-7 hookup (MULTI_AGENT_IMPLEMENTATION_PLAN.md) of the deterministic Router (G0-G2)
    into the real /chat endpoint - only for requested_scope WORKSPACE/AGGREGATE, entirely separate
    from the LangGraph Personal-agent path (untouched by this function).

    Two shapes: body.specialist_action is None -> read-only brief (build_delivery_brief/
    build_executive_brief). body.specialist_action set -> dispatch to the matching
    propose_*_reminder/propose_*_meeting tool instead, returning status="interrupted" for the
    caller to confirm/reject via POST /chat/resume - the real HITL loop
    (_pending_specialist_proposals + hitl_executor.execute_action_proposal), not just a preview
    nobody could ever confirm.

    Gated by MULTI_AGENT_ENABLED (checked here, before any DB work) and then by the resolved
    profile's own PRODUCT_DELIVERY_AGENT_ENABLED/QUALITY_ASSURANCE_AGENT_ENABLED/
    EXECUTIVE_AGENT_ENABLED flag once route_agent_request resolves it - MULTI_AGENT_IMPLEMENTATION_
    PLAN.md G6 "Có flag cho từng profile và MULTI_AGENT_ENABLED làm master kill switch". Both
    default False.
    """
    settings = get_settings()
    if not settings.multi_agent_enabled:
        return ChatResponse(
            response=_SPECIALIST_DENY_TEXT[PolicyReason.FEATURE_DISABLED], thread_id=thread_id, status="error"
        )

    if body.requested_scope == RequestedScope.WORKSPACE and body.target_agent_workspace_id:
        target_workspace = await db.get(AgentWorkspace, body.target_agent_workspace_id)
        organization_workspace_id = target_workspace.organization_workspace_id if target_workspace else None
    else:
        org_ids = await _user_organization_workspace_ids(db, current_user.id)
        if len(org_ids) == 1:
            organization_workspace_id = org_ids[0]
        elif not org_ids:
            organization_workspace_id = None
        else:
            return ChatResponse(
                response="Bạn thuộc nhiều tổ chức - vui lòng chọn một agent workspace cụ thể thay vì executive brief tổng hợp.",
                thread_id=thread_id,
                status="error",
            )

    if organization_workspace_id is None:
        return ChatResponse(
            response=_SPECIALIST_DENY_TEXT[PolicyReason.NOT_MEMBER],
            thread_id=thread_id,
            status="error",
        )

    profile_guess = await _guess_target_profile(db, body.requested_scope, body.target_agent_workspace_id)
    if body.specialist_action is None:
        intent = _BRIEF_INTENT_BY_PROFILE[profile_guess]
    else:
        intent = _SPECIALIST_ACTION_INTENT.get((profile_guess, body.specialist_action.kind))
        if intent is None:
            return ChatResponse(
                response="Agent workspace này không hỗ trợ hành động được yêu cầu.", thread_id=thread_id, status="error"
            )
    invocation = AgentInvocationRequest(
        message=body.message,
        conversation_id=body.conversation_id,
        requested_scope=body.requested_scope,
        target_agent_workspace_id=body.target_agent_workspace_id,
    )
    try:
        route = await agent_router.route_agent_request(
            db, organization_workspace_id=organization_workspace_id, invocation=invocation, intent=intent
        )
    except agent_router.AgentRouteDeniedError as exc:
        return ChatResponse(
            response=_SPECIALIST_DENY_TEXT.get(exc.reason, "Yêu cầu không được chấp nhận."),
            thread_id=thread_id,
            status="error",
        )

    if route.profile not in _SPECIALIST_BRIEF_TOOL:
        # quality_assurance - see _SPECIALIST_BRIEF_TOOL's own docstring.
        return ChatResponse(
            response="Quality Assurance Agent chưa sẵn sàng cho luồng chat này.", thread_id=thread_id, status="error"
        )

    if not getattr(settings, _PROFILE_ENABLED_FLAG[route.profile]):
        return ChatResponse(
            response=_SPECIALIST_DENY_TEXT[PolicyReason.FEATURE_DISABLED], thread_id=thread_id, status="error"
        )

    context = await build_agent_context(
        db,
        user=current_user,
        organization_workspace_id=organization_workspace_id,
        invocation=invocation,
        intent=route.intent,
        agent_profile=route.profile,
    )

    # AgentRunRecorder (G6 audit) always writes one agent_runs row on exit, ALLOW or DENY alike,
    # with a real measured latency_ms - see context_builder.AgentRunRecorder. token_usage is
    # honestly left at 0: this path calls zero LLMs (release_readiness/risks are computed by code,
    # not a model), so there is no token cost to record here yet.
    async with AgentRunRecorder(db, context):
        if context.authorization.decision != PolicyDecision.ALLOW:
            return ChatResponse(
                response=_SPECIALIST_DENY_TEXT.get(context.authorization.reason, "Yêu cầu bị từ chối."),
                thread_id=thread_id,
                status="error",
            )
        if body.specialist_action is None:
            tool = _SPECIALIST_BRIEF_TOOL[route.profile]
            result = await tool(db, context)
        else:
            result = await _propose_specialist_action(db, context, route.profile, body.specialist_action)

    if result.status == ToolResultStatus.ERROR:
        return ChatResponse(
            response=result.error_message or "Không lấy được dữ liệu.", thread_id=thread_id, status="error"
        )

    if body.specialist_action is not None:
        proposal = ActionProposal.model_validate(result.payload["proposal"])
        _pending_specialist_proposals[thread_id] = proposal
        interrupt_type = _INTERRUPT_TYPE_BY_PROPOSAL_ACTION[proposal.action]
        return ChatResponse(
            response="Vui lòng xác nhận hành động được đề xuất.",
            thread_id=thread_id,
            status="interrupted",
            interrupt=InterruptPayload(type=interrupt_type, draft=proposal.payload),
        )

    if route.profile == AgentProfile.EXECUTIVE:
        text = _format_executive_brief_text(result.payload["executive_brief"])
    else:
        text = _format_workspace_brief_text(result.payload["workspace_brief"])
    return ChatResponse(response=text, thread_id=thread_id, status="completed")


_REMINDER_TOOL_BY_PROFILE = {
    AgentProfile.PRODUCT_DELIVERY: delivery_tool.propose_delivery_reminder,
}
_MEETING_TOOL_BY_PROFILE = {
    AgentProfile.PRODUCT_DELIVERY: delivery_tool.propose_delivery_meeting,
    AgentProfile.EXECUTIVE: executive_tool.propose_executive_meeting,
}


async def _propose_specialist_action(
    db: AsyncSession, context: AgentContext, profile: AgentProfile, action: SpecialistActionRequest
) -> ToolResult:
    """Calls the one propose_* tool matching (profile, action.kind) - the tool itself only ever
    drafts an ActionProposal preview (G5), never runs the real side effect (that happens in
    resume_chat -> _resume_specialist_action, only after a human confirms). action.due_at/
    starts_at are guaranteed present for their respective kind by SpecialistActionRequest's own
    validator - _run_specialist_chat already resolved (profile, action.kind) into a valid intent
    before this is ever called, so profile is guaranteed to be a key in the matching dict below."""
    if action.kind == "propose_reminder":
        due_at = datetime.fromisoformat(action.due_at)
        return await _REMINDER_TOOL_BY_PROFILE[profile](db, context, title=action.title, due_at=due_at, message=action.message)
    starts_at = datetime.fromisoformat(action.starts_at)
    return await _MEETING_TOOL_BY_PROFILE[profile](
        db, context, title=action.title, starts_at=starts_at, attendee_ids=tuple(action.attendee_ids)
    )


def _build_specialist_action_fn(db: AsyncSession, proposal: ActionProposal, confirming_user_id: str):
    """The real side effect for a confirmed specialist ActionProposal - reuses the exact same
    already-shipped, already-tested services the Personal agent's own calendar/reminder tools call
    (reminder_service.schedule_reminder / calendar_service.create_event), never a parallel
    implementation. Always acts as the CONFIRMING user (their own Reminder, their own connected
    Google Calendar) - a specialist "reminder"/"meeting" proposal has no separate concept of
    creating something in someone else's account."""
    payload = proposal.payload
    if proposal.action == "preview_delivery_reminder":

        async def _create_reminder() -> dict:
            # A specialist reminder still lives in the confirming user's own Personal workspace -
            # there is no separate "Agent Workspace reminder" concept (same reuse decision as
            # Reminder.source="agent" below, matching the Personal agent's own create_reminder tool).
            workspace = await resolve_workspace_for_user(db, confirming_user_id, None)
            reminder = await reminder_service.schedule_reminder(
                workspace_id=workspace.id,
                owner_id=confirming_user_id,
                title=payload["title"],
                due_at_iso=payload["due_at"],
                message=payload.get("message", ""),
                source="agent",  # matches Reminder.source's documented "manual" | "agent" | "proactive"
            )
            return {"reminder_id": reminder.id, "title": reminder.title, "due_at": reminder.due_at.isoformat()}

        return _create_reminder

    async def _create_meeting() -> dict:
        attendee_ids = payload.get("attendee_ids") or []
        emails: list[str] = []
        if attendee_ids:
            emails = list(
                (await db.execute(select(User.email).where(User.id.in_(attendee_ids)))).scalars()
            )
        start_dt = datetime.fromisoformat(payload["starts_at"])
        end_dt = start_dt + _DEFAULT_MEETING_DURATION
        event = await calendar_service.create_event(
            confirming_user_id, payload["title"], start_dt.isoformat(), end_dt.isoformat(), attendees=emails
        )
        return {"event_id": event.get("id"), "title": payload["title"], "starts_at": payload["starts_at"]}

    return _create_meeting


def _format_specialist_action_result(proposal: ActionProposal, result_payload: dict) -> str:
    if proposal.action == "preview_delivery_reminder":
        return f"Đã tạo nhắc nhở: \"{result_payload['title']}\" (hạn {result_payload['due_at']})."
    return f"Đã tạo lịch họp: \"{result_payload['title']}\" lúc {result_payload['starts_at']}."


async def _resume_specialist_action(request: ResumeRequest, current_user: User, db: AsyncSession) -> ChatResponse:
    """Confirms/rejects a specialist propose_*_reminder/meeting - the real HITL completion for
    _run_specialist_chat's status="interrupted" responses. Same shape as resume_chat's LangGraph
    branch (approve/reject, one final ChatResponse) but for a proposal tracked in
    _pending_specialist_proposals instead of a checkpointer thread.

    Deliberately does NOT pop the proposal on a successful approve (only on reject, or once
    hitl_executor itself says the proposal is unusable) - execute_action_proposal's own
    idempotency_key check already makes a second "confirm" on the same thread_id safe (it returns
    the same stored result instead of creating a second reminder/meeting), so a double-click just
    replays the same success message instead of hitting a 500 from falling through to the
    LangGraph branch below with a thread_id that was never a real checkpointer thread."""
    proposal = _pending_specialist_proposals.get(request.thread_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This proposal was already resolved or has expired")
    if proposal.actor_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your conversation")

    if not request.approved:
        del _pending_specialist_proposals[request.thread_id]
        return ChatResponse(response="Đã huỷ đề xuất.", thread_id=request.thread_id, status="completed")

    action_fn = _build_specialist_action_fn(db, proposal, current_user.id)
    try:
        result = await execute_action_proposal(db, proposal=proposal, confirming_user_id=current_user.id, action_fn=action_fn)
    except ActionProposalRejectedError as exc:
        _pending_specialist_proposals.pop(request.thread_id, None)  # unusable - nothing left to be idempotent about
        return ChatResponse(response=str(exc), thread_id=request.thread_id, status="error")
    except CalendarNotConnectedError:
        return ChatResponse(
            response="Bạn chưa kết nối Google Calendar - vào trang Calendar để kết nối trước khi tạo lịch họp.",
            thread_id=request.thread_id,
            status="error",
        )

    if result.status == ToolResultStatus.ERROR:
        return ChatResponse(
            response=result.error_message or "Không thực hiện được hành động.", thread_id=request.thread_id, status="error"
        )

    return ChatResponse(
        response=_format_specialist_action_result(proposal, result.payload), thread_id=request.thread_id, status="completed"
    )


def _build_chat_response(
    result: dict,
    thread_id: str,
    context_scope: AuthorizedContextMetadata | None = None,
) -> ChatResponse:
    interrupts = result.get("__interrupt__")
    if interrupts:
        payload = interrupts[0].value
        return ChatResponse(
            response="Please confirm the proposed action.",
            thread_id=thread_id,
            status="interrupted",
            interrupt=InterruptPayload(**payload),
            context_scope=context_scope,
        )

    error = result.get("error")
    if error:
        return ChatResponse(response=error, thread_id=thread_id, status="error", context_scope=context_scope)

    final_text = ""
    for m in reversed(result.get("messages", [])):
        # A trailing ToolMessage means graph.py routed straight to END after a "terminal" tool
        # (summarize_conversation/extract_tasks) - its content is already the final answer.
        if isinstance(m, (AIMessage, ToolMessage)) and m.content:
            final_text = m.content
            break
    if not final_text:
        final_text = (
            "Orbit không tạo được câu trả lời cho yêu cầu này — hãy thử diễn đạt lại hoặc hỏi cụ "
            "thể hơn."
        )
    return ChatResponse(
        response=final_text,
        thread_id=thread_id,
        status="completed",
        context_scope=context_scope,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Chat với AI agent."""
    thread_id = request.thread_id or str(uuid4())

    # Ràng buộc đề bài: "tối ưu chi phí" - chặn hẳn cuộc gọi LLM mới (không chỉ cảnh báo) một khi
    # đã chạm daily_token_budget. Chỉ áp dụng cho lượt chat MỚI - resume_chat() bên dưới cố tình
    # không chặn, vì nó hoàn tất một hành động con người đã bấm xác nhận rồi (human-in-the-loop),
    # chặn ở đó sẽ để interrupt() treo lơ lửng không cách nào hoàn tất hay huỷ.
    if await usage_service.is_over_budget():
        return ChatResponse(
            response=(
                "Đã vượt hạn mức token/chi phí AI hôm nay. Vui lòng thử lại vào ngày mai hoặc "
                "liên hệ admin để tăng hạn mức."
            ),
            thread_id=thread_id,
            status="error",
        )

    if request.requested_scope != RequestedScope.PERSONAL:
        # Deterministic Router path (product_delivery/quality_assurance/executive) - separate from
        # the LangGraph Personal-agent flow below; see _run_specialist_chat's docstring for scope.
        return await _run_specialist_chat(request, current_user, db, thread_id)

    if request.conversation_id is not None:
        await require_conversation_access(db, current_user, request.conversation_id, "viewer")
        conversation = await db.get(Conversation, request.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        if request.workspace_id is not None and request.workspace_id != conversation.workspace_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="conversation_id does not belong to workspace_id",
            )
        workspace_id = conversation.workspace_id
    else:
        workspace = await resolve_workspace_for_user(db, current_user.id, request.workspace_id)
        workspace_id = workspace.id
    if request.conversation_id is not None:
        # Conversation membership and AI consent are separate checks.
        await chat_service.assert_ai_permission(db, request.conversation_id, current_user.id)

    internal_thread_id, expired = await thread_memory_service.prepare_thread(
        db, current_user, workspace_id, thread_id
    )
    if expired:
        await agent_graph.checkpointer.adelete_thread(internal_thread_id)
    config = {"configurable": {"thread_id": internal_thread_id}}
    context_scope = None
    conversation_view = None
    if request.conversation_id is not None:
        conversation_view = await consent_service.build_authorized_message_view(
            db,
            request.conversation_id,
            request.context_limit,
            user_id=current_user.id,
            scope=request.scope,
        )
        context_text = conversation_view.text
        context_scope = AuthorizedContextMetadata(
            included_participants=conversation_view.included_participant_names,
            excluded_participants=conversation_view.excluded_participant_names,
            included_message_count=conversation_view.included_message_count,
            window_message_count=conversation_view.window_message_count,
            coverage=conversation_view.coverage,
            source_message_ids=conversation_view.source_message_ids,
            consent_scope_hash=conversation_view.consent_scope_hash,
        )
        if conversation_view.window_message_count and not conversation_view.source_message_ids:
            return ChatResponse(
                response="Không có tin nhắn nào trong phạm vi đã chọn được phép xử lý bởi Assistant.",
                thread_id=thread_id,
                status="completed",
                context_scope=context_scope,
            )
    else:
        scoped_messages = request.messages[-request.context_limit :] if request.messages else []
        context_text = _format_messages(scoped_messages)
    inputs = {
        "messages": [HumanMessage(content=request.message)],
        "context": context_text,
        "user_id": current_user.id,
        "workspace_id": workspace_id,
        "conversation_id": request.conversation_id,
        "consent_scope_hash": conversation_view.consent_scope_hash if conversation_view else None,
        "source_message_ids": conversation_view.source_message_ids if conversation_view else [],
    }
    try:
        result = await agent_graph.agent.ainvoke(inputs, config)
    except Exception:
        raise HTTPException(status_code=500, detail="AI service is temporarily unavailable")
    response = _build_chat_response(result, thread_id, context_scope)
    if request.conversation_id is None and response.status != "error":
        preview = response.response if response.status == "completed" else request.message
        await assistant_thread_service.touch_new_or_existing(
            db,
            thread_id=thread_id,
            owner_id=current_user.id,
            user_message=request.message,
            ai_preview=preview,
        )
    return response


@router.post("/chat/resume", response_model=ChatResponse)
async def resume_chat(
    request: ResumeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Resume an interrupted agent run with the user's confirm/reject decision."""
    if request.thread_id in _pending_specialist_proposals:
        # A specialist propose_*_reminder/meeting confirmation - not a LangGraph checkpointer
        # thread at all, see _pending_specialist_proposals's own docstring.
        return await _resume_specialist_action(request, current_user, db)

    thread = await thread_memory_service.require_resumable_thread(
        db, current_user, request.thread_id
    )
    config = {"configurable": {"thread_id": thread.id}}
    try:
        snapshot = await agent_graph.agent.aget_state(config)
        state_values = snapshot.values or {}
        conversation_id = state_values.get("conversation_id")
        consent_scope_hash = state_values.get("consent_scope_hash")
        if conversation_id:
            await chat_service.assert_ai_permission(db, conversation_id, current_user.id)
            current_hash = await consent_service.get_consent_scope_hash(db, conversation_id)
            if not consent_scope_hash or current_hash != consent_scope_hash:
                return ChatResponse(
                    response=(
                        "Quyền AI của conversation đã thay đổi từ khi hành động được đề xuất. "
                        "Vui lòng mở lại conversation và tạo đề xuất mới."
                    ),
                    thread_id=request.thread_id,
                    status="error",
                )
        result = await agent_graph.agent.ainvoke(
            Command(resume={"approved": request.approved, "edits": request.edits}), config
        )
    except Exception:
        raise HTTPException(status_code=500, detail="AI service is temporarily unavailable")
    response = _build_chat_response(result, request.thread_id)
    if response.status != "error":
        preview = response.response if response.status == "completed" else "Đang chờ xác nhận thêm..."
        await assistant_thread_service.touch_if_exists(
            db,
            owner_id=current_user.id,
            thread_id=request.thread_id,
            ai_preview=preview,
        )
    return response


@router.get("/status")
async def agent_status():
    """Kiểm tra trạng thái agent."""
    return {"status": "ready", "agent": "LangGraph Agent v1.0"}


@router.get("/usage/status", response_model=UsageStatusOut)
async def usage_status(current_user: User = Depends(get_current_user)) -> UsageStatusOut:
    del current_user
    return UsageStatusOut(**(await usage_service.get_usage_summary()))
