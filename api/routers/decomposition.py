"""Project decomposition: a draft session whose turns stream progress over SSE.

A turn is the expensive call in this app (14-22 model calls measured, FR-15),
so it streams: a `progress` event before every model call and after every tool
call, then one `result` event with the whole session, or one `error` event.
Errors after the stream has started can't change the HTTP status, so they
arrive in-band with the same `{type, message}` shape as the error envelope.

Each turn runs on a copy of the draft, which replaces the session's draft only
when the turn completes. A failed or cancelled turn therefore leaves the draft
exactly as it was — and the M/T refs the model uses stay stable (S-2).
Cancelling is closing the connection: the running turn stops before its next
model call instead of spending tokens on a result nobody will see.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import BaseMessage, HumanMessage

from agents.pm.decomposition import (
    DecompositionDraft,
    TurnProgress,
    confirm_decomposition,
    run_decomposition_turn,
    start_existing_project_draft,
    start_new_project_draft,
)
from api.deps import server_today
from api.errors import ApiError, NotFoundError, provider_message, require_provider
from api.schemas import (
    ChatMessageOut,
    DecompositionConfirmIn,
    DecompositionMessageIn,
    DecompositionResultOut,
    DecompositionSessionOut,
    DecompositionStartIn,
    DraftMilestoneOut,
    DraftOut,
    DraftTaskOut,
    MilestoneOut,
    ProjectOut,
    TaskOut,
    TaskRefOut,
    TurnStatsOut,
)
from api.sessions import DraftSession, DraftStore, get_draft_store
from tools.projects import get_project

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/decomposition", tags=["decomposition"])

KIND = "decomposition"


@dataclass
class DecompositionState:
    draft: DecompositionDraft
    history: list[BaseMessage] = field(default_factory=list)  # incl. tool traffic; what the model sees
    transcript: list[tuple[str, str]] = field(default_factory=list)  # what the user sees
    last_turn: TurnStatsOut | None = None


class TurnCancelled(Exception):
    """Raised from the progress callback once the client has gone away."""


def _draft_out(draft: DecompositionDraft) -> DraftOut:
    return DraftOut(
        project_name=draft.project_name,
        project_description=draft.project_description,
        project_id=draft.project_id,
        milestones=[
            DraftMilestoneOut(
                ref=m.ref,
                name=m.name,
                description=m.description,
                due_date=m.due_date,
                existing_id=m.existing_id,
                existing_task_titles=list(m.existing_task_titles),
                tasks=[
                    DraftTaskOut(
                        ref=t.ref,
                        title=t.title,
                        description=t.description,
                        existing_task_id=t.existing_task_id,
                    )
                    for t in m.tasks
                ],
            )
            for m in draft.milestones
        ],
        eligible_tasks=[TaskRefOut(id=i, title=title) for i, title in draft.eligible_tasks.items()],
        new_task_count=draft.new_task_count,
    )


def _session_out(session: DraftSession) -> DecompositionSessionOut:
    state: DecompositionState = session.payload
    return DecompositionSessionOut(
        session_id=session.id,
        draft=_draft_out(state.draft),
        messages=[ChatMessageOut(role=role, text=text) for role, text in state.transcript],
        last_turn=state.last_turn,
    )


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _progress_data(p: TurnProgress) -> dict:
    return {"phase": p.phase, "step": p.step, "tool_calls": p.tool_calls, "tool": p.tool}


async def _turn_events(
    store: DraftStore, session: DraftSession, body: DecompositionMessageIn
) -> AsyncIterator[str]:
    try:
        hold = store.exclusive(session)
        hold.__enter__()
    except ApiError as exc:
        yield _sse("error", {"type": exc.type, "message": exc.message})
        return

    loop = asyncio.get_running_loop()
    events: asyncio.Queue[TurnProgress] = asyncio.Queue()
    cancelled = threading.Event()
    state: DecompositionState = session.payload
    text = body.text
    # A copy, committed only if the turn completes. `without` copies too, and
    # drops what the user unticked so the model doesn't build on it.
    excluded = (set(body.exclude_milestone_refs), set(body.exclude_task_refs))
    draft = state.draft.without(*excluded) if any(excluded) else copy.deepcopy(state.draft)
    history = [*state.history, HumanMessage(text)]

    def on_progress(p: TurnProgress) -> None:
        # Runs on the worker thread.
        if cancelled.is_set():
            raise TurnCancelled
        loop.call_soon_threadsafe(events.put_nowait, p)

    work = asyncio.ensure_future(
        asyncio.to_thread(run_decomposition_turn, history, draft, server_today(), on_progress=on_progress)
    )
    try:
        while not work.done():
            getter = asyncio.ensure_future(events.get())
            done, _ = await asyncio.wait({getter, work}, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                yield _sse("progress", _progress_data(getter.result()))
            else:
                getter.cancel()
        while not events.empty():
            yield _sse("progress", _progress_data(events.get_nowait()))

        result = work.result()
        state.draft = draft
        state.history = result.history
        state.transcript = [*state.transcript, ("user", text), ("assistant", result.reply)]
        state.last_turn = TurnStatsOut(steps=result.steps, tool_calls=result.tool_calls, hit_limit=result.hit_limit)
        yield _sse("result", _session_out(session).model_dump(mode="json"))
    except TurnCancelled:
        return
    except Exception as exc:  # noqa: BLE001 — reported in-band; the status line is already sent
        logger.exception("decomposition turn failed")
        yield _sse("error", {"type": "provider", "message": provider_message(exc)})
    finally:
        # Also reached when the client disconnects mid-stream: tell the worker
        # to stop at its next step. It works on a copy, so releasing the
        # session now can't let it touch the draft.
        cancelled.set()
        if not work.done():
            # Nobody will read the abandoned turn's outcome (usually
            # TurnCancelled); retrieve it so asyncio doesn't log it as lost.
            work.add_done_callback(lambda f: f.cancelled() or f.exception())
        hold.__exit__(None, None, None)


@router.post("/sessions", response_model=DecompositionSessionOut, status_code=status.HTTP_201_CREATED)
def start_decomposition_endpoint(
    body: DecompositionStartIn, store: DraftStore = Depends(get_draft_store)
) -> DecompositionSessionOut:
    """Start a draft for an existing project (its milestones and attachable
    backlog tasks pre-loaded) or a new one (created only on confirm). No model call."""
    if body.project_id is not None:
        if get_project(body.project_id) is None:
            raise NotFoundError("Project", body.project_id)
        draft = start_existing_project_draft(body.project_id)
    else:
        draft = start_new_project_draft(body.name or "", body.description)
    return _session_out(store.create(KIND, DecompositionState(draft=draft)))


@router.get("/sessions/{session_id}", response_model=DecompositionSessionOut)
def get_decomposition_endpoint(
    session_id: str, store: DraftStore = Depends(get_draft_store)
) -> DecompositionSessionOut:
    return _session_out(store.get(session_id, KIND))


@router.post(
    "/sessions/{session_id}/messages",
    responses={200: {"content": {"text/event-stream": {}}, "description": "progress, then result or error"}},
)
def decomposition_message_endpoint(
    session_id: str, body: DecompositionMessageIn, store: DraftStore = Depends(get_draft_store)
) -> StreamingResponse:
    """**Model calls (many), streamed.** Runs one decomposition turn.

    New items listed in `exclude_*` are removed from the draft first.

    Events: `progress` `{phase, step, tool_calls, tool}` as the loop runs;
    then either `result` (the whole session, with `last_turn` stats and
    `hit_limit`) or `error` `{type, message}`. A missing session or missing
    provider key fails before the stream starts, as a normal JSON error.
    """
    session = store.get(session_id, KIND)
    require_provider()
    return StreamingResponse(
        _turn_events(store, session, body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{session_id}/confirm", response_model=DecompositionResultOut)
def confirm_decomposition_endpoint(
    session_id: str,
    body: DecompositionConfirmIn,
    store: DraftStore = Depends(get_draft_store),
) -> DecompositionResultOut:
    """Write the draft, minus any excluded new items, and end the session.

    confirm_decomposition's guards ("adds nothing", "new milestone(s) without
    tasks") come back as a 400 with their message and keep the session: both
    are fixed by another turn or by including more items (FR-14).
    """
    session = store.get(session_id, KIND)
    with store.exclusive(session):
        state: DecompositionState = session.payload
        draft = state.draft.without(set(body.exclude_milestone_refs), set(body.exclude_task_refs))
        result = confirm_decomposition(draft)
    store.delete(session_id)
    return DecompositionResultOut(
        project=ProjectOut.model_validate(result.project),
        milestones=[MilestoneOut.model_validate(m) for m in result.milestones],
        new_tasks=[TaskOut.model_validate(t) for t in result.new_tasks],
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_decomposition_endpoint(
    session_id: str, store: DraftStore = Depends(get_draft_store)
) -> Response:
    """Discard the draft. A no-op for a session that's already gone."""
    store.delete(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
