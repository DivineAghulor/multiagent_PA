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
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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


class ChatMessageOut(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class TaskRefOut(BaseModel):
    """A task named by id and title only, where the full row isn't needed."""

    id: int
    title: str


class ProposalGoalOut(BaseModel):
    """A proposed goal with its IDs resolved to names for display (FR-8).
    Every ID here survived sanitize_proposal, so each one is real (S-6)."""

    description: str
    project_id: int | None
    project_name: str | None
    habit_id: int | None
    habit_name: str | None
    target_count: int | None
    tasks: list[TaskRefOut]


class ProposalOut(BaseModel):
    reply: str
    goals: list[ProposalGoalOut]


class PlanningSessionOut(BaseModel):
    """The whole state of a planning conversation. Every session endpoint
    returns it, so the client never has to merge deltas (FR-7)."""

    session_id: str
    week_start: date
    context: PlanningContextOut
    messages: list[ChatMessageOut]
    proposal: ProposalOut | None  # the whole plan as of the last turn
    warnings: list[str]  # what sanitising changed in the last turn's proposal


# --- Decomposition -------------------------------------------------------

class DraftTaskOut(BaseModel):
    ref: str  # T3 — the model's handle for it; stable for the life of the draft
    title: str
    description: str | None
    existing_task_id: int | None  # set: an existing backlog task being attached


class DraftMilestoneOut(BaseModel):
    ref: str  # M1
    name: str
    description: str | None
    due_date: date | None
    existing_id: int | None  # set: already in the DB, only gains tasks/order
    existing_task_titles: list[str]  # tasks it already has in the DB
    tasks: list[DraftTaskOut]  # what this draft adds under it


class DraftOut(BaseModel):
    project_name: str
    project_description: str | None
    project_id: int | None  # None: a new project, created on confirm
    milestones: list[DraftMilestoneOut]
    eligible_tasks: list[TaskRefOut]  # existing tasks the model may attach
    new_task_count: int


class TurnStatsOut(BaseModel):
    """What the last turn cost (NFR-3) and whether it hit the step cap (FR-12)."""

    steps: int  # model calls
    tool_calls: int
    hit_limit: bool


class DecompositionSessionOut(BaseModel):
    session_id: str
    draft: DraftOut
    messages: list[ChatMessageOut]
    last_turn: TurnStatsOut | None


class DecompositionResultOut(BaseModel):
    project: ProjectOut
    milestones: list[MilestoneOut]
    new_tasks: list[TaskOut]


class ReviewDraftOut(BaseModel):
    summary: str


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


# --- Request bodies ------------------------------------------------------
#
# Partial updates (the *UpdateIn models) distinguish an omitted field from an
# explicit null: omitted means "leave it alone", null means "clear it". The
# handler passes `model_dump(exclude_unset=True)` straight to the tool, whose
# UNSET defaults cover the omitted ones.

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Text = Annotated[str, StringConstraints(max_length=5000)]
Rating = Annotated[int, Field(ge=1, le=4)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _PartialIn(_In):
    # Fields that may be omitted but, when present, may not be null.
    _required_if_present: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _no_null_for_required(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for name in cls._required_if_present.default:  # type: ignore[attr-defined]
                if name in data and data[name] is None:
                    raise ValueError(f"{name} may be omitted but not null")
        return data


class CaptureIn(_In):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class TaskUpdateIn(_PartialIn):
    _required_if_present = ("title",)

    title: Name | None = None
    description: Text | None = None
    due_date: date | None = None
    project_id: int | None = None
    milestone_id: int | None = None


class PriorityIn(_In):
    importance: Rating
    urgency: Rating


class StatusIn(_In):
    status: TaskStatus


class ScheduleIn(_In):
    scheduled_for: date | None


class ProjectCreateIn(_In):
    name: Name
    description: Text | None = None
    target_date: date | None = None


class ProjectUpdateIn(_PartialIn):
    _required_if_present = ("name", "status")

    name: Name | None = None
    description: Text | None = None
    status: ProjectStatus | None = None
    target_date: date | None = None


class HabitCreateIn(_In):
    name: Name
    description: Text | None = None
    frequency: HabitFrequency = HabitFrequency.DAILY
    target_per_period: Annotated[int, Field(ge=1, le=100)] = 1


class HabitUpdateIn(_PartialIn):
    _required_if_present = ("name", "frequency", "target_per_period", "active")

    name: Name | None = None
    description: Text | None = None
    frequency: HabitFrequency | None = None
    target_per_period: Annotated[int, Field(ge=1, le=100)] | None = None
    active: bool | None = None


class MilestoneUpdateIn(_In):
    """update_milestone treats None as "unchanged", so nothing here can be cleared."""

    name: Name | None = None
    description: Text | None = None
    status: MilestoneStatus | None = None
    due_date: date | None = None


class HabitLogIn(_In):
    date: date


Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class PlanGoalEditIn(_In):
    """The user's edit of one proposed goal, by its position in the proposal."""

    index: Annotated[int, Field(ge=0)]
    description: Name
    target_count: Annotated[int, Field(ge=1)] | None = None


class PlanConfirmIn(_In):
    """Omit `goals` to confirm the proposal as it stands. Otherwise only the
    listed goals are written, with the given wording and target; what each goal
    links to (project, habit, tasks) always comes from the proposal."""

    goals: list[PlanGoalEditIn] | None = None


class PlanningStartIn(_In):
    week_start: date | None = None  # defaults to planning_week_start(today)


class MessageIn(_In):
    text: Message


class DecompositionStartIn(_In):
    """Either an existing project to extend, or a new one to create on confirm."""

    project_id: int | None = None
    name: Name | None = None
    description: Text | None = None

    @model_validator(mode="after")
    def _one_target(self) -> "DecompositionStartIn":
        if (self.project_id is None) == (self.name is None):
            raise ValueError("give either project_id or name, not both")
        return self


class DecompositionMessageIn(MessageIn):
    """A turn, plus new items the user unticked: they're dropped from the draft
    before the model sees it, so the next turn works on what the user kept."""

    exclude_milestone_refs: list[str] = []
    exclude_task_refs: list[str] = []


class DecompositionConfirmIn(_In):
    """Refs of new items to leave out — the outline's include checkboxes."""

    exclude_milestone_refs: list[str] = []
    exclude_task_refs: list[str] = []


class ReviewSaveIn(_In):
    """None saves goal verdicts and notes only; text also stores the narrative."""

    summary: Annotated[str, StringConstraints(max_length=20000)] | None = None


class CarryOverIn(_In):
    new_week_start: date
