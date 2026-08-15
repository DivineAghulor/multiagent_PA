"""Typed, empty-bodied CRUD tool stubs for Milestone. Sub-agents fill these in."""
from __future__ import annotations

from datetime import date

from db.models import Milestone, MilestoneStatus


def create_milestone(
    project_id: int, name: str, description: str | None = None, due_date: date | None = None
) -> Milestone:
    """Used when decomposing a project into milestones."""
    raise NotImplementedError


def get_milestone(milestone_id: int) -> Milestone | None:
    raise NotImplementedError


def list_milestones(project_id: int | None = None, status: MilestoneStatus | None = None) -> list[Milestone]:
    raise NotImplementedError


def update_milestone(
    milestone_id: int,
    name: str | None = None,
    description: str | None = None,
    status: MilestoneStatus | None = None,
    due_date: date | None = None,
) -> Milestone:
    raise NotImplementedError


def delete_milestone(milestone_id: int) -> None:
    raise NotImplementedError
