"""Habits and habit logs: reads, create, edit, deactivate, and day ticking."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, Response, status

from api.deps import server_today
from api.errors import InvalidRequestError, NotFoundError
from api.schemas import HabitCreateIn, HabitLogIn, HabitLogOut, HabitOut, HabitUpdateIn
from tools.habits import (
    create_habit,
    deactivate_habit,
    get_habit,
    get_habit_logs,
    list_habits,
    log_habit_completion,
    remove_habit_log,
    update_habit,
)

router = APIRouter(prefix="/api/habits", tags=["habits"])


def _require(habit_id: int) -> None:
    if get_habit(habit_id) is None:
        raise NotFoundError("Habit", habit_id)


@router.get("", response_model=list[HabitOut])
def list_habits_endpoint(active_only: bool = Query(True)) -> list[HabitOut]:
    return [HabitOut.model_validate(h) for h in list_habits(active_only=active_only)]


@router.post("", response_model=HabitOut, status_code=status.HTTP_201_CREATED)
def create_habit_endpoint(body: HabitCreateIn) -> HabitOut:
    return HabitOut.model_validate(
        create_habit(
            body.name,
            frequency=body.frequency,
            target_per_period=body.target_per_period,
            description=body.description,
        )
    )


@router.get("/{habit_id}", response_model=HabitOut)
def get_habit_endpoint(habit_id: int) -> HabitOut:
    habit = get_habit(habit_id)
    if habit is None:
        raise NotFoundError("Habit", habit_id)
    return HabitOut.model_validate(habit)


@router.patch("/{habit_id}", response_model=HabitOut)
def update_habit_endpoint(habit_id: int, body: HabitUpdateIn) -> HabitOut:
    """Edit name, description, frequency, target, or reactivate with active=true."""
    _require(habit_id)
    return HabitOut.model_validate(update_habit(habit_id, **body.model_dump(exclude_unset=True)))


@router.post("/{habit_id}/deactivate", response_model=HabitOut)
def deactivate_habit_endpoint(habit_id: int) -> HabitOut:
    """Stop offering it to planning. Logs and past goals are kept."""
    _require(habit_id)
    return HabitOut.model_validate(deactivate_habit(habit_id))


@router.get("/{habit_id}/logs", response_model=list[HabitLogOut])
def list_habit_logs_endpoint(habit_id: int, start: date, end: date) -> list[HabitLogOut]:
    """Completions in an inclusive date range, e.g. one week of the week grid."""
    _require(habit_id)
    return [HabitLogOut.model_validate(log) for log in get_habit_logs(habit_id, start, end)]


@router.post("/{habit_id}/logs", response_model=HabitLogOut, status_code=status.HTTP_201_CREATED)
def log_habit_endpoint(habit_id: int, body: HabitLogIn) -> HabitLogOut:
    """Tick a day. Idempotent: logging the same day twice keeps one log.
    A future day is rejected, since it hasn't happened yet (FR-16)."""
    _require(habit_id)
    if body.date > server_today():
        raise InvalidRequestError(f"{body.date.isoformat()} is in the future")
    return HabitLogOut.model_validate(log_habit_completion(habit_id, body.date))


@router.delete("/{habit_id}/logs/{log_date}", status_code=status.HTTP_204_NO_CONTENT)
def unlog_habit_endpoint(habit_id: int, log_date: date) -> Response:
    """Untick a day. A no-op when the day had no log."""
    _require(habit_id)
    remove_habit_log(habit_id, log_date)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
