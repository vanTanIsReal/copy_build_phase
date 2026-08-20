from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import graph as agent_graph
from src.agents import router as agent_router
from src.agents.context_builder import AgentRunRecorder, build_agent_context
from src.agents.contracts import (
    AgentIntent,
    AgentInvocationRequest,
    AgentProfile,
    PolicyDecision,
    PolicyReason,
    RequestedScope,
    ToolResultStatus,
)
from src.agents.tools import delivery_tool, executive_tool, quality_tool
from src.api.rate_limit import crud_rate_limit, limiter
from src.auth.dependencies import get_current_user
from src.config import get_settings
from src.db.models import AgentWorkspace, User, Workspace, WorkspaceMembership
from src.db.session import get_db
from src.models.schemas import ChatMessage, ChatRequest, ChatResponse, InterruptPayload, ResumeRequest
from src.models.usage_schemas import UsageStatusOut
from src.services import assistant_thread_service, chat_service, quick_action_service, usage_service

# Ngày 6-7 hookup (MULTI_AGENT_IMPLEMENTATION_PLAN.md): which specialist tool builds the read-only
# brief for a resolved route.profile. Only the brief-producing intents are reachable from /chat -
# propose_*_reminder/propose_*_meeting stay reachable only from tests/scripts/run_eval.py (see
# _run_specialist_chat's docstring for why).
_SPECIALIST_BRIEF_TOOL = {
    AgentProfile.PRODUCT_DELIVERY: delivery_tool.build_delivery_brief,
    AgentProfile.QUALITY_ASSURANCE: quality_tool.build_quality_brief,
    AgentProfile.EXECUTIVE: executive_tool.build_executive_brief,
}

_SPECIALIST_DENY_TEXT = {
    PolicyReason.NOT_MEMBER: "Bạn chưa là thành viên của agent workspace này.",
    PolicyReason.WRONG_WORKSPACE: "Không tìm thấy agent workspace này trong tổ chức của bạn.",
    PolicyReason.PROFILE_MISMATCH: "Agent workspace này không khớp với loại yêu cầu.",
    PolicyReason.INVALID_SCOPE: "Yêu cầu không hợp lệ cho phạm vi này.",
    PolicyReason.RESOURCE_NOT_ALLOWED: "Bạn không có quyền truy cập dữ liệu này.",
    PolicyReason.CONSENT_CHANGED: "Quyền chia sẻ dữ liệu đã thay đổi, vui lòng thử lại.",
    PolicyReason.FEATURE_DISABLED: "Tính năng này hiện chưa được bật.",
}

router = APIRouter()

# thread_id -> owner user id. In-memory only: enough to stop one user resuming another
# user's interrupted (unconfirmed calendar/reminder) run; doesn't need to survive a restart
# since thread_ids are random UUIDs nobody else can guess anyway.
_thread_owners: dict[str, str] = {}


def _check_thread_owner(thread_id: str, current_user: User) -> None:
    owner = _thread_owners.get(thread_id)
    if owner is not None and owner != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your conversation")


def _format_messages(messages: list[ChatMessage]) -> str:
    lines = []
    for m in messages:
        ts = chat_service.format_local_timestamp(m.timestamp) if m.timestamp else None
        who = f"{m.sender or m.role}" + (f" [{ts}]" if ts else "")
        lines.append(f"{who}: {m.content}")
    return "\n".join(lines)


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


