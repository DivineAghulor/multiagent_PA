"""Run evals/pm_weekly_planning.yaml against the real configured LLM provider.

Behavior check, not a unit test — hits a live API. The fixture backlog is
seeded into an in-memory SQLite DB, never the dev DB. Run manually:
    uv run python evals/run_pm_weekly_planning.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db.session  # noqa: E402
from agents.pm.planning import (  # noqa: E402
    describe_proposal,
    load_planning_context,
    propose_weekly_plan,
    sanitize_proposal,
)
from db.models import Base, HabitFrequency  # noqa: E402
from tools.habits import create_habit  # noqa: E402
from tools.projects import create_project  # noqa: E402
from tools.tasks import create_task, update_task_priority  # noqa: E402


def seed(fixture: dict) -> None:
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db.session.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    projects = {name: create_project(name).id for name in fixture["projects"]}
    for h in fixture["habits"]:
        create_habit(h["name"], HabitFrequency(h["frequency"]), h["target_per_period"])
    for t in fixture["tasks"]:
        task = create_task(t["title"], project_id=projects.get(t.get("project")))
        if "importance" in t:
            update_task_priority(task.id, t["importance"], t["urgency"])


def check(case: dict, proposal, warnings: list[str], ctx) -> list[str]:
    problems = [f"sanitizer fixed: {w}" for w in warnings]
    goals = proposal.goals
    if len(goals) < case.get("min_goals", 0):
        problems.append(f"only {len(goals)} goal(s), expected >= {case['min_goals']}")
    if len(goals) > case.get("max_goals", 99):
        problems.append(f"{len(goals)} goal(s), expected <= {case['max_goals']}")

    habit_names = {h.id: h.name for h in ctx.habits}
    targets = {habit_names[g.habit_id]: g.target_count for g in goals if g.habit_id is not None}
    for name, want in case.get("habit_targets", {}).items():
        if name not in targets:
            problems.append(f"no goal for habit {name!r}")
        elif targets[name] != want:
            problems.append(f"habit {name!r} target {targets[name]}, expected {want}")
    for name in case.get("forbidden_habits", []):
        if name in targets:
            problems.append(f"unwanted goal for habit {name!r}")

    task_titles = {t.id: t.title for t in ctx.backlog}
    linked = {task_titles[tid] for g in goals for tid in g.task_ids}
    problems += [f"task not linked: {t!r}" for t in case.get("linked_tasks", []) if t not in linked]
    problems += [f"task wrongly linked: {t!r}" for t in case.get("unlinked_tasks", []) if t in linked]
    return problems


def main() -> int:
    spec = yaml.safe_load(Path(__file__).with_name("pm_weekly_planning.yaml").read_text())
    seed(spec["fixture"])
    week_start = spec["fixture"]["week_start"]
    if not isinstance(week_start, date):
        week_start = date.fromisoformat(week_start)
    ctx = load_planning_context(week_start)

    cases = spec["cases"]
    failures = 0
    for case in cases:
        turns = case.get("turns") or [case["input"]]
        history: list[tuple[str, str]] = []
        for turn in turns:
            history.append(("user", turn))
            proposal, warnings = sanitize_proposal(propose_weekly_plan(history, ctx), ctx)
            history.append(("assistant", describe_proposal(proposal, ctx)))

        problems = check(case, proposal, warnings, ctx)
        if problems:
            failures += 1
        print(f"[{'FAIL' if problems else 'PASS'}] {' / '.join(turns)!r}")
        for p in problems:
            print(f"         ! {p}")
        for line in describe_proposal(proposal, ctx).splitlines():
            print(f"         {line}")

    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
