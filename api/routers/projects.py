"""Project and milestone reads."""
from __future__ import annotations

from fastapi import APIRouter, Query

from api.errors import NotFoundError
from api.schemas import MilestoneOut, ProjectDetailOut, ProjectOut, TaskOut
from db.models import MilestoneStatus, ProjectStatus
from tools.milestones import list_milestones
from tools.projects import get_project, list_projects
from tools.tasks import list_tasks

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects_endpoint(status: ProjectStatus | None = Query(None)) -> list[ProjectOut]:
    return [ProjectOut.model_validate(p) for p in list_projects(status=status)]


@router.get("/{project_id}", response_model=ProjectDetailOut)
def get_project_endpoint(project_id: int) -> ProjectDetailOut:
    """A project with its milestones and tasks — the project detail screen in
    one request, since it always needs all three."""
    project = get_project(project_id)
    if project is None:
        raise NotFoundError("Project", project_id)
    # Built field by field, not by validating the ORM object: `milestones` and
    # `tasks` are also relationship names, so from_attributes would try to read
    # them off a detached instance and raise DetachedInstanceError. They come
    # from their own tool calls instead.
    return ProjectDetailOut(
        **ProjectOut.model_validate(project).model_dump(),
        milestones=[MilestoneOut.model_validate(m) for m in list_milestones(project_id=project_id)],
        tasks=[TaskOut.model_validate(t) for t in list_tasks(project_id=project_id)],
    )


@router.get("/{project_id}/milestones", response_model=list[MilestoneOut])
def list_milestones_endpoint(
    project_id: int, status: MilestoneStatus | None = Query(None)
) -> list[MilestoneOut]:
    if get_project(project_id) is None:
        raise NotFoundError("Project", project_id)
    return [
        MilestoneOut.model_validate(m)
        for m in list_milestones(project_id=project_id, status=status)
    ]
