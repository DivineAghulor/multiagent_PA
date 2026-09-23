"""Typed CRUD tools for Milestone. Stubs are filled in per-phase; see NOTES.md."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.models import Milestone, MilestoneStatus, Project, Task, TaskStatus
from db.session import get_session

_CLOSED_TASK_STATUSES = (TaskStatus.DONE, TaskStatus.CANCELLED)


@dataclass
class NewTaskSpec:
    title: str
    description: str | None = None


@dataclass
class MilestoneSpec:
    """One milestone of a confirmed decomposition. `existing_milestone_id` set
    means only reposition it and add tasks under it; otherwise it is created."""

    name: str
    description: str | None = None
    due_date: date | None = None
    existing_milestone_id: int | None = None
    new_tasks: list[NewTaskSpec] = field(default_factory=list)
    attach_task_ids: list[int] = field(default_factory=list)


def _ordered(stmt):
    return stmt.order_by(
        Milestone.position.is_(None), Milestone.position, Milestone.due_date.is_(None), Milestone.due_date, Milestone.id
    )


def create_milestone(
    project_id: int,
    name: str,
    description: str | None = None,
    due_date: date | None = None,
    position: int | None = None,
) -> Milestone:
    """Used when decomposing a project into milestones."""
    with get_session() as session:
        if session.get(Project, project_id) is None:
            raise ValueError(f"Project {project_id} not found")
        milestone = Milestone(
            project_id=project_id, name=name, description=description, due_date=due_date, position=position
        )
        session.add(milestone)
        session.flush()
        session.refresh(milestone)
        return milestone


def get_milestone(milestone_id: int) -> Milestone | None:
    with get_session() as session:
        return session.scalars(
            select(Milestone).where(Milestone.id == milestone_id).options(selectinload(Milestone.tasks))
        ).first()


def list_milestones(project_id: int | None = None, status: MilestoneStatus | None = None) -> list[Milestone]:
    """Ordered by position (unpositioned last), then due date, then id."""
    stmt = _ordered(select(Milestone).options(selectinload(Milestone.tasks)))
    if project_id is not None:
        stmt = stmt.where(Milestone.project_id == project_id)
    if status is not None:
        stmt = stmt.where(Milestone.status == status)
    with get_session() as session:
        return list(session.scalars(stmt).all())


def update_milestone(
    milestone_id: int,
    name: str | None = None,
    description: str | None = None,
    status: MilestoneStatus | None = None,
    due_date: date | None = None,
) -> Milestone:
    with get_session() as session:
        milestone = session.get(Milestone, milestone_id)
        if milestone is None:
            raise ValueError(f"Milestone {milestone_id} not found")
        if name is not None:
            milestone.name = name
        if description is not None:
            milestone.description = description
        if status is not None:
            milestone.status = status
        if due_date is not None:
            milestone.due_date = due_date
        session.flush()
        session.refresh(milestone)
        return milestone


def delete_milestone(milestone_id: int) -> None:
    """Delete a milestone; its tasks stay, unlinked (FK is SET NULL)."""
    with get_session() as session:
        milestone = session.get(Milestone, milestone_id)
        if milestone is None:
            raise ValueError(f"Milestone {milestone_id} not found")
        for task in milestone.tasks:
            task.milestone_id = None
        session.delete(milestone)


def create_milestones_with_tasks(
    project_id: int, specs: list[MilestoneSpec]
) -> tuple[list[Milestone], list[Task]]:
    """Write a confirmed decomposition in one transaction: milestones get
    positions 1..n in spec order, new tasks are created unrated in BACKLOG,
    attached tasks get their milestone set. Returns (milestones, new tasks)."""
    with get_session() as session:
        if session.get(Project, project_id) is None:
            raise ValueError(f"Project {project_id} not found")

        milestones: list[Milestone] = []
        new_tasks: list[Task] = []
        for position, spec in enumerate(specs, 1):
            if spec.existing_milestone_id is not None:
                milestone = session.get(Milestone, spec.existing_milestone_id)
                if milestone is None or milestone.project_id != project_id:
                    raise ValueError(f"Milestone {spec.existing_milestone_id} is not part of project {project_id}")
                milestone.position = position
            else:
                milestone = Milestone(
                    project_id=project_id,
                    name=spec.name,
                    description=spec.description,
                    due_date=spec.due_date,
                    position=position,
                )
                session.add(milestone)
            session.flush()
            milestones.append(milestone)

            for task_id in spec.attach_task_ids:
                task = session.get(Task, task_id)
                if (
                    task is None
                    or task.project_id != project_id
                    or task.milestone_id is not None
                    or task.status in _CLOSED_TASK_STATUSES
                ):
                    raise ValueError(f"Task {task_id} can no longer be attached to a milestone of project {project_id}")
                task.milestone_id = milestone.id
            for new in spec.new_tasks:
                task = Task(
                    title=new.title,
                    description=new.description,
                    project_id=project_id,
                    milestone_id=milestone.id,
                )
                session.add(task)
                new_tasks.append(task)
        session.flush()
        for task in new_tasks:
            session.refresh(task)
        ids = [m.id for m in milestones]
        loaded = {
            m.id: m
            for m in session.scalars(
                select(Milestone).where(Milestone.id.in_(ids)).options(selectinload(Milestone.tasks))
            )
        }
        return [loaded[i] for i in ids], new_tasks
