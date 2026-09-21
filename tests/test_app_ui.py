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

from datetime import date, datetime, timezone  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from agents.pm.schemas import ProposedGoal, WeeklyPlanProposal  # noqa: E402

MONDAY = date(2026, 9, 21)


def _planning_model(proposal: WeeklyPlanProposal) -> MagicMock:
    model = MagicMock()
    model.invoke.return_value = proposal
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
    with patch("agents.pm.planning.get_structured_model", return_value=_planning_model(proposal)):
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


# --- Project breakdown mode --------------------------------------------------

from langchain_core.messages import AIMessage  # noqa: E402


def _breakdown_model():
    from tests.test_decomposition import ScriptedModel, call

    return ScriptedModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    call("add_milestone", name="Pilot recorded"),
                    call("add_task", milestone_ref="M1", title="Buy a microphone"),
                    call("add_task", milestone_ref="M1", title="Record episode 1"),
                    call("add_milestone", name="Launched"),
                    call("add_task", milestone_ref="M4", title="Publish episode 1"),
                ],
            ),
            AIMessage(content="Two milestones, three tasks."),
        ]
    )


@pytest.fixture()
def breakdown_app(app):
    app.run()
    app.sidebar.radio[0].set_value("Project breakdown").run()
    app.text_input(key="bd_name").set_value("Podcast").run()
    app.button(key="bd_start").click().run()
    with patch("agents.pm.decomposition.get_default_chat_model", return_value=_breakdown_model()):
        app.chat_input[0].set_value("break it down").run()
    return app


def test_breakdown_shows_draft_without_saving(breakdown_app) -> None:
    from tools.projects import list_projects

    assert not breakdown_app.exception
    labels = [c.label.strip() for c in breakdown_app.checkbox]
    assert labels == ["1. Pilot recorded", "Buy a microphone", "Record episode 1", "2. Launched", "Publish episode 1"]
    assert breakdown_app.chat_message[-1].markdown[0].value == "Two milestones, three tasks."
    assert list_projects() == []


def test_confirming_breakdown_saves_included_items_then_asks_for_ratings(breakdown_app) -> None:
    from tools.milestones import list_milestones
    from tools.projects import list_projects

    breakdown_app.checkbox[2].uncheck().run()  # drop "Record episode 1"
    breakdown_app.button(key="bd_confirm").click().run()

    assert not breakdown_app.exception
    [project] = list_projects()
    milestones = list_milestones(project_id=project.id)
    assert [[t.title for t in m.tasks] for m in milestones] == [["Buy a microphone"], ["Publish episode 1"]]
    assert "Saved 2 milestone(s) and 2 new task(s)" in breakdown_app.success[0].value
    assert len(breakdown_app.selectbox) == 1 + 2 * 2  # project picker + a rating pair per new task


def test_discarding_breakdown_saves_nothing(breakdown_app) -> None:
    from tools.projects import list_projects

    breakdown_app.button(key="bd_discard").click().run()

    assert not breakdown_app.exception
    assert breakdown_app.session_state["bd_draft"] is None
    assert list_projects() == []


def test_breakdown_provider_error_keeps_draft_and_shows_message(breakdown_app) -> None:
    class Failing:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    before = len(breakdown_app.checkbox)
    with patch("agents.pm.decomposition.get_default_chat_model", return_value=Failing()):
        breakdown_app.chat_input[0].set_value("add more").run()

    assert not breakdown_app.exception
    assert "RESOURCE_EXHAUSTED" in breakdown_app.error[0].value
    assert len(breakdown_app.checkbox) == before


# --- This week (review) mode -------------------------------------------------

from datetime import timedelta  # noqa: E402

REVIEW_MONDAY = date(2026, 9, 14)


@pytest.fixture()
def review_app(app, monkeypatch):
    """A week with one task goal (1 of 2 done) and one habit goal (0 of 2)."""
    from tools.habits import create_habit
    from tools.tasks import complete_task, create_task
    from tools.weekly_goals import create_weekly_goal

    # Pin "today" to a Friday inside the reviewed week.
    monkeypatch.setattr("agents.pm.review.today", lambda: REVIEW_MONDAY + timedelta(days=4))

    habit = create_habit("Gym")
    create_weekly_goal(REVIEW_MONDAY, "Gym twice", habit_id=habit.id, target_count=2)
    a, b = create_task("Update pricing copy"), create_task("Fix signup form")
    create_weekly_goal(REVIEW_MONDAY, "Ship pricing", task_ids=[a.id, b.id])
    complete_task(a.id, completed_at=datetime(2026, 9, 15, tzinfo=timezone.utc))

    app.run()
    app.sidebar.radio[0].set_value("This week").run()
    app.habit_id, app.task_ids = habit.id, (a.id, b.id)
    return app


