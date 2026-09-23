"""The tools/* write paths the web app needed (requirements §6.6). No model calls."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from db.models import HabitFrequency, ProjectStatus, TaskPriority, TaskStatus
from tools.habits import create_habit, deactivate_habit, get_habit, list_habits, update_habit
from tools.milestones import create_milestone
from tools.projects import archive_project, create_project, list_projects, update_project
from tools.tasks import (
    complete_task,
    create_task,
    delete_task,
    get_task,
    schedule_task,
    set_task_status,
    update_task,
)


# --- update_task ---------------------------------------------------------

def test_update_task_changes_only_what_is_passed(db_session) -> None:
    task = create_task("Draft copy", description="for the homepage", importance=4, urgency=4)

    updated = update_task(task.id, title="  Write copy  ")

    assert updated.title == "Write copy"
    assert updated.description == "for the homepage"
    assert updated.priority == TaskPriority.URGENT  # the rating is untouched


def test_update_task_none_clears_a_nullable_field(db_session) -> None:
    project = create_project("Website")
    task = create_task("Write copy", description="x", project_id=project.id, due_date=date(2026, 10, 1))

    updated = update_task(task.id, description=None, due_date=None, project_id=None)

    assert (updated.description, updated.due_date, updated.project_id) == (None, None, None)


def test_update_task_blank_description_is_stored_as_none(db_session) -> None:
    task = create_task("Write copy", description="x")
    assert update_task(task.id, description="   ").description is None


def test_update_task_rejects_an_empty_title(db_session) -> None:
    task = create_task("Write copy")
    with pytest.raises(ValueError, match="empty"):
        update_task(task.id, title="  ")
    assert get_task(task.id).title == "Write copy"


def test_update_task_rejects_an_unknown_project(db_session) -> None:
    task = create_task("Write copy")
    with pytest.raises(ValueError, match="Project 999"):
        update_task(task.id, project_id=999)


def test_update_task_milestone_must_belong_to_the_resulting_project(db_session) -> None:
    website = create_project("Website")
    garden = create_project("Garden")
    milestone = create_milestone(website.id, "Design")
    task = create_task("Write copy", project_id=website.id, milestone_id=milestone.id)

    # Moving the task away while its milestone stays behind is rejected...
    with pytest.raises(ValueError, match="belongs to project"):
        update_task(task.id, project_id=garden.id)
    assert get_task(task.id).project_id == website.id

    # ...but moving it and clearing the milestone in one call is fine.
    moved = update_task(task.id, project_id=garden.id, milestone_id=None)
    assert (moved.project_id, moved.milestone_id) == (garden.id, None)


def test_update_task_missing_task(db_session) -> None:
    with pytest.raises(ValueError, match="Task 999 not found"):
        update_task(999, title="x")


# --- delete / status / schedule ------------------------------------------

def test_delete_task(db_session) -> None:
    task = create_task("Write copy")
    delete_task(task.id)
    assert get_task(task.id) is None
    with pytest.raises(ValueError):
        delete_task(task.id)


def test_set_task_status_done_stamps_completion_and_keeps_it_on_repeat(db_session) -> None:
    task = create_task("Write copy")
    done = set_task_status(task.id, TaskStatus.DONE)
    assert done.status == TaskStatus.DONE and done.completed_at is not None

    again = set_task_status(task.id, TaskStatus.DONE)
    assert again.completed_at == done.completed_at


def test_set_task_status_away_from_done_clears_completion(db_session) -> None:
    task = create_task("Write copy")
    complete_task(task.id, completed_at=datetime(2026, 9, 15, tzinfo=timezone.utc))

    blocked = set_task_status(task.id, TaskStatus.BLOCKED)

    assert blocked.status == TaskStatus.BLOCKED
    assert blocked.completed_at is None


def test_schedule_and_unschedule_a_task(db_session) -> None:
    task = create_task("Write copy")
    assert schedule_task(task.id, date(2026, 9, 16)).scheduled_for == date(2026, 9, 16)
    assert schedule_task(task.id, None).scheduled_for is None


# --- projects ------------------------------------------------------------

def test_update_project(db_session) -> None:
    project = create_project("Website", description="Rebuild", target_date=date(2026, 12, 1))

    updated = update_project(project.id, name="Site", target_date=None, status=ProjectStatus.ON_HOLD)

    assert (updated.name, updated.description, updated.target_date, updated.status) == (
        "Site",
        "Rebuild",
        None,
        ProjectStatus.ON_HOLD,
    )


def test_archive_project_hides_it_from_active_lists_and_is_reversible(db_session) -> None:
    project = create_project("Website")

    assert archive_project(project.id).status == ProjectStatus.ARCHIVED
    assert list_projects(status=ProjectStatus.ACTIVE) == []

    update_project(project.id, status=ProjectStatus.ACTIVE)
    assert [p.name for p in list_projects(status=ProjectStatus.ACTIVE)] == ["Website"]


def test_update_project_missing_or_blank(db_session) -> None:
    with pytest.raises(ValueError, match="Project 999"):
        update_project(999, name="x")
    project = create_project("Website")
    with pytest.raises(ValueError, match="empty"):
        update_project(project.id, name=" ")


# --- habits --------------------------------------------------------------

def test_update_habit(db_session) -> None:
    habit = create_habit("Run", description="5k")

    updated = update_habit(habit.id, frequency=HabitFrequency.WEEKLY, target_per_period=3, description=None)

    assert (updated.name, updated.frequency, updated.target_per_period, updated.description) == (
        "Run",
        HabitFrequency.WEEKLY,
        3,
        None,
    )


def test_update_habit_rejects_a_non_positive_target(db_session) -> None:
    habit = create_habit("Run")
    with pytest.raises(ValueError, match="at least 1"):
        update_habit(habit.id, target_per_period=0)


def test_deactivate_and_reactivate_a_habit(db_session) -> None:
    habit = create_habit("Run")

    assert deactivate_habit(habit.id).active is False
    assert list_habits(active_only=True) == []

    update_habit(habit.id, active=True)
    assert get_habit(habit.id).active is True


def test_deactivate_missing_habit(db_session) -> None:
    with pytest.raises(ValueError, match="Habit 999"):
        deactivate_habit(999)
