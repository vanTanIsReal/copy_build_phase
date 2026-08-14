from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.rate_limit import crud_rate_limit
from src.auth.dependencies import require_admin
from src.config import get_settings
from src.db.models import (
    AIPermission,
    AuditLog,
    Conversation,
    GoogleCalendarCredential,
    Memory,
    Message,
    Reminder,
    SystemConfig,
    Task,
    User,
)
from src.db.session import get_db
from src.models.admin_schemas import (
    AdminAIManagement,
    AdminAIUsageReport,
    AdminAuditLogOut,
    AdminAuditLogPage,
    AdminConversationOut,
    AdminMemoryOut,
    AdminMessageOut,
    AdminReminderOut,
    AdminStats,
    AdminSystemHealth,
    AdminTaskOut,
    AdminUserOut,
    UpdateAIConfigurationRequest,
    UpdateBudgetRequest,
    UpdateRoleRequest,
    UpdateStatusRequest,
)
from src.services import ai_config_service, reminder_service, usage_service
from src.services.audit_service import record_audit_event
from src.services.scheduler import scheduler
from src.websocket.manager import manager

router = APIRouter(dependencies=[Depends(require_admin), Depends(crud_rate_limit)])


async def _get_user_or_404(user_id: str, db: AsyncSession) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _conversation_label(conversation: Conversation | None) -> str | None:
    if conversation is None:
        return None
    return conversation.name or ("Direct message" if conversation.type == "direct" else "Group chat")


@router.get("/stats", response_model=AdminStats)
async def get_stats(db: AsyncSession = Depends(get_db)) -> AdminStats:
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    total_conversations = (await db.execute(select(func.count()).select_from(Conversation))).scalar_one()
    total_messages = (await db.execute(select(func.count()).select_from(Message))).scalar_one()
    since = datetime.now(UTC) - timedelta(days=7)
    new_users = (
        await db.execute(select(func.count()).select_from(User).where(User.created_at >= since))
    ).scalar_one()

    budget = await usage_service.get_daily_token_budget()
    usage = await usage_service.get_usage_today()
    budget_used_pct = round(usage["total_tokens"] / budget * 100, 1) if budget else 0.0

    return AdminStats(
        total_users=total_users,
        total_conversations=total_conversations,
        total_messages=total_messages,
        new_users_last_7_days=new_users,
        tokens_used_today=usage["total_tokens"],
        prompt_tokens_today=usage["prompt_tokens"],
        completion_tokens_today=usage["completion_tokens"],
        requests_today=usage["request_count"],
        estimated_cost_usd_today=usage["estimated_cost_usd"],
        unpriced_tokens_today=usage["unpriced_tokens"],
        daily_token_budget=budget,
        budget_used_pct=budget_used_pct,
    )


@router.get("/system-health", response_model=AdminSystemHealth)
async def get_system_health(db: AsyncSession = Depends(get_db)) -> AdminSystemHealth:
    settings = get_settings()
    components: list[dict[str, str]] = []

    try:
        await db.execute(select(1))
        dialect = db.get_bind().dialect.name
        components.append({"key": "database", "label": "Database", "status": "operational", "detail": f"{dialect} connected"})
    except Exception:  # noqa: BLE001 - health response must describe a failed dependency, not crash
        components.append({"key": "database", "label": "Database", "status": "down", "detail": "Connection failed"})

    scheduler_running = scheduler.running
    scheduler_jobs = len(scheduler.get_jobs()) if scheduler_running else 0
    components.append({
        "key": "scheduler",
        "label": "Scheduler",
        "status": "operational" if scheduler_running else "degraded",
        "detail": f"Running with {scheduler_jobs} jobs" if scheduler_running else "Not running",
    })

    active_connections = sum(len(connections) for connections in manager.active.values())
    components.append({
        "key": "websocket",
        "label": "WebSocket",
        "status": "operational",
        "detail": f"{active_connections} active connections across {len(manager.active)} users",
    })

    provider_keys = {"google": settings.google_api_key, "groq": settings.groq_api_key, "openai": settings.openai_api_key}
    llm_configured = bool(provider_keys[settings.llm_provider])
    components.append({
        "key": "llm",
        "label": "LLM provider",
        "status": "operational" if llm_configured else "degraded",
        "detail": f"{settings.llm_provider} / {settings.model_name}" if llm_configured else f"{settings.llm_provider} credential missing",
    })

    calendar_configured = all((
        settings.google_calendar_client_id, settings.google_calendar_client_secret, settings.credential_encryption_key,
    ))
    connected_calendars = (await db.execute(select(func.count()).select_from(GoogleCalendarCredential))).scalar_one()
    components.append({
        "key": "calendar",
        "label": "Google Calendar",
        "status": "operational" if calendar_configured else "degraded",
        "detail": f"Configured; {connected_calendars} connected accounts" if calendar_configured else "OAuth integration not fully configured",
    })

    statuses = {component["status"] for component in components}
    overall_status = "down" if "down" in statuses else "degraded" if "degraded" in statuses else "operational"
    return AdminSystemHealth(overall_status=overall_status, checked_at=datetime.now(UTC), components=components)


