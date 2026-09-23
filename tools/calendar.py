"""CRUD tools for CalendarEvent, wired to the local DB and Google Calendar."""
from __future__ import annotations

from datetime import datetime

from db.models import CalendarEvent, CalendarEventStatus
from db.session import get_session
from integrations.google_calendar_client import (
    delete_event as google_delete_event,
    insert_event as google_insert_event,
    list_google_events,
    update_event as google_update_event,
)


def create_event(
    title: str,
    start_time: datetime,
    end_time: datetime,
    description: str | None = None,
    task_id: int | None = None,
    timezone: str = "UTC",
) -> CalendarEvent:
    """Create a local CalendarEvent row only (no Google sync)."""
    with get_session() as session:
        event = CalendarEvent(
            title=title,
            start_time=start_time,
            end_time=end_time,
            description=description,
            task_id=task_id,
            timezone=timezone,
        )
        session.add(event)
        session.flush()
        session.refresh(event)
        return event


def schedule_event(
    title: str,
    start_time: datetime,
    end_time: datetime,
    description: str | None = None,
    task_id: int | None = None,
    timezone: str = "UTC",
) -> CalendarEvent:
    """Create locally AND push to Google Calendar, storing google_event_id."""
    google_event = google_insert_event(
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=description,
        timezone=timezone,
    )

    with get_session() as session:
        event = CalendarEvent(
            title=title,
            start_time=start_time,
            end_time=end_time,
            description=description,
            task_id=task_id,
            timezone=timezone,
            status=CalendarEventStatus.CONFIRMED,
            google_event_id=google_event["id"],
        )
        session.add(event)
        session.flush()
        session.refresh(event)
        return event


def get_event(event_id: int) -> CalendarEvent | None:
    with get_session() as session:
        return session.get(CalendarEvent, event_id)


def list_events(
    start: datetime | None = None, end: datetime | None = None, status: CalendarEventStatus | None = None
) -> list[CalendarEvent]:
    with get_session() as session:
        query = session.query(CalendarEvent)
        if start is not None:
            query = query.filter(CalendarEvent.start_time >= start)
        if end is not None:
            query = query.filter(CalendarEvent.end_time <= end)
        if status is not None:
            query = query.filter(CalendarEvent.status == status)
        return query.order_by(CalendarEvent.start_time).all()


def propose_reschedule(event_id: int, new_start_time: datetime, new_end_time: datetime, reason: str) -> CalendarEvent:
    """Stage a proposed time and set status=PENDING_CONFIRMATION, awaiting_confirmation=True."""
    with get_session() as session:
        event = session.get(CalendarEvent, event_id)
        if event is None:
            raise ValueError(f"CalendarEvent {event_id} not found")
        event.proposed_start_time = new_start_time
        event.proposed_end_time = new_end_time
        event.reschedule_reason = reason
        event.awaiting_confirmation = True
        event.status = CalendarEventStatus.PENDING_CONFIRMATION
        session.flush()
        session.refresh(event)
        return event


def confirm_reschedule(event_id: int) -> CalendarEvent:
    """Apply proposed_start_time/proposed_end_time, clear awaiting_confirmation."""
    with get_session() as session:
        event = session.get(CalendarEvent, event_id)
        if event is None:
            raise ValueError(f"CalendarEvent {event_id} not found")
        if event.proposed_start_time is None or event.proposed_end_time is None:
            raise ValueError(f"CalendarEvent {event_id} has no staged reschedule to confirm")

        event.start_time = event.proposed_start_time
        event.end_time = event.proposed_end_time
        event.proposed_start_time = None
        event.proposed_end_time = None
        event.reschedule_reason = None
        event.awaiting_confirmation = False
        event.status = CalendarEventStatus.CONFIRMED

        if event.google_event_id:
            google_update_event(
                google_event_id=event.google_event_id,
                start_time=event.start_time,
                end_time=event.end_time,
                timezone=event.timezone,
            )

        session.flush()
        session.refresh(event)
        return event


def reject_reschedule(event_id: int) -> CalendarEvent:
    """Discard the staged proposal, restore prior confirmed state."""
    with get_session() as session:
        event = session.get(CalendarEvent, event_id)
        if event is None:
            raise ValueError(f"CalendarEvent {event_id} not found")
        event.proposed_start_time = None
        event.proposed_end_time = None
        event.reschedule_reason = None
        event.awaiting_confirmation = False
        event.status = CalendarEventStatus.CONFIRMED
        session.flush()
        session.refresh(event)
        return event


def cancel_event(event_id: int) -> CalendarEvent:
    with get_session() as session:
        event = session.get(CalendarEvent, event_id)
        if event is None:
            raise ValueError(f"CalendarEvent {event_id} not found")

        if event.google_event_id:
            google_delete_event(event.google_event_id)

        event.status = CalendarEventStatus.CANCELLED
        session.flush()
        session.refresh(event)
        return event


def sync_from_google(days_ahead: int = 30) -> list[CalendarEvent]:
    """Pull events from Google Calendar into local storage (feeds the priority engine)."""
    from datetime import timedelta, timezone as dt_timezone

    now = datetime.now(dt_timezone.utc)
    window_end = now + timedelta(days=days_ahead)
    google_events = list_google_events(time_min=now, time_max=window_end)

    synced: list[CalendarEvent] = []
    with get_session() as session:
        for g_event in google_events:
            google_event_id = g_event["id"]
            existing = (
                session.query(CalendarEvent)
                .filter(CalendarEvent.google_event_id == google_event_id)
                .one_or_none()
            )

            start_raw = g_event.get("start", {}).get("dateTime")
            end_raw = g_event.get("end", {}).get("dateTime")
            if not start_raw or not end_raw:
                continue  # skip all-day events for now; no time component to store

            start_time = datetime.fromisoformat(start_raw)
            end_time = datetime.fromisoformat(end_raw)
            title = g_event.get("summary", "(untitled)")
            description = g_event.get("description")

            if existing:
                existing.title = title
                existing.description = description
                existing.start_time = start_time
                existing.end_time = end_time
                event = existing
            else:
                event = CalendarEvent(
                    google_event_id=google_event_id,
                    title=title,
                    description=description,
                    start_time=start_time,
                    end_time=end_time,
                    status=CalendarEventStatus.CONFIRMED,
                )
                session.add(event)

            session.flush()
            session.refresh(event)
            synced.append(event)

    return synced