async def _resolve_specialist_intent(
    db: AsyncSession, requested_scope: RequestedScope, target_agent_workspace_id: str | None
) -> AgentIntent:
    if requested_scope == RequestedScope.AGGREGATE:
        return AgentIntent.EXECUTIVE_BRIEF
    if target_agent_workspace_id:
        workspace = await db.get(AgentWorkspace, target_agent_workspace_id)
        if workspace is not None and workspace.agent_profile == AgentProfile.QUALITY_ASSURANCE.value:
            return AgentIntent.QUALITY_BRIEF
    # Fallback when the target can't be resolved (missing workspace, wrong org, ...) - safe because
    # agent_router.route_agent_request checks the workspace's existence/org BEFORE it ever checks
    # whether this intent is allowed for the resolved profile, so an unresolved target still ends up
    # denied with the correct WRONG_WORKSPACE reason regardless of this placeholder.
    return AgentIntent.DELIVERY_BRIEF


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
    from the LangGraph Personal-agent path above (that path is untouched by this function).

    Scope of this hookup is deliberately read-only: only the brief-producing intents
    (build_delivery_brief/build_quality_brief/build_executive_brief) are reachable here.
    propose_*_reminder/propose_*_meeting stay reachable only from tests/scripts/run_eval.py - they
    already return an ActionProposal preview, but nothing here turns that into a real
    interrupt()/resume flow yet. Wiring a brand-new approval UI in the same pass risked the
    project's human-in-the-loop guarantee (CLAUDE.md's hard constraint), so it is left as an
    explicit, separate follow-up instead of done half-way.

    A real user has zero AgentWorkspace/organization membership today (see Workspace's own
    docstring in src/db/models.py) - this function never fabricates one; no membership resolves to
    a real DENY_NOT_MEMBER below, exactly like any other authorization failure.
    """
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

    intent = await _resolve_specialist_intent(db, body.requested_scope, body.target_agent_workspace_id)
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
        tool = _SPECIALIST_BRIEF_TOOL[route.profile]
        result = await tool(db, context)

    if result.status == ToolResultStatus.ERROR:
        return ChatResponse(
            response=result.error_message or "Không lấy được dữ liệu.", thread_id=thread_id, status="error"
        )

    if route.profile == AgentProfile.EXECUTIVE:
        text = _format_executive_brief_text(result.payload["executive_brief"])
    else:
        text = _format_workspace_brief_text(result.payload["workspace_brief"])
    return ChatResponse(response=text, thread_id=thread_id, status="completed")


def _build_chat_response(result: dict, thread_id: str) -> ChatResponse:
    interrupts = result.get("__interrupt__")
    if interrupts:
        payload = interrupts[0].value
        return ChatResponse(
            response="Please confirm the proposed action.",
            thread_id=thread_id,
            status="interrupted",
            interrupt=InterruptPayload(**payload),
        )

    error = result.get("error")
    if error:
        return ChatResponse(response=error, thread_id=thread_id, status="error")

    final_text = ""
    for m in reversed(result.get("messages", [])):
        # A trailing ToolMessage means graph.py routed straight to END after a "terminal" tool
        # (summarize_conversation/extract_tasks) - its content is already the final answer.
        if isinstance(m, (AIMessage, ToolMessage)) and m.content:
            final_text = m.content
            break
    if not final_text:
        # The planner's last AIMessage can legitimately have empty content (e.g. it emitted a tool
        # call with no accompanying text, or had nothing to say given the tools/context it had).
        # Without this, the frontend renders a bubble with no text and no error - status is
        # "completed" so the "status === 'error'" fallback text never kicks in either. Better to
        # surface it plainly than let it look like the AI silently did nothing.
        final_text = (
            "Orbit không tạo được câu trả lời cho yêu cầu này — hãy thử diễn đạt lại hoặc hỏi cụ "
            "thể hơn."
        )
    return ChatResponse(response=final_text, thread_id=thread_id, status="completed")


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(get_settings().rate_limit_chat)
async def chat(
    request: Request,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Chat với AI agent."""
    if body.conversation_id:
        # Don't trust the client's word that `messages` came from a conversation it's allowed to
        # see - verify current_user is actually a participant before the agent processes them.
        await chat_service.assert_participant(db, body.conversation_id, current_user.id)
        # Being a participant isn't consent for the AI to read this conversation - that's a
        # separate, explicit per-user grant (AIPanel's Grant/Revoke permission toggle).
        await chat_service.assert_ai_permission(db, body.conversation_id, current_user.id)

    thread_id = body.thread_id or str(uuid4())
    _check_thread_owner(thread_id, current_user)

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

    if body.requested_scope != RequestedScope.PERSONAL:
        # Deterministic Router path (product_delivery/quality_assurance/executive) - separate from
        # the LangGraph Personal-agent flow below; see _run_specialist_chat's docstring for scope.
        return await _run_specialist_chat(body, current_user, db, thread_id)

    _thread_owners.setdefault(thread_id, current_user.id)
    config = {"configurable": {"thread_id": thread_id}}
    if body.conversation_id and body.scope:
        # Server-resolved scope takes priority over any client-supplied `messages` - the whole
        # point of `scope` is to not trust the client's already-loaded (at most 50) messages.
        scoped = await chat_service.get_scoped_messages(db, body.conversation_id, current_user.id, body.scope)
        context_text = _format_messages(scoped) if scoped else ""
    else:
        context_text = _format_messages(body.messages) if body.messages else ""

    if body.quick_action:
        # AIPanel's deterministic Quick Actions (Summarize/Extract tasks) always send one fixed
        # message the planner's system prompt always maps to the same tool - there's no real
        # decision to make, so the planner's LLM call is pure overhead. Skip the planner + the
        # whole LangGraph/checkpointer run entirely (these requests never carry a thread_id from
        # AIPanel anyway - each click is a one-shot exchange, nothing relies on it being
        # rememberable later) and call the tool's own logic directly - 1 LLM call instead of 2.
        # Same guards as the graph path above still apply (participant/permission/budget), just no
        # LLM decision step after them.
        try:
            text = await quick_action_service.run_quick_action(body.quick_action, context_text)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        return ChatResponse(response=text, thread_id=thread_id, status="completed")

    inputs = {
        "messages": [HumanMessage(content=body.message)],
        "context": context_text,
        "user_id": current_user.id,
        "conversation_id": body.conversation_id,
    }
    try:
        result = await agent_graph.agent.ainvoke(inputs, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    response = _build_chat_response(result, thread_id)

    if body.conversation_id is None and response.status != "error":
        # Personal Assistant session (not an AIPanel-embedded call, which always sets
        # conversation_id) - keep the /assistant page's "Gần đây" thread list in sync.
        # quick_action requests never reach this point (they return earlier above), so no separate
        # check for that is needed here.
        preview = response.response if response.status == "completed" else body.message
        await assistant_thread_service.touch_new_or_existing(
            db, thread_id=thread_id, owner_id=current_user.id, user_message=body.message, ai_preview=preview
        )
    return response


@router.post("/chat/resume", response_model=ChatResponse)
@limiter.exempt
async def resume_chat(
    request: ResumeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Resume an interrupted agent run with the user's confirm/reject decision.

    Exempt from rate limiting (see src/api/rate_limit.py) - same reasoning as its exemption from
    usage_service.is_over_budget() above: this completes an already-approved human-in-the-loop
    action tied to a thread_id the user already owns, not a fresh request. Limiting it risks
    leaving an interrupt() permanently stuck with no way to complete or cancel.
    """
    _check_thread_owner(request.thread_id, current_user)
    config = {"configurable": {"thread_id": request.thread_id}}
    try:
        result = await agent_graph.agent.ainvoke(
            Command(resume={"approved": request.approved, "edits": request.edits}), config
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    response = _build_chat_response(result, request.thread_id)

    if response.status != "error":
        # Only touches a row that already exists (assistant_thread_service.touch_if_exists) - a
        # resume for a conversation-embedded interrupt (e.g. AIPanel's "Suggest reminder") never
        # had one created in the first place, and must stay that way.
        preview = response.response if response.status == "completed" else "Đang chờ xác nhận thêm..."
        await assistant_thread_service.touch_if_exists(db, thread_id=request.thread_id, ai_preview=preview)
    return response


@router.get("/status")
@limiter.exempt
async def agent_status():
    """Kiểm tra trạng thái agent."""
    return {"status": "ready", "agent": "LangGraph Agent v1.0"}


@router.get("/usage/status", response_model=UsageStatusOut, dependencies=[Depends(crud_rate_limit)])
async def usage_status(current_user: User = Depends(get_current_user)) -> UsageStatusOut:
    """Non-admin usage indicator (Sidebar.jsx's "Ngân sách AI hôm nay" widget) - any authenticated
    user, not just admins (see usage_service.get_usage_summary() for exactly what is/isn't
    included; the admin-only breakdown with cost/model data stays at GET /admin/stats)."""
    del current_user  # only used as the auth gate
    summary = await usage_service.get_usage_summary()
    return UsageStatusOut(**summary)
