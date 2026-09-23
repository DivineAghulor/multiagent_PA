"""Natural-language event creation: freeform text -> CalendarEvent.

Design: the LLM only extracts simple fields (title, a clock time, and a date
ONLY if one is explicitly stated). Resolving "which actual day" from a bare
time like '5pm' is done in plain Python (_resolve_datetime), not by the LLM,
so that logic is deterministic and testable without any API calls.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from pydantic import BaseModel, Field

from db.models import CalendarEvent
from llm.factory import get_default_chat_model
from tools.calendar import schedule_event


class ParsedEventFields(BaseModel):
    title: str = Field(description="Short descriptive title for the event")
    start_time: str = Field(description="Start clock time in 24-hour HH:MM format, e.g. '17:00'")
    end_time: str | None = Field(
        default=None, description="End clock time in 24-hour HH:MM format, ONLY if explicitly mentioned"
    )
    duration_minutes: int | None = Field(
        default=None, description="Duration in minutes, ONLY if mentioned instead of an explicit end time"
    )
    explicit_date: str | None = Field(
        default=None,
        description=(
            "Date in YYYY-MM-DD format, ONLY if a specific date/day is explicitly mentioned "
            "in the text (e.g. 'tomorrow', 'next Friday', 'March 3rd'). Null if no date is mentioned."
        ),
    )
    description: str | None = Field(default=None, description="Any additional detail beyond the title")


def _resolve_datetime(parsed: ParsedEventFields, reference_time: datetime) -> tuple[datetime, datetime]:
    """Turn extracted fields + a reference 'now' into concrete start/end datetimes.

    If no explicit date was given: use today if the time hasn't passed yet
    relative to reference_time, otherwise roll forward to tomorrow.
    """
    hour, minute = map(int, parsed.start_time.split(":"))
    start_clock = time(hour=hour, minute=minute)

    if parsed.explicit_date:
        event_date: date = date.fromisoformat(parsed.explicit_date)
    else:
        candidate = datetime.combine(reference_time.date(), start_clock, tzinfo=reference_time.tzinfo)
        event_date = reference_time.date() if candidate > reference_time else reference_time.date() + timedelta(days=1)

    start_dt = datetime.combine(event_date, start_clock, tzinfo=reference_time.tzinfo)

    if parsed.end_time:
        eh, em = map(int, parsed.end_time.split(":"))
        end_dt = datetime.combine(event_date, time(hour=eh, minute=em), tzinfo=reference_time.tzinfo)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)  # e.g. "10pm to 1am" crosses midnight
    elif parsed.duration_minutes:
        end_dt = start_dt + timedelta(minutes=parsed.duration_minutes)
    else:
        end_dt = start_dt + timedelta(hours=1)  # default 1-hour event

    return start_dt, end_dt


def parse_event_text(text: str, reference_time: datetime | None = None) -> ParsedEventFields:
    """Use the LLM to extract structured event fields from freeform text."""
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    llm = get_default_chat_model(temperature=0)
    structured_llm = llm.with_structured_output(ParsedEventFields)

    weekday_name = reference_time.strftime("%A")
    prompt = (
        f"Extract calendar event details from this text: {text!r}\n"
        f"Current date/time for reference: {reference_time.isoformat()} ({weekday_name}).\n"
        "Only set explicit_date if a specific date is actually mentioned in the text "
        "(including relative references like 'tomorrow' or 'next Friday').\n"
        "If you set explicit_date, work out the day-of-week arithmetic carefully step by step: "
        "state which day of the week today is, count forward day by day to the target day, "
        "and double check your final date actually falls on the day of the week the text implies "
        "before answering.\n"
        "If a date is mentioned WITHOUT a year (e.g. 'March 3rd'), assume the reference year first, "
        "then check: has that date already passed relative to the reference date/time above? "
        "If yes, use the following year instead, since people naturally mean a future date."
    )
    return structured_llm.invoke(prompt)


def create_event_from_text(text: str, reference_time: datetime | None = None) -> CalendarEvent:
    """Parse freeform text and create + sync a CalendarEvent from it (end to end)."""
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    parsed = parse_event_text(text, reference_time)
    start_dt, end_dt = _resolve_datetime(parsed, reference_time)

    return schedule_event(
        title=parsed.title,
        start_time=start_dt,
        end_time=end_dt,
        description=parsed.description,
    )