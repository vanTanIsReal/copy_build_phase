from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.config import get_settings
from src.db.models import Conversation, Task, User
from src.db.session import get_db
from src.models.task_schemas import TaskCreateRequest, TaskOut, UpdateTaskStatusRequest
from src.services import consent_service
from src.services.authorization_service import require_conversation_access
from src.services.workspace_service import resolve_workspace_for_user
from src.websocket.manager import manager

router = APIRouter()

_PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}

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
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


async def _get_own_task_or_404(task_id: str, current_user: User, db: AsyncSession) -> Task:
    task = (
        await db.execute(select(Task).where(Task.id == task_id, Task.owner_id == current_user.id))
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
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


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    workspace_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[TaskOut]:
    workspace = await resolve_workspace_for_user(db, current_user.id, workspace_id)
    tasks = (
        await db.execute(
            select(Task)
            .where(Task.owner_id == current_user.id, Task.workspace_id == workspace.id)
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
        if conversation is None or conversation.workspace_id != workspace.id:
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

        existing = (
            await db.execute(
                select(Task).where(
                    Task.owner_id == current_user.id,
                    Task.workspace_id == workspace.id,
                    Task.conversation_id == request.conversation_id,
                    Task.source == "ai_extracted",
                    Task.status == "suggested",
                    Task.title == request.title,
                    Task.consent_scope_hash == request.consent_scope_hash,
                    Task.source_message_ids == request.source_message_ids,
                )
            )
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
    if task.status == "suggested" and request.status in {"pending", "in_progress", "completed"}:
        await _require_current_ai_provenance(task, db)
    task.status = request.status
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
