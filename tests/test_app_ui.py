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


# --- Weekly planning mode ----------------------------------------------------

from datetime import date  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from agents.pm.schemas import ProposedGoal, WeeklyPlanProposal  # noqa: E402

MONDAY = date(2026, 9, 21)


def _planning_model(proposal: WeeklyPlanProposal) -> MagicMock:
    model = MagicMock()
    model.with_structured_output.return_value.invoke.return_value = proposal
    return model


@pytest.fixture()
def planning_app(app):
    from tools.habits import create_habit
    from tools.tasks import create_task

    gym = create_habit("Gym")
    task = create_task("Update pricing page copy")
    app.run()
    app.sidebar.radio[0].set_value("Weekly planning").run()
    app.date_input[0].set_value(MONDAY).run()
    proposal = WeeklyPlanProposal(
        reply="Two goals for the week.",
        goals=[
            ProposedGoal(description="Gym 3x", habit_id=gym.id, target_count=3),
            ProposedGoal(description="Ship pricing", task_ids=[task.id]),
        ],
    )
    with patch("agents.pm.planning.get_default_chat_model", return_value=_planning_model(proposal)):
        app.chat_input[0].set_value("gym 3 times and ship the pricing page").run()
    app.task_id = task.id
    return app


def test_planning_proposal_is_shown_but_not_saved(planning_app) -> None:
    from tools.weekly_goals import list_weekly_goals

    assert not planning_app.exception
    assert len(planning_app.checkbox) == 2
    assert [t.value for t in planning_app.text_input] == ["Gym 3x", "Ship pricing"]
    assert "Two goals for the week." in planning_app.session_state["plan_history"][-1][1]
    assert list_weekly_goals() == []  # nothing persisted before confirmation


def test_confirming_plan_saves_only_included_edited_goals(planning_app) -> None:
    from db.models import TaskStatus
    from tools.tasks import get_task
    from tools.weekly_goals import list_weekly_goals

    planning_app.checkbox[0].uncheck().run()  # drop the gym goal
    planning_app.text_input[1].set_value("Ship the pricing page").run()
    planning_app.button(key="plan_confirm").click().run()

    assert not planning_app.exception
    goals = list_weekly_goals(week_start=MONDAY)
    assert [g.description for g in goals] == ["Ship the pricing page"]
    assert get_task(planning_app.task_id).status == TaskStatus.TODO
    assert planning_app.session_state["plan_proposal"] is None
    assert "Saved 1 goal(s)" in planning_app.session_state["plan_history"][-1][1]


def test_discarding_plan_saves_nothing(planning_app) -> None:
    from tools.weekly_goals import list_weekly_goals

    planning_app.button(key="plan_discard").click().run()

    assert not planning_app.exception
    assert planning_app.session_state["plan_proposal"] is None
    assert len(planning_app.checkbox) == 0
    assert list_weekly_goals() == []
