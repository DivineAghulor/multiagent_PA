"""Typed CRUD tools for WeeklyGoal. Stubs are filled in per-phase; see NOTES.md."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.models import Habit, Project, Task, TaskStatus, WeeklyGoal, WeeklyGoalStatus
from db.session import get_session

# Sessions close on return (expire_on_commit=False), so relationships callers
# read afterwards must be loaded up front.
_EAGER = (
    selectinload(WeeklyGoal.tasks),
    selectinload(WeeklyGoal.habit),
    selectinload(WeeklyGoal.project),
)


def create_weekly_goal(
    week_start: date,
    description: str,
    project_id: int | None = None,
    habit_id: int | None = None,
    target_count: int | None = None,
    task_ids: list[int] | None = None,
) -> WeeklyGoal:
    """Create a goal and link its backlog tasks (BACKLOG -> TODO) in one transaction."""
    if week_start.weekday() != 0:
        raise ValueError("week_start must be a Monday")
    if project_id is not None and habit_id is not None:
        raise ValueError("a weekly goal targets a project or a habit, not both")
    if target_count is not None and target_count < 1:
        raise ValueError("target_count must be at least 1")
    task_ids = list(dict.fromkeys(task_ids or []))

    with get_session() as session:
        if project_id is not None and session.get(Project, project_id) is None:
            raise ValueError(f"Project {project_id} not found")
        if habit_id is not None and session.get(Habit, habit_id) is None:
            raise ValueError(f"Habit {habit_id} not found")

        tasks = session.scalars(select(Task).where(Task.id.in_(task_ids))).all() if task_ids else []
        found = {t.id for t in tasks}
        if missing := [i for i in task_ids if i not in found]:
            raise ValueError(f"Task(s) not found: {missing}")
        if unavailable := [t.id for t in tasks if t.status != TaskStatus.BACKLOG or t.weekly_goal_id]:
            raise ValueError(f"Task(s) no longer in the unassigned backlog: {unavailable}")

        goal = WeeklyGoal(
            week_start=week_start,
            description=description,
            project_id=project_id,
            habit_id=habit_id,
            target_count=target_count,
        )
        session.add(goal)
        session.flush()
        for task in tasks:
            task.weekly_goal_id = goal.id
            task.status = TaskStatus.TODO
        session.flush()
        return session.scalars(select(WeeklyGoal).where(WeeklyGoal.id == goal.id).options(*_EAGER)).one()


def get_weekly_goal(weekly_goal_id: int) -> WeeklyGoal | None:
    with get_session() as session:
        return session.scalars(
            select(WeeklyGoal).where(WeeklyGoal.id == weekly_goal_id).options(*_EAGER)
        ).first()


def list_weekly_goals(week_start: date | None = None, status: WeeklyGoalStatus | None = None) -> list[WeeklyGoal]:
    stmt = select(WeeklyGoal).options(*_EAGER).order_by(WeeklyGoal.week_start, WeeklyGoal.id)
    if week_start is not None:
        stmt = stmt.where(WeeklyGoal.week_start == week_start)
    if status is not None:
        stmt = stmt.where(WeeklyGoal.status == status)
    with get_session() as session:
        return list(session.scalars(stmt).all())


def update_weekly_goal_status(weekly_goal_id: int, status: WeeklyGoalStatus) -> WeeklyGoal:
    with get_session() as session:
        goal = session.get(WeeklyGoal, weekly_goal_id)
        if goal is None:
            raise ValueError(f"WeeklyGoal {weekly_goal_id} not found")
        goal.status = status
        session.flush()
        session.refresh(goal)
        return goal


def record_weekly_review(weekly_goal_id: int, review_notes: str, status: WeeklyGoalStatus) -> WeeklyGoal:
    """Attach notes + final status when comparing goals to completions."""
    raise NotImplementedError


def delete_weekly_goal(weekly_goal_id: int) -> None:
    """Delete a goal; its linked tasks that were never started go back to the backlog."""
    with get_session() as session:
        goal = session.get(WeeklyGoal, weekly_goal_id)
        if goal is None:
            raise ValueError(f"WeeklyGoal {weekly_goal_id} not found")
        for task in goal.tasks:
            task.weekly_goal_id = None
            if task.status == TaskStatus.TODO:
                task.status = TaskStatus.BACKLOG
        session.delete(goal)
