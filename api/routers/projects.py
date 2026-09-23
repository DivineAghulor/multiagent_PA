"""Projects and milestones: reads, create, edit, archive."""
from __future__ import annotations

from fastapi import APIRouter, Query, status

from api.errors import NotFoundError
from api.schemas import (
    MilestoneOut,
    MilestoneUpdateIn,
    ProjectCreateIn,
    ProjectDetailOut,
    ProjectOut,
    ProjectUpdateIn,
    TaskOut,
)
from db.models import MilestoneStatus, ProjectStatus
from tools.milestones import get_milestone, list_milestones, update_milestone
from tools.projects import archive_project, create_project, get_project, list_projects, update_project
from tools.tasks import list_tasks

router = APIRouter(prefix="/api", tags=["projects"])


def _require(project_id: int) -> None:
    if get_project(project_id) is None:
        raise NotFoundError("Project", project_id)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects_endpoint(status: ProjectStatus | None = Query(None)) -> list[ProjectOut]:
    return [ProjectOut.model_validate(p) for p in list_projects(status=status)]


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project_endpoint(body: ProjectCreateIn) -> ProjectOut:
    """A project with no milestones yet; the decomposition screen breaks it down."""
    return ProjectOut.model_validate(create_project(body.name, body.description, body.target_date))


@router.get("/projects/{project_id}", response_model=ProjectDetailOut)
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


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project_endpoint(project_id: int, body: ProjectUpdateIn) -> ProjectOut:
    """Edit name, description, status or target date. Omitted fields are
    unchanged; null clears description or target date."""
    _require(project_id)
    return ProjectOut.model_validate(update_project(project_id, **body.model_dump(exclude_unset=True)))


@router.post("/projects/{project_id}/archive", response_model=ProjectOut)
def archive_project_endpoint(project_id: int) -> ProjectOut:
    """Hide from planning, keep the history. Undo by PATCHing status back to active."""
    _require(project_id)
    return ProjectOut.model_validate(archive_project(project_id))


@router.get("/projects/{project_id}/milestones", response_model=list[MilestoneOut])
def list_milestones_endpoint(
    project_id: int, status: MilestoneStatus | None = Query(None)
) -> list[MilestoneOut]:
    _require(project_id)
    return [
        MilestoneOut.model_validate(m)
        for m in list_milestones(project_id=project_id, status=status)
    ]


@router.patch("/milestones/{milestone_id}", response_model=MilestoneOut)
def update_milestone_endpoint(milestone_id: int, body: MilestoneUpdateIn) -> MilestoneOut:
    """Status updates from the project screen (FR-25), plus name/description/due date."""
    if get_milestone(milestone_id) is None:
        raise NotFoundError("Milestone", milestone_id)
    return MilestoneOut.model_validate(update_milestone(milestone_id, **body.model_dump(exclude_unset=True)))
