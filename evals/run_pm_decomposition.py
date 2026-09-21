"""Run evals/pm_decomposition.yaml against the real configured LLM provider.

Behavior check, not a unit test — hits a live API. Every case runs on its own
fresh in-memory SQLite DB, never the dev DB. Run manually:
    uv run python evals/run_pm_decomposition.py
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db.session  # noqa: E402
from agents.pm.decomposition import (  # noqa: E402
    confirm_decomposition,
    run_decomposition_turn,
    start_existing_project_draft,
    start_new_project_draft,
)
from db.models import Base  # noqa: E402
from tools.milestones import create_milestone  # noqa: E402
from tools.projects import create_project, find_project_by_name  # noqa: E402
from tools.tasks import create_task  # noqa: E402

NEAR_DUPLICATE = 0.9


def _date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def seed(fixture: dict) -> None:
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db.session.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    for p in fixture["projects"]:
        project = create_project(p["name"], p.get("description"))
        for pos, m in enumerate(p.get("milestones", []), 1):
            milestone = create_milestone(project.id, m["name"], position=pos)
            for title in m.get("tasks", []):
                create_task(title, project_id=project.id, milestone_id=milestone.id)
        for title in p.get("tasks", []):
            create_task(title, project_id=project.id)


def similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= NEAR_DUPLICATE


def check(case: dict, draft, eligible: dict[int, str], results, today: date) -> list[str]:
    problems = []
    if any(r.hit_limit for r in results):
        problems.append("hit the step limit")
    new_milestones = [m for m in draft.milestones if m.existing_id is None]

    if case.get("expect_no_milestones"):
        if new_milestones or draft.new_task_count:
            problems.append("drafted a plan instead of asking a clarifying question")
        return problems

    if sum(r.tool_calls for r in results) < 2:
        problems.append("fewer than 2 tool calls, not iterative")
    n = len(draft.milestones)
    if n < case.get("min_milestones", 1):
        problems.append(f"{n} milestone(s), expected >= {case.get('min_milestones', 1)}")
    if n > case.get("max_milestones", 99):
        problems.append(f"{n} milestone(s), expected <= {case['max_milestones']}")
    problems += [f"new milestone without tasks: {m.name!r}" for m in new_milestones if not m.tasks]
    cap = case.get("max_tasks_per_milestone")
    if cap:
        problems += [f"{m.name!r} has {len(m.tasks)} tasks (> {cap})" for m in draft.milestones if len(m.tasks) > cap]

    titles = [t.title for m in draft.milestones for t in m.tasks]
    for i, a in enumerate(titles):
        for b in titles[i + 1 :]:
            if similar(a, b):
                problems.append(f"near-duplicate tasks: {a!r} / {b!r}")
    attached = {t.existing_task_id for m in draft.milestones for t in m.tasks if t.existing_task_id}
    for m in draft.milestones:
        for t in m.tasks:
            if t.existing_task_id is None:
                problems += [
                    f"new task {t.title!r} duplicates existing {old!r}"
                    for tid, old in eligible.items()
                    if similar(t.title, old)
                ]
    for title in case.get("must_attach", []):
        if not any(eligible.get(tid) == title for tid in attached):
            problems.append(f"existing task not attached: {title!r}")

    text = " ".join([m.name for m in draft.milestones] + titles).lower()
    if case.get("keywords_any") and not any(k.lower() in text for k in case["keywords_any"]):
        problems.append(f"none of {case['keywords_any']} appear in the plan")
    dues = [m.due_date for m in draft.milestones if m.due_date]
    if case.get("expect_due_dates") and not dues:
        problems.append("no due dates despite a timeline")
    if case.get("latest_due"):
        latest = _date(case["latest_due"])
        problems += [f"due date {d} after {latest}" for d in dues if d > latest]

    try:
        confirm_decomposition(draft)
    except Exception as e:  # noqa: BLE001 — any failure here is an eval failure
        problems.append(f"confirm failed: {e}")
    return problems


def run_turns(case: dict, draft, today: date, retries: int = 2):
    """Run a case's turns, retrying transient provider errors (503/UNAVAILABLE)."""
    for attempt in range(retries + 1):
        history, results = [], []
        try:
            for turn in case["turns"]:
                result = run_decomposition_turn([*history, HumanMessage(turn)], draft, today)
                history = result.history
                results.append(result)
            return results
        except Exception as e:  # noqa: BLE001
            transient = "UNAVAILABLE" in str(e) or "503" in str(e)
            if not transient or attempt == retries:
                raise
            print(f"         transient error, retrying in 30s: {str(e)[:80]}", flush=True)
            time.sleep(30)
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="run only case(s) with this name (repeatable)")
    args = parser.parse_args()

    spec = yaml.safe_load(Path(__file__).with_name("pm_decomposition.yaml").read_text())
    today = _date(spec["today"])
    cases = [c for c in spec["cases"] if not args.case or c["name"] in args.case]
    if not cases:
        print(f"no case matched {args.case}; known: {[c['name'] for c in spec['cases']]}")
        return 1
    failures = 0
    for case in cases:
        seed(spec["fixture"])
        if "existing" in case:
            draft = start_existing_project_draft(find_project_by_name(case["existing"]).id)
        else:
            draft = start_new_project_draft(case["project"]["name"], case["project"].get("description"))
        eligible = dict(draft.eligible_tasks)

        try:
            results = run_turns(case, draft, today)
        except Exception as e:  # noqa: BLE001 — provider error, not a behavior failure
            failures += 1
            print(f"[ERROR] {case['name']}: {e}", flush=True)
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                print("         provider quota exhausted; stopping the run")
                break
            continue

        problems = check(case, draft, eligible, results, today)
        failures += bool(problems)
        stats = ", ".join(f"{r.steps} steps/{r.tool_calls} calls" for r in results)
        print(f"[{'FAIL' if problems else 'PASS'}] {case['name']} ({stats})", flush=True)
        for p in problems:
            print(f"         ! {p}")
        print(f"         reply: {results[-1].reply}")
        for line in draft.render().splitlines():
            print(f"         {line}")

    total = len(cases)
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
