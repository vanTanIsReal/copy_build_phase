from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.models.calendar_schemas import CalendarEventOut, CalendarSlotOut

TaskStatus = Literal["suggested", "pending", "in_progress", "completed", "dismissed"]
TaskPriority = Literal["High", "Medium", "Low"]


class TaskOut(BaseModel):
    id: str
    conversation_id: str | None
    title: str
    due_at: datetime | None
    priority: TaskPriority
    status: TaskStatus
    source: Literal["manual", "proactive"]
    created_at: datetime


class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    due_at: datetime | None = None
    priority: TaskPriority = "Medium"
    conversation_id: str | None = None
    source: Literal["manual", "proactive"] = "manual"


class UpdateTaskStatusRequest(BaseModel):
    status: TaskStatus


class TaskAcceptRequest(BaseModel):
    """Body for POST /tasks/{id}/accept. Both fields are how the caller resolves a conflict a
    previous call to this same endpoint reported - see accept_task in task_routes.py."""

    due_at: datetime | None = None  # override the task's date/time (a picked alternative, or a custom pick)
    force: bool = False  # accept at the (possibly overridden) time even though it conflicts


class TaskAcceptResponse(BaseModel):
    task: TaskOut
    conflict: bool
    conflicts: list[CalendarEventOut] = Field(default_factory=list)
    alternatives: list[CalendarSlotOut] = Field(default_factory=list)
