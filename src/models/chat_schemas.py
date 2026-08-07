from typing import Literal

from pydantic import BaseModel, Field

from src.models.auth_schemas import UserPublic


class ConversationCreateRequest(BaseModel):
    type: Literal["direct", "group"]
    participant_ids: list[str] = Field(..., min_length=1)
    name: str | None = None


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    sender_name: str
    content: str
    created_at: str


class ConversationSummary(BaseModel):
    id: str
    type: Literal["direct", "group"]
    name: str
    participants: list[UserPublic]
    last_message: MessageOut | None
    unread_count: int
    updated_at: str


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]


class GroupSearchResult(BaseModel):
    id: str
    name: str
    member_count: int
    is_member: bool
    last_message: MessageOut | None
    updated_at: str


class GroupSearchResponse(BaseModel):
    groups: list[GroupSearchResult]


class MessageListResponse(BaseModel):
    messages: list[MessageOut]
    has_more: bool


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
