"""Weekly planning: the read-only context, and the planning conversation.

A conversation is a draft session (api/sessions.py): nothing reaches the
database until confirm, which writes the WeeklyGoal rows and ends the session
(FR-9). Every turn's proposal goes through sanitize_proposal, and its warnings
go back to the client (S-6).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status

from agents.pm.planning import (
    PlanningContext,
    confirm_weekly_plan,
    load_planning_context,
    planning_week_start,
    render_planning_context,
    run_planning_turn,
)
from agents.pm.schemas import WeeklyPlanProposal
from api.deps import server_today
from api.errors import InvalidRequestError, model_call
from api.schemas import (
    ChatMessageOut,
    HabitOut,
    MessageIn,
    PlanConfirmIn,
    PlanningContextOut,
    PlanningSessionOut,
    PlanningStartIn,
    ProjectOut,
    ProposalGoalOut,
    ProposalOut,
    TaskOut,
    TaskRefOut,
    WeeklyGoalOut,
)
from api.sessions import DraftSession, DraftStore, get_draft_store

router = APIRouter(prefix="/api/planning", tags=["planning"])

KIND = "planning"


@dataclass
class PlanningState:
    ctx: PlanningContext
    history: list[tuple[str, str]] = field(default_factory=list)  # what the model sees
    transcript: list[tuple[str, str]] = field(default_factory=list)  # what the user sees
    proposal: WeeklyPlanProposal | None = None
    warnings: list[str] = field(default_factory=list)


def _monday(week_start: date) -> date:
    if week_start.weekday() != 0:
        raise InvalidRequestError(
            f"week_start must be a Monday; {week_start.isoformat()} is a "
            f"{week_start.strftime('%A')}"
        )
    return week_start


def _context_out(ctx: PlanningContext) -> PlanningContextOut:
    return PlanningContextOut(
        week_start=ctx.week_start,
        backlog=[TaskOut.model_validate(t) for t in ctx.backlog],
        projects=[ProjectOut.model_validate(p) for p in ctx.projects],
        habits=[HabitOut.model_validate(h) for h in ctx.habits],
        existing_goals=[WeeklyGoalOut.model_validate(g) for g in ctx.existing_goals],
        rendered=render_planning_context(ctx),
    )


def _proposal_out(proposal: WeeklyPlanProposal, ctx: PlanningContext) -> ProposalOut:
    projects = {p.id: p.name for p in ctx.projects}
    habits = {h.id: h.name for h in ctx.habits}
    tasks = {t.id: t.title for t in ctx.backlog}
    return ProposalOut(
        reply=proposal.reply,
        goals=[
            ProposalGoalOut(
                description=g.description,
                project_id=g.project_id,
                project_name=projects.get(g.project_id) if g.project_id is not None else None,
                habit_id=g.habit_id,
                habit_name=habits.get(g.habit_id) if g.habit_id is not None else None,
                target_count=g.target_count,
                tasks=[TaskRefOut(id=tid, title=tasks.get(tid, f"Task {tid}")) for tid in g.task_ids],
            )
            for g in proposal.goals
        ],
    )


def _session_out(session: DraftSession) -> PlanningSessionOut:
    state: PlanningState = session.payload
    return PlanningSessionOut(
        session_id=session.id,
        week_start=state.ctx.week_start,
        context=_context_out(state.ctx),
        messages=[ChatMessageOut(role=role, text=text) for role, text in state.transcript],
        proposal=_proposal_out(state.proposal, state.ctx) if state.proposal else None,
        warnings=state.warnings,
    )


@router.get("/context", response_model=PlanningContextOut)
def planning_context_endpoint(week_start: date | None = Query(None)) -> PlanningContextOut:
    """Defaults to the week planning would target now — this week, or next week
    at the weekend (`planning_week_start`). No model call: shows exactly what
    the model would be given before any call is spent (FR-6)."""
    week = planning_week_start(server_today()) if week_start is None else _monday(week_start)
    return _context_out(load_planning_context(week))


@router.post("/sessions", response_model=PlanningSessionOut, status_code=status.HTTP_201_CREATED)
def start_planning_endpoint(
    body: PlanningStartIn, store: DraftStore = Depends(get_draft_store)
) -> PlanningSessionOut:
    """Open a planning conversation for a week. No model call yet."""
    week = planning_week_start(server_today()) if body.week_start is None else _monday(body.week_start)
    session = store.create(KIND, PlanningState(ctx=load_planning_context(week)))
    return _session_out(session)


@router.get("/sessions/{session_id}", response_model=PlanningSessionOut)
def get_planning_endpoint(
    session_id: str, store: DraftStore = Depends(get_draft_store)
) -> PlanningSessionOut:
    return _session_out(store.get(session_id, KIND))


@router.post("/sessions/{session_id}/messages", response_model=PlanningSessionOut)
def planning_message_endpoint(
    session_id: str, body: MessageIn, store: DraftStore = Depends(get_draft_store)
) -> PlanningSessionOut:
    """**Model call (one).** Run a planning turn and return the whole session:
    the reply, the complete sanitised plan, and what sanitising changed.

    The context is reloaded first, so a task captured or completed since the
    last turn is reflected rather than proposed from a stale list. A failed
    call leaves the conversation exactly as it was.
    """
    session = store.get(session_id, KIND)
    with store.exclusive(session):
        state: PlanningState = session.payload
        ctx = load_planning_context(state.ctx.week_start)
        with model_call():
            turn = run_planning_turn(state.history, ctx, body.text)
        state.ctx = ctx
        state.history = turn.history
        state.transcript = [*state.transcript, ("user", body.text), ("assistant", turn.proposal.reply)]
        state.proposal = turn.proposal
        state.warnings = turn.warnings
    return _session_out(session)


@router.post("/sessions/{session_id}/confirm", response_model=list[WeeklyGoalOut])
def confirm_planning_endpoint(
    session_id: str,
    body: PlanConfirmIn | None = None,
    store: DraftStore = Depends(get_draft_store),
) -> list[WeeklyGoalOut]:
    """Write the current plan's goals and end the session (FR-9).

    With `goals`, only those are written, reworded and re-targeted as the user
    edited them. confirm_weekly_plan re-checks the plan against the live
    backlog; if a task in it has since been taken or deleted, nothing is
    written, the session is kept, and another turn can repair the plan.
    """
    session = store.get(session_id, KIND)
    with store.exclusive(session):
        state: PlanningState = session.payload
        if state.proposal is None or not state.proposal.goals:
            raise InvalidRequestError("There is no plan to confirm yet. Describe the week you want first.")
        proposed = state.proposal.goals
        if body is not None and body.goals is not None:
            if bad := [e.index for e in body.goals if e.index >= len(proposed)]:
                raise InvalidRequestError(f"The plan has no goal at position(s) {bad}")
            proposed = [
                proposed[e.index].model_copy(update={"description": e.description, "target_count": e.target_count})
                for e in body.goals
            ]
            if not proposed:
                raise InvalidRequestError("No goals selected, so there is nothing to save.")
        goals = confirm_weekly_plan(state.ctx.week_start, proposed)
    store.delete(session_id)
    return [WeeklyGoalOut.model_validate(g) for g in goals]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_planning_endpoint(session_id: str, store: DraftStore = Depends(get_draft_store)) -> Response:
    """Discard the conversation. A no-op for a session that's already gone."""
    store.delete(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
