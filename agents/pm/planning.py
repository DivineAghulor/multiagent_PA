"""Weekly planning: backlog + projects + habits + user intent -> proposed
WeeklyGoals. The model only proposes; confirm_weekly_plan writes, and only
after the user confirms (see phase2-implementation.md)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from db.models import Habit, Project, ProjectStatus, Task, WeeklyGoal
from llm.factory import get_structured_model
from tools.habits import list_habits
from tools.projects import list_projects
from tools.tasks import get_backlog
from tools.weekly_goals import create_weekly_goal, list_weekly_goals

from .schemas import ProposedGoal, WeeklyPlanProposal

PLANNING_SYSTEM_PROMPT = """You help the user plan their week. Using the backlog \
tasks, projects and habits listed below, and what the user says they want out of \
the week, propose a small, realistic set of weekly goals (usually 2-5).

Rules:
- Only use IDs that appear in the lists below. Never invent an ID.
- A goal is about a project or a habit, never both.
- Attach backlog tasks (task_ids) only where they clearly serve the goal. Each task \
belongs to at most one goal.
- Habit goals must set target_count to how many times this week: use the number the \
user gave, otherwise the habit's usual frequency.
- For a goal with tasks, set target_count only if the user wants fewer than all of \
them done; otherwise leave it null.
- Respect what the user says to focus on or leave out. Don't add goals for areas they \
excluded. When they leave the choice to you, prefer higher importance/urgency tasks.
- Don't repeat goals already set for this week.
- Every turn, return the complete plan including the user's feedback so far, not \
just the changes.
- reply: 1-3 sentences summarizing the plan or asking a clarifying question. If \
there isn't enough to go on, return no goals and ask."""


@dataclass
class PlanningContext:
    week_start: date
    backlog: list[Task]
    projects: list[Project]
    habits: list[Habit]
    existing_goals: list[WeeklyGoal]


def planning_week_start(today: date) -> date:
    """Monday of the week being planned: this week, or next week on a weekend."""
    monday = today - timedelta(days=today.weekday())
    return monday + timedelta(days=7) if today.weekday() >= 5 else monday


def load_planning_context(week_start: date) -> PlanningContext:
    return PlanningContext(
        week_start=week_start,
        backlog=[t for t in get_backlog() if t.weekly_goal_id is None],
        projects=list_projects(status=ProjectStatus.ACTIVE),
        habits=list_habits(active_only=True),
        existing_goals=list_weekly_goals(week_start=week_start),
    )


def _lines(items: list[str]) -> str:
    return "\n".join(items) if items else "(none)"


def render_planning_context(ctx: PlanningContext) -> str:
    project_names = {p.id: p.name for p in ctx.projects}
    tasks = []
    for t in ctx.backlog:
        parts = [f"- [task {t.id}] {t.title}"]
        if t.project_id is not None:
            parts.append(f"project: {project_names.get(t.project_id, '?')} (id {t.project_id})")
        if t.importance is not None and t.urgency is not None:
            parts.append(f"importance {t.importance}/4, urgency {t.urgency}/4")
        else:
            parts.append("unrated")
        if t.due_date is not None:
            parts.append(f"due {t.due_date.isoformat()}")
        tasks.append(" | ".join(parts))
    projects = [
        f"- [project {p.id}] {p.name}" + (f": {p.description}" if p.description else "")
        for p in ctx.projects
    ]
    habits = [
        f"- [habit {h.id}] {h.name} ({h.frequency.value}, {h.target_per_period} per period)"
        for h in ctx.habits
    ]
    existing = [f"- {g.description}" for g in ctx.existing_goals]
    return (
        f"Week being planned: starts Monday {ctx.week_start.isoformat()}.\n\n"
        "Backlog tasks (importance and urgency are rated 1-4, where 1 is the "
        "lowest and 4 the highest):\n"
        f"{_lines(tasks)}\n\n"
        f"Active projects:\n{_lines(projects)}\n\n"
        f"Active habits:\n{_lines(habits)}\n\n"
        f"Goals already set for this week:\n{_lines(existing)}"
    )


