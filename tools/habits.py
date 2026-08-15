"""Typed, empty-bodied CRUD tool stubs for Habit/HabitLog. Sub-agents fill these in."""
from __future__ import annotations

from datetime import date

from db.models import Habit, HabitFrequency, HabitLog


def create_habit(
    name: str,
    frequency: HabitFrequency = HabitFrequency.DAILY,
    target_per_period: int = 1,
    description: str | None = None,
) -> Habit:
    raise NotImplementedError


def get_habit(habit_id: int) -> Habit | None:
    raise NotImplementedError


def list_habits(active_only: bool = True) -> list[Habit]:
    raise NotImplementedError


def deactivate_habit(habit_id: int) -> Habit:
    raise NotImplementedError


def log_habit_completion(habit_id: int, on_date: date, note: str | None = None) -> HabitLog:
    raise NotImplementedError


def get_habit_logs(habit_id: int, start: date, end: date) -> list[HabitLog]:
    """Completion logs in a date range, e.g. a weekly review window."""
    raise NotImplementedError
