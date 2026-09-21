"""Unit tests for weekly planning. The LLM is always mocked — zero live API calls."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from agents.pm.planning import (
    confirm_weekly_plan,
    load_planning_context,
    planning_week_start,
    propose_weekly_plan,
    render_planning_context,
    sanitize_proposal,
)
from agents.pm.schemas import ProposedGoal, WeeklyPlanProposal
from db.models import HabitFrequency, TaskStatus
from tools.habits import create_habit
from tools.projects import create_project
from tools.tasks import create_task, get_task, update_task_priority
from tools.weekly_goals import create_weekly_goal, list_weekly_goals

MONDAY = date(2026, 9, 21)


@pytest.fixture()
def seeded(db_session):
    website = create_project("Website")
    gym = create_habit("Gym", frequency=HabitFrequency.WEEKLY, target_per_period=3)
    pricing = create_task("Update pricing page copy", project_id=website.id)
    update_task_priority(pricing.id, importance=4, urgency=3)
    dentist = create_task("Call the dentist")
    return {"website": website, "gym": gym, "pricing": pricing, "dentist": dentist}


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 9, 21), date(2026, 9, 21)),  # Monday -> this week
        (date(2026, 9, 25), date(2026, 9, 21)),  # Friday -> this week
        (date(2026, 9, 26), date(2026, 9, 28)),  # Saturday -> next week
        (date(2026, 9, 27), date(2026, 9, 28)),  # Sunday -> next week
    ],
)
def test_planning_week_start(today, expected) -> None:
    assert planning_week_start(today) == expected


def test_context_excludes_tasks_already_linked_to_a_goal(seeded) -> None:
    create_weekly_goal(MONDAY, "Dentist", task_ids=[seeded["dentist"].id])

    ctx = load_planning_context(MONDAY)

    assert [t.id for t in ctx.backlog] == [seeded["pricing"].id]
    assert [g.description for g in ctx.existing_goals] == ["Dentist"]


def test_render_context_shows_ids_ratings_and_existing_goals(seeded) -> None:
    create_weekly_goal(MONDAY, "Already here")
    text = render_planning_context(load_planning_context(MONDAY))

    assert f"[task {seeded['pricing'].id}] Update pricing page copy" in text
    assert "importance 4/4, urgency 3/4" in text
    assert f"project: Website (id {seeded['website'].id})" in text
    assert f"[habit {seeded['gym'].id}] Gym (weekly, 3 per period)" in text
    assert "- Already here" in text
    assert "2026-09-21" in text


def test_propose_weekly_plan_sends_context_and_full_history(seeded) -> None:
    expected = WeeklyPlanProposal(reply="Here's a plan.", goals=[])
    model = MagicMock()
    model.invoke.return_value = expected
    history = [("user", "gym 3x"), ("assistant", "ok"), ("user", "and the pricing page")]

    with patch("agents.pm.planning.get_structured_model", return_value=model) as factory:
        result = propose_weekly_plan(history, load_planning_context(MONDAY))

    assert result is expected
    factory.assert_called_once_with(WeeklyPlanProposal)  # provider-agnostic structured output
    messages = model.invoke.call_args.args[0]
    assert messages[0][0] == "system"
    assert "Update pricing page copy" in messages[0][1]
    assert messages[1:] == history


def test_sanitize_drops_hallucinated_and_duplicate_ids(seeded) -> None:
    ctx = load_planning_context(MONDAY)
    p, g, t = seeded["website"].id, seeded["gym"].id, seeded["pricing"].id
    raw = WeeklyPlanProposal(
        reply="plan",
        goals=[
            ProposedGoal(description="Pricing", project_id=p, task_ids=[t, t, 999]),
            ProposedGoal(description="Pricing again", project_id=424, task_ids=[t]),
            ProposedGoal(description="Gym", project_id=p, habit_id=g, target_count=3),
            ProposedGoal(description="Ghost habit", habit_id=777, target_count=0),
            ProposedGoal(description="   "),
        ],
    )

    clean, warnings = sanitize_proposal(raw, ctx)

    assert [x.description for x in clean.goals] == ["Pricing", "Pricing again", "Gym", "Ghost habit"]
    assert clean.goals[0].task_ids == [t]
    assert clean.goals[1].task_ids == [] and clean.goals[1].project_id is None
    assert (clean.goals[2].habit_id, clean.goals[2].project_id) == (g, None)
    assert clean.goals[3].habit_id is None and clean.goals[3].target_count is None
    assert len(warnings) == 7


def test_sanitize_caps_task_target_at_task_count(seeded) -> None:
    raw = WeeklyPlanProposal(
        reply="", goals=[ProposedGoal(description="Pricing", task_ids=[seeded["pricing"].id], target_count=5)]
    )
    clean, warnings = sanitize_proposal(raw, load_planning_context(MONDAY))
    assert clean.goals[0].target_count == 1
    assert len(warnings) == 1


def test_sanitize_passes_a_clean_proposal_untouched(seeded) -> None:
    raw = WeeklyPlanProposal(
        reply="plan",
        goals=[
            ProposedGoal(description="Gym 3x", habit_id=seeded["gym"].id, target_count=3),
            ProposedGoal(
                description="Pricing", project_id=seeded["website"].id, task_ids=[seeded["pricing"].id]
            ),
        ],
    )
    clean, warnings = sanitize_proposal(raw, load_planning_context(MONDAY))
    assert warnings == []
    assert clean == raw


def test_confirm_weekly_plan_writes_goals_and_links_tasks(seeded) -> None:
    goals = [
        ProposedGoal(description="Gym 3x", habit_id=seeded["gym"].id, target_count=3),
        ProposedGoal(description="Pricing", project_id=seeded["website"].id, task_ids=[seeded["pricing"].id]),
    ]

    created = confirm_weekly_plan(MONDAY, goals)

    assert [g.description for g in created] == ["Gym 3x", "Pricing"]
    assert [g.description for g in list_weekly_goals(week_start=MONDAY)] == ["Gym 3x", "Pricing"]
    pricing = get_task(seeded["pricing"].id)
    assert pricing.weekly_goal_id == created[1].id
    assert pricing.status == TaskStatus.TODO
    assert get_task(seeded["dentist"].id).status == TaskStatus.BACKLOG


def test_confirm_rejects_a_stale_plan_without_writing(seeded) -> None:
    goals = [
        ProposedGoal(description="Gym 3x", habit_id=seeded["gym"].id, target_count=3),
        ProposedGoal(description="Pricing", task_ids=[seeded["pricing"].id]),
    ]
    # the task gets planned elsewhere after the proposal was made
    create_weekly_goal(MONDAY, "Someone else", task_ids=[seeded["pricing"].id])

    with pytest.raises(ValueError, match="out of date"):
        confirm_weekly_plan(MONDAY, goals)
    assert [g.description for g in list_weekly_goals()] == ["Someone else"]
