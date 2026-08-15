"""Typed, empty-bodied CRUD tool stubs for Task. Sub-agents fill these in."""
from __future__ import annotations

from datetime import date

from db.models import Task, TaskPriority, TaskStatus


def create_task(
    title: str,
    description: str | None = None,
    project_id: int | None = None,
    milestone_id: int | None = None,
    weekly_goal_id: int | None = None,
    priority: TaskPriority = TaskPriority.MEDIUM,
    due_date: date | None = None,
) -> Task:
    """Create a task, defaulting to TaskStatus.BACKLOG."""
    raise NotImplementedError


def get_task(task_id: int) -> Task | None:
    raise NotImplementedError


def get_backlog() -> list[Task]:
    """Tasks with status BACKLOG, for weekly-planning triage."""
    raise NotImplementedError


def list_tasks(
    status: TaskStatus | None = None,
    project_id: int | None = None,
    milestone_id: int | None = None,
    weekly_goal_id: int | None = None,
) -> list[Task]:
    raise NotImplementedError


def update_task_status(task_id: int, status: TaskStatus) -> Task:
    raise NotImplementedError


def schedule_task(task_id: int, scheduled_for: date) -> Task:
    """Assign a task to a date during weekly planning."""
    raise NotImplementedError


def complete_task(task_id: int) -> Task:
    """Mark DONE and stamp completed_at."""
    raise NotImplementedError


def update_task(
    task_id: int,
    title: str | None = None,
    description: str | None = None,
    priority: TaskPriority | None = None,
    due_date: date | None = None,
    project_id: int | None = None,
    milestone_id: int | None = None,
    weekly_goal_id: int | None = None,
) -> Task:
    raise NotImplementedError


def delete_task(task_id: int) -> None:
    raise NotImplementedError
