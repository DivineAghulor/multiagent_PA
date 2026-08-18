"""Unit tests for agents/calendar_nlp.py.

_resolve_datetime is pure logic tested directly with no mocking.
Functions that call the LLM (parse_event_text, create_event_from_text)
have the LLM mocked -- never call a real provider in tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agents.calendar_nlp import ParsedEventFields, _resolve_datetime, create_event_from_text, parse_event_text
from db.session import get_session


# --- _resolve_datetime: pure logic, no LLM involved ------------------------

def test_resolve_time_later_today_stays_today():
    reference = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)  # 9am
    parsed = ParsedEventFields(title="Dinner", start_time="17:00")

    start, end = _resolve_datetime(parsed, reference)

    assert start.date() == reference.date()
    assert start.hour == 17
    assert end == start + timedelta(hours=1)  # default 1hr duration


def test_resolve_time_already_passed_rolls_to_tomorrow():
    reference = datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc)  # 8pm
    parsed = ParsedEventFields(title="Dinner", start_time="17:00")  # 5pm already passed

    start, _ = _resolve_datetime(parsed, reference)

    assert start.date() == reference.date() + timedelta(days=1)
    assert start.hour == 17


def test_resolve_explicit_date_overrides_rollover_logic():
    reference = datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc)
    parsed = ParsedEventFields(title="Dinner", start_time="17:00", explicit_date="2026-08-25")

    start, _ = _resolve_datetime(parsed, reference)

    assert start.date().isoformat() == "2026-08-25"


def test_resolve_explicit_end_time():
    reference = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    parsed = ParsedEventFields(title="Meeting", start_time="14:00", end_time="15:30")

    start, end = _resolve_datetime(parsed, reference)

    assert start.hour == 14
    assert end.hour == 15 and end.minute == 30


def test_resolve_duration_minutes():
    reference = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    parsed = ParsedEventFields(title="Call", start_time="10:00", duration_minutes=45)

    start, end = _resolve_datetime(parsed, reference)

    assert end == start + timedelta(minutes=45)


def test_resolve_end_time_crossing_midnight():
    reference = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    parsed = ParsedEventFields(title="Late show", start_time="22:00", end_time="01:00")

    start, end = _resolve_datetime(parsed, reference)

    assert end.date() == start.date() + timedelta(days=1)
    assert end.hour == 1


# --- parse_event_text: LLM mocked ------------------------------------------

def test_parse_event_text_uses_structured_output(mocker):
    fake_parsed = ParsedEventFields(title="Dinner", start_time="17:00")
    mock_structured_llm = mocker.Mock()
    mock_structured_llm.invoke.return_value = fake_parsed

    mock_llm = mocker.Mock()
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mocker.patch("agents.calendar_nlp.get_default_chat_model", return_value=mock_llm)

    result = parse_event_text("Dinner at 5pm")

    assert result == fake_parsed
    mock_llm.with_structured_output.assert_called_once_with(ParsedEventFields)
    mock_structured_llm.invoke.assert_called_once()


# --- create_event_from_text: LLM mocked, hits real local DB ----------------

@pytest.fixture
def cleanup_events():
    created_ids: list[int] = []
    yield created_ids
    with get_session() as session:
        from db.models import CalendarEvent

        for event_id in created_ids:
            event = session.get(CalendarEvent, event_id)
            if event is not None:
                session.delete(event)


def test_create_event_from_text_end_to_end(cleanup_events, mocker):
    reference = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    fake_parsed = ParsedEventFields(title="Dinner", start_time="17:00")

    mocker.patch("agents.calendar_nlp.parse_event_text", return_value=fake_parsed)
    # schedule_event is imported into calendar_nlp's namespace, so patch it there
    mocker.patch("agents.calendar_nlp.schedule_event", side_effect=lambda **kw: kw)

    result = create_event_from_text("Dinner at 5pm", reference_time=reference)

    assert result["title"] == "Dinner"
    assert result["start_time"].hour == 17