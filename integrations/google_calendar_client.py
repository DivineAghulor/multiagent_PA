"""Thin wrapper around the Google Calendar API v3.

Keeps all raw googleapiclient calls in one place so tools/calendar.py stays
readable, and so unit tests can mock get_calendar_service() instead of
reaching through to real network calls.
"""
from __future__ import annotations

from datetime import datetime

from googleapiclient.discovery import build

from integrations.google_oauth import get_credentials

CALENDAR_ID = "primary"


def get_calendar_service():
    """Build an authenticated Google Calendar API client."""
    creds = get_credentials()
    return build("calendar", "v3", credentials=creds)


def insert_event(
    title: str,
    start_time: datetime,
    end_time: datetime,
    description: str | None = None,
    timezone: str = "UTC",
) -> dict:
    """Create an event on Google Calendar. Returns the created event resource (includes 'id')."""
    service = get_calendar_service()
    body = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_time.isoformat(), "timeZone": timezone},
        "end": {"dateTime": end_time.isoformat(), "timeZone": timezone},
    }
    return service.events().insert(calendarId=CALENDAR_ID, body=body).execute()


def update_event(
    google_event_id: str,
    start_time: datetime,
    end_time: datetime,
    timezone: str = "UTC",
) -> dict:
    """Update an existing event's time on Google Calendar. Returns the updated event resource."""
    service = get_calendar_service()
    body = {
        "start": {"dateTime": start_time.isoformat(), "timeZone": timezone},
        "end": {"dateTime": end_time.isoformat(), "timeZone": timezone},
    }
    return service.events().patch(calendarId=CALENDAR_ID, eventId=google_event_id, body=body).execute()


def delete_event(google_event_id: str) -> None:
    """Delete an event from Google Calendar."""
    service = get_calendar_service()
    service.events().delete(calendarId=CALENDAR_ID, eventId=google_event_id).execute()


def list_google_events(time_min: datetime, time_max: datetime) -> list[dict]:
    """List events from Google Calendar within a time window."""
    service = get_calendar_service()
    result = (
        service.events()
        .list(
            calendarId=CALENDAR_ID,
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return result.get("items", [])