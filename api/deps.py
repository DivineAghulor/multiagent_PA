"""Shared request dependencies. Nothing here touches the database directly."""
from __future__ import annotations

from datetime import date

from fastapi import Path

from agents.pm.review import current_week_start, today
from api.errors import InvalidRequestError


def server_today() -> date:
    """The server's date. API-3: never the browser clock, so the UI, the agents
    and the tests all agree on which week is "this" week."""
    return today()


def this_week_start() -> date:
    return current_week_start(server_today())


def week_start_param(
    week_start: date = Path(description="Monday of the week, ISO YYYY-MM-DD"),
) -> date:
    """Weeks are keyed by their Monday throughout (WeeklyGoal.week_start,
    WeeklyReview.week_start). A non-Monday is rejected rather than snapped to
    one, so a wrong date never silently reads a different week."""
    if week_start.weekday() != 0:
        raise InvalidRequestError(
            f"week_start must be a Monday; {week_start.isoformat()} is a "
            f"{week_start.strftime('%A')}"
        )
    return week_start
