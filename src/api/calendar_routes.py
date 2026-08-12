from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from src.auth.dependencies import get_current_user
from src.db.models import CalendarSyncState, GoogleCalendarCredential, User
from src.db.session import get_db
from src.models.calendar_schemas import (
    CalendarEventCreateRequest,
    CalendarEventOut,
    CalendarEventUpdateRequest,
    GoogleCalendarConnectionOut,
    GoogleCalendarConnectRequest,
)
from src.services import calendar_service

router = APIRouter()


def _to_out(event: dict) -> CalendarEventOut:
    return CalendarEventOut(**calendar_service.to_out_dict(event))


async def _user_service(user: User, db: AsyncSession):
    credential = await db.get(GoogleCalendarCredential, user.id)
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="Bạn cần kết nối tài khoản Google Calendar trước khi sử dụng tính năng này.",
        )
    try:
        service, refreshed_json = await run_in_threadpool(
            calendar_service.get_calendar_service, credential.credentials_json
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên Google Calendar đã hết hạn. Vui lòng kết nối lại.",
        ) from exc
    if refreshed_json != credential.credentials_json:
        credential.credentials_json = refreshed_json
        await db.commit()
    return service


@router.get("/calendar/connection", response_model=GoogleCalendarConnectionOut)
async def connection_status(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> GoogleCalendarConnectionOut:
    credential = await db.get(GoogleCalendarCredential, current_user.id)
    return GoogleCalendarConnectionOut(
        connected=credential is not None,
        google_email=credential.google_email or None if credential else None,
    )


@router.post("/calendar/connection", response_model=GoogleCalendarConnectionOut)
async def connect_calendar(
    request: GoogleCalendarConnectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GoogleCalendarConnectionOut:
    try:
        credentials = await run_in_threadpool(calendar_service.exchange_authorization_code, request.code)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Không thể kết nối Google Calendar.") from exc

    credential = await db.get(GoogleCalendarCredential, current_user.id)
    if credential is None:
        credential = GoogleCalendarCredential(user_id=current_user.id, credentials_json=credentials.to_json())
        db.add(credential)
    else:
        credential.credentials_json = credentials.to_json()
    await db.commit()
    return GoogleCalendarConnectionOut(connected=True, google_email=credential.google_email or None)


@router.delete("/calendar/connection", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_calendar(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    credential = await db.get(GoogleCalendarCredential, current_user.id)
    if credential is not None:
        await db.delete(credential)
    sync_state = await db.get(CalendarSyncState, current_user.id)
    if sync_state is not None:
        await db.delete(sync_state)
    await db.commit()


@router.get("/calendar/events", response_model=list[CalendarEventOut])
async def list_events(
    time_min: str | None = Query(default=None),
    time_max: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CalendarEventOut]:
    service = await _user_service(current_user, db)
    now = datetime.now(UTC)
    try:
        items = await run_in_threadpool(
            calendar_service.list_events,
            time_min or now.isoformat(),
            time_max or (now + timedelta(days=60)).isoformat(),
            100,
            service=service,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Google Calendar error: {exc}") from exc
    return [_to_out(event) for event in items]


@router.post("/calendar/events", response_model=CalendarEventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    request: CalendarEventCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CalendarEventOut:
    service = await _user_service(current_user, db)
    try:
        created = await run_in_threadpool(
            calendar_service.create_event,
            request.summary,
            request.start_iso,
            request.end_iso,
            request.description,
            request.attendees,
            service=service,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Google Calendar error: {exc}") from exc
    out = _to_out(created)
    await calendar_service.broadcast_change("calendar_event_created", {"event": out.model_dump()}, current_user.id)
    return out


@router.patch("/calendar/events/{event_id}", response_model=CalendarEventOut)
async def update_event(
    event_id: str,
    request: CalendarEventUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CalendarEventOut:
    service = await _user_service(current_user, db)
    try:
        updated = await run_in_threadpool(
            calendar_service.update_event,
            event_id,
            request.summary,
            request.start_iso,
            request.end_iso,
            request.description,
            service=service,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Google Calendar error: {exc}") from exc
    out = _to_out(updated)
    await calendar_service.broadcast_change("calendar_event_updated", {"event": out.model_dump()}, current_user.id)
    return out


@router.delete("/calendar/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = await _user_service(current_user, db)
    try:
        await run_in_threadpool(calendar_service.delete_event, event_id, service=service)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Google Calendar error: {exc}") from exc
    await calendar_service.broadcast_change("calendar_event_deleted", {"event_id": event_id}, current_user.id)
