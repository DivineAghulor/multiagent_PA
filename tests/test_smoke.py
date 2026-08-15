"""Phase 0 smoke test: project is importable without a live DB or API keys."""
from __future__ import annotations

import pytest


def test_models_import() -> None:
    from db.models import Base, CalendarEvent, Habit, HabitLog, Milestone, Project, Task, WeeklyGoal

    assert "tasks" in Base.metadata.tables
    assert "calendar_events" in Base.metadata.tables


def test_tools_import() -> None:
    import tools.calendar
    import tools.habits
    import tools.milestones
    import tools.projects
    import tools.tasks
    import tools.weekly_goals


def test_session_module_importable() -> None:
    """Engine creation is lazy — importing db.session must not open a connection."""
    import db.session

    assert db.session.engine is not None


def test_llm_factory_rejects_unsupported_provider() -> None:
    from llm.factory import get_chat_model

    with pytest.raises(ValueError):
        get_chat_model("not-a-real-provider", "some-model")
