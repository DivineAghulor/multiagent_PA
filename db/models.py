"""SQLAlchemy 2.0 declarative models: Task, Project, Milestone, Habit,
HabitLog, WeeklyGoal, CalendarEvent.

Shared conventions:
  - Base: declarative base for all models.
  - TimestampMixin: created_at/updated_at on every table.
  - Integer identity primary keys.
"""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# --- Enums -------------------------------------------------------------

class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class MilestoneStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskStatus(str, enum.Enum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class HabitFrequency(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    WEEKDAYS = "weekdays"
    CUSTOM = "custom"


class WeeklyGoalStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    ACHIEVED = "achieved"
    MISSED = "missed"
    CARRIED_OVER = "carried_over"


class CalendarEventStatus(str, enum.Enum):
    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    PENDING_CONFIRMATION = "pending_confirmation"  # reschedule awaiting human sign-off
    CANCELLED = "cancelled"


# --- Models --------------------------------------------------------------

class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        SqlEnum(ProjectStatus, name="project_status"),
        default=ProjectStatus.ACTIVE,
        nullable=False,
    )
    target_date: Mapped[date | None] = mapped_column(Date)

    milestones: Mapped[list["Milestone"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")


class Milestone(Base, TimestampMixin):
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[MilestoneStatus] = mapped_column(
        SqlEnum(MilestoneStatus, name="milestone_status"),
        default=MilestoneStatus.PLANNED,
        nullable=False,
    )
    due_date: Mapped[date | None] = mapped_column(Date)

    project: Mapped["Project"] = relationship(back_populates="milestones")
    tasks: Mapped[list["Task"]] = relationship(back_populates="milestone")


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        SqlEnum(TaskStatus, name="task_status"),
        default=TaskStatus.BACKLOG,
        nullable=False,
        index=True,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SqlEnum(TaskPriority, name="task_priority"),
        default=TaskPriority.MEDIUM,
        nullable=False,
    )

    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL")
    )
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="SET NULL")
    )
    weekly_goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("weekly_goals.id", ondelete="SET NULL")
    )

    due_date: Mapped[date | None] = mapped_column(Date)
    scheduled_for: Mapped[date | None] = mapped_column(Date)  # date assigned during weekly planning
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped["Project | None"] = relationship(back_populates="tasks")
    milestone: Mapped["Milestone | None"] = relationship(back_populates="tasks")
    weekly_goal: Mapped["WeeklyGoal | None"] = relationship(back_populates="tasks")
    calendar_events: Mapped[list["CalendarEvent"]] = relationship(back_populates="task")


class Habit(Base, TimestampMixin):
    __tablename__ = "habits"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[HabitFrequency] = mapped_column(
        SqlEnum(HabitFrequency, name="habit_frequency"),
        default=HabitFrequency.DAILY,
        nullable=False,
    )
    target_per_period: Mapped[int] = mapped_column(default=1, nullable=False)  # e.g. 3x/week
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    logs: Mapped[list["HabitLog"]] = relationship(
        back_populates="habit", cascade="all, delete-orphan"
    )


class HabitLog(Base, TimestampMixin):
    __tablename__ = "habit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    habit_id: Mapped[int] = mapped_column(
        ForeignKey("habits.id", ondelete="CASCADE"), nullable=False
    )
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    habit: Mapped["Habit"] = relationship(back_populates="logs")

    __table_args__ = (
        UniqueConstraint("habit_id", "log_date", name="uq_habit_log_habit_date"),
    )


class WeeklyGoal(Base, TimestampMixin):
    __tablename__ = "weekly_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # Monday of target week
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[WeeklyGoalStatus] = mapped_column(
        SqlEnum(WeeklyGoalStatus, name="weekly_goal_status"),
        default=WeeklyGoalStatus.PLANNED,
        nullable=False,
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)

    project: Mapped["Project | None"] = relationship()
    tasks: Mapped[list["Task"]] = relationship(back_populates="weekly_goal")


class CalendarEvent(Base, TimestampMixin):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_event_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True
    )  # null until synced to Google Calendar
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    status: Mapped[CalendarEventStatus] = mapped_column(
        SqlEnum(CalendarEventStatus, name="calendar_event_status"),
        default=CalendarEventStatus.TENTATIVE,
        nullable=False,
    )

    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL")
    )
    task: Mapped["Task | None"] = relationship(back_populates="calendar_events")

    # Human-in-the-loop reschedule/confirmation flow
    proposed_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proposed_end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reschedule_reason: Mapped[str | None] = mapped_column(Text)
    awaiting_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
