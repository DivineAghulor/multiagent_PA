"""Unit tests for tools/calendar.py. Google Calendar API calls are mocked;
these tests hit the real local dev database (rows are cleaned up after each test).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from db.models import CalendarEventStatus
from db.session import get_session
import tools.calendar as calendar_tools


@pytest.fixture
def cleanup_events():
    """Track event IDs created during a test and delete them afterward."""
    created_ids: list[int] = []
    yield created_ids
    with get_session() as session:
        from db.models import CalendarEvent

        for event_id in created_ids:
            event = session.get(CalendarEvent, event_id)
            if event is not None:
                session.delete(event)


def _times():
    start = datetime.now(timezone.utc) + timedelta(days=1)
    end = start + timedelta(hours=1)
    return start, end


def test_create_event_local_only(cleanup_events, mocker):
    google_insert = mocker.patch.object(calendar_tools, "google_insert_event")
    start, end = _times()

    event = calendar_tools.create_event(title="Focus block", start_time=start, end_time=end)
    cleanup_events.append(event.id)

    assert event.id is not None
    assert event.title == "Focus block"
    assert event.google_event_id is None
    google_insert.assert_not_called()


def test_schedule_event_pushes_to_google_and_saves_id(cleanup_events, mocker):
    mocker.patch.object(calendar_tools, "google_insert_event", return_value={"id": "gcal-abc123"})
    start, end = _times()

    event = calendar_tools.schedule_event(title="Dentist", start_time=start, end_time=end)
    cleanup_events.append(event.id)

    assert event.google_event_id == "gcal-abc123"
    assert event.status == CalendarEventStatus.CONFIRMED


def test_get_event_returns_none_when_missing():
    assert calendar_tools.get_event(999_999) is None


def test_list_events_filters_by_status(cleanup_events, mocker):
    mocker.patch.object(calendar_tools, "google_insert_event", return_value={"id": "gcal-xyz"})
    start, end = _times()

    local_only = calendar_tools.create_event(title="Local", start_time=start, end_time=end)
    cleanup_events.append(local_only.id)
    synced = calendar_tools.schedule_event(title="Synced", start_time=start, end_time=end)
    cleanup_events.append(synced.id)

    confirmed = calendar_tools.list_events(status=CalendarEventStatus.CONFIRMED)
    assert any(e.id == synced.id for e in confirmed)
    assert not any(e.id == local_only.id for e in confirmed)  # local_only defaults to TENTATIVE


def test_propose_then_confirm_reschedule(cleanup_events, mocker):
    mocker.patch.object(calendar_tools, "google_insert_event", return_value={"id": "gcal-r1"})
    google_update = mocker.patch.object(calendar_tools, "google_update_event")
    start, end = _times()

    event = calendar_tools.schedule_event(title="Standup", start_time=start, end_time=end)
    cleanup_events.append(event.id)

    new_start = start + timedelta(hours=2)
    new_end = end + timedelta(hours=2)
    proposed = calendar_tools.propose_reschedule(event.id, new_start, new_end, reason="conflict")
    assert proposed.awaiting_confirmation is True
    assert proposed.status == CalendarEventStatus.PENDING_CONFIRMATION

    confirmed = calendar_tools.confirm_reschedule(event.id)
    assert confirmed.awaiting_confirmation is False
    assert confirmed.status == CalendarEventStatus.CONFIRMED
    assert confirmed.start_time == new_start
    google_update.assert_called_once()


def test_propose_then_reject_reschedule(cleanup_events, mocker):
    mocker.patch.object(calendar_tools, "google_insert_event", return_value={"id": "gcal-r2"})
    start, end = _times()

    event = calendar_tools.schedule_event(title="1:1", start_time=start, end_time=end)
    cleanup_events.append(event.id)

    calendar_tools.propose_reschedule(event.id, start + timedelta(hours=3), end + timedelta(hours=3), reason="test")
    rejected = calendar_tools.reject_reschedule(event.id)

    assert rejected.awaiting_confirmation is False
    assert rejected.status == CalendarEventStatus.CONFIRMED
    assert rejected.start_time == start  # unchanged


def test_cancel_event_deletes_from_google(cleanup_events, mocker):
    mocker.patch.object(calendar_tools, "google_insert_event", return_value={"id": "gcal-c1"})
    google_delete = mocker.patch.object(calendar_tools, "google_delete_event")
    start, end = _times()

    event = calendar_tools.schedule_event(title="Cancel me", start_time=start, end_time=end)
    cleanup_events.append(event.id)

    cancelled = calendar_tools.cancel_event(event.id)

    assert cancelled.status == CalendarEventStatus.CANCELLED
    google_delete.assert_called_once_with("gcal-c1")


def test_sync_from_google_creates_new_local_events(cleanup_events, mocker):
    start, end = _times()
    fake_google_event = {
        "id": "gcal-sync-1",
        "summary": "Imported meeting",
        "description": "from Google",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    mocker.patch.object(calendar_tools, "list_google_events", return_value=[fake_google_event])

    synced = calendar_tools.sync_from_google(days_ahead=7)
    cleanup_events.extend(e.id for e in synced)

    assert len(synced) == 1
    assert synced[0].google_event_id == "gcal-sync-1"
    assert synced[0].title == "Imported meeting"


def test_sync_from_google_updates_existing_event_on_rerun(cleanup_events, mocker):
    start, end = _times()
    fake_google_event = {
        "id": "gcal-sync-2",
        "summary": "Original title",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    mocker.patch.object(calendar_tools, "list_google_events", return_value=[fake_google_event])
    first_sync = calendar_tools.sync_from_google(days_ahead=7)
    cleanup_events.extend(e.id for e in first_sync)

    fake_google_event["summary"] = "Updated title"
    mocker.patch.object(calendar_tools, "list_google_events", return_value=[fake_google_event])
    second_sync = calendar_tools.sync_from_google(days_ahead=7)

    assert len(second_sync) == 1
    assert second_sync[0].id == first_sync[0].id  # same row, not a duplicate
    assert second_sync[0].title == "Updated title"