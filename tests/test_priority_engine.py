"""Exhaustive unit tests for the Priority Engine. Everything here is pure
logic -- no DB, no API, no mocking needed at all.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from agents.priority_engine import (
    SchedulingDecision,
    _should_schedule_now,
    decide_scheduling,
    find_next_available_slot,
)
from db.models import Task, TaskPriority


TODAY = date(2026, 8, 18)


# --- _should_schedule_now: every priority x due-date combination -----------

@pytest.mark.parametrize("priority", list(TaskPriority))
def test_overdue_always_schedules_regardless_of_priority(priority):
    overdue_date = TODAY - timedelta(days=1)
    should, reason = _should_schedule_now(priority, overdue_date, TODAY)
    assert should is True
    assert reason == "overdue"


def test_no_due_date_urgent_schedules_now():
    should, _ = _should_schedule_now(TaskPriority.URGENT, None, TODAY)
    assert should is True


@pytest.mark.parametrize("priority", [TaskPriority.LOW, TaskPriority.MEDIUM, TaskPriority.HIGH])
def test_no_due_date_non_urgent_stays_in_backlog(priority):
    should, _ = _should_schedule_now(priority, None, TODAY)
    assert should is False


def test_urgent_with_future_due_date_schedules_now():
    should, _ = _should_schedule_now(TaskPriority.URGENT, TODAY + timedelta(days=30), TODAY)
    assert should is True


def test_high_priority_due_within_3_days_schedules_now():
    should, _ = _should_schedule_now(TaskPriority.HIGH, TODAY + timedelta(days=3), TODAY)
    assert should is True


def test_high_priority_due_in_4_days_stays_in_backlog():
    should, _ = _should_schedule_now(TaskPriority.HIGH, TODAY + timedelta(days=4), TODAY)
    assert should is False


def test_medium_priority_due_today_schedules_now():
    should, _ = _should_schedule_now(TaskPriority.MEDIUM, TODAY, TODAY)
    assert should is True


def test_medium_priority_due_tomorrow_stays_in_backlog():
    should, _ = _should_schedule_now(TaskPriority.MEDIUM, TODAY + timedelta(days=1), TODAY)
    assert should is False


def test_low_priority_due_today_stays_in_backlog():
    should, _ = _should_schedule_now(TaskPriority.LOW, TODAY, TODAY)
    assert should is False


# --- find_next_available_slot: interval math --------------------------------

def test_finds_slot_with_no_busy_periods():
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    slot = find_next_available_slot([], now, duration_minutes=60)
    assert slot == now


def test_finds_gap_between_two_busy_periods():
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    busy = [
        (now, now + timedelta(hours=1)),  # 9-10am busy
        (now + timedelta(hours=2), now + timedelta(hours=3)),  # 11am-12pm busy
    ]
    slot = find_next_available_slot(busy, now, duration_minutes=60)
    assert slot == now + timedelta(hours=1)  # 10-11am gap fits


def test_skips_gap_too_small_for_duration():
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    busy = [
        (now, now + timedelta(hours=1)),  # 9-10am busy
        (now + timedelta(hours=1, minutes=15), now + timedelta(hours=2)),  # 10:15-11am busy
    ]
    # only a 15-minute gap exists between the two busy periods; need 60 minutes
    slot = find_next_available_slot(busy, now, duration_minutes=60)
    assert slot == now + timedelta(hours=2)  # pushed past both


def test_returns_none_when_fully_booked_within_lookahead():
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    busy = [(now, now + timedelta(days=5))]  # busy for the entire lookahead window and beyond
    slot = find_next_available_slot(busy, now, duration_minutes=60, lookahead_days=3)
    assert slot is None


def test_unsorted_busy_periods_still_work():
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    busy = [
        (now + timedelta(hours=2), now + timedelta(hours=3)),  # given out of order
        (now, now + timedelta(hours=1)),
    ]
    slot = find_next_available_slot(busy, now, duration_minutes=60)
    assert slot == now + timedelta(hours=1)


# --- decide_scheduling: full integration of both pieces ---------------------

def _make_task(priority: TaskPriority, due_date: date | None) -> Task:
    return Task(title="Test task", priority=priority, due_date=due_date)


def test_decide_scheduling_backlog_when_not_urgent():
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    task = _make_task(TaskPriority.LOW, due_date=None)
    result = decide_scheduling(task, busy_periods=[], now=now)
    assert result.decision == SchedulingDecision.LEAVE_IN_BACKLOG
    assert result.suggested_start is None


def test_decide_scheduling_schedules_now_with_free_slot():
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    task = _make_task(TaskPriority.URGENT, due_date=None)
    result = decide_scheduling(task, busy_periods=[], now=now)
    assert result.decision == SchedulingDecision.SCHEDULE_NOW
    assert result.suggested_start == now
    assert result.suggested_end == now + timedelta(hours=1)


def test_decide_scheduling_needs_manual_when_urgent_but_no_slot():
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    task = _make_task(TaskPriority.URGENT, due_date=None)
    fully_booked = [(now, now + timedelta(days=5))]
    result = decide_scheduling(task, busy_periods=fully_booked, now=now)
    assert result.decision == SchedulingDecision.NEEDS_MANUAL_SCHEDULING
    assert result.suggested_start is None