"""Backlog capture — the first endpoint that calls a model."""
from __future__ import annotations

from fastapi import APIRouter, status

from agents.pm.backlog import capture_backlog_from_text
from api.errors import model_call
from api.schemas import CaptureIn, TaskOut

router = APIRouter(prefix="/api/backlog", tags=["backlog"])


@router.post("/capture", response_model=list[TaskOut], status_code=status.HTTP_201_CREATED)
def capture_endpoint(body: CaptureIn) -> list[TaskOut]:
    """**Model call (one).** Split freeform text into tasks and save them unrated.

    The model runs before anything is written, so a provider failure or
    malformed output creates nothing (FR-5) and comes back as a `provider`
    error. An empty list means the text held no tasks — not an error.
    """
    with model_call():
        tasks = capture_backlog_from_text(body.text)
    return [TaskOut.model_validate(t) for t in tasks]
