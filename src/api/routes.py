from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import graph as agent_graph
from src.api.rate_limit import crud_rate_limit, limiter
from src.auth.dependencies import get_current_user
from src.config import get_settings
from src.db.models import User
from src.db.session import get_db
from src.models.schemas import ChatMessage, ChatRequest, ChatResponse, InterruptPayload, ResumeRequest
from src.models.usage_schemas import UsageStatusOut
from src.services import assistant_thread_service, chat_service, quick_action_service, usage_service

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