def propose_weekly_plan(history: list[tuple[str, str]], ctx: PlanningContext) -> WeeklyPlanProposal:
    """One planning turn. `history` is the whole conversation as (role, text) pairs."""
    model = get_structured_model(WeeklyPlanProposal)
    system = PLANNING_SYSTEM_PROMPT + "\n\n" + render_planning_context(ctx)
    return model.invoke([("system", system), *history])


def sanitize_proposal(
    proposal: WeeklyPlanProposal, ctx: PlanningContext
) -> tuple[WeeklyPlanProposal, list[str]]:
    """Drop IDs the context doesn't contain and tasks used twice; warn about each fix."""
    project_ids = {p.id for p in ctx.projects}
    habit_ids = {h.id for h in ctx.habits}
    backlog_ids = {t.id for t in ctx.backlog}
    used: set[int] = set()
    warnings: list[str] = []
    goals: list[ProposedGoal] = []

    for g in proposal.goals:
        label = g.description.strip()
        if not label:
            warnings.append("Dropped a goal with no description")
            continue
        project_id, habit_id, target = g.project_id, g.habit_id, g.target_count
        if project_id is not None and project_id not in project_ids:
            warnings.append(f"'{label}': unknown project id {project_id} removed")
            project_id = None
        if habit_id is not None and habit_id not in habit_ids:
            warnings.append(f"'{label}': unknown habit id {habit_id} removed")
            habit_id = None
        if project_id is not None and habit_id is not None:
            warnings.append(f"'{label}': had both a project and a habit; kept the habit")
            project_id = None

        task_ids: list[int] = []
        for tid in dict.fromkeys(g.task_ids):
            if tid not in backlog_ids:
                warnings.append(f"'{label}': task {tid} is not in the unassigned backlog, removed")
            elif tid in used:
                warnings.append(f"'{label}': task {tid} already belongs to another goal, removed")
            else:
                task_ids.append(tid)
                used.add(tid)

        if target is not None and target < 1:
            warnings.append(f"'{label}': target {target} is not positive, cleared")
            target = None
        if target is not None and habit_id is None and task_ids and target > len(task_ids):
            warnings.append(f"'{label}': target {target} exceeds its {len(task_ids)} task(s), capped")
            target = len(task_ids)

        goals.append(
            ProposedGoal(
                description=label,
                project_id=project_id,
                habit_id=habit_id,
                target_count=target,
                task_ids=task_ids,
            )
        )
    return WeeklyPlanProposal(reply=proposal.reply, goals=goals), warnings


def describe_proposal(proposal: WeeklyPlanProposal, ctx: PlanningContext) -> str:
    """Human-readable plan, used both for display and as the assistant's turn in history."""
    names = {
        **{("task", t.id): t.title for t in ctx.backlog},
        **{("project", p.id): p.name for p in ctx.projects},
        **{("habit", h.id): h.name for h in ctx.habits},
    }
    lines = [proposal.reply]
    for i, g in enumerate(proposal.goals, 1):
        line = f"{i}. {g.description}"
        if g.habit_id is not None:
            line += f" [habit: {names[('habit', g.habit_id)]} (id {g.habit_id})]"
        if g.project_id is not None:
            line += f" [project: {names[('project', g.project_id)]} (id {g.project_id})]"
        if g.target_count is not None:
            line += f" — target {g.target_count}"
        lines.append(line)
        lines.extend(f"   - [task {tid}] {names[('task', tid)]}" for tid in g.task_ids)
    return "\n".join(lines)


def confirm_weekly_plan(week_start: date, goals: list[ProposedGoal]) -> list[WeeklyGoal]:
    """Persist user-confirmed goals. Re-validates against the live DB first, so a
    proposal gone stale (backlog changed since it was made) is rejected, not half-applied."""
    ctx = load_planning_context(week_start)
    clean, warnings = sanitize_proposal(WeeklyPlanProposal(reply="", goals=goals), ctx)
    if warnings:
        raise ValueError("Plan is out of date with the backlog: " + "; ".join(warnings))
    return [
        create_weekly_goal(
            week_start=week_start,
            description=g.description,
            project_id=g.project_id,
            habit_id=g.habit_id,
            target_count=g.target_count,
            task_ids=g.task_ids,
        )
        for g in clean.goals
    ]
