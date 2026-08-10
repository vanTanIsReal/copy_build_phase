import json
import logging
from datetime import UTC, datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import select

from src.config import get_settings
from src.db import session as db_session
from src.db.models import CalendarSyncState, GoogleCalendarCredential
from src.websocket.manager import manager

logger = logging.getLogger(__name__)
_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def exchange_authorization_code(code: str) -> Credentials:
    settings = get_settings()
    flow = Flow.from_client_secrets_file(settings.google_credentials_path, scopes=_SCOPES)
    flow.redirect_uri = "postmessage"
    flow.fetch_token(code=code)
    return flow.credentials


def get_calendar_service(credentials_json: str):
    creds = Credentials.from_authorized_user_info(json.loads(credentials_json), _SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("calendar", "v3", credentials=creds), creds.to_json()


async def get_user_calendar_service(user_id: str):
    if not user_id:
        raise RuntimeError("Google Calendar requires an authenticated user")
    async with db_session.async_session_maker() as db:
        credential = await db.get(GoogleCalendarCredential, user_id)
        if credential is None:
            raise RuntimeError("Google Calendar is not connected for this user")
        service, refreshed_json = get_calendar_service(credential.credentials_json)
        if refreshed_json != credential.credentials_json:
            credential.credentials_json = refreshed_json
            await db.commit()
        return service


def list_events(time_min_iso: str, time_max_iso: str, max_results: int = 50, *, service) -> list[dict]:
    settings = get_settings()
    response = service.events().list(
        calendarId=settings.google_calendar_id,
        timeMin=time_min_iso,
        timeMax=time_max_iso,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return response.get("items", [])


def create_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
    attendees: list[str] | None = None,
    *,
    service,
) -> dict:
    settings = get_settings()
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso, "timeZone": settings.calendar_timezone},
        "end": {"dateTime": end_iso, "timeZone": settings.calendar_timezone},
        "attendees": [{"email": attendee} for attendee in (attendees or [])],
    }
    return service.events().insert(calendarId=settings.google_calendar_id, body=body).execute()


def update_event(
    event_id: str,
    summary: str | None = None,
    start_iso: str | None = None,
    end_iso: str | None = None,
    description: str | None = None,
    *,
    service,
) -> dict:
    settings = get_settings()
    body: dict = {}
    if summary is not None:
        body["summary"] = summary
    if description is not None:
        body["description"] = description
    if start_iso is not None:
        body["start"] = {"dateTime": start_iso, "timeZone": settings.calendar_timezone}
    if end_iso is not None:
        body["end"] = {"dateTime": end_iso, "timeZone": settings.calendar_timezone}
    return service.events().patch(calendarId=settings.google_calendar_id, eventId=event_id, body=body).execute()


def delete_event(event_id: str, *, service) -> None:
    service.events().delete(calendarId=get_settings().google_calendar_id, eventId=event_id).execute()


async def broadcast_change(event_type: str, payload: dict, user_id: str | None = None) -> None:
    recipients = [user_id] if user_id else list(manager.active.keys())
    await manager.broadcast_to_users(recipients, {"type": event_type, **payload})


def to_out_dict(event: dict) -> dict:
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event["id"],
        "title": event.get("summary", "(No title)"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "url": event.get("htmlLink"),
    }


def _fetch_changes(service, sync_token: str | None) -> tuple[list[dict], str | None]:
    kwargs: dict = {"calendarId": get_settings().google_calendar_id, "singleEvents": True}
    if sync_token:
        kwargs["syncToken"] = sync_token
    else:
        kwargs["timeMin"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    items: list[dict] = []
    page_token = None
    while True:
        response = service.events().list(**kwargs, pageToken=page_token).execute()
        items.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return items, response.get("nextSyncToken")


async def poll_calendar_changes() -> None:
    async with db_session.async_session_maker() as db:
        user_ids = (await db.execute(select(GoogleCalendarCredential.user_id))).scalars().all()
    for user_id in user_ids:
        await _poll_user_calendar(user_id)


async def _poll_user_calendar(user_id: str) -> None:
    async with db_session.async_session_maker() as db:
        credential = await db.get(GoogleCalendarCredential, user_id)
        if credential is None:
            return
        state = await db.get(CalendarSyncState, user_id)
        sync_token = state.sync_token if state else None
        try:
            service, refreshed_json = get_calendar_service(credential.credentials_json)
            if refreshed_json != credential.credentials_json:
                credential.credentials_json = refreshed_json
                await db.commit()
        except Exception:
            logger.exception("Calendar credentials failed for user %s", user_id)
            return

    try:
        items, next_sync_token = _fetch_changes(service, sync_token)
    except HttpError as exc:
        if not sync_token or exc.resp.status != 410:
            logger.exception("Calendar poll failed for user %s", user_id)
            return
        try:
            items, next_sync_token = _fetch_changes(service, None)
        except Exception:
            logger.exception("Calendar full resync failed for user %s", user_id)
            return
    except Exception:
        logger.exception("Calendar poll failed for user %s", user_id)
        return

    for event in items:
        if event.get("status") == "cancelled":
            await broadcast_change("calendar_event_deleted", {"event_id": event["id"]}, user_id)
        else:
            await broadcast_change("calendar_event_updated", {"event": to_out_dict(event)}, user_id)

    async with db_session.async_session_maker() as db:
        state = await db.get(CalendarSyncState, user_id)
        if state is None:
            state = CalendarSyncState(id=user_id)
            db.add(state)
        state.sync_token = next_sync_token
        await db.commit()
