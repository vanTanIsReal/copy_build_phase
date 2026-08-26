import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.config import get_settings
from src.db.models import Conversation, Task, User, Workspace
from src.db.session import get_db
from src.models.task_schemas import TaskCreateRequest, TaskOut, UpdateTaskStatusRequest
from src.services import calendar_service, consent_service, reminder_service
from src.services.authorization_service import require_conversation_access
from src.services.google_credentials import CalendarNotConnectedError
from src.services.workspace_service import resolve_workspace_for_user
from src.websocket.manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()

_PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}
# Task only carries a single due_at, not a start/end range, so an accepted AI suggestion gets a
# fixed-length placeholder event on Google Calendar - same convention as a quick manual add. The
# user can always resize/edit it afterwards from the Calendar page.
_ACCEPTED_TASK_EVENT_DURATION = timedelta(minutes=30)
# Upper bound on how long before an accepted task's due_at its synced Reminder fires - same
# default the manual "New reminder" form and the agent's create_reminder tool both use.
# _reminder_lead_minutes below caps this further when due_at is too soon for the full 30 minutes.
_ACCEPTED_TASK_REMINDER_LEAD_MINUTES = 30

def _to_out(task: Task, *, due_at_override=None) -> TaskOut:
    due_at = due_at_override if due_at_override is not None else task.due_at
    if due_at is not None and due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=ZoneInfo(get_settings().calendar_timezone))
    return TaskOut(
        id=task.id,
        workspace_id=task.workspace_id,
        conversation_id=task.conversation_id,
        title=task.title,
        due_at=due_at,
        priority=task.priority,
        status=task.status,
        source=task.source,
        source_message_ids=task.source_message_ids,
        consent_scope_hash=task.consent_scope_hash,
        invalidated_reason=task.invalidated_reason,
        calendar_event_id=task.calendar_event_id,
        reminder_id=task.reminder_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


async def _get_own_task_or_404(task_id: str, current_user: User, db: AsyncSession) -> Task:
    task = (
        await db.execute(select(Task).where(Task.id == task_id, Task.owner_id == current_user.id))
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    # Same workspace_id caveat as list_tasks below: a task proactively suggested to a participant
    # of a personal-workspace conversation can legitimately carry a *different* participant's
    # personal workspace_id. `owner_id` above already proved this task is this user's own -
    # re-validating workspace membership on top of that only makes sense for an organization
    # workspace, where it's a real multi-tenant boundary. Without this, Accept/Dismiss on a
    # proactively-suggested task raised "Workspace access denied" for its own owner.
    workspace = await db.get(Workspace, task.workspace_id)
    if workspace is not None and workspace.type == "organization":
        await resolve_workspace_for_user(db, current_user.id, task.workspace_id)
    return task


async def _require_current_ai_provenance(task: Task, db: AsyncSession) -> None:
    if task.source not in {"ai_extracted", "proactive"}:
        return
    if (
        task.source == "proactive"
        and task.source_message_ids is None
        and task.consent_scope_hash is None
        and task.source_sender_id is None
    ):
        # Backward compatibility for suggestions created before provenance fields existed.
        # Current proactive_service always writes all three fields, so new records cannot use this path.
        return
    if task.conversation_id is None or not task.source_message_ids or not task.consent_scope_hash:
        task.status = "invalidated"
        task.invalidated_reason = "missing_ai_provenance"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This AI candidate no longer has verifiable source context",
        )

    current_hash = await consent_service.get_consent_scope_hash(db, task.conversation_id)
    sources_allowed = await consent_service.validate_authorized_source_ids(
        db,
        task.conversation_id,
        task.source_message_ids,
    )
    if current_hash != task.consent_scope_hash or not sources_allowed:
        task.status = "invalidated"
        task.invalidated_reason = "source_consent_changed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This AI candidate is stale because its source consent changed",
        )


