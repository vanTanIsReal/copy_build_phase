from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from langchain_core.tools import tool
from langgraph.types import interrupt

from src.config import get_settings

_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_calendar_service():
    settings = get_settings()
    creds = Credentials.from_authorized_user_file(settings.google_token_path, _SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(settings.google_token_path, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


@tool
async def create_calendar_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
    attendees: list[str] | None = None,
) -> str:
    """Draft a Google Calendar event. Requires the user's explicit confirmation before it is
    actually created.

    Args:
        summary: Event title.
        start_iso: Event start time as an ISO 8601 datetime string.
        end_iso: Event end time as an ISO 8601 datetime string.
        description: Optional event details.
        attendees: Optional list of attendee email addresses.
    """
    draft = {
        "summary": summary,
        "start": start_iso,
        "end": end_iso,
        "description": description,
        "attendees": attendees or [],
    }
    decision = interrupt({"type": "calendar_event", "draft": draft})
    if not decision or not decision.get("approved"):
        return "Calendar event was not created (user declined)."

    draft.update(decision.get("edits") or {})
    settings = get_settings()
    service = _get_calendar_service()
    body = {
        "summary": draft["summary"],
        "description": draft["description"],
        "start": {"dateTime": draft["start"], "timeZone": settings.calendar_timezone},
        "end": {"dateTime": draft["end"], "timeZone": settings.calendar_timezone},
        "attendees": [{"email": a} for a in draft["attendees"]],
    }
    created = service.events().insert(calendarId=settings.google_calendar_id, body=body).execute()
    return f"Event created: {created.get('htmlLink', created.get('id'))}"


@tool
async def list_calendar_events(time_min_iso: str, time_max_iso: str, max_results: int = 10) -> str:
    """List existing calendar events in a time range. Read-only, no confirmation needed.

    Args:
        time_min_iso: Start of the range as an ISO 8601 datetime string.
        time_max_iso: End of the range as an ISO 8601 datetime string.
        max_results: Maximum number of events to return.
    """
    settings = get_settings()
    service = _get_calendar_service()
    resp = (
        service.events()
        .list(
            calendarId=settings.google_calendar_id,
            timeMin=time_min_iso,
            timeMax=time_max_iso,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    items = resp.get("items", [])
    if not items:
        return "No events found in that range."
    return "\n".join(f"- {e.get('summary')} ({e['start'].get('dateTime', e['start'].get('date'))})" for e in items)
