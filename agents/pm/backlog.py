"""Backlog capture: freeform text -> persisted Task rows."""
from __future__ import annotations

from langchain_core.tools import tool

from db.models import Task
from tools.projects import find_project_by_name
from tools.tasks import create_task

from .extraction import extract_tasks


def capture_backlog_from_text(text: str) -> list[Task]:
    """Extract tasks from text and persist them, unrated (importance/urgency left None)."""
    batch = extract_tasks(text)
    created = []
    for extracted in batch.tasks:
        project = find_project_by_name(extracted.project_hint) if extracted.project_hint else None
        task = create_task(
            title=extracted.title,
            description=extracted.description,
            project_id=project.id if project else None,
            importance=None,
            urgency=None,
        )
        created.append(task)
    return created


@tool
def add_tasks_to_backlog(text: str) -> str:
    """Extract and save tasks from the user's freeform description of things
    they need to do. Use this when the user describes new work, not when
    they're asking about existing tasks."""
    tasks = capture_backlog_from_text(text)
    return f"Added {len(tasks)} task(s) to the backlog: " + ", ".join(t.title for t in tasks)
