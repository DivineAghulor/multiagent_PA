"""The week screen and stored review history — all deterministic, no model call.

Generating review prose is a model call and lands in W4; what is here is the
facts (`build_week_review`) plus whatever narrative was already saved.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from agents.pm.review import GoalReview, WeekReview, build_week_review, render_review_facts
from api.deps import this_week_start, week_start_param
from api.schemas import (
    GoalProgressOut,
    HabitOut,
    TaskOut,
    WeeklyGoalOut,
    WeeklyReviewOut,
    WeekOut,
)
from tools.reviews import get_week_summary, list_week_summaries

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


@router.get("/reviews", response_model=list[WeeklyReviewOut])
def list_reviews_endpoint(limit: int | None = Query(None, ge=1, le=200)) -> list[WeeklyReviewOut]:
    """Stored week summaries, newest week first — the review history view.

    Each row carries the counts the prose was written against; they are not
    recomputed here (requirements §6.7 SCH-2).
    """
    return [WeeklyReviewOut.model_validate(r) for r in list_week_summaries(limit=limit)]
