"""Typed, empty-bodied CRUD tool stubs for CalendarEvent. Sub-agents fill these in."""
from __future__ import annotations

from datetime import datetime

from db.models import CalendarEvent, CalendarEventStatus


def create_event(
    title: str,
    start_time: datetime,
    end_time: datetime,
    description: str | None = None,
    task_id: int | None = None,
    timezone: str = "UTC",
) -> CalendarEvent:
    """Create a local CalendarEvent row only (no Google sync)."""
    raise NotImplementedError


def schedule_event(
    title: str,
    start_time: datetime,
    end_time: datetime,
    description: str | None = None,
    task_id: int | None = None,
    timezone: str = "UTC",
) -> CalendarEvent:
    """Create locally AND push to Google Calendar, storing google_event_id."""
    raise NotImplementedError


def get_event(event_id: int) -> CalendarEvent | None:
    raise NotImplementedError


def list_events(
    start: datetime | None = None, end: datetime | None = None, status: CalendarEventStatus | None = None
) -> list[CalendarEvent]:
    raise NotImplementedError


def propose_reschedule(event_id: int, new_start_time: datetime, new_end_time: datetime, reason: str) -> CalendarEvent:
    """Stage a proposed time and set status=PENDING_CONFIRMATION, awaiting_confirmation=True."""
    raise NotImplementedError


def confirm_reschedule(event_id: int) -> CalendarEvent:
    """Apply proposed_start_time/proposed_end_time, clear awaiting_confirmation."""
    raise NotImplementedError


def reject_reschedule(event_id: int) -> CalendarEvent:
    """Discard the staged proposal, restore prior confirmed state."""
    raise NotImplementedError


def cancel_event(event_id: int) -> CalendarEvent:
    raise NotImplementedError


def sync_from_google(days_ahead: int = 30) -> list[CalendarEvent]:
    """Pull events from Google Calendar into local storage (feeds the priority engine)."""
    raise NotImplementedError
