"""The week screen, its review, carry-over, and stored review history.

Everything here is deterministic except drafting the review's prose, which is
one model call and writes nothing. Saving is a separate request that sends
the prose back, so what gets stored is exactly what the user read (FR-19/20).
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from agents.pm.review import (
    GoalReview,
    WeekReview,
    build_week_review,
    render_review_facts,
    save_review,
    summarize_week,
)
from api.deps import this_week_start, week_start_param
from api.errors import NotFoundError, model_call
from api.schemas import (
    CarryOverIn,
    GoalProgressOut,
    HabitOut,
    ReviewDraftOut,
    ReviewSaveIn,
    TaskOut,
    WeeklyGoalOut,
    WeeklyReviewOut,
    WeekOut,
)
from tools.reviews import get_week_summary, list_week_summaries
from tools.weekly_goals import carry_over_weekly_goal, get_weekly_goal

router = APIRouter(prefix="/api", tags=["weeks"])


def _goal_progress(g: GoalReview) -> GoalProgressOut:
    # goal.tasks/goal.habit are eager-loaded by tools.weekly_goals; nothing
    # here triggers a lazy load on a detached instance.
    return GoalProgressOut(
        goal=WeeklyGoalOut.model_validate(g.goal),
        kind=g.kind,
        completed=g.completed,
        target=g.target,
        done=g.done,
        outstanding=g.outstanding,
        status=g.status,
        achieved=g.achieved,
        headline=g.headline(),
        tasks=[TaskOut.model_validate(t) for t in g.goal.tasks],
        habit=HabitOut.model_validate(g.goal.habit) if g.goal.habit else None,
    )


def _week_out(review: WeekReview) -> WeekOut:
    stored = get_week_summary(review.week_start)
    return WeekOut(
        week_start=review.week_start,
        week_end=review.week_end,
        goals=[_goal_progress(g) for g in review.goals],
        unplanned_done=[TaskOut.model_validate(t) for t in review.unplanned_done],
        achieved_count=review.achieved_count,
        measurable_count=review.measurable_count,
        facts=render_review_facts(review),
        review=WeeklyReviewOut.model_validate(stored) if stored else None,
    )


@router.get("/weeks/current", response_model=WeekOut)
def current_week_endpoint() -> WeekOut:
    """This week, resolved from the server's date rather than the browser's."""
    return _week_out(build_week_review(this_week_start()))


@router.get("/weeks/{week_start}", response_model=WeekOut)
def week_endpoint(week_start: date = Depends(week_start_param)) -> WeekOut:
    return _week_out(build_week_review(week_start))


@router.post("/weeks/{week_start}/review/draft", response_model=ReviewDraftOut)
def draft_review_endpoint(week_start: date = Depends(week_start_param)) -> ReviewDraftOut:
    """**Model call (one).** Prose over the week's computed facts, for the user
    to read before saving. Writes nothing, so a failure loses nothing (FR-19)."""
    with model_call():
        summary = summarize_week(build_week_review(week_start))
    return ReviewDraftOut(summary=summary)


@router.post("/weeks/{week_start}/review", response_model=WeekOut)
def save_review_endpoint(body: ReviewSaveIn, week_start: date = Depends(week_start_param)) -> WeekOut:
    """Record the review: per-goal notes and ACHIEVED/MISSED, and — when
    `summary` is given — the narrative with the counts it was written against
    (FR-20, FR-22). No model call. Re-saving a week overwrites its own review."""
    save_review(build_week_review(week_start), body.summary)
    return _week_out(build_week_review(week_start))


@router.post("/weekly-goals/{goal_id}/carry-over", response_model=WeeklyGoalOut)
def carry_over_endpoint(goal_id: int, body: CarryOverIn) -> WeeklyGoalOut:
    """Copy a goal into a later week with its unfinished tasks; the original
    becomes carried_over (FR-21). Only ever on an explicit user action."""
    if get_weekly_goal(goal_id) is None:
        raise NotFoundError("Weekly goal", goal_id)
    return WeeklyGoalOut.model_validate(carry_over_weekly_goal(goal_id, body.new_week_start))


@router.get("/reviews", response_model=list[WeeklyReviewOut])
def list_reviews_endpoint(limit: int | None = Query(None, ge=1, le=200)) -> list[WeeklyReviewOut]:
    """Stored week summaries, newest week first — the review history view.

    Each row carries the counts the prose was written against; they are not
    recomputed here (requirements §6.7 SCH-2).
    """
    return [WeeklyReviewOut.model_validate(r) for r in list_week_summaries(limit=limit)]
