from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.db.models import Task, User
from src.db.session import get_db
from src.models.task_schemas import TaskCreateRequest, TaskOut, UpdateTaskStatusRequest
from src.websocket.manager import manager

router = APIRouter()

_PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}


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
async def list_tasks(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[TaskOut]:
    tasks = (await db.execute(select(Task).where(Task.owner_id == current_user.id))).scalars().all()
    def _sort_key(t: Task) -> tuple[bool, float, int]:
        # .timestamp() sidesteps aware/naive datetime comparison issues (SQLite may round-trip
        # DateTime(timezone=True) values as naive) - fine for a relative sort ordering.
        return (t.due_at is None, t.due_at.timestamp() if t.due_at else 0.0, _PRIORITY_RANK.get(t.priority, 1))

    tasks.sort(key=_sort_key)
    return [_to_out(t) for t in tasks]


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: TaskCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    task = Task(
        owner_id=current_user.id,
        conversation_id=request.conversation_id,
        title=request.title,
        due_at=request.due_at,
        priority=request.priority,
        source=request.source,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    out = _to_out(task)
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
