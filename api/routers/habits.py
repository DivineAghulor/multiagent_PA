"""Habit and habit-log reads."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from api.errors import NotFoundError
from api.schemas import HabitLogOut, HabitOut
from tools.habits import get_habit, get_habit_logs, list_habits

router = APIRouter(prefix="/api/habits", tags=["habits"])


@router.get("", response_model=list[HabitOut])
def list_habits_endpoint(active_only: bool = Query(True)) -> list[HabitOut]:
    return [HabitOut.model_validate(h) for h in list_habits(active_only=active_only)]


@router.get("/{habit_id}", response_model=HabitOut)
def get_habit_endpoint(habit_id: int) -> HabitOut:
    habit = get_habit(habit_id)
    if habit is None:
        raise NotFoundError("Habit", habit_id)
    return HabitOut.model_validate(habit)


@router.get("/{habit_id}/logs", response_model=list[HabitLogOut])
def list_habit_logs_endpoint(habit_id: int, start: date, end: date) -> list[HabitLogOut]:
    """Completions in an inclusive date range, e.g. one week of the week grid."""
    if get_habit(habit_id) is None:
        raise NotFoundError("Habit", habit_id)
    return [HabitLogOut.model_validate(log) for log in get_habit_logs(habit_id, start, end)]
