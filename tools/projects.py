"""Typed, empty-bodied CRUD tool stubs for Project. Sub-agents fill these in."""
from __future__ import annotations

from datetime import date

from db.models import Project, ProjectStatus


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
