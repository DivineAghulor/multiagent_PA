"""Unit tests for backlog capture. extract_tasks (the LLM call) is always
mocked here — zero live API calls."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from agents.pm.backlog import capture_backlog_from_text
from agents.pm.schemas import ExtractedTask, ExtractedTaskBatch
from tools.projects import find_project_by_name
from tools.tasks import create_task, get_task, update_task_priority


def test_capture_backlog_creates_tasks(db_session) -> None:
    fake_response = ExtractedTaskBatch(
        tasks=[
            ExtractedTask(title="Fix login bug", description=None, project_hint=None),
            ExtractedTask(title="Redesign landing page", description=None, project_hint="Website"),
        ]
    )
    with patch("agents.pm.backlog.extract_tasks", return_value=fake_response):
        tasks = capture_backlog_from_text("fix the login bug and redesign the landing page")

    assert len(tasks) == 2
    assert tasks[0].importance is None
    assert tasks[0].urgency is None
    assert {t.title for t in tasks} == {"Fix login bug", "Redesign landing page"}


def test_capture_backlog_no_tasks_found(db_session) -> None:
    with patch("agents.pm.backlog.extract_tasks", return_value=ExtractedTaskBatch(tasks=[])):
        tasks = capture_backlog_from_text("not sure what to do today honestly")

    assert tasks == []


def test_capture_backlog_resolves_known_project_hint(db_session) -> None:
    from db.session import get_session
    from db.models import Project

    with get_session() as session:
        session.add(Project(name="Website"))

    fake_response = ExtractedTaskBatch(
        tasks=[ExtractedTask(title="Redesign landing page", description=None, project_hint="website")]
    )
    with patch("agents.pm.backlog.extract_tasks", return_value=fake_response):
        tasks = capture_backlog_from_text("redesign the landing page")

    assert tasks[0].project_id is not None
    assert find_project_by_name("Website").id == tasks[0].project_id


def test_update_task_priority_rates_a_task(db_session) -> None:
    task = create_task(title="Fix login bug")
    assert task.importance is None

    updated = update_task_priority(task.id, importance=3, urgency=2)

    assert updated.importance == 3
    assert updated.urgency == 2
    assert get_task(task.id).importance == 3


def test_update_task_priority_rejects_out_of_range(db_session) -> None:
    task = create_task(title="Fix login bug")

    with pytest.raises(ValueError):
        update_task_priority(task.id, importance=5, urgency=2)
