"""Seed the local dev DB with projects, habits and backlog tasks for manual
testing of the Streamlit harness.

The UI has no way to create projects or habits, so weekly planning and the
existing-project breakdown flow need this data to be testable at all.
Re-running is safe: anything already present by name is left alone.

    uv run python scripts/seed_dev_data.py
    uv run python scripts/seed_dev_data.py --wipe   # delete everything first
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.models import (  # noqa: E402
    CalendarEvent,
    Habit,
    HabitFrequency,
    HabitLog,
    Milestone,
    Project,
    Task,
    WeeklyGoal,
)
from db.session import get_session  # noqa: E402
from tools.habits import create_habit, list_habits  # noqa: E402
from tools.projects import create_project, find_project_by_name  # noqa: E402
from tools.tasks import create_task, list_tasks, update_task_priority  # noqa: E402

PROJECTS = [
    ("Website relaunch", "New marketing site with a rebuilt signup flow"),
    ("Thesis", "Master's thesis, submission in the spring"),
]

HABITS = [
    ("Gym", HabitFrequency.WEEKLY, 3),
    ("Reading", HabitFrequency.DAILY, 1),
    ("Meditation", HabitFrequency.DAILY, 1),
]

# (title, project name or None, importance, urgency) — importance/urgency are 1-4,
# 1 = lowest, 4 = highest; None leaves the task unrated.
TASKS = [
    ("Fix broken signup form", "Website relaunch", 4, 4),
    ("Write new homepage copy", "Website relaunch", 3, 2),
    ("Set up analytics", "Website relaunch", 2, 2),
    ("Write literature review chapter", "Thesis", 4, 2),
    ("Email supervisor the draft outline", "Thesis", 3, 3),
    ("Format bibliography", "Thesis", 1, 1),
    ("Renew passport", None, 3, 2),
    ("Call the dentist", None, None, None),
]

# Child rows first: tasks reference projects/milestones/goals.
_WIPE_ORDER = (HabitLog, CalendarEvent, Task, Milestone, WeeklyGoal, Habit, Project)


def wipe() -> None:
    with get_session() as session:
        for model in _WIPE_ORDER:
            session.query(model).delete()
    print("wiped all rows")


def seed() -> None:
    for name, description in PROJECTS:
        if find_project_by_name(name) is None:
            create_project(name, description)
            print(f"project: {name}")

    existing_habits = {h.name.lower() for h in list_habits(active_only=False)}
    for name, frequency, target in HABITS:
        if name.lower() not in existing_habits:
            create_habit(name, frequency, target)
            print(f"habit: {name}")

    existing_titles = {t.title.lower() for t in list_tasks()}
    for title, project_name, importance, urgency in TASKS:
        if title.lower() in existing_titles:
            continue
        project = find_project_by_name(project_name) if project_name else None
        task = create_task(title, project_id=project.id if project else None)
        if importance is not None:
            update_task_priority(task.id, importance, urgency)
        print(f"task: {title}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wipe", action="store_true", help="delete every row first (destructive)")
    args = parser.parse_args()
    if args.wipe:
        wipe()
    seed()
    print("done - run scripts/dump_dev_state.py to see the result")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
