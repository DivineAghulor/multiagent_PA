"""Typed CRUD tools for Habit/HabitLog. Stubs are filled in per-phase; see NOTES.md."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from db.models import Habit, HabitFrequency, HabitLog
from db.session import get_session


def create_habit(
    name: str,
    frequency: HabitFrequency = HabitFrequency.DAILY,
    target_per_period: int = 1,
    description: str | None = None,
) -> Habit:
    if target_per_period < 1:
        raise ValueError("target_per_period must be at least 1")
    with get_session() as session:
        habit = Habit(
            name=name,
            frequency=frequency,
            target_per_period=target_per_period,
            description=description,
        )
        session.add(habit)
        session.flush()
        session.refresh(habit)
        return habit


def get_habit(habit_id: int) -> Habit | None:
    with get_session() as session:
        return session.get(Habit, habit_id)


def list_habits(active_only: bool = True) -> list[Habit]:
    stmt = select(Habit).order_by(Habit.id)
    if active_only:
        stmt = stmt.where(Habit.active.is_(True))
    with get_session() as session:
        return list(session.scalars(stmt).all())


def deactivate_habit(habit_id: int) -> Habit:
    raise NotImplementedError


def log_habit_completion(habit_id: int, on_date: date, note: str | None = None) -> HabitLog:
    raise NotImplementedError


def get_habit_logs(habit_id: int, start: date, end: date) -> list[HabitLog]:
    """Completion logs in a date range, e.g. a weekly review window."""
    raise NotImplementedError
