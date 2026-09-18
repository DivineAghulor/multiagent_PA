"""UI wiring tests for app_test.py via Streamlit's AppTest harness.

Covers the chat -> capture -> rating-dialog flow. extract_tasks is mocked, so
these run with zero live API calls (see CLAUDE.md testing conventions).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from agents.pm.schemas import ExtractedTask, ExtractedTaskBatch

APP_PATH = str(Path(__file__).resolve().parents[1] / "app_test.py")

FAKE_BATCH = ExtractedTaskBatch(
    tasks=[
        ExtractedTask(title="Call the dentist", description=None, project_hint=None),
        ExtractedTask(title="Buy groceries", description=None, project_hint=None),
    ]
)


@pytest.fixture()
def app(db_session):
    return AppTest.from_file(APP_PATH, default_timeout=30)


def test_chat_submit_captures_tasks_and_shows_rating_dialog(app) -> None:
    app.run()
    assert not app.exception

    with patch("agents.pm.backlog.extract_tasks", return_value=FAKE_BATCH):
        app.chat_input[0].set_value("call the dentist and buy groceries").run()

    assert not app.exception
    assert len(app.session_state["pending_tasks"]) == 2
    assert "Added 2 task(s)" in app.session_state["history"][-1][1]
    # one selectbox pair + one save button per unrated task
    assert len(app.selectbox) == 4
    assert len(app.button) == 2


def test_saving_a_rating_removes_that_task_from_the_dialog(app) -> None:
    app.run()
    with patch("agents.pm.backlog.extract_tasks", return_value=FAKE_BATCH):
        app.chat_input[0].set_value("call the dentist and buy groceries").run()

    rated_id = app.session_state["pending_tasks"][0].id
    app.selectbox[0].set_value(3).run()
    app.selectbox[1].set_value(4).run()
    app.button[0].click().run()

    assert not app.exception
    assert app.session_state["rated_ids"] == {rated_id}
    assert len(app.button) == 1  # the rated task dropped out of the dialog

    from tools.tasks import get_task

    task = get_task(rated_id)
    assert (task.importance, task.urgency) == (3, 4)


def test_input_with_no_tasks_reports_none_and_shows_no_dialog(app) -> None:
    app.run()
    with patch("agents.pm.backlog.extract_tasks", return_value=ExtractedTaskBatch(tasks=[])):
        app.chat_input[0].set_value("not sure what to do today honestly").run()

    assert not app.exception
    assert app.session_state["pending_tasks"] == []
    assert "didn't find any tasks" in app.session_state["history"][-1][1]
    assert len(app.button) == 0
