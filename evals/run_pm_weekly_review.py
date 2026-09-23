"""Run evals/pm_weekly_review.yaml against the real configured LLM provider.

Behavior check, not a unit test — hits a live API (one call per case). Each case
seeds its own in-memory SQLite DB, never the dev DB. Run manually:
    uv run python evals/run_pm_weekly_review.py
    uv run python evals/run_pm_weekly_review.py --case "mixed week"
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db.session  # noqa: E402
from agents.pm.review import build_week_review, render_review_facts, summarize_week  # noqa: E402
from db.models import Base  # noqa: E402
from tools.habits import create_habit, log_habit_completion  # noqa: E402
from tools.tasks import complete_task, create_task  # noqa: E402
from tools.weekly_goals import create_weekly_goal  # noqa: E402

BULLET_STARTS = ("- ", "* ", "#", "•")


def _date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def seed(case: dict) -> date:
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db.session.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    week_start = _date(case["week_start"])
    habits = {
        h["name"]: create_habit(h["name"], target_per_period=h.get("target_per_period", 1)).id
        for h in case.get("habits", [])
    }
    for spec in case["goals"]:
        habit_id = habits.get(spec.get("habit")) if spec.get("habit") else None
        task_ids = [create_task(t).id for t in spec.get("tasks", [])]
        goal = create_weekly_goal(
            week_start,
            spec["description"],
            habit_id=habit_id,
            target_count=spec.get("target"),
            task_ids=task_ids,
        )
        for i in range(spec.get("logged_days", 0)):
            log_habit_completion(habit_id, week_start + timedelta(days=i))
        done = set(spec.get("done", []))
        for task in goal.tasks:
            if task.title in done:
                complete_task(task.id, completed_at=datetime.combine(week_start, datetime.min.time(), timezone.utc))
    for title in case.get("unplanned_done", []):
        task = create_task(title)
        complete_task(task.id, completed_at=datetime.combine(week_start, datetime.min.time(), timezone.utc))
    return week_start


def _mentions(low: str, wanted) -> bool:
    """A wanted item is a string, or a list of alternatives where any one counts
    (models write "twice out of three" as readily as "2/3")."""
    options = [wanted] if isinstance(wanted, str) else wanted
    return any(str(o).lower() in low for o in options)


def check(case: dict, summary: str) -> list[str]:
    problems = []
    low = summary.lower()
    problems += [f"missing {w!r}" for w in case.get("must_mention", []) if not _mentions(low, w)]
    problems += [f"should not say {s!r}" for s in case.get("must_not_mention", []) if s.lower() in low]
    words = len(summary.split())
    if words < case.get("word_min", 0):
        problems.append(f"{words} words, expected >= {case['word_min']}")
    if words > case.get("word_max", 10**6):
        problems.append(f"{words} words, expected <= {case['word_max']}")
    if any(line.strip().startswith(BULLET_STARTS) for line in summary.splitlines()):
        problems.append("used bullets/headings; the prompt asks for prose")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="run only case(s) with this name (repeatable)")
    parser.add_argument("--facts-only", action="store_true", help="print the computed facts, no model call")
    args = parser.parse_args()

    spec = yaml.safe_load(Path(__file__).with_name("pm_weekly_review.yaml").read_text())
    cases = [c for c in spec["cases"] if not args.case or c["name"] in args.case]
    if not cases:
        print(f"no case matched {args.case}; known: {[c['name'] for c in spec['cases']]}")
        return 1

    failures = 0
    for case in cases:
        week_start = seed(case)
        review = build_week_review(week_start)

        if args.facts_only:
            print(f"--- {case['name']} ---")
            print(render_review_facts(review))
            continue

        try:
            summary = summarize_week(review)
        except Exception as e:  # noqa: BLE001 — provider error, not a behavior failure
            failures += 1
            print(f"[ERROR] {case['name']}: {e}", flush=True)
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                print("         provider quota exhausted; stopping the run")
                break
            continue

        problems = check(case, summary)
        failures += bool(problems)
        print(f"[{'FAIL' if problems else 'PASS'}] {case['name']}", flush=True)
        for p in problems:
            print(f"         ! {p}")
        for line in summary.splitlines():
            print(f"         {line}")

    if not args.facts_only:
        total = len(cases)
        print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
