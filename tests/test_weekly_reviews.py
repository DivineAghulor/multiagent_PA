"""Persistence of the week's narrative summary (tools/reviews.py) and its
wiring into save_review. No model calls anywhere here."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from tools.reviews import (
    delete_week_summary,
    get_week_summary,
    list_week_summaries,
    save_week_summary,
)

MONDAY = date(2026, 9, 14)


def summary_for(week_start: date, text: str = "You had a decent week."):
    return save_week_summary(
        week_start,
        text,
        achieved_count=1,
        measurable_count=2,
        unplanned_count=1,
    )


def test_saving_and_reading_back_a_summary(db_session) -> None:
    saved = summary_for(MONDAY)

    assert saved.week_start == MONDAY
    assert saved.generated_at is not None

    stored = get_week_summary(MONDAY)
    assert stored.summary == "You had a decent week."
    assert (stored.achieved_count, stored.measurable_count, stored.unplanned_count) == (1, 2, 1)


def test_no_summary_for_an_unreviewed_week(db_session) -> None:
    assert get_week_summary(MONDAY) is None


def test_re_reviewing_a_week_overwrites_its_row(db_session) -> None:
    first = summary_for(MONDAY, "First take.")
    second = save_week_summary(
        MONDAY, "Second take.", achieved_count=2, measurable_count=2, unplanned_count=0
    )

    assert second.id == first.id  # upserted, not a second row
    assert len(list_week_summaries()) == 1
    stored = get_week_summary(MONDAY)
    assert stored.summary == "Second take."
    assert stored.achieved_count == 2


def test_empty_summary_is_rejected(db_session) -> None:
    with pytest.raises(ValueError):
        save_week_summary(MONDAY, "   ", achieved_count=0, measurable_count=0, unplanned_count=0)


def test_summaries_are_listed_most_recent_week_first(db_session) -> None:
    summary_for(MONDAY, "This week.")
    summary_for(MONDAY - timedelta(days=7), "Last week.")
    summary_for(MONDAY - timedelta(days=14), "Two weeks ago.")

    assert [r.summary for r in list_week_summaries()] == [
        "This week.",
        "Last week.",
        "Two weeks ago.",
    ]
    assert [r.summary for r in list_week_summaries(limit=2)] == ["This week.", "Last week."]


def test_deleting_a_summary(db_session) -> None:
    summary_for(MONDAY)
    delete_week_summary(MONDAY)
    assert get_week_summary(MONDAY) is None
    delete_week_summary(MONDAY)  # deleting a missing week is a no-op
