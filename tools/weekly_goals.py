"""Typed, empty-bodied CRUD tool stubs for WeeklyGoal. Sub-agents fill these in."""
from __future__ import annotations

from datetime import date

from db.models import WeeklyGoal, WeeklyGoalStatus


def create_weekly_goal(week_start: date, description: str, project_id: int | None = None) -> WeeklyGoal:
    raise NotImplementedError


def get_weekly_goal(weekly_goal_id: int) -> WeeklyGoal | None:
    raise NotImplementedError


def list_weekly_goals(week_start: date | None = None, status: WeeklyGoalStatus | None = None) -> list[WeeklyGoal]:
    raise NotImplementedError


def update_weekly_goal_status(weekly_goal_id: int, status: WeeklyGoalStatus) -> WeeklyGoal:
    raise NotImplementedError


def record_weekly_review(weekly_goal_id: int, review_notes: str, status: WeeklyGoalStatus) -> WeeklyGoal:
    """Attach notes + final status when comparing goals to completions."""
    raise NotImplementedError


def delete_weekly_goal(weekly_goal_id: int) -> None:
    raise NotImplementedError
