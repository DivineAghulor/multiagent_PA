"""Read-only planning context.

The planning conversation itself (sessions, turns, confirmation) is W3. This
endpoint exists now because the context is pure database work: showing it
before a session starts lets the user see exactly what the model will be given
without spending a call (FR-6).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from agents.pm.planning import (
    load_planning_context,
    planning_week_start,
    render_planning_context,
)
from api.deps import server_today
from api.errors import InvalidRequestError
from api.schemas import (
    HabitOut,
    PlanningContextOut,
    ProjectOut,
    TaskOut,
    WeeklyGoalOut,
)

router = APIRouter(prefix="/api/planning", tags=["planning"])


@router.get("/context", response_model=PlanningContextOut)
def planning_context_endpoint(week_start: date | None = Query(None)) -> PlanningContextOut:
    """Defaults to the week planning would target now — this week, or next week
    at the weekend (`planning_week_start`)."""
    if week_start is None:
        week_start = planning_week_start(server_today())
    elif week_start.weekday() != 0:
        raise InvalidRequestError(
            f"week_start must be a Monday; {week_start.isoformat()} is a "
            f"{week_start.strftime('%A')}"
        )
    ctx = load_planning_context(week_start)
    return PlanningContextOut(
        week_start=ctx.week_start,
        backlog=[TaskOut.model_validate(t) for t in ctx.backlog],
        projects=[ProjectOut.model_validate(p) for p in ctx.projects],
        habits=[HabitOut.model_validate(h) for h in ctx.habits],
        existing_goals=[WeeklyGoalOut.model_validate(g) for g in ctx.existing_goals],
        rendered=render_planning_context(ctx),
    )
