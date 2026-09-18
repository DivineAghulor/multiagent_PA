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


class ProposedGoal(BaseModel):
    """One goal in a proposed weekly plan. IDs must come from the planning context."""

    description: str = Field(description="Concrete outcome for the week, e.g. 'Ship the pricing page'")
    project_id: int | None = Field(
        default=None, description="ID of the project this goal advances, else null"
    )
    habit_id: int | None = Field(
        default=None, description="ID of the habit this goal tracks, else null. Never set with project_id"
    )
    target_count: int | None = Field(
        default=None,
        description=(
            "Measurable target: for a habit goal, how many times this week; for a goal "
            "with task_ids, how many of those tasks to finish; null if purely qualitative"
        ),
    )
    task_ids: list[int] = Field(
        default_factory=list, description="IDs of backlog tasks to work on for this goal"
    )


class WeeklyPlanProposal(BaseModel):
    """The complete proposed plan for the week as of this turn, plus a reply to the user."""

    reply: str = Field(description="Short conversational message to the user about this plan")
    goals: list[ProposedGoal]
