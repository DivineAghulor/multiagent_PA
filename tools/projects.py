"""Typed CRUD tools for Project. Stubs are filled in per-phase; see NOTES.md."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from db.models import Project, ProjectStatus
from db.session import get_session


def find_project_by_name(name: str) -> Project | None:
    """Case-insensitive exact-name lookup, used to resolve an LLM-extracted
    project hint to an existing Project row. Returns None on no match — callers
    should not treat a miss as an error (the hint may not name a real project)."""
    with get_session() as session:
        stmt = select(Project).where(func.lower(Project.name) == name.strip().lower())
        return session.scalars(stmt).first()


def create_project(name: str, description: str | None = None, target_date: date | None = None) -> Project:
    raise NotImplementedError


def get_project(project_id: int) -> Project | None:
    raise NotImplementedError


def list_projects(status: ProjectStatus | None = None) -> list[Project]:
    raise NotImplementedError


def update_project(
    project_id: int,
    name: str | None = None,
    description: str | None = None,
    status: ProjectStatus | None = None,
    target_date: date | None = None,
) -> Project:
    raise NotImplementedError


def archive_project(project_id: int) -> Project:
    raise NotImplementedError


def delete_project(project_id: int) -> None:
    raise NotImplementedError
