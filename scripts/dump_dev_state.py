"""Print everything in the DB the PM track writes: projects, milestones,
habits, weekly goals and tasks. Use it beside the Streamlit harness to check
what a flow actually persisted (and that a proposal persisted nothing).

    uv run python scripts/dump_dev_state.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.habits import list_habits  # noqa: E402
from tools.milestones import list_milestones  # noqa: E402
from tools.projects import list_projects  # noqa: E402
from tools.tasks import list_tasks  # noqa: E402
from tools.weekly_goals import list_weekly_goals  # noqa: E402


def section(title: str, rows: list[str]) -> None:
    print(f"\n{title} ({len(rows)})")
    for row in rows or ["  (none)"]:
        print(row)


def main() -> int:
    projects = list_projects()
    section("PROJECTS", [f"  [{p.id}] {p.name} - {p.status.value}" for p in projects])

    milestones = list_milestones()
    section(
        "MILESTONES",
        [
            f"  [{m.id}] pos={m.position} project={m.project_id} {m.name}"
            f" - {m.status.value}{f', due {m.due_date}' if m.due_date else ''}"
            f" ({len(m.tasks)} task(s))"
            for m in milestones
        ],
    )

    section(
        "HABITS",
        [
            f"  [{h.id}] {h.name} - {h.frequency.value}, {h.target_per_period} per period"
            f"{'' if h.active else ' (inactive)'}"
            for h in list_habits(active_only=False)
        ],
    )

    section(
        "WEEKLY GOALS",
        [
            f"  [{g.id}] week of {g.week_start} - {g.description}"
            f" [{g.status.value}]{f' target={g.target_count}' if g.target_count else ''}"
            f"{f' habit={g.habit_id}' if g.habit_id else ''}{f' project={g.project_id}' if g.project_id else ''}"
            f"{f' tasks={[t.title for t in g.tasks]}' if g.tasks else ''}"
            for g in list_weekly_goals()
        ],
    )

    # importance/urgency are 1-4, 1 = lowest, 4 = highest; '-' means unrated.
    section(
        "TASKS",
        [
            f"  [{t.id}] {t.status.value:<12} {t.title}"
            f" | imp/urg {t.importance or '-'}/{t.urgency or '-'}"
            f" | project={t.project_id} milestone={t.milestone_id} goal={t.weekly_goal_id}"
            for t in list_tasks()
        ],
    )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
