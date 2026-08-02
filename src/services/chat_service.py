from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.security import hash_password
from src.db.models import Conversation, ConversationParticipant, Message, User
from src.models.auth_schemas import UserPublic
from src.models.chat_schemas import ConversationSummary, MessageOut

DEMO_GROUPS = [
    {
        "name": "Product Launch Team",
        "members": [("Maya Chen", "demo-maya@orbit.local"), ("Jordan Lee", "demo-jordan@orbit.local")],
        "messages": [
            ("demo-maya@orbit.local", "The launch checklist is ready for review."),
            ("demo-jordan@orbit.local", "I will add the final campaign numbers this afternoon."),
        ],
    },
    {
        "name": "Leadership Circle",
        "members": [("Jordan Lee", "demo-jordan@orbit.local"), ("Chris Morgan", "demo-chris@orbit.local")],
        "messages": [
            ("demo-jordan@orbit.local", "Can we confirm the Q3 planning room before Friday?"),
            ("demo-chris@orbit.local", "Yes, I will send the calendar invite after the stand-up."),
        ],
    },
    {
        "name": "Design System Crew",
        "members": [("Maya Chen", "demo-maya@orbit.local"), ("Chris Morgan", "demo-chris@orbit.local")],
        "messages": [
            ("demo-chris@orbit.local", "The new button states are ready in the component library."),
            ("demo-maya@orbit.local", "Great. I will review accessibility and mobile states next."),
        ],
    },
]

PUBLIC_DEMO_GROUP = {
    "name": "AI Builders Community",
    "members": [
        ("Maya Chen", "demo-maya@orbit.local"),
        ("Jordan Lee", "demo-jordan@orbit.local"),
        ("Chris Morgan", "demo-chris@orbit.local"),
    ],
    "messages": [
        ("demo-maya@orbit.local", "Welcome to the AI builders community."),
        ("demo-jordan@orbit.local", "Share your favorite agent workflow here."),
    ],
}


async def ensure_demo_groups(db: AsyncSession, current_user_id: str) -> None:
    """Create development-only group conversations for a user on first chat visit."""
    demo_names = [group["name"] for group in DEMO_GROUPS]
    existing_names = set(
        (
            await db.execute(
                select(Conversation.name)
                .join(ConversationParticipant, ConversationParticipant.conversation_id == Conversation.id)
                .where(
                    ConversationParticipant.user_id == current_user_id,
                    Conversation.type == "group",
                    Conversation.name.in_(demo_names),
                )
            )
        )
        .scalars()
        .all()
    )
    missing_groups = [group for group in DEMO_GROUPS if group["name"] not in existing_names]
    public_group_exists = (
        await db.execute(
            select(Conversation.id).where(
                Conversation.type == "group", Conversation.name == PUBLIC_DEMO_GROUP["name"]
            )
        )
    ).scalar_one_or_none() is not None
    if not missing_groups and public_group_exists:
        return

    member_specs = {}
    seed_groups = [*missing_groups]
    if not public_group_exists:
        seed_groups.append(PUBLIC_DEMO_GROUP)
    for group in seed_groups:
        for display_name, email in group["members"]:
            member_specs[email] = display_name

    demo_users = {}
    for email, display_name in member_specs.items():
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            user = User(email=email, password_hash=hash_password("demo-password"), display_name=display_name)
            db.add(user)
            await db.flush()
        demo_users[email] = user

    for group_index, group in enumerate(missing_groups):
        created_at = datetime.now(UTC) - timedelta(minutes=(len(missing_groups) - group_index) * 4)
        conversation = Conversation(
            type="group",
            name=group["name"],
            created_by=current_user_id,
            created_at=created_at,
            updated_at=created_at,
        )
        db.add(conversation)
        await db.flush()

        participant_ids = {current_user_id, *(demo_users[email].id for _, email in group["members"])}
        for participant_id in participant_ids:
            db.add(ConversationParticipant(conversation_id=conversation.id, user_id=participant_id))

        for message_index, (email, content) in enumerate(group["messages"]):
            db.add(
                Message(
                    conversation_id=conversation.id,
                    sender_id=demo_users[email].id,
                    content=content,
                    created_at=created_at + timedelta(minutes=message_index + 1),
                )
            )

    if not public_group_exists:
        created_at = datetime.now(UTC) - timedelta(minutes=2)
        public_group = Conversation(
            type="group",
            name=PUBLIC_DEMO_GROUP["name"],
            created_by=demo_users["demo-maya@orbit.local"].id,
            created_at=created_at,
            updated_at=created_at,
        )
        db.add(public_group)
        await db.flush()
        for _, email in PUBLIC_DEMO_GROUP["members"]:
            db.add(ConversationParticipant(conversation_id=public_group.id, user_id=demo_users[email].id))
        for message_index, (email, content) in enumerate(PUBLIC_DEMO_GROUP["messages"]):
            db.add(
                Message(
                    conversation_id=public_group.id,
                    sender_id=demo_users[email].id,
                    content=content,
                    created_at=created_at + timedelta(minutes=message_index + 1),
                )
            )

    await db.commit()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def serialize_message(message: Message, sender: User) -> MessageOut:
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        sender_name=sender.display_name,
        content=message.content,
        created_at=_iso(message.created_at),
    )


