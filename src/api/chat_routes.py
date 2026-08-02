from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.config import get_settings
from src.db.models import Conversation, ConversationParticipant, Message, User
from src.db.session import get_db
from src.models.auth_schemas import UserPublic
from src.models.chat_schemas import (
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationSummary,
    GroupSearchResponse,
    GroupSearchResult,
    MessageListResponse,
    MessageOut,
    SendMessageRequest,
)
from src.services import chat_service
from src.websocket.manager import manager

router = APIRouter()


@router.get("/users", response_model=list[UserPublic])
async def list_users(
    search: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserPublic]:
    stmt = select(User).where(User.id != current_user.id)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(or_(User.display_name.ilike(pattern), User.email.ilike(pattern)))
    users = (await db.execute(stmt)).scalars().all()
    return [UserPublic(id=u.id, email=u.email, display_name=u.display_name, role=u.role) for u in users]


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    if get_settings().app_env == "development":
        await chat_service.ensure_demo_groups(db, current_user.id)

    conversation_ids = (
        (
            await db.execute(
                select(ConversationParticipant.conversation_id).where(
                    ConversationParticipant.user_id == current_user.id
                )
            )
        )
        .scalars()
        .all()
    )
    conversations = (
        (
            await db.execute(
                select(Conversation)
                .where(Conversation.id.in_(conversation_ids))
                .order_by(Conversation.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    summaries = [await chat_service.build_conversation_summary(db, c, current_user.id) for c in conversations]
    return ConversationListResponse(conversations=summaries)


@router.get("/groups", response_model=GroupSearchResponse)
async def list_groups(
    search: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroupSearchResponse:
    if get_settings().app_env == "development":
        await chat_service.ensure_demo_groups(db, current_user.id)

    stmt = select(Conversation).where(Conversation.type == "group")
    if search:
        stmt = stmt.where(Conversation.name.ilike(f"%{search}%"))
    conversations = (await db.execute(stmt.order_by(Conversation.updated_at.desc()))).scalars().all()

    groups = []
    for conversation in conversations:
        summary = await chat_service.build_conversation_summary(db, conversation, current_user.id)
        groups.append(
            GroupSearchResult(
                id=summary.id,
                name=summary.name,
                member_count=len(summary.participants),
                is_member=any(participant.id == current_user.id for participant in summary.participants),
                last_message=summary.last_message,
                updated_at=summary.updated_at,
            )
        )
    return GroupSearchResponse(groups=groups)


@router.post("/conversations", response_model=ConversationSummary)
async def create_conversation(
    request: ConversationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSummary:
    if request.type == "direct":
        if len(request.participant_ids) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Direct conversations need exactly one other participant",
            )
        conversation = await chat_service.get_or_create_direct_conversation(
            db, current_user.id, request.participant_ids[0]
        )
    else:
        if not request.name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group conversations require a name")
        conversation = await chat_service.create_group_conversation(
            db, current_user.id, request.participant_ids, request.name
        )
    return await chat_service.build_conversation_summary(db, conversation, current_user.id)


@router.post("/conversations/{conversation_id}/join", response_model=ConversationSummary)
async def join_group(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSummary:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.type != "group":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    participant = (
        await db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if participant is None:
        db.add(ConversationParticipant(conversation_id=conversation_id, user_id=current_user.id))
        await db.commit()

    return await chat_service.build_conversation_summary(db, conversation, current_user.id)


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def get_messages(
    conversation_id: str,
    before: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageListResponse:
    await chat_service.assert_participant(db, conversation_id, current_user.id)

    stmt = (
        select(Message, User).join(User, User.id == Message.sender_id).where(Message.conversation_id == conversation_id)
    )
    if before:
        before_message = await db.get(Message, before)
        if before_message is not None:
            stmt = stmt.where(Message.created_at < before_message.created_at)
    stmt = stmt.order_by(Message.created_at.desc()).limit(limit + 1)

    rows = (await db.execute(stmt)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    messages = [chat_service.serialize_message(m, u) for m, u in reversed(rows)]
    return MessageListResponse(messages=messages, has_more=has_more)


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut)
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    await chat_service.assert_participant(db, conversation_id, current_user.id)
    message = await chat_service.create_message(db, conversation_id, current_user.id, request.content)
    message_out = chat_service.serialize_message(message, current_user)

    participant_ids = await chat_service.get_participant_ids(db, conversation_id)
    await manager.broadcast_to_users(participant_ids, {"type": "new_message", "message": message_out.model_dump()})
    return message_out


@router.post("/conversations/{conversation_id}/read")
async def mark_conversation_read(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await chat_service.mark_read(db, conversation_id, current_user.id)
    return {"status": "ok"}
