"""Typed CRUD tools for WeeklyReview — the persisted narrative for a week."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select

from db.models import WeeklyReview
from db.session import get_session


def save_week_summary(
    week_start: date,
    summary: str,
    achieved_count: int,
    measurable_count: int,
    unplanned_count: int,
) -> WeeklyReview:
    """Upsert the summary for a week. Re-reviewing a week overwrites its row,
    matching record_weekly_review's re-runnable behaviour; there is no history."""
    if not summary.strip():
        raise ValueError("summary is empty")
    with get_session() as session:
        review = session.scalar(
            select(WeeklyReview).where(WeeklyReview.week_start == week_start)
        )
        if review is None:
            review = WeeklyReview(week_start=week_start)
            session.add(review)
        review.summary = summary.strip()
        review.achieved_count = achieved_count
        review.measurable_count = measurable_count
        review.unplanned_count = unplanned_count
        review.generated_at = datetime.now(timezone.utc)
        session.flush()
        session.refresh(review)
        return review


def get_week_summary(week_start: date) -> WeeklyReview | None:
    with get_session() as session:
        return session.scalar(
            select(WeeklyReview).where(WeeklyReview.week_start == week_start)
        )


def list_week_summaries(limit: int | None = None) -> list[WeeklyReview]:
    """Stored summaries, most recent week first."""
    with get_session() as session:
        stmt = select(WeeklyReview).order_by(WeeklyReview.week_start.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(session.scalars(stmt))


def delete_week_summary(week_start: date) -> None:
    with get_session() as session:
        review = session.scalar(
            select(WeeklyReview).where(WeeklyReview.week_start == week_start)
        )
        if review is not None:
            session.delete(review)