async def _sync_task_to_calendar(task: Task, current_user: User) -> None:
    """Accepting an AI-suggested task auto-creates the matching Google Calendar event - the
    Accept click itself is the human confirmation this product's human-in-the-loop rule
    requires before writing to Calendar (product decision: Accept = confirm-and-sync, no
    separate dialog). Never blocks Accept though: if the task has no due_at, already has an
    event, the user hasn't connected Google Calendar, or the API call fails, the task is still
    accepted and the failure is only logged.
    """
    if task.source not in {"proactive", "ai_extracted"} or task.due_at is None or task.calendar_event_id:
        return
    due_at = task.due_at
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=ZoneInfo(get_settings().calendar_timezone))
    end_at = due_at + _ACCEPTED_TASK_EVENT_DURATION
    try:
        created = await calendar_service.create_event(
            current_user.id,
            task.title,
            due_at.isoformat(),
            end_at.isoformat(),
            "Automatically synced from an accepted Orbit task suggestion.",
        )
    except CalendarNotConnectedError:
        return
    except Exception:  # noqa: BLE001 - accepting the task must never fail because Calendar did
        logger.exception("Could not auto-sync accepted task %s to Google Calendar", task.id)
        return
    task.calendar_event_id = created.get("id")
    await calendar_service.broadcast_change(
        current_user.id, "calendar_event_created", {"event": calendar_service.to_out_dict(created)}
    )


