import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rate_limit import crud_rate_limit
from src.auth.dependencies import get_current_user
from src.config import get_settings
from src.db.models import Task, User
from src.db.session import get_db
from src.models.task_schemas import (
    TaskAcceptRequest,
    TaskAcceptResponse,
    TaskCreateRequest,
    TaskOut,
    UpdateTaskStatusRequest,
)
from src.services import calendar_service, reminder_service, task_service
from src.services.google_credentials import CalendarNotConnected
from src.websocket.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(crud_rate_limit)])


def _to_out(task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        conversation_id=task.conversation_id,
        title=task.title,
        due_at=task.due_at,
        priority=task.priority,
        status=task.status,
        source=task.source,
        created_at=task.created_at,
    )


async def _get_own_task_or_404(task_id: str, current_user: User, db: AsyncSession) -> Task:
    task = (
        await db.execute(select(Task).where(Task.id == task_id, Task.owner_id == current_user.id))
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(current_user: User = Depends(get_current_user)) -> list[TaskOut]:
    tasks = await task_service.list_tasks_for_owner(current_user.id)
    return [_to_out(t) for t in tasks]


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: TaskCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    due_at = request.due_at
    if due_at is not None and due_at.tzinfo is None:
        # Same ambiguity reminder_service/proactive_service already guard against: a naive due_at
        # (no UTC offset - e.g. AIPanel's "Extract tasks" posting the LLM's raw due_at straight
        # here) would otherwise let Postgres/asyncpg interpret it using the DB server's own session
        # timezone, which only happens to match calendar_timezone by coincidence on a given machine
        # (verified: local Postgres here defaults to Asia/Bangkok, not something this app controls) -
        # explicit is correct everywhere, not just on this machine.
        due_at = due_at.replace(tzinfo=ZoneInfo(get_settings().calendar_timezone))

    task = Task(
        owner_id=current_user.id,
        conversation_id=request.conversation_id,
        title=request.title,
        due_at=due_at,
        priority=request.priority,
        source=request.source,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    out = _to_out(task)
    await manager.broadcast_to_users([current_user.id], {"type": "task_created", "task": out.model_dump(mode="json")})
    return out


async def _add_to_calendar_and_reminder(db: AsyncSession, task: Task, owner_id: str) -> None:
    """A proactively-detected task with a due date, once explicitly Accepted, also gets a real
    Google Calendar event and a real Reminder - the Accept click is the human confirmation, so
    neither needs its own interrupt() step. Best-effort: the task itself must stay accepted even
    if Calendar/Reminder creation fails.

    Also links whichever of the two actually got created back onto the Task
    (calendar_event_id/reminder_id), so delete_task can cascade-delete them later, and a Calendar
    event deleted from anywhere (this app, the agent's delete_calendar_event tool, or directly in
    Google Calendar) can find and remove this same Task - see calendar_service.notify_event_deleted."""
    start_iso = task.due_at.isoformat()
    end_iso = (task.due_at + timedelta(minutes=30)).isoformat()
    linked = False
    try:
        event = await calendar_service.create_event(owner_id, summary=task.title, start_iso=start_iso, end_iso=end_iso)
        await calendar_service.broadcast_change(
            owner_id, "calendar_event_created", {"event": calendar_service.to_out_dict(event)}
        )
        task.calendar_event_id = event["id"]
        linked = True
    except CalendarNotConnected:
        logger.info("Skipped auto-create calendar event for task %s - owner hasn't connected Calendar", task.id)
    except Exception:  # noqa: BLE001 - best-effort, must not block the task Accept
        logger.exception("Auto-create calendar event for accepted task %s failed", task.id)

    try:
        reminder = await reminder_service.schedule_reminder(
            owner_id=owner_id, title=task.title, due_at_iso=start_iso, lead_minutes=30, source="proactive"
        )
        task.reminder_id = reminder.id
        linked = True
    except Exception:  # noqa: BLE001 - best-effort, must not block the task Accept
        logger.exception("Auto-create reminder for accepted task %s failed", task.id)

    if linked:
        await db.commit()
        await db.refresh(task)


@router.post("/tasks/{task_id}/accept", response_model=TaskAcceptResponse)
async def accept_task(
    task_id: str,
    request: TaskAcceptRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskAcceptResponse:
    """Accept a suggested task - the endpoint the Accept button in Tasks/Task Inbox calls (in
    place of PATCH .../status, which still exists unchanged for Dismiss/Complete/etc. and for a
    plain accept with no schedule at all - see is_accepting_proactive_schedule below).

    For a proactive task that has (or is being given) a due_at, this checks the owner's Google
    Calendar for a conflict at that time FIRST, same check the agent's create_calendar_event tool
    already does (calendar_tool.py) - a plain status PATCH skipped it entirely, silently
    double-booking. First call (no due_at/force in the body): checks the task's own due_at; a
    conflict is reported back (conflict=true, conflicts, alternatives) WITHOUT changing anything,
    so the caller can re-call this same endpoint to resolve it:
      - due_at set (a picked alternative, or a custom date/time): re-checked at the NEW time; once
        accepted, that time becomes the task's own due_at, so the Calendar event and Reminder
        _add_to_calendar_and_reminder creates next are built from that same single value - task,
        calendar and reminder never disagree on the time.
      - force=true: skip the check and accept at the (possibly already-overridden) time anyway.
    Cancelling instead of resolving is the existing Dismiss action (PATCH .../status
    "dismissed") - not this endpoint.
    """
    task = await _get_own_task_or_404(task_id, current_user, db)
    if task.status != "suggested":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Task is not pending review")

    due_at = request.due_at or task.due_at
    if due_at is not None and due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=ZoneInfo(get_settings().calendar_timezone))

    # Only a proactive task with a schedule ever gets a Calendar event/Reminder auto-created below
    # (is_accepting_proactive_schedule's own condition, mirrored here) - a manual task, or one with
    # no due_at, has nothing that could conflict, so skip straight to accepting it.
    needs_schedule_check = task.source == "proactive" and due_at is not None
    if needs_schedule_check and not request.force:
        start_iso = due_at.isoformat()
        end_iso = (due_at + timedelta(minutes=30)).isoformat()
        try:
            conflicts = await calendar_service.find_conflicts(current_user.id, start_iso, end_iso)
        except CalendarNotConnected:
            conflicts = []
        if conflicts:
            alternatives = await calendar_service.suggest_alternative_slots(current_user.id, start_iso, end_iso)
            return TaskAcceptResponse(
                task=_to_out(task),
                conflict=True,
                conflicts=[calendar_service.to_out_dict(e) for e in conflicts],
                alternatives=alternatives,
            )

    # Conditional UPDATE, not a read-modify-write on the ORM object: a double-click (or two open
    # tabs) firing this endpoint twice for the same task must create at most ONE Calendar event
    # and ONE Reminder, not two - a plain "if task.status == 'suggested': task.status = ...' would
    # let both requests pass the check before either commits. Only the request whose UPDATE
    # actually flips a "suggested" row (rowcount == 1) goes on to create the Calendar
    # event/Reminder; a request that loses the race treats it as already accepted.
    values: dict = {"status": "pending"}
    if due_at is not None:
        values["due_at"] = due_at
    result = await db.execute(
        sa_update(Task).where(Task.id == task.id, Task.status == "suggested").values(**values)
    )
    await db.commit()
    await db.refresh(task)
    out = _to_out(task)
    won_race = result.rowcount == 1
    if won_race:
        await manager.broadcast_to_users([current_user.id], {"type": "task_updated", "task": out.model_dump(mode="json")})
        if needs_schedule_check:
            # out (the TaskOut sent back / already broadcast above) never carries
            # calendar_event_id/reminder_id - those are an internal link, not public API surface -
            # so this doesn't need recomputing after _add_to_calendar_and_reminder sets them.
            await _add_to_calendar_and_reminder(db, task, current_user.id)
    return TaskAcceptResponse(task=out, conflict=False)


@router.patch("/tasks/{task_id}/status", response_model=TaskOut)
async def update_task_status(
    task_id: str,
    request: UpdateTaskStatusRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    task = await _get_own_task_or_404(task_id, current_user, db)
    is_accepting_proactive_schedule = (
        task.status == "suggested"
        and request.status == "pending"
        and task.source == "proactive"
        and task.due_at is not None
    )
    task.status = request.status
    await db.commit()
    await db.refresh(task)
    out = _to_out(task)
    await manager.broadcast_to_users([current_user.id], {"type": "task_updated", "task": out.model_dump(mode="json")})

    if is_accepting_proactive_schedule:
        await _add_to_calendar_and_reminder(db, task, current_user.id)

    return out


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    task = await _get_own_task_or_404(task_id, current_user, db)
    calendar_event_id, reminder_id = task.calendar_event_id, task.reminder_id
    await db.delete(task)
    await db.commit()
    await manager.broadcast_to_users([current_user.id], {"type": "task_deleted", "task_id": task_id})

    # Cascade: an Accepted task may have a real Calendar event + Reminder behind it
    # (_add_to_calendar_and_reminder) - deleting the Task must not leave those orphaned. Best-effort
    # and only AFTER the Task delete above has committed - a Calendar/Reminder failure here must
    # never undo or block the Task delete itself.
    if calendar_event_id:
        try:
            await calendar_service.delete_event(current_user.id, calendar_event_id)
            await calendar_service.broadcast_change(
                current_user.id, "calendar_event_deleted", {"event_id": calendar_event_id}
            )
        except CalendarNotConnected:
            pass
        except Exception:  # noqa: BLE001 - best-effort, the Task is already deleted
            logger.exception("Failed to delete linked Calendar event for task %s", task_id)
    if reminder_id:
        try:
            await reminder_service.cancel_reminder(reminder_id, owner_id=current_user.id)
        except Exception:  # noqa: BLE001 - best-effort, the Task is already deleted
            logger.exception("Failed to cancel linked reminder for task %s", task_id)
