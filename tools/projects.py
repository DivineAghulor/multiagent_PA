"""Typed CRUD tools for Project. Stubs are filled in per-phase; see NOTES.md."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from db.models import Project, ProjectStatus
from db.session import get_session

from .common import UNSET, Unset


def find_project_by_name(name: str) -> Project | None:
    """Case-insensitive exact-name lookup, used to resolve an LLM-extracted
    project hint to an existing Project row. Returns None on no match — callers
    should not treat a miss as an error (the hint may not name a real project)."""
    with get_session() as session:
        stmt = select(Project).where(func.lower(Project.name) == name.strip().lower())
        return session.scalars(stmt).first()


def create_project(name: str, description: str | None = None, target_date: date | None = None) -> Project:
    with get_session() as session:
        project = Project(name=name, description=description, target_date=target_date)
        session.add(project)
        session.flush()
        session.refresh(project)
        return project


def get_project(project_id: int) -> Project | None:
    with get_session() as session:
        return session.get(Project, project_id)


def list_projects(status: ProjectStatus | None = None) -> list[Project]:
    stmt = select(Project).order_by(Project.id)
    if status is not None:
        stmt = stmt.where(Project.status == status)
    with get_session() as session:
        return list(session.scalars(stmt).all())


def update_project(
    project_id: int,
    name: str | Unset = UNSET,
    description: str | None | Unset = UNSET,
    status: ProjectStatus | Unset = UNSET,
    target_date: date | None | Unset = UNSET,
) -> Project:
    """Edit a project. Omitted arguments are left alone; None clears a nullable field."""
    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise ValueError(f"Project {project_id} not found")
        if name is not UNSET:
            if not name.strip():
                raise ValueError("name is empty")
            project.name = name.strip()
        if description is not UNSET:
            project.description = (description.strip() or None) if description else None
        if status is not UNSET:
            project.status = status
        if target_date is not UNSET:
            project.target_date = target_date
        session.flush()
        session.refresh(project)
        return project


def archive_project(project_id: int) -> Project:
    """Hide a project from planning without deleting its history. Reversible via update_project."""
    return update_project(project_id, status=ProjectStatus.ARCHIVED)


def delete_project(project_id: int) -> None:
    """Delete a project and its milestones (cascade); its tasks stay, unlinked."""
    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise ValueError(f"Project {project_id} not found")
        session.delete(project)
