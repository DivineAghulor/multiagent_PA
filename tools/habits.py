"""Typed CRUD tools for Habit/HabitLog. Stubs are filled in per-phase; see NOTES.md."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from db.models import Habit, HabitFrequency, HabitLog
from db.session import get_session

from .common import UNSET, Unset


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


def update_habit(
    habit_id: int,
    name: str | Unset = UNSET,
    description: str | None | Unset = UNSET,
    frequency: HabitFrequency | Unset = UNSET,
    target_per_period: int | Unset = UNSET,
    active: bool | Unset = UNSET,
) -> Habit:
    """Edit a habit. Omitted arguments are left alone; None clears the description.
    Existing logs are kept whatever changes — they record what happened."""
    if target_per_period is not UNSET and target_per_period < 1:
        raise ValueError("target_per_period must be at least 1")
    with get_session() as session:
        habit = session.get(Habit, habit_id)
        if habit is None:
            raise ValueError(f"Habit {habit_id} not found")
        if name is not UNSET:
            if not name.strip():
                raise ValueError("name is empty")
            habit.name = name.strip()
        if description is not UNSET:
            habit.description = (description.strip() or None) if description else None
        if frequency is not UNSET:
            habit.frequency = frequency
        if target_per_period is not UNSET:
            habit.target_per_period = target_per_period
        if active is not UNSET:
            habit.active = active
        session.flush()
        session.refresh(habit)
        return habit


def deactivate_habit(habit_id: int) -> Habit:
    """Stop offering a habit to planning; its logs and past goals are kept."""
    return update_habit(habit_id, active=False)


def log_habit_completion(habit_id: int, on_date: date, note: str | None = None) -> HabitLog:
    """Record a completion. Idempotent: one log per habit per day (unique constraint),
    so re-logging the same day updates that row instead of failing."""
    with get_session() as session:
        if session.get(Habit, habit_id) is None:
            raise ValueError(f"Habit {habit_id} not found")
        log = session.scalars(
            select(HabitLog).where(HabitLog.habit_id == habit_id, HabitLog.log_date == on_date)
        ).first()
        if log is None:
            log = HabitLog(habit_id=habit_id, log_date=on_date, completed=True, note=note)
            session.add(log)
        else:
            log.completed = True
            if note is not None:
                log.note = note
        session.flush()
        session.refresh(log)
        return log


def remove_habit_log(habit_id: int, on_date: date) -> None:
    """Undo a logged completion (no-op if there isn't one)."""
    with get_session() as session:
        log = session.scalars(
            select(HabitLog).where(HabitLog.habit_id == habit_id, HabitLog.log_date == on_date)
        ).first()
        if log is not None:
            session.delete(log)


def get_habit_logs(habit_id: int, start: date, end: date) -> list[HabitLog]:
    """Completion logs in a date range, e.g. a weekly review window (inclusive)."""
    with get_session() as session:
        return list(
            session.scalars(
                select(HabitLog)
                .where(HabitLog.habit_id == habit_id, HabitLog.log_date >= start, HabitLog.log_date <= end)
                .order_by(HabitLog.log_date)
            ).all()
        )
