"""Task reads and writes."""
from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from api.errors import NotFoundError
from api.schemas import PriorityIn, ScheduleIn, StatusIn, TaskOut, TaskUpdateIn
from db.models import TaskStatus
from tools.tasks import (
    complete_task,
    delete_task,
    get_task,
    list_tasks,
    reopen_task,
    schedule_task,
    set_task_status,
    update_task,
    update_task_priority,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _require(task_id: int) -> None:
    # Tools report a missing row as ValueError, which the API maps to 400;
    # checking first makes it the 404 it is.
    if get_task(task_id) is None:
        raise NotFoundError("Task", task_id)


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


@router.patch("/{task_id}", response_model=TaskOut)
def update_task_endpoint(task_id: int, body: TaskUpdateIn) -> TaskOut:
    """Edit title, description, due date, project or milestone. Omitted fields
    are unchanged; an explicit null clears the field."""
    _require(task_id)
    return TaskOut.model_validate(update_task(task_id, **body.model_dump(exclude_unset=True)))


@router.patch("/{task_id}/priority", response_model=TaskOut)
def rate_task_endpoint(task_id: int, body: PriorityIn) -> TaskOut:
    """Set the importance/urgency pair; the priority bucket is derived from it."""
    _require(task_id)
    return TaskOut.model_validate(update_task_priority(task_id, body.importance, body.urgency))


@router.put("/{task_id}/status", response_model=TaskOut)
def set_status_endpoint(task_id: int, body: StatusIn) -> TaskOut:
    """Any status change. Moving to done stamps completed_at; moving away clears it."""
    _require(task_id)
    return TaskOut.model_validate(set_task_status(task_id, body.status))


@router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task_endpoint(task_id: int) -> TaskOut:
    _require(task_id)
    return TaskOut.model_validate(complete_task(task_id))


@router.post("/{task_id}/reopen", response_model=TaskOut)
def reopen_task_endpoint(task_id: int) -> TaskOut:
    """Undo a completion: back to To do, completed_at cleared."""
    _require(task_id)
    return TaskOut.model_validate(reopen_task(task_id))


@router.put("/{task_id}/schedule", response_model=TaskOut)
def schedule_task_endpoint(task_id: int, body: ScheduleIn) -> TaskOut:
    """Pin a task to a day; null unschedules it."""
    _require(task_id)
    return TaskOut.model_validate(schedule_task(task_id, body.scheduled_for))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_endpoint(task_id: int) -> Response:
    _require(task_id)
    delete_task(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
