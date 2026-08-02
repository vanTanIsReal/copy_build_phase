from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AdminUserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime


class AdminStats(BaseModel):
    total_users: int
    total_conversations: int
    total_messages: int
    new_users_last_7_days: int


class UpdateRoleRequest(BaseModel):
    role: Literal["user", "admin"]


class UpdateStatusRequest(BaseModel):
    is_active: bool


class AdminConversationOut(BaseModel):
    id: str
    type: str
    name: str | None
    created_by: str
    created_at: datetime
    participant_count: int
    message_count: int


class AdminMessageOut(BaseModel):
    id: str
    sender_id: str
    sender_display_name: str
    content: str
    created_at: datetime
