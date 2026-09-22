"""Task reads. Writes land in W2 alongside the tools/tasks.py stubs."""
from __future__ import annotations

from fastapi import APIRouter, Query

from api.errors import NotFoundError
from api.schemas import TaskOut
from db.models import TaskStatus
from tools.tasks import get_task, list_tasks

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
def list_tasks_endpoint(
    status: TaskStatus | None = Query(None),
    project_id: int | None = Query(None),
    milestone_id: int | None = Query(None),
    weekly_goal_id: int | None = Query(None),
) -> list[TaskOut]:
    """Filtered task list, oldest first.

    Sorting (FR-3) is done in the client: this is one person's task list, it
    arrives in full, and re-sorting it there costs nothing and keeps ordering
    logic out of the web layer.
    """
    tasks = list_tasks(
        status=status,
        project_id=project_id,
        milestone_id=milestone_id,
        weekly_goal_id=weekly_goal_id,
    )
    return [TaskOut.model_validate(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskOut)
def get_task_endpoint(task_id: int) -> TaskOut:
    task = get_task(task_id)
    if task is None:
        raise NotFoundError("Task", task_id)
    return TaskOut.model_validate(task)