def _reminder_lead_minutes(due_at) -> int:
    """Cap the default lead time to what's actually left before due_at, so a task due soon (but
    still genuinely in the future) doesn't silently lose its reminder just because a fixed
    30-minute lead would push the notification time itself into the past. Only a due_at that's
    already at or past now falls through unchanged - schedule_reminder still rejects that one, as
    it should.
    """
    due = due_at if due_at.tzinfo else due_at.replace(tzinfo=ZoneInfo(get_settings().calendar_timezone))
    remaining_minutes = (due.astimezone(UTC) - datetime.now(UTC)).total_seconds() / 60
    if remaining_minutes <= 0:
        return _ACCEPTED_TASK_REMINDER_LEAD_MINUTES
    return max(1, min(_ACCEPTED_TASK_REMINDER_LEAD_MINUTES, int(remaining_minutes // 2)))


async def _sync_task_to_reminder(task: Task, current_user: User, db: AsyncSession) -> None:
    """Same "Accept = confirm-and-sync" product decision as _sync_task_to_calendar above, applied
    to Reminders instead: the Accept click is the explicit human confirmation, so the reminder is
    scheduled directly with no separate dialog. Unlike Calendar sync this never depends on a
    connected external account, but it still must never block Accept: a due_at that's already at
    or past now (see _reminder_lead_minutes) raises ValueError, which is only logged.

    Deliberately does NOT reuse task.workspace_id: a proactive/ai_extracted task can legitimately
    carry a different personal workspace_id than the accepting user's own (see list_tasks's
    comment on the same caveat) - GET /reminders filters strictly on owner_id AND workspace_id
    (no personal-workspace exception like list_tasks has), so a reminder saved under the task's
    workspace_id would silently never show up on the accepting user's own Reminders page. Resolve
    the user's own workspace instead, exactly like reminder_routes.create_reminder does.
    """
    if task.source not in {"proactive", "ai_extracted"} or task.due_at is None or task.reminder_id:
        return
    try:
        workspace = await resolve_workspace_for_user(db, current_user.id, None)
        reminder = await reminder_service.schedule_reminder(
            workspace_id=workspace.id,
            owner_id=current_user.id,
            title=task.title,
            due_at_iso=task.due_at,
            lead_minutes=_reminder_lead_minutes(task.due_at),
            message="Automatically scheduled from an accepted Orbit task suggestion.",
            source="proactive",
        )
    except ValueError:
        logger.info("Skipped reminder sync for task %s: due_at too close to now", task.id)
        return
    except Exception:  # noqa: BLE001 - accepting the task must never fail because this did
        logger.exception("Could not auto-sync accepted task %s to a Reminder", task.id)
        return
    task.reminder_id = reminder.id


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    workspace_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[TaskOut]:
    workspace = await resolve_workspace_for_user(db, current_user.id, workspace_id)
    # Same reasoning as create_task below and src/api/routes.py's /chat handler: a task the
    # proactive detector suggests to a participant of a personal-workspace direct/group
    # conversation gets workspace_id = conversation.workspace_id, anchored to whichever
    # participant's personal workspace created the conversation first - which is legitimately a
    # *different* personal workspace than this owner's own. Requiring an exact match here silently
    # hid every such task from its own owner's Task list. Only enforce the match for an
    # organization workspace, where it's a real multi-tenant boundary; a personal workspace's
    # boundary is ownership itself (Task.owner_id), not which conversation happened to spawn it.
    filters = [Task.owner_id == current_user.id]
    if workspace.type == "organization":
        filters.append(Task.workspace_id == workspace.id)
    tasks = (
        await db.execute(
            select(Task)
            .where(*filters)
            .order_by(
                Task.due_at.is_(None),
                Task.due_at.asc(),
                case((Task.priority == "High", 0), (Task.priority == "Medium", 1), else_=2),
                Task.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return [_to_out(t) for t in tasks]


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: TaskCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    workspace = await resolve_workspace_for_user(db, current_user.id, request.workspace_id)
    if request.conversation_id is not None:
        await require_conversation_access(db, current_user, request.conversation_id, "viewer")
        conversation = await db.get(Conversation, request.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        # Same reasoning as src/api/routes.py's /chat handler: a personal-workspace direct/group
        # conversation is anchored to whichever participant's personal workspace created it first
        # (see chat_service.get_or_create_direct_conversation) - the OTHER participant's own
        # resolved `workspace` here is legitimately a different personal workspace. Only reject
        # the mismatch when it would actually matter, i.e. an organization workspace.
        if conversation.workspace_id != workspace.id and workspace.type == "organization":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="conversation_id does not belong to the selected workspace",
            )
    if request.source == "ai_extracted":
        if (
            request.conversation_id is None
            or not request.source_message_ids
            or not request.consent_scope_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="AI-extracted candidates require conversation provenance and a consent snapshot",
            )
        current_hash = await consent_service.get_consent_scope_hash(db, request.conversation_id)
        if current_hash != request.consent_scope_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Conversation AI consent changed; extract the candidate again",
            )
        if not await consent_service.validate_authorized_source_ids(
            db, request.conversation_id, request.source_message_ids
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Candidate provenance includes a message that AI is not allowed to process",
            )

        # Same workspace_id caveat as list_tasks above - this idempotency lookup must find the
        # candidate by ownership, not by matching the caller's own resolved workspace, or a
        # personal-workspace participant retrying this call would never see their own earlier
        # candidate and would create a duplicate every time instead of returning the existing one.
        dedup_filters = [
            Task.owner_id == current_user.id,
            Task.conversation_id == request.conversation_id,
            Task.source == "ai_extracted",
            Task.status == "suggested",
            Task.title == request.title,
            Task.consent_scope_hash == request.consent_scope_hash,
            Task.source_message_ids == request.source_message_ids,
        ]
        if workspace.type == "organization":
            dedup_filters.append(Task.workspace_id == workspace.id)
        existing = (
            await db.execute(select(Task).where(*dedup_filters))
        ).scalar_one_or_none()
        if existing is not None:
            return _to_out(existing)
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
        workspace_id=workspace.id,
        owner_id=current_user.id,
        conversation_id=request.conversation_id,
        title=request.title,
        due_at=due_at,
        priority=request.priority,
        status="pending" if request.source == "manual" else "suggested",
        source=request.source,
        source_message_ids=request.source_message_ids if request.source == "ai_extracted" else None,
        consent_scope_hash=request.consent_scope_hash if request.source == "ai_extracted" else None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    out = _to_out(task, due_at_override=due_at)
    await manager.broadcast_to_users([current_user.id], {"type": "task_created", "task": out.model_dump(mode="json")})
    return out


@router.patch("/tasks/{task_id}/status", response_model=TaskOut)
async def update_task_status(
    task_id: str,
    request: UpdateTaskStatusRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    task = await _get_own_task_or_404(task_id, current_user, db)
    if task.status == "invalidated":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This AI candidate is no longer valid because its source consent changed",
        )
    # "Accept" is specifically suggested -> pending (see TaskPage.jsx/TaskInboxPage.jsx accept()) -
    # that's the explicit human confirmation that should trigger the Calendar auto-sync below.
    is_accept = task.status == "suggested" and request.status == "pending"
    if task.status == "suggested" and request.status in {"pending", "in_progress", "completed"}:
        await _require_current_ai_provenance(task, db)
    task.status = request.status
    if is_accept:
        await _sync_task_to_calendar(task, current_user)
        await _sync_task_to_reminder(task, current_user, db)
    await db.commit()
    await db.refresh(task)
    out = _to_out(task)
    await manager.broadcast_to_users([current_user.id], {"type": "task_updated", "task": out.model_dump(mode="json")})

    return out


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    task = await _get_own_task_or_404(task_id, current_user, db)
    await db.delete(task)
    await db.commit()
    await manager.broadcast_to_users([current_user.id], {"type": "task_deleted", "task_id": task_id})
