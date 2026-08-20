from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Conversation, Memory, User
from src.models.memory_schemas import MemoryCreateRequest
from src.services import chat_service, consent_service
from src.services.authorization_service import require_conversation_access


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def is_expired(memory: Memory, now: datetime | None = None) -> bool:
    if memory.expires_at is None:
        return False
    return _utc(memory.expires_at) <= (now or datetime.now(UTC))


async def validate_memory_source(
    db: AsyncSession,
    user: User,
    conversation_id: str,
    workspace_id: str,
    source_message_ids: list[str],
    consent_scope_hash: str,
) -> None:
    await require_conversation_access(db, user, conversation_id, "viewer")
    await chat_service.assert_ai_permission(db, conversation_id, user.id)
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Memory source does not belong to the selected workspace",
        )
    current_hash = await consent_service.get_consent_scope_hash(db, conversation_id)
    if current_hash != consent_scope_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation AI consent changed; create the memory from fresh context",
        )
    if not await consent_service.validate_authorized_source_ids(db, conversation_id, source_message_ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Memory provenance includes a message that AI is not allowed to process",
        )


async def create_memory_from_request(
    db: AsyncSession,
    user: User,
    workspace_id: str,
    request: MemoryCreateRequest,
) -> Memory:
    if request.expires_at is not None and _utc(request.expires_at) <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expires_at must be in the future",
        )
    if request.source_conversation_id:
        await validate_memory_source(
            db,
            user,
            request.source_conversation_id,
            workspace_id,
            request.source_message_ids,
            request.consent_scope_hash or "",
        )
    memory = Memory(
        workspace_id=workspace_id,
        owner_id=user.id,
        category=request.category,
        title=request.title,
        detail=request.detail,
        memory_type=request.memory_type,
        source_conversation_id=request.source_conversation_id,
        source_message_ids=request.source_message_ids,
        consent_scope_hash=request.consent_scope_hash,
        sensitivity=request.sensitivity,
        confidence=request.confidence,
        expires_at=request.expires_at,
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    return memory


async def search_active_memories(
    db: AsyncSession,
    *,
    owner_id: str,
    workspace_id: str,
    query: str = "",
    memory_types: set[str] | None = None,
    limit: int = 10,
) -> list[Memory]:
    now = datetime.now(UTC)
    owner = await db.get(User, owner_id)
    if owner is None or not owner.is_active:
        return []
    stmt = select(Memory).where(
        Memory.owner_id == owner_id,
        Memory.workspace_id == workspace_id,
        or_(Memory.expires_at.is_(None), Memory.expires_at > now),
    )
    if memory_types:
        stmt = stmt.where(Memory.memory_type.in_(memory_types))
    if query.strip():
        pattern = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                Memory.title.ilike(pattern),
                Memory.detail.ilike(pattern),
                Memory.category.ilike(pattern),
            )
        )
    candidates = list(
        (await db.execute(stmt.order_by(Memory.updated_at.desc()).limit(max(1, min(limit * 3, 50))))).scalars()
    )
    active: list[Memory] = []
    for memory in candidates:
        if memory.source_conversation_id:
            try:
                await require_conversation_access(db, owner, memory.source_conversation_id, "viewer")
            except HTTPException:
                continue
            current_hash = await consent_service.get_consent_scope_hash(db, memory.source_conversation_id)
            if current_hash != memory.consent_scope_hash:
                continue
            if not await consent_service.validate_authorized_source_ids(
                db, memory.source_conversation_id, memory.source_message_ids
            ):
                continue
        memory.last_accessed_at = now
        active.append(memory)
        if len(active) >= limit:
            break
    if active:
        await db.commit()
    return active
