"""Weekly review: compare a week's WeeklyGoals against what actually got done.

All counting happens here in code; the model only writes prose over facts it is
given (see phase4-implementation.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from db.models import Task, TaskStatus, WeeklyGoal, WeeklyGoalStatus
from llm.factory import get_default_chat_model
from tools.habits import get_habit_logs
from tools.reviews import save_week_summary
from tools.tasks import list_tasks
from tools.weekly_goals import list_weekly_goals, record_weekly_review

REVIEW_SYSTEM_PROMPT = """You write a short weekly review for someone based only \
on the facts you're given.

Rules:
- Never invent or recalculate numbers. Use the counts exactly as given.
- Don't call a goal achieved unless the facts say it was.
- Cover: what went well, what slipped and a plausible reason why, and one or two \
concrete suggestions for next week.
- Mention work completed outside the plan, if there was any — it counts.
- Write 2-4 short paragraphs, addressed to the person as "you". No headings, no \
bullet lists, no preamble."""

HABIT, TASKS, QUALITATIVE = "habit", "tasks", "qualitative"


@dataclass
class GoalReview:
    goal: WeeklyGoal
    kind: str  # HABIT | TASKS | QUALITATIVE
    completed: int
    target: int | None
    done: list[str]  # task titles, or logged dates for a habit goal
    outstanding: list[str]
    status: WeeklyGoalStatus | None  # None when the goal isn't measurable

    @property
    def achieved(self) -> bool:
        return self.status == WeeklyGoalStatus.ACHIEVED

    def headline(self) -> str:
        if self.kind == QUALITATIVE:
            return f"{self.goal.description}: no target or tasks attached, so progress isn't measurable"
        unit = "completion(s)" if self.kind == HABIT else "task(s) done"
        return f"{self.goal.description}: {self.completed}/{self.target} {unit}"


@dataclass
class WeekReview:
    week_start: date
    goals: list[GoalReview]
    unplanned_done: list[Task]  # completed during the week, not linked to any goal

    @property
    def week_end(self) -> date:
        return self.week_start + timedelta(days=6)

    @property
    def achieved_count(self) -> int:
        return sum(1 for g in self.goals if g.achieved)

    @property
    def measurable_count(self) -> int:
        return sum(1 for g in self.goals if g.status is not None)


def today() -> date:
    """Indirection for "now" so the UI and tests can agree on the date."""
    return date.today()


def current_week_start(today: date) -> date:
    """Monday of the week containing `today` (unlike planning_week_start, which
    rolls forward to next week at the weekend)."""
    return today - timedelta(days=today.weekday())


def _completed_in_week(task: Task, week_start: date, week_end: date) -> bool:
    if task.status != TaskStatus.DONE:
        return False
    if task.completed_at is None:  # completed without a timestamp: count it
        return True
    return week_start <= task.completed_at.date() <= week_end


def _review_goal(goal: WeeklyGoal, week_start: date, week_end: date) -> GoalReview:
    if goal.habit_id is not None:
        logs = [log for log in get_habit_logs(goal.habit_id, week_start, week_end) if log.completed]
        target = goal.target_count or (goal.habit.target_per_period if goal.habit else None)
        completed = len(logs)
        return GoalReview(
            goal=goal,
            kind=HABIT,
            completed=completed,
            target=target,
            done=[log.log_date.isoformat() for log in logs],
            outstanding=[],
            status=(
                None
                if target is None
                else WeeklyGoalStatus.ACHIEVED
                if completed >= target
                else WeeklyGoalStatus.MISSED
            ),
        )

    if goal.tasks:
        done = [t for t in goal.tasks if t.status == TaskStatus.DONE]
        outstanding = [t for t in goal.tasks if t.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)]
        target = goal.target_count or len(goal.tasks)
        return GoalReview(
            goal=goal,
            kind=TASKS,
            completed=len(done),
            target=target,
            done=[t.title for t in done],
            outstanding=[t.title for t in outstanding],
            status=WeeklyGoalStatus.ACHIEVED if len(done) >= target else WeeklyGoalStatus.MISSED,
        )

    return GoalReview(
        goal=goal, kind=QUALITATIVE, completed=0, target=goal.target_count, done=[], outstanding=[], status=None
    )


def build_week_review(week_start: date) -> WeekReview:
    """Deterministic comparison of the week's goals against what was completed."""
    week_end = week_start + timedelta(days=6)
    goals = [_review_goal(g, week_start, week_end) for g in list_weekly_goals(week_start=week_start)]
    planned_task_ids = {t.id for g in goals for t in g.goal.tasks}
    unplanned = [
        t
        for t in list_tasks(status=TaskStatus.DONE)
        if t.id not in planned_task_ids and _completed_in_week(t, week_start, week_end)
    ]
    return WeekReview(week_start=week_start, goals=goals, unplanned_done=unplanned)


def render_review_facts(review: WeekReview) -> str:
    """The facts block the model summarizes. Numbers here are final."""
    lines = [
        f"Week of Monday {review.week_start.isoformat()} to {review.week_end.isoformat()}.",
        f"Goals set: {len(review.goals)}. Measurable: {review.measurable_count}. "
        f"Achieved: {review.achieved_count}.",
        "",
        "Goals:",
    ]
    if not review.goals:
        lines.append("- (none were set for this week)")
    for g in review.goals:
        verdict = "not measurable" if g.status is None else g.status.value
        lines.append(f"- {g.headline()} [{verdict}]")
        if g.kind == HABIT and g.done:
            lines.append(f"    logged on: {', '.join(g.done)}")
        if g.done and g.kind == TASKS:
            lines.append(f"    done: {'; '.join(g.done)}")
        if g.outstanding:
            lines.append(f"    not done: {'; '.join(g.outstanding)}")

    lines.append("")
    if review.unplanned_done:
        lines.append("Completed this week but not part of any goal:")
        lines.extend(f"- {t.title}" for t in review.unplanned_done)
    else:
        lines.append("Nothing was completed outside the planned goals.")
    return "\n".join(lines)


def summarize_week(review: WeekReview) -> str:
    """The single model call of this phase: prose over the computed facts."""
    model = get_default_chat_model()
    response = model.invoke(
        [
            ("system", REVIEW_SYSTEM_PROMPT),
            ("human", render_review_facts(review)),
        ]
    )
    return response.text.strip()


def goal_note(g: GoalReview) -> str:
    """The factual per-goal note stored on WeeklyGoal.review_notes."""
    note = g.headline()
    if g.outstanding:
        note += f". Outstanding: {'; '.join(g.outstanding)}"
    return note


def save_review(review: WeekReview, summary: str | None = None) -> list[WeeklyGoal]:
    """Write per-goal notes and ACHIEVED/MISSED. Unmeasurable goals are left alone.
    Re-running a review for the same week overwrites its own notes.

    With `summary`, the week's narrative is persisted too, alongside the counts
    it was written against (see tools/reviews.py on why they're snapshotted)."""
    saved = []
    for g in review.goals:
        if g.status is None:
            continue
        saved.append(record_weekly_review(g.goal.id, goal_note(g), g.status))
    if summary is not None:
        save_week_summary(
            week_start=review.week_start,
            summary=summary,
            achieved_count=review.achieved_count,
            measurable_count=review.measurable_count,
            unplanned_count=len(review.unplanned_done),
        )
    return saved


def missed_goals(review: WeekReview) -> list[GoalReview]:
    """Goals eligible for carry-over into a later week."""
    return [g for g in review.goals if g.status == WeeklyGoalStatus.MISSED]
