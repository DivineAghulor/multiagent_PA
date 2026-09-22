"""Pydantic response models for the HTTP boundary.

Deliberately separate from agents/pm/schemas.py, which is LLM-facing: these
shapes are a contract with the frontend and change for different reasons.

ORM objects are never returned directly. `from_attributes` reads only the
fields declared here, which also keeps serialisation off unloaded
relationships — touching one on a detached instance raises
DetachedInstanceError (progress.md, Phase 4). Where a relationship is needed,
the tool that loaded it eagerly passes it in explicitly.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from db.models import (
    HabitFrequency,
    MilestoneStatus,
    ProjectStatus,
    TaskPriority,
    TaskStatus,
    WeeklyGoalStatus,
)


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Tasks ---------------------------------------------------------------

class TaskOut(_Out):
    id: int
    title: str
    description: str | None
    status: TaskStatus
    # Derived from the importance/urgency pair (tools.tasks.derive_priority);
    # display shorthand only, never an input. See requirements §6.7 SCH-5.
    priority: TaskPriority
    importance: int | None
    urgency: int | None
    project_id: int | None
    milestone_id: int | None
    weekly_goal_id: int | None
    due_date: date | None
    scheduled_for: date | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- Projects and milestones ---------------------------------------------

class MilestoneOut(_Out):
    id: int
    project_id: int
    name: str
    description: str | None
    status: MilestoneStatus
    due_date: date | None
    position: int | None


class ProjectOut(_Out):
    id: int
    name: str
    description: str | None
    status: ProjectStatus
    target_date: date | None
    created_at: datetime
    updated_at: datetime


class ProjectDetailOut(ProjectOut):
    milestones: list[MilestoneOut] = []
    tasks: list[TaskOut] = []


# --- Habits --------------------------------------------------------------

class HabitOut(_Out):
    id: int
    name: str
    description: str | None
    frequency: HabitFrequency
    target_per_period: int
    active: bool


class HabitLogOut(_Out):
    id: int
    habit_id: int
    log_date: date
    completed: bool
    note: str | None


# --- Weekly goals and the week screen ------------------------------------

class WeeklyGoalOut(_Out):
    id: int
    week_start: date
    description: str
    status: WeeklyGoalStatus
    project_id: int | None
    habit_id: int | None
    target_count: int | None
    reviewed_at: datetime | None
    review_notes: str | None


class GoalProgressOut(BaseModel):
    """One goal's deterministic progress, from agents.pm.review.GoalReview.

    `status` is the review's verdict for the week, which is not the same thing
    as the goal row's own status until a review is saved — it is None when the
    goal has no measurable target at all.
    """

    goal: WeeklyGoalOut
    kind: str  # "habit" | "tasks" | "qualitative"
    completed: int
    target: int | None
    done: list[str]  # task titles, or ISO dates for a habit goal
    outstanding: list[str]
    status: WeeklyGoalStatus | None
    achieved: bool
    headline: str
    tasks: list[TaskOut]
    habit: HabitOut | None


class WeeklyReviewOut(_Out):
    """A stored narrative. Its counts are the ones the prose was written
    against, not recomputed — see requirements §6.7 SCH-2.
    """

    week_start: date
    summary: str
    achieved_count: int
    measurable_count: int
    unplanned_count: int
    generated_at: datetime


class WeekOut(BaseModel):
    week_start: date
    week_end: date
    goals: list[GoalProgressOut]
    unplanned_done: list[TaskOut]
    achieved_count: int
    measurable_count: int
    facts: str  # render_review_facts output; the same text the model is given
    review: WeeklyReviewOut | None  # the stored summary, when the week has one


# --- Planning ------------------------------------------------------------

class PlanningContextOut(BaseModel):
    """Exactly what the planning model will be shown, as structure and as the
    rendered prompt text, so the user can see it before spending a call.
    """

    week_start: date
    backlog: list[TaskOut]
    projects: list[ProjectOut]
    habits: list[HabitOut]
    existing_goals: list[WeeklyGoalOut]
    rendered: str


# --- Health --------------------------------------------------------------

class HealthOut(BaseModel):
    status: str  # "ok" | "degraded"
    database: bool
    provider: str
    model: str
    # Presence only. Never a key or a slice of one — see the resolved NOTES.md
    # entry about logging partial keys.
    provider_key_configured: bool
    tracing: bool
    today: date