@router.get("/ai-management", response_model=AdminAIManagement)
async def get_ai_management(db: AsyncSession = Depends(get_db)) -> AdminAIManagement:
    settings = get_settings()
    provider_keys = {"google": settings.google_api_key, "groq": settings.groq_api_key, "openai": settings.openai_api_key}
    granted_permissions = (
        await db.execute(select(func.count()).select_from(AIPermission).where(AIPermission.granted.is_(True)))
    ).scalar_one()
    revoked_permissions = (
        await db.execute(select(func.count()).select_from(AIPermission).where(AIPermission.granted.is_(False)))
    ).scalar_one()
    proactive_suggestions = (
        await db.execute(select(func.count()).select_from(Task).where(Task.source == "proactive"))
    ).scalar_one()
    proactive_accepted = (
        await db.execute(
            select(func.count()).select_from(Task).where(
                Task.source == "proactive", Task.status.in_(("pending", "in_progress", "completed"))
            )
        )
    ).scalar_one()
    proactive_dismissed = (
        await db.execute(
            select(func.count()).select_from(Task).where(Task.source == "proactive", Task.status == "dismissed")
        )
    ).scalar_one()
    return AdminAIManagement(
        provider=settings.llm_provider,
        model=settings.model_name,
        temperature=settings.llm_temperature,
        daily_token_budget=await usage_service.get_daily_token_budget(),
        llm_configured=bool(provider_keys[settings.llm_provider]),
        human_confirmation_required=True,
        conversation_consent_required=True,
        granted_permissions=granted_permissions,
        revoked_permissions=revoked_permissions,
        proactive_suggestions=proactive_suggestions,
        proactive_accepted=proactive_accepted,
        proactive_dismissed=proactive_dismissed,
        configured_providers=ai_config_service.configured_providers(),
        model_options=ai_config_service.MODEL_OPTIONS,
    )


@router.patch("/ai-management", response_model=AdminAIManagement)
async def update_ai_management(
    request: UpdateAIConfigurationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> AdminAIManagement:
    if request.provider not in ai_config_service.configured_providers():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"API key for {request.provider} is not configured"
        )
    if not ai_config_service.is_supported_model(request.provider, request.model):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported model for the selected provider")

    settings = get_settings()
    previous = {"provider": settings.llm_provider, "model": settings.model_name, "temperature": settings.llm_temperature}
    current = {"provider": request.provider, "model": request.model, "temperature": request.temperature}

    config = await db.get(SystemConfig, "default")
    if config is None:
        config = SystemConfig(id="default")
        db.add(config)
    config.llm_provider = request.provider
    config.model_name = request.model
    config.llm_temperature = request.temperature
    config.updated_by = current_user.id
    await record_audit_event(
        db,
        actor=current_user,
        action="platform.ai_model_changed",
        target_type="ai_configuration",
        target_id=request.model,
        metadata={"previous": previous, "current": current},
    )
    await db.commit()
    ai_config_service.apply_ai_configuration(request.provider, request.model, request.temperature)
    return await get_ai_management(db)


@router.get("/ai-usage", response_model=AdminAIUsageReport)
async def get_ai_usage(days: int = Query(default=7, ge=1, le=30)) -> AdminAIUsageReport:
    return AdminAIUsageReport.model_validate(await usage_service.get_usage_report(days))


