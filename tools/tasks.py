"""Typed CRUD tools for Task. Stubs are filled in per-phase; see NOTES.md."""
from __future__ import annotations

from datetime import date

from db.models import Task, TaskPriority, TaskStatus
from db.session import get_session


def _validate_priority_pair(importance: int | None, urgency: int | None) -> None:
    if importance is not None and not (1 <= importance <= 4):
        raise ValueError("importance must be between 1 and 4")
    if urgency is not None and not (1 <= urgency <= 4):
        raise ValueError("urgency must be between 1 and 4")


def create_task(
    title: str,
    description: str | None = None,
    project_id: int | None = None,
    milestone_id: int | None = None,
    weekly_goal_id: int | None = None,
    priority: TaskPriority = TaskPriority.MEDIUM,
    due_date: date | None = None,
    importance: int | None = None,
    urgency: int | None = None,
) -> Task:
    """Create a task, defaulting to TaskStatus.BACKLOG.

    `importance`/`urgency` are separate from `priority` — see the note on
    Task.importance in db/models.py.
    """
    _validate_priority_pair(importance, urgency)
    with get_session() as session:
        task = Task(
            title=title,
            description=description,
            project_id=project_id,
            milestone_id=milestone_id,
            weekly_goal_id=weekly_goal_id,
            priority=priority,
            due_date=due_date,
            importance=importance,
            urgency=urgency,
        )
        session.add(task)
        session.flush()
        session.refresh(task)
        return task


def get_task(task_id: int) -> Task | None:
    with get_session() as session:
        return session.get(Task, task_id)


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


def update_task_priority(task_id: int, importance: int, urgency: int) -> Task:
    """Set the importance/urgency rating captured right after backlog capture."""
    _validate_priority_pair(importance, urgency)
    with get_session() as session:
        task = session.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        task.importance = importance
        task.urgency = urgency
        session.flush()
        session.refresh(task)
        return task
