"""Unit tests for the WeeklyGoal tools and the task/project/habit reads that
weekly planning depends on."""
from __future__ import annotations

from datetime import date

import pytest

from db.models import HabitFrequency, ProjectStatus, TaskStatus, WeeklyGoalStatus
from tools.habits import create_habit, list_habits
from tools.projects import create_project, list_projects
from tools.tasks import create_task, get_backlog, get_task, list_tasks, update_task_status
from tools.weekly_goals import (
    create_weekly_goal,
    delete_weekly_goal,
    get_weekly_goal,
    list_weekly_goals,
    update_weekly_goal_status,
)

MONDAY = date(2026, 9, 21)


def test_create_weekly_goal_links_tasks_and_moves_them_to_todo(db_session) -> None:
    project = create_project("Website")
    t1 = create_task("Update pricing copy", project_id=project.id)
    t2 = create_task("Fix footer links", project_id=project.id)

    goal = create_weekly_goal(
        MONDAY, "Ship the pricing page", project_id=project.id, target_count=2, task_ids=[t1.id, t2.id]
    )

    assert goal.status == WeeklyGoalStatus.PLANNED
    assert goal.target_count == 2
    assert {t.id for t in goal.tasks} == {t1.id, t2.id}
    assert goal.project.name == "Website"
    for tid in (t1.id, t2.id):
        task = get_task(tid)
        assert task.weekly_goal_id == goal.id
        assert task.status == TaskStatus.TODO


def test_create_weekly_goal_for_a_habit(db_session) -> None:
    habit = create_habit("Gym", frequency=HabitFrequency.WEEKLY, target_per_period=3)

    goal = create_weekly_goal(MONDAY, "Gym three times", habit_id=habit.id, target_count=3)

    assert get_weekly_goal(goal.id).habit.name == "Gym"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"week_start": date(2026, 9, 22)},  # a Tuesday
        {"target_count": 0},
        {"project_id": 999},
        {"habit_id": 999},
        {"task_ids": [999]},
    ],
)
def test_create_weekly_goal_rejects_invalid_input(db_session, kwargs) -> None:
    args = {"week_start": MONDAY, "description": "Goal", **kwargs}
    with pytest.raises(ValueError):
        create_weekly_goal(**args)


def test_create_weekly_goal_rejects_project_and_habit_together(db_session) -> None:
    project = create_project("Website")
    habit = create_habit("Gym")
    with pytest.raises(ValueError):
        create_weekly_goal(MONDAY, "Both", project_id=project.id, habit_id=habit.id)


def test_create_weekly_goal_rejects_task_already_linked_or_started(db_session) -> None:
    linked = create_task("Linked")
    started = create_task("Started")
    create_weekly_goal(MONDAY, "First", task_ids=[linked.id])
    update_task_status(started.id, TaskStatus.IN_PROGRESS)

    for tid in (linked.id, started.id):
        with pytest.raises(ValueError):
            create_weekly_goal(MONDAY, "Second", task_ids=[tid])
    assert list_weekly_goals() and len(list_weekly_goals()) == 1  # nothing half-written


def test_list_weekly_goals_filters_by_week_and_status(db_session) -> None:
    a = create_weekly_goal(MONDAY, "This week")
    create_weekly_goal(date(2026, 9, 28), "Next week")
    update_weekly_goal_status(a.id, WeeklyGoalStatus.IN_PROGRESS)

    assert [g.description for g in list_weekly_goals(week_start=MONDAY)] == ["This week"]
    assert [g.description for g in list_weekly_goals(status=WeeklyGoalStatus.PLANNED)] == ["Next week"]


def test_delete_weekly_goal_returns_unstarted_tasks_to_backlog(db_session) -> None:
    todo = create_task("Still todo")
    started = create_task("Started")
    goal = create_weekly_goal(MONDAY, "Goal", task_ids=[todo.id, started.id])
    update_task_status(started.id, TaskStatus.IN_PROGRESS)

    delete_weekly_goal(goal.id)

    assert get_weekly_goal(goal.id) is None
    assert get_task(todo.id).status == TaskStatus.BACKLOG
    assert get_task(todo.id).weekly_goal_id is None
    assert get_task(started.id).status == TaskStatus.IN_PROGRESS


def test_backlog_and_list_reads(db_session) -> None:
    project = create_project("Website")
    a = create_task("A", project_id=project.id)
    b = create_task("B")
    update_task_status(b.id, TaskStatus.DONE)

    assert [t.id for t in get_backlog()] == [a.id]
    assert [t.id for t in list_tasks(project_id=project.id)] == [a.id]
    assert [t.id for t in list_tasks(status=TaskStatus.DONE)] == [b.id]
    assert [p.name for p in list_projects(status=ProjectStatus.ACTIVE)] == ["Website"]


def test_list_habits_active_only(db_session) -> None:
    from db.models import Habit
    from db.session import get_session

    create_habit("Gym")
    with get_session() as session:
        session.add(Habit(name="Old habit", active=False))

    assert [h.name for h in list_habits()] == ["Gym"]
    assert len(list_habits(active_only=False)) == 2
