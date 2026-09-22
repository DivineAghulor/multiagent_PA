"""Task.priority is derived from (importance, urgency) and never set directly."""
from __future__ import annotations

import pytest

from db.models import TaskPriority
from tools.tasks import create_task, derive_priority, get_task, update_task_priority


@pytest.mark.parametrize(
    "importance,urgency,expected",
    [
        (4, 4, TaskPriority.URGENT),
        (3, 3, TaskPriority.URGENT),
        (4, 2, TaskPriority.HIGH),
        (3, 1, TaskPriority.HIGH),
        (2, 4, TaskPriority.MEDIUM),
        (1, 3, TaskPriority.MEDIUM),
        (2, 2, TaskPriority.LOW),
        (1, 1, TaskPriority.LOW),
    ],
)
def test_derive_priority_covers_every_quadrant(importance, urgency, expected) -> None:
    assert derive_priority(importance, urgency) == expected


@pytest.mark.parametrize("pair", [(None, None), (3, None), (None, 4)])
def test_derive_priority_defaults_to_medium_when_unrated(pair) -> None:
    assert derive_priority(*pair) == TaskPriority.MEDIUM


def test_created_task_gets_its_derived_priority(db_session) -> None:
    task = create_task("Fix login bug", importance=4, urgency=3)
    assert task.priority == TaskPriority.URGENT
    assert get_task(task.id).priority == TaskPriority.URGENT


def test_unrated_task_is_medium(db_session) -> None:
    assert create_task("Someday maybe").priority == TaskPriority.MEDIUM


def test_rating_a_task_updates_its_priority(db_session) -> None:
    task = create_task("Renew passport")
    assert task.priority == TaskPriority.MEDIUM

    update_task_priority(task.id, importance=4, urgency=1)
    assert get_task(task.id).priority == TaskPriority.HIGH

    # re-rating moves it again, rather than leaving the first derivation behind
    update_task_priority(task.id, importance=1, urgency=1)
    assert get_task(task.id).priority == TaskPriority.LOW


def test_priority_is_not_a_create_task_parameter() -> None:
    with pytest.raises(TypeError):
        create_task("Nope", priority=TaskPriority.URGENT)