async def assert_participant(db: AsyncSession, conversation_id: str, user_id: str) -> None:
    participant = (
        await db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if participant is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a participant of this conversation")


async def get_participant_ids(db: AsyncSession, conversation_id: str) -> list[str]:
    rows = await db.execute(
        select(ConversationParticipant.user_id).where(ConversationParticipant.conversation_id == conversation_id)
    )
    return [r[0] for r in rows.all()]


async def create_message(db: AsyncSession, conversation_id: str, sender_id: str, content: str) -> Message:
    message = Message(conversation_id=conversation_id, sender_id=sender_id, content=content)
    db.add(message)
    conversation = await db.get(Conversation, conversation_id)
    conversation.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(message)
    return message


async def mark_read(db: AsyncSession, conversation_id: str, user_id: str) -> None:
    participant = (
        await db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if participant is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a participant of this conversation")
    participant.last_read_at = datetime.now(UTC)
    await db.commit()


async def get_or_create_direct_conversation(db: AsyncSession, user_a_id: str, user_b_id: str) -> Conversation:
    candidate_ids = (
        (
            await db.execute(
                select(ConversationParticipant.conversation_id)
                .join(Conversation, Conversation.id == ConversationParticipant.conversation_id)
                .where(Conversation.type == "direct", ConversationParticipant.user_id == user_a_id)
            )
        )
        .scalars()
        .all()
    )
    for cid in candidate_ids:
        participant_ids = await get_participant_ids(db, cid)
        if set(participant_ids) == {user_a_id, user_b_id}:
            return await db.get(Conversation, cid)

    conversation = Conversation(type="direct", name=None, created_by=user_a_id)
    db.add(conversation)
    await db.flush()
    db.add(ConversationParticipant(conversation_id=conversation.id, user_id=user_a_id))
    db.add(ConversationParticipant(conversation_id=conversation.id, user_id=user_b_id))
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def create_group_conversation(
    db: AsyncSession, creator_id: str, member_ids: list[str], name: str
) -> Conversation:
    conversation = Conversation(type="group", name=name, created_by=creator_id)
    db.add(conversation)
    await db.flush()
    all_member_ids = {creator_id, *member_ids}
    for member_id in all_member_ids:
        db.add(ConversationParticipant(conversation_id=conversation.id, user_id=member_id))
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def build_conversation_summary(
    db: AsyncSession, conversation: Conversation, current_user_id: str
) -> ConversationSummary:
    participant_rows = (
        await db.execute(
            select(User, ConversationParticipant)
            .join(ConversationParticipant, ConversationParticipant.user_id == User.id)
            .where(ConversationParticipant.conversation_id == conversation.id)
        )
    ).all()
    participants = [
        UserPublic(id=u.id, email=u.email, display_name=u.display_name, role=u.role) for u, _ in participant_rows
    ]
    my_participant = next((cp for _, cp in participant_rows if cp.user_id == current_user_id), None)

    if conversation.type == "group":
        name = conversation.name or "Group"
    else:
        other = next((u for u, _ in participant_rows if u.id != current_user_id), None)
        name = other.display_name if other else "Direct message"

    last_message_row = (
        await db.execute(
            select(Message, User)
            .join(User, User.id == Message.sender_id)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
    ).first()
    last_message = serialize_message(last_message_row[0], last_message_row[1]) if last_message_row else None

    unread_count = 0
    if my_participant is not None:
        unread_count = (
            await db.execute(
                select(func.count(Message.id)).where(
                    Message.conversation_id == conversation.id,
                    Message.created_at > my_participant.last_read_at,
                    Message.sender_id != current_user_id,
                )
            )
        ).scalar_one()

    return ConversationSummary(
        id=conversation.id,
        type=conversation.type,
        name=name,
        participants=participants,
        last_message=last_message,
        unread_count=unread_count,
        updated_at=_iso(conversation.updated_at),
    )
