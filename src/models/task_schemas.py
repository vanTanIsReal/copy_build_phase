from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TaskStatus = Literal["suggested", "pending", "in_progress", "completed", "dismissed", "invalidated"]
TaskPriority = Literal["High", "Medium", "Low"]


class TaskSourceMessageOut(BaseModel):
    """One message that contributed to an AI-suggested task, for the "why did Orbit suggest this"
    hover detail - source_message_ids[0] is always the message that first proposed the commitment
    (see proactive_service.py), so sender_name of the first entry is who proposed it."""

    sender_name: str
    content: str
    created_at: datetime


class TaskOut(BaseModel):
    id: str
    workspace_id: str
    conversation_id: str | None
    title: str
    due_at: datetime | None
    priority: TaskPriority
    status: TaskStatus
    source: Literal["manual", "ai_extracted", "proactive"]
    source_message_ids: list[str] | None = None
    consent_scope_hash: str | None = None
    invalidated_reason: str | None = None
    calendar_event_id: str | None = None
    reminder_id: str | None = None
    source_messages: list[TaskSourceMessageOut] | None = None
    created_at: datetime
    updated_at: datetime


class TaskCreateRequest(BaseModel):
    workspace_id: str | None = None
    title: str = Field(..., min_length=1, max_length=200)
    due_at: datetime | None = None
    priority: TaskPriority = "Medium"
    conversation_id: str | None = None
    source: Literal["manual", "ai_extracted"] = "manual"
    source_message_ids: list[str] | None = None
    consent_scope_hash: str | None = None


class UpdateTaskStatusRequest(BaseModel):
    status: TaskStatus
    # Set together with an Accept (suggested -> pending) on a task the AI couldn't find a clear
    # date/time for (due_at was null) - the frontend prompts for it at that moment instead of a
    # separate edit step, so Calendar/Reminder sync on Accept has something to schedule against.
    # Never clears an existing due_at: omitted or null leaves the task's current value untouched.
    due_at: datetime | None = None