@router.get("/audit-log", response_model=AdminAuditLogPage)
async def list_audit_log(
    q: str | None = None,
    actor_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AdminAuditLogPage:
    stmt = select(AuditLog, User).outerjoin(User, User.id == AuditLog.actor_user_id)
    conditions = []
    if q:
        pattern = f"%{q}%"
        conditions.append(
            AuditLog.action.ilike(pattern) | AuditLog.target_type.ilike(pattern)
            | AuditLog.target_id.ilike(pattern) | User.email.ilike(pattern)
        )
    if actor_type:
        conditions.append(AuditLog.actor_type == actor_type)
    if conditions:
        stmt = stmt.where(*conditions)

    total = (await db.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit))).all()
    return AdminAuditLogPage(
        total=total,
        items=[
            AdminAuditLogOut(
                id=record.id,
                actor_user_id=record.actor_user_id,
                actor_email=actor.email if actor else None,
                actor_display_name=actor.display_name if actor else None,
                actor_type=record.actor_type,
                action=record.action,
                target_type=record.target_type,
                target_id=record.target_id,
                metadata=record.metadata_json,
                created_at=record.created_at,
            )
            for record, actor in rows
        ],
    )


@router.patch("/settings/budget", response_model=AdminStats)
async def update_daily_token_budget(
    request: UpdateBudgetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> AdminStats:
    """Runtime override for Settings.daily_token_budget (the .env value) - previously the only way
    to raise the budget was editing .env + restarting the server, which the in-app error message
    ("liên hệ admin để tăng hạn mức") implied an admin could just do from here. Takes effect
    immediately for the next usage_service.is_over_budget()/_maybe_alert_budget() check, no restart."""
    await usage_service.set_daily_token_budget(request.daily_token_budget, updated_by=current_user.id)
    await record_audit_event(
        db,
        actor=current_user,
        action="platform.budget_changed",
        target_type="system_config",
        target_id=None,
        metadata={"daily_token_budget": request.daily_token_budget},
    )
    await db.commit()
    return await get_stats(db=db)


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(q: str | None = None, db: AsyncSession = Depends(get_db)) -> list[AdminUserOut]:
    stmt = select(User).order_by(User.created_at.desc())
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where((User.email.ilike(pattern)) | (User.display_name.ilike(pattern)))
    users = (await db.execute(stmt)).scalars().all()
    return [AdminUserOut.model_validate(u, from_attributes=True) for u in users]


@router.patch("/users/{user_id}/role", response_model=AdminUserOut)
async def update_user_role(
    user_id: str,
    request: UpdateRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> AdminUserOut:
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change your own role")
    user = await _get_user_or_404(user_id, db)
    previous_role = user.role
    user.role = request.role
    await record_audit_event(
        db,
        actor=current_user,
        action="user.role_changed",
        target_type="user",
        target_id=user.id,
        metadata={"previous": previous_role, "current": request.role},
    )
    await db.commit()
    await db.refresh(user)
    return AdminUserOut.model_validate(user, from_attributes=True)


@router.patch("/users/{user_id}/status", response_model=AdminUserOut)
async def update_user_status(
    user_id: str,
    request: UpdateStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> AdminUserOut:
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change your own status")
    user = await _get_user_or_404(user_id, db)
    user.is_active = request.is_active
    await record_audit_event(
        db,
        actor=current_user,
        action="user.status_changed",
        target_type="user",
        target_id=user.id,
        metadata={"is_active": request.is_active},
    )
    await db.commit()
    await db.refresh(user)
    return AdminUserOut.model_validate(user, from_attributes=True)


@router.get("/conversations", response_model=list[AdminConversationOut])
async def list_conversations(db: AsyncSession = Depends(get_db)) -> list[AdminConversationOut]:
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.participants), selectinload(Conversation.messages))
        .order_by(Conversation.updated_at.desc())
    )
    conversations = (await db.execute(stmt)).scalars().all()
    return [
        AdminConversationOut(
            id=c.id,
            type=c.type,
            name=c.name,
            created_by=c.created_by,
            created_at=c.created_at,
            participant_count=len(c.participants),
            message_count=len(c.messages),
        )
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}/messages", response_model=list[AdminMessageOut])
async def get_conversation_messages(
    conversation_id: str, db: AsyncSession = Depends(get_db)
) -> list[AdminMessageOut]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .options(selectinload(Message.sender))
        .order_by(Message.created_at.asc())
    )
    messages = (await db.execute(stmt)).scalars().all()
    return [
        AdminMessageOut(
            id=m.id,
            sender_id=m.sender_id,
            sender_display_name=m.sender.display_name,
            content=m.content,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> None:
    conversation = (
        await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    await record_audit_event(
        db, actor=current_user, action="conversation.deleted", target_type="conversation", target_id=conversation.id
    )
    await db.delete(conversation)
    await db.commit()


@router.get("/tasks", response_model=list[AdminTaskOut])
async def list_all_tasks(owner_id: str | None = None, db: AsyncSession = Depends(get_db)) -> list[AdminTaskOut]:
    stmt = (
        select(Task)
        .options(selectinload(Task.owner), selectinload(Task.conversation))
        .order_by(Task.created_at.desc())
    )
    if owner_id:
        stmt = stmt.where(Task.owner_id == owner_id)
    tasks = (await db.execute(stmt)).scalars().all()
    return [
        AdminTaskOut(
            id=t.id,
            conversation_id=t.conversation_id,
            title=t.title,
            due_at=t.due_at,
            priority=t.priority,
            status=t.status,
            source=t.source,
            created_at=t.created_at,
            owner_id=t.owner_id,
            owner_email=t.owner.email,
            owner_display_name=t.owner.display_name,
            conversation_label=_conversation_label(t.conversation),
        )
        for t in tasks
    ]


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_admin(
    task_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
) -> None:
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    await record_audit_event(db, actor=current_user, action="task.deleted", target_type="task", target_id=task.id)
    await db.delete(task)
    await db.commit()


@router.get("/reminders", response_model=list[AdminReminderOut])
async def list_all_reminders(
    owner_id: str | None = None, db: AsyncSession = Depends(get_db)
) -> list[AdminReminderOut]:
    stmt = select(Reminder).options(selectinload(Reminder.owner)).order_by(Reminder.created_at.desc())
    if owner_id:
        stmt = stmt.where(Reminder.owner_id == owner_id)
    reminders = (await db.execute(stmt)).scalars().all()
    return [
        AdminReminderOut(
            id=r.id,
            title=r.title,
            message=r.message,
            due_at=r.due_at,
            fire_at=r.fire_at,
            status=r.status,
            source=r.source,
            created_at=r.created_at,
            owner_id=r.owner_id,
            owner_email=r.owner.email if r.owner else None,
            owner_display_name=r.owner.display_name if r.owner else None,
        )
        for r in reminders
    ]


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder_admin(
    reminder_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
) -> None:
    deleted = await reminder_service.admin_delete_reminder(reminder_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")
    await record_audit_event(
        db, actor=current_user, action="reminder.deleted", target_type="reminder", target_id=reminder_id
    )
    await db.commit()


@router.get("/memories", response_model=list[AdminMemoryOut])
async def list_all_memories(owner_id: str | None = None, db: AsyncSession = Depends(get_db)) -> list[AdminMemoryOut]:
    stmt = select(Memory).options(selectinload(Memory.owner)).order_by(Memory.created_at.desc())
    if owner_id:
        stmt = stmt.where(Memory.owner_id == owner_id)
    memories = (await db.execute(stmt)).scalars().all()
    return [
        AdminMemoryOut(
            id=m.id,
            category=m.category,
            title=m.title,
            detail=m.detail,
            created_at=m.created_at,
            owner_id=m.owner_id,
            owner_email=m.owner.email,
            owner_display_name=m.owner.display_name,
        )
        for m in memories
    ]


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_admin(
    memory_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
) -> None:
    memory = (await db.execute(select(Memory).where(Memory.id == memory_id))).scalar_one_or_none()
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    await record_audit_event(db, actor=current_user, action="memory.deleted", target_type="memory", target_id=memory.id)
    await db.delete(memory)
    await db.commit()
