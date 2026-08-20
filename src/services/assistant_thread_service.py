from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import graph as agent_graph
from src.db.models import AssistantThread

_TITLE_MAX = 60
_PREVIEW_MAX = 80
_LIST_LIMIT = 50


def _truncate(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())  # keep titles/previews on one line regardless of input formatting
    return collapsed if len(collapsed) <= limit else collapsed[:limit].rstrip() + "…"


async def _get_own_thread(db: AsyncSession, owner_id: str, thread_id: str) -> AssistantThread | None:
    return (
        await db.execute(
            select(AssistantThread).where(
                AssistantThread.owner_id == owner_id,
                AssistantThread.thread_id == thread_id,
            )
        )
    ).scalar_one_or_none()


async def touch_new_or_existing(
    db: AsyncSession, *, thread_id: str, owner_id: str, user_message: str, ai_preview: str
) -> None:
    """Called after a completed Personal Assistant turn (chat() with conversation_id=None - see
    routes.py). Creates the row on a brand new thread_id, title fixed from the first message; an
    existing thread only gets its preview/updated_at refreshed, title never changes after creation
    (same spirit as a conversation's name)."""
    existing = await _get_own_thread(db, owner_id, thread_id)
    if existing is None:
        db.add(
            AssistantThread(
                thread_id=thread_id,
                owner_id=owner_id,
                title=_truncate(user_message, _TITLE_MAX),
                preview=_truncate(ai_preview, _PREVIEW_MAX),
            )
        )
    else:
        existing.preview = _truncate(ai_preview, _PREVIEW_MAX)
    await db.commit()


async def touch_if_exists(db: AsyncSession, *, owner_id: str, thread_id: str, ai_preview: str) -> None:
    """Called after /chat/resume completes. Only updates a row that was already created by
    touch_new_or_existing - never creates one, so a resume for a conversation-embedded interrupt
    (e.g. AIPanel's "Suggest reminder") doesn't start showing up in the Assistant's own thread
    list."""
    existing = await _get_own_thread(db, owner_id, thread_id)
    if existing is not None:
        existing.preview = _truncate(ai_preview, _PREVIEW_MAX)
        await db.commit()


async def list_threads(db: AsyncSession, owner_id: str) -> list[AssistantThread]:
    result = await db.execute(
        select(AssistantThread)
        .where(AssistantThread.owner_id == owner_id)
        .order_by(AssistantThread.updated_at.desc())
        .limit(_LIST_LIMIT)
    )
    return list(result.scalars())


async def get_owned_thread(db: AsyncSession, owner_id: str, thread_id: str) -> AssistantThread | None:
    return await _get_own_thread(db, owner_id, thread_id)


async def get_thread_messages(owner_id: str, thread_id: str) -> list[dict]:
    """Read a thread's message history the officially-supported LangGraph way (aget_state), not by
    reaching into the checkpointer's own Postgres tables directly - see AssistantThread's docstring
    for why those tables can't be queried for this on their own anyway (no owner_id link).
    Tool-call-only AIMessages (empty content) and ToolMessages are dropped - only human/assistant
    text turns make sense to replay in the chat UI."""
    snapshot = await agent_graph.agent.aget_state(
        {"configurable": {"thread_id": f"{owner_id}:{thread_id}"}}
    )
    messages = (snapshot.values or {}).get("messages", []) if snapshot else []
    out: list[dict] = []
    for m in messages:
        if isinstance(m, HumanMessage) and m.content:
            out.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage) and m.content:
            out.append({"role": "assistant", "content": m.content})
    return out
