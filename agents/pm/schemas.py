"""LLM-facing extraction schemas for the PM sub-agent.

Deliberately separate from db.models.Task: the model only ever produces
title/description/project_hint, never importance/urgency/id/status.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedTask(BaseModel):
    """A single actionable task identified in the user's text."""

    title: str = Field(description="Short imperative summary, e.g. 'Fix login bug'")
    description: str | None = Field(default=None, description="Extra detail, only if given")
    project_hint: str | None = Field(
        default=None, description="Project this task belongs to, if implied, else null"
    )


class ExtractedTaskBatch(BaseModel):
    """All tasks identified in one piece of user text."""

    tasks: list[ExtractedTask]
