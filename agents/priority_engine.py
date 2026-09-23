"""Priority Engine: deterministic (NOT LLM-driven) logic deciding whether a
task gets scheduled now or left in the backlog.

Two pure functions, each independently and exhaustively testable:
  - _should_schedule_now: priority + due date -> urgency verdict, no calendar involved
  - find_next_available_slot: pure interval math over a list of busy periods

decide_scheduling combines both into one final decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum

from db.models import Task, TaskPriority


class SchedulingDecision(str, Enum):
    SCHEDULE_NOW = "schedule_now"
    LEAVE_IN_BACKLOG = "leave_in_backlog"
    NEEDS_MANUAL_SCHEDULING = "needs_manual_scheduling"  # urgent, but no free slot found


@dataclass
class SchedulingResult:
    decision: SchedulingDecision
    reason: str
    suggested_start: datetime | None = None
    suggested_end: datetime | None = None


def _should_schedule_now(priority: TaskPriority, due_date: date | None, today: date) -> tuple[bool, str]:
    """Priority/urgency classification only -- no calendar awareness here."""
    if due_date is not None and due_date < today:
        return True, "overdue"

    if due_date is None:
        if priority == TaskPriority.URGENT:
            return True, "urgent priority, no due date"
        return False, "no due date, not urgent enough"

    days_until_due = (due_date - today).days

    if priority == TaskPriority.URGENT:
        return True, "urgent priority"
    if priority == TaskPriority.HIGH and days_until_due <= 3:
        return True, "high priority, due within 3 days"
    if priority == TaskPriority.MEDIUM and days_until_due == 0:
        return True, "medium priority, due today"

    return False, "not urgent enough yet"


def find_next_available_slot(
    busy_periods: list[tuple[datetime, datetime]],
    earliest_start: datetime,
    duration_minutes: int = 60,
    lookahead_days: int = 3,
) -> datetime | None:
    """Find the earliest free slot of the given duration, scanning forward from earliest_start.

    Pure function: takes a plain list of (start, end) busy periods, does no DB/API calls.
    Returns None if nothing fits within lookahead_days.
    """
    duration = timedelta(minutes=duration_minutes)
    search_end = earliest_start + timedelta(days=lookahead_days)
    sorted_busy = sorted(busy_periods)

    candidate = earliest_start
    for busy_start, busy_end in sorted_busy:
        if candidate + duration <= busy_start:
            return candidate  # free gap found before this busy period
        if busy_end > candidate:
            candidate = busy_end  # push candidate past this busy period

    if candidate + duration <= search_end:
        return candidate

    return None


def decide_scheduling(
    task: Task,
    busy_periods: list[tuple[datetime, datetime]],
    now: datetime,
    duration_minutes: int = 60,
) -> SchedulingResult:
    """Combine priority/urgency classification with real calendar availability."""
    should_schedule, reason = _should_schedule_now(task.priority, task.due_date, now.date())

    if not should_schedule:
        return SchedulingResult(decision=SchedulingDecision.LEAVE_IN_BACKLOG, reason=reason)

    slot_start = find_next_available_slot(busy_periods, now, duration_minutes)
    if slot_start is None:
        return SchedulingResult(
            decision=SchedulingDecision.NEEDS_MANUAL_SCHEDULING,
            reason=f"{reason}, but no free slot found in lookahead window",
        )

    return SchedulingResult(
        decision=SchedulingDecision.SCHEDULE_NOW,
        reason=reason,
        suggested_start=slot_start,
        suggested_end=slot_start + timedelta(minutes=duration_minutes),
    )