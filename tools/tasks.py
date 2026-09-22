"""Typed CRUD tools for Task. Stubs are filled in per-phase; see NOTES.md."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select

from db.models import Task, TaskPriority, TaskStatus
from db.session import get_session


def _validate_priority_pair(importance: int | None, urgency: int | None) -> None:
    if importance is not None and not (1 <= importance <= 4):
        raise ValueError("importance must be between 1 and 4")
    if urgency is not None and not (1 <= urgency <= 4):
        raise ValueError("urgency must be between 1 and 4")


def derive_priority(importance: int | None, urgency: int | None) -> TaskPriority:
    """The coarse Task.priority bucket for an importance/urgency pair.

    Eisenhower quadrants: important + urgent is URGENT, important alone is HIGH,
    urgent alone is MEDIUM, neither is LOW. An unrated task (either value unset)
    is MEDIUM, the column's default. MEDIUM therefore covers both "unrated" and
    "urgent but not important" — use the pair itself to tell those apart.
    """
    if importance is None or urgency is None:
        return TaskPriority.MEDIUM
    if importance >= 3:
        return TaskPriority.URGENT if urgency >= 3 else TaskPriority.HIGH
    return TaskPriority.MEDIUM if urgency >= 3 else TaskPriority.LOW


def create_task(
    title: str,
    description: str | None = None,
    project_id: int | None = None,
    milestone_id: int | None = None,
    weekly_goal_id: int | None = None,
    due_date: date | None = None,
    importance: int | None = None,
    urgency: int | None = None,
) -> Task:
    """Create a task, defaulting to TaskStatus.BACKLOG.

    `priority` is not a parameter: it's derived from `importance`/`urgency`.
    """
    _validate_priority_pair(importance, urgency)
    with get_session() as session:
        task = Task(
            title=title,
            description=description,
            project_id=project_id,
            milestone_id=milestone_id,
            weekly_goal_id=weekly_goal_id,
            priority=derive_priority(importance, urgency),
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
    return list_tasks(status=TaskStatus.BACKLOG)


def list_tasks(
    status: TaskStatus | None = None,
    project_id: int | None = None,
    milestone_id: int | None = None,
    weekly_goal_id: int | None = None,
) -> list[Task]:
    stmt = select(Task).order_by(Task.id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if project_id is not None:
        stmt = stmt.where(Task.project_id == project_id)
    if milestone_id is not None:
        stmt = stmt.where(Task.milestone_id == milestone_id)
    if weekly_goal_id is not None:
        stmt = stmt.where(Task.weekly_goal_id == weekly_goal_id)
    with get_session() as session:
        return list(session.scalars(stmt).all())


def update_task_status(task_id: int, status: TaskStatus) -> Task:
    with get_session() as session:
        task = session.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        task.status = status
        session.flush()
        session.refresh(task)
        return task


def schedule_task(task_id: int, scheduled_for: date) -> Task:
    """Assign a task to a date during weekly planning."""
    raise NotImplementedError


def complete_task(task_id: int, completed_at: datetime | None = None) -> Task:
    """Mark DONE and stamp completed_at (defaults to now; pass a value to backdate)."""
    with get_session() as session:
        task = session.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        task.status = TaskStatus.DONE
        task.completed_at = completed_at or datetime.now(timezone.utc)
        session.flush()
        session.refresh(task)
        return task


def reopen_task(task_id: int, status: TaskStatus = TaskStatus.TODO) -> Task:
    """Undo a completion: back to TODO (or another open status) and clear completed_at."""
    if status in (TaskStatus.DONE, TaskStatus.CANCELLED):
        raise ValueError("reopen_task needs an open status")
    with get_session() as session:
        task = session.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        task.status = status
        task.completed_at = None
        session.flush()
        session.refresh(task)
        return task


def update_task(
    task_id: int,
    title: str | None = None,
    description: str | None = None,
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
        task.priority = derive_priority(importance, urgency)
        session.flush()
        session.refresh(task)
        return task
