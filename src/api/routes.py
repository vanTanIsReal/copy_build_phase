from uuid import uuid4

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from src.agents.graph import agent
from src.models.schemas import ChatMessage, ChatRequest, ChatResponse, InterruptPayload, ResumeRequest

router = APIRouter()


def _format_messages(messages: list[ChatMessage]) -> str:
    return "\n".join(f"{m.sender or m.role}: {m.content}" for m in messages)


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

    final_text = ""
    for m in reversed(result.get("messages", [])):
        if isinstance(m, AIMessage) and m.content:
            final_text = m.content
            break
    return ChatResponse(response=final_text, thread_id=thread_id, status="completed")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Chat với AI agent."""
    thread_id = request.thread_id or str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    context_text = _format_messages(request.messages) if request.messages else ""
    inputs = {"messages": [HumanMessage(content=request.message)], "context": context_text}
    try:
        result = await agent.ainvoke(inputs, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return _build_chat_response(result, thread_id)


@router.post("/chat/resume", response_model=ChatResponse)
async def resume_chat(request: ResumeRequest) -> ChatResponse:
    """Resume an interrupted agent run with the user's confirm/reject decision."""
    config = {"configurable": {"thread_id": request.thread_id}}
    try:
        result = await agent.ainvoke(Command(resume={"approved": request.approved, "edits": request.edits}), config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return _build_chat_response(result, request.thread_id)


@router.get("/status")
async def agent_status():
    """Kiểm tra trạng thái agent."""
    return {"status": "ready", "agent": "LangGraph Agent v1.0"}
