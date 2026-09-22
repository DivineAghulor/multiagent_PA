"""Unit tests for the weekly review. Counting is deterministic and tested
directly; the one model call is mocked — zero live API calls."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from agents.pm.review import (
    HABIT,
    QUALITATIVE,
    TASKS,
    build_week_review,
    current_week_start,
    goal_note,
    missed_goals,
    render_review_facts,
    save_review,
    summarize_week,
)
from db.models import HabitFrequency, TaskStatus, WeeklyGoalStatus
from tools.habits import create_habit, get_habit_logs, log_habit_completion, remove_habit_log
from tools.reviews import get_week_summary
from tools.tasks import complete_task, create_task, get_task, list_tasks, reopen_task
from tools.weekly_goals import carry_over_weekly_goal, create_weekly_goal, get_weekly_goal, list_weekly_goals

MONDAY = date(2026, 9, 14)
SUNDAY = date(2026, 9, 20)


def at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)


@pytest.fixture()
def week(db_session):
    """A mixed week: a habit goal (2 of 3), a task goal (2 of 3 done), a
    qualitative goal, plus planned and unplanned work outside it."""
    gym = create_habit("Gym", frequency=HabitFrequency.WEEKLY, target_per_period=3)
    habit_goal = create_weekly_goal(MONDAY, "Gym three times", habit_id=gym.id, target_count=3)
    log_habit_completion(gym.id, MONDAY)
    log_habit_completion(gym.id, MONDAY + timedelta(days=2))
    log_habit_completion(gym.id, MONDAY - timedelta(days=1))  # previous week: must not count

    t1 = create_task("Update pricing copy")
    t2 = create_task("Fix signup form")
    t3 = create_task("Write launch post")
    task_goal = create_weekly_goal(MONDAY, "Ship the pricing page", task_ids=[t1.id, t2.id, t3.id])
    complete_task(t1.id, completed_at=at(MONDAY + timedelta(days=1)))
    complete_task(t2.id, completed_at=at(MONDAY + timedelta(days=3)))

    vague = create_weekly_goal(MONDAY, "Be more focused")

    extra = create_task("Renew passport")
    complete_task(extra.id, completed_at=at(SUNDAY))  # unplanned, inside the week
    old = create_task("Something last week")
    complete_task(old.id, completed_at=at(MONDAY - timedelta(days=3)))  # outside the week

    return {
        "gym": gym,
        "habit_goal": habit_goal,
        "task_goal": task_goal,
        "vague": vague,
        "tasks": (t1, t2, t3),
        "extra": extra,
        "old": old,
    }


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 9, 14), MONDAY),  # Monday
        (date(2026, 9, 18), MONDAY),  # Friday
        (date(2026, 9, 20), MONDAY),  # Sunday stays in the current week
        (date(2026, 9, 21), date(2026, 9, 21)),
    ],
)
def test_current_week_start(today, expected) -> None:
    assert current_week_start(today) == expected


def test_build_week_review_counts_each_goal_kind(week) -> None:
    review = build_week_review(MONDAY)
    habit, tasks, vague = review.goals

    assert (habit.kind, habit.completed, habit.target) == (HABIT, 2, 3)
    assert habit.status == WeeklyGoalStatus.MISSED  # the out-of-week log didn't count
    assert habit.done == ["2026-09-14", "2026-09-16"]

    assert (tasks.kind, tasks.completed, tasks.target) == (TASKS, 2, 3)
    assert tasks.status == WeeklyGoalStatus.MISSED
    assert tasks.done == ["Update pricing copy", "Fix signup form"]
    assert tasks.outstanding == ["Write launch post"]

    assert (vague.kind, vague.status) == (QUALITATIVE, None)
    assert review.measurable_count == 2
    assert review.achieved_count == 0


def test_unplanned_completions_are_scoped_to_the_week(week) -> None:
    review = build_week_review(MONDAY)
    assert [t.title for t in review.unplanned_done] == ["Renew passport"]


def test_task_goal_with_a_lower_target_is_achieved(db_session) -> None:
    a, b = create_task("A"), create_task("B")
    create_weekly_goal(MONDAY, "Two of these", target_count=1, task_ids=[a.id, b.id])
    complete_task(a.id, completed_at=at(MONDAY))

    [goal] = build_week_review(MONDAY).goals
    assert (goal.completed, goal.target, goal.status) == (1, 1, WeeklyGoalStatus.ACHIEVED)


def test_habit_goal_falls_back_to_the_habits_own_target(db_session) -> None:
    habit = create_habit("Reading", frequency=HabitFrequency.DAILY, target_per_period=2)
    create_weekly_goal(MONDAY, "Read", habit_id=habit.id)
    log_habit_completion(habit.id, MONDAY)
    log_habit_completion(habit.id, SUNDAY)

    [goal] = build_week_review(MONDAY).goals
    assert (goal.completed, goal.target, goal.status) == (2, 2, WeeklyGoalStatus.ACHIEVED)


def test_task_completed_without_a_timestamp_still_counts(db_session) -> None:
    from tools.tasks import update_task_status

    t = create_task("No timestamp")
    create_weekly_goal(MONDAY, "Goal", task_ids=[t.id])
    update_task_status(t.id, TaskStatus.DONE)  # status set directly, completed_at stays None

    [goal] = build_week_review(MONDAY).goals
    assert goal.status == WeeklyGoalStatus.ACHIEVED


def test_render_facts_states_real_numbers(week) -> None:
    text = render_review_facts(build_week_review(MONDAY))
    assert "Week of Monday 2026-09-14 to 2026-09-20." in text
    assert "Goals set: 3. Measurable: 2. Achieved: 0." in text
    assert "Gym three times: 2/3 completion(s) [missed]" in text
    assert "Ship the pricing page: 2/3 task(s) done [missed]" in text
    assert "not done: Write launch post" in text
    assert "isn't measurable" in text and "[not measurable]" in text
    assert "Completed this week but not part of any goal:\n- Renew passport" in text


def test_render_facts_with_no_goals(db_session) -> None:
    text = render_review_facts(build_week_review(MONDAY))
    assert "(none were set for this week)" in text
    assert "Nothing was completed outside the planned goals." in text


def test_summarize_week_sends_facts_and_returns_prose(week) -> None:
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="  You had a decent week.  ")

    with patch("agents.pm.review.get_default_chat_model", return_value=model):
        summary = summarize_week(build_week_review(MONDAY))

    assert summary == "You had a decent week."
    system, human = model.invoke.call_args.args[0]
    assert "Never invent or recalculate numbers" in system[1]
    assert "Gym three times: 2/3" in human[1]


def test_save_review_writes_notes_and_status_and_is_idempotent(week) -> None:
    review = build_week_review(MONDAY)

    saved = save_review(review)

    assert len(saved) == 2  # the qualitative goal is skipped
    habit_goal = get_weekly_goal(week["habit_goal"].id)
    assert habit_goal.status == WeeklyGoalStatus.MISSED
    assert habit_goal.review_notes == "Gym three times: 2/3 completion(s)"
    assert habit_goal.reviewed_at is not None
    task_goal = get_weekly_goal(week["task_goal"].id)
    assert "Outstanding: Write launch post" in task_goal.review_notes
    assert get_weekly_goal(week["vague"].id).status == WeeklyGoalStatus.PLANNED

    # finish the outstanding task, re-review: the earlier verdict is replaced
    complete_task(week["tasks"][2].id, completed_at=at(SUNDAY))
    save_review(build_week_review(MONDAY))
    task_goal = get_weekly_goal(week["task_goal"].id)
    assert task_goal.status == WeeklyGoalStatus.ACHIEVED
    assert task_goal.review_notes == "Ship the pricing page: 3/3 task(s) done"


def test_save_review_persists_the_summary_with_the_counts_it_describes(week) -> None:
    review = build_week_review(MONDAY)

    save_review(review, "You had a decent week.")

    stored = get_week_summary(MONDAY)
    assert stored.summary == "You had a decent week."
    # snapshotted, so later completions can't make the prose contradict them
    assert (stored.achieved_count, stored.measurable_count, stored.unplanned_count) == (0, 2, 1)

    complete_task(week["tasks"][2].id, completed_at=at(SUNDAY))
    assert get_week_summary(MONDAY).achieved_count == 0


def test_save_review_without_a_summary_persists_no_narrative(week) -> None:
    save_review(build_week_review(MONDAY))

    assert get_week_summary(MONDAY) is None
    # per-goal notes are still written
    assert get_weekly_goal(week["habit_goal"].id).reviewed_at is not None


def test_re_reviewing_replaces_the_stored_summary(week) -> None:
    save_review(build_week_review(MONDAY), "First take.")
    complete_task(week["tasks"][2].id, completed_at=at(SUNDAY))
    save_review(build_week_review(MONDAY), "Second take.")

    stored = get_week_summary(MONDAY)
    assert stored.summary == "Second take."
    assert stored.achieved_count == 1


def test_missed_goals_lists_only_measurable_misses(week) -> None:
    assert [g.goal.description for g in missed_goals(build_week_review(MONDAY))] == [
        "Gym three times",
        "Ship the pricing page",
    ]


def test_goal_note_for_an_achieved_goal_has_no_outstanding_clause(db_session) -> None:
    t = create_task("Only task")
    create_weekly_goal(MONDAY, "Do it", task_ids=[t.id])
    complete_task(t.id, completed_at=at(MONDAY))
    [goal] = build_week_review(MONDAY).goals
    assert goal_note(goal) == "Do it: 1/1 task(s) done"


# --- carry-over ---------------------------------------------------------------


def test_carry_over_moves_only_unfinished_tasks(week) -> None:
    next_week = MONDAY + timedelta(days=7)

    carried = carry_over_weekly_goal(week["task_goal"].id, next_week)

    assert carried.week_start == next_week
    assert carried.status == WeeklyGoalStatus.PLANNED
    assert [t.title for t in carried.tasks] == ["Write launch post"]
    original = get_weekly_goal(week["task_goal"].id)
    assert original.status == WeeklyGoalStatus.CARRIED_OVER
    assert [t.title for t in original.tasks] == ["Update pricing copy", "Fix signup form"]
    assert build_week_review(MONDAY).goals[1].completed == 2  # history stays truthful


def test_carry_over_copies_habit_goal_settings(week) -> None:
    carried = carry_over_weekly_goal(week["habit_goal"].id, MONDAY + timedelta(days=7))
    assert (carried.habit_id, carried.target_count) == (week["gym"].id, 3)


@pytest.mark.parametrize("target", [date(2026, 9, 15), MONDAY, date(2026, 9, 7)])
def test_carry_over_rejects_bad_target_weeks(week, target) -> None:
    with pytest.raises(ValueError):
        carry_over_weekly_goal(week["task_goal"].id, target)
    assert len(list_weekly_goals()) == 3


# --- completion tools ----------------------------------------------------------


def test_complete_and_reopen_task(db_session) -> None:
    task = create_task("Something")
    done = complete_task(task.id)
    assert done.status == TaskStatus.DONE and done.completed_at is not None

    reopened = reopen_task(task.id)
    assert reopened.status == TaskStatus.TODO and reopened.completed_at is None
    assert get_task(task.id).completed_at is None

    with pytest.raises(ValueError):
        reopen_task(task.id, TaskStatus.DONE)
    with pytest.raises(ValueError):
        complete_task(9999)


def test_habit_logging_is_idempotent_and_removable(db_session) -> None:
    habit = create_habit("Gym")
    log_habit_completion(habit.id, MONDAY)
    log_habit_completion(habit.id, MONDAY, note="second time")  # same day, no duplicate row

    logs = get_habit_logs(habit.id, MONDAY, SUNDAY)
    assert len(logs) == 1 and logs[0].note == "second time"

    remove_habit_log(habit.id, MONDAY)
    assert get_habit_logs(habit.id, MONDAY, SUNDAY) == []
    remove_habit_log(habit.id, MONDAY)  # no-op, no error

    with pytest.raises(ValueError):
        log_habit_completion(9999, MONDAY)


def test_get_habit_logs_is_bounded_by_the_range(db_session) -> None:
    habit = create_habit("Gym")
    for offset in (-1, 0, 6, 7):
        log_habit_completion(habit.id, MONDAY + timedelta(days=offset))

    logs = get_habit_logs(habit.id, MONDAY, SUNDAY)
    assert [log.log_date for log in logs] == [MONDAY, SUNDAY]
    assert len(list_tasks()) == 0