def test_this_week_shows_progress_and_completion_controls(review_app) -> None:
    labels = [c.label for c in review_app.checkbox]
    assert not review_app.exception
    assert labels[:7] == ["Mo 14", "Tu 15", "We 16", "Th 17", "Fr 18", "Sa 19", "Su 20"]
    assert labels[7:9] == ["Update pricing copy", "Fix signup form"]
    assert [c.value for c in review_app.checkbox[7:9]] == [True, False]
    # future days can't be logged
    assert [c.disabled for c in review_app.checkbox[:7]] == [False] * 5 + [True, True]
    assert any("Gym twice: 0/2 completion(s)" in m.value for m in review_app.markdown)
    assert any("Ship pricing: 1/2 task(s) done" in m.value for m in review_app.markdown)


def test_ticking_a_task_completes_it_and_unticking_reopens_it(review_app) -> None:
    from db.models import TaskStatus
    from tools.tasks import get_task

    review_app.checkbox[8].check().run()  # "Fix signup form"

    assert not review_app.exception
    assert get_task(review_app.task_ids[1]).status == TaskStatus.DONE
    assert any("Ship pricing: 2/2 task(s) done" in m.value for m in review_app.markdown)

    review_app.checkbox[7].uncheck().run()  # reopen "Update pricing copy"
    assert get_task(review_app.task_ids[0]).status == TaskStatus.TODO
    assert get_task(review_app.task_ids[0]).completed_at is None


def test_ticking_a_habit_day_logs_it(review_app) -> None:
    from tools.habits import get_habit_logs

    review_app.checkbox[1].check().run()  # Tuesday

    assert not review_app.exception
    logs = get_habit_logs(review_app.habit_id, REVIEW_MONDAY, REVIEW_MONDAY + timedelta(days=6))
    assert [log.log_date for log in logs] == [date(2026, 9, 15)]

    review_app.checkbox[1].uncheck().run()
    assert get_habit_logs(review_app.habit_id, REVIEW_MONDAY, REVIEW_MONDAY + timedelta(days=6)) == []


def test_generating_the_review_saves_notes_and_status(review_app) -> None:
    from db.models import WeeklyGoalStatus
    from tools.weekly_goals import list_weekly_goals

    model = MagicMock()
    model.invoke.return_value = AIMessage(content="A steady week overall.")
    with patch("agents.pm.review.get_default_chat_model", return_value=model):
        review_app.button(key="rv_generate").click().run()

    assert not review_app.exception
    assert any("A steady week overall." in m.value for m in review_app.markdown)
    goals = list_weekly_goals(week_start=REVIEW_MONDAY)
    assert [g.status for g in goals] == [WeeklyGoalStatus.MISSED, WeeklyGoalStatus.MISSED]
    assert goals[0].review_notes == "Gym twice: 0/2 completion(s)"
    assert all(g.reviewed_at is not None for g in goals)


def test_review_provider_error_saves_nothing(review_app) -> None:
    from db.models import WeeklyGoalStatus
    from tools.weekly_goals import list_weekly_goals

    model = MagicMock()
    model.invoke.side_effect = RuntimeError("503 UNAVAILABLE")
    with patch("agents.pm.review.get_default_chat_model", return_value=model):
        review_app.button(key="rv_generate").click().run()

    assert not review_app.exception
    assert "503 UNAVAILABLE" in review_app.error[0].value
    assert [g.status for g in list_weekly_goals()] == [WeeklyGoalStatus.PLANNED] * 2


def test_carrying_a_missed_goal_into_next_week(review_app) -> None:
    from db.models import WeeklyGoalStatus
    from tools.weekly_goals import list_weekly_goals

    carry_boxes = [c for c in review_app.checkbox if c.label == "Ship pricing"]
    carry_boxes[0].check().run()
    review_app.button(key="rv_carry").click().run()

    assert not review_app.exception
    next_week = list_weekly_goals(week_start=REVIEW_MONDAY + timedelta(days=7))
    assert [g.description for g in next_week] == ["Ship pricing"]
    assert [t.title for t in next_week[0].tasks] == ["Fix signup form"]  # only the unfinished one
    original = [g for g in list_weekly_goals(week_start=REVIEW_MONDAY) if g.description == "Ship pricing"][0]
    assert original.status == WeeklyGoalStatus.CARRIED_OVER
