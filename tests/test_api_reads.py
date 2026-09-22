"""W1's read-only HTTP surface, driven through FastAPI's TestClient against the
in-memory SQLite DB the db_session fixture installs. No model call happens on
any of these paths — that is the point of W1."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app
from db.models import HabitFrequency
from tools.habits import create_habit, log_habit_completion
from tools.milestones import create_milestone
from tools.projects import create_project
from tools.reviews import save_week_summary
from tools.tasks import complete_task, create_task
from tools.weekly_goals import create_weekly_goal

MONDAY = date(2026, 9, 14)
TUESDAY = MONDAY + timedelta(days=1)


@pytest.fixture()
def client(db_session):
    with TestClient(app) as test_client:
        yield test_client


def error_of(response) -> tuple[str, str]:
    body = response.json()["error"]
    return body["type"], body["message"]


# --- Health --------------------------------------------------------------

def test_health_reports_configuration_without_exposing_any_key(client) -> None:
    body = client.get("/api/health").json()

    assert body["database"] is True
    assert body["status"] in {"ok", "degraded"}
    assert isinstance(body["provider_key_configured"], bool)
    # Presence only: no field may carry a key or a fragment of one.
    assert set(body) == {
        "status",
        "database",
        "provider",
        "model",
        "provider_key_configured",
        "tracing",
        "today",
    }


# --- Tasks ---------------------------------------------------------------

def test_task_list_is_empty_before_anything_is_captured(client) -> None:
    assert client.get("/api/tasks").json() == []


def test_task_list_exposes_the_derived_priority_alongside_the_pair(client) -> None:
    create_task("Fix login bug", importance=4, urgency=3)

    task = client.get("/api/tasks").json()[0]

    assert (task["importance"], task["urgency"]) == (4, 3)
    assert task["priority"] == "urgent"
    assert task["status"] == "backlog"


def test_task_list_filters(client) -> None:
    project = create_project("Website")
    create_task("Unrelated")
    create_task("Write copy", project_id=project.id)

    in_project = client.get("/api/tasks", params={"project_id": project.id}).json()
    assert [t["title"] for t in in_project] == ["Write copy"]

    assert client.get("/api/tasks", params={"status": "done"}).json() == []


def test_unknown_task_is_a_typed_404(client) -> None:
    response = client.get("/api/tasks/999")

    assert response.status_code == 404
    assert error_of(response) == ("not_found", "Task 999 not found")


def test_an_unparseable_filter_is_a_typed_422(client) -> None:
    response = client.get("/api/tasks", params={"status": "nonsense"})

    assert response.status_code == 422
    kind, message = error_of(response)
    assert kind == "validation"
    assert "status" in message


# --- Projects ------------------------------------------------------------

def test_project_detail_carries_its_milestones_and_tasks(client) -> None:
    project = create_project("Website", description="Rebuild")
    milestone = create_milestone(project.id, "Design", position=1)
    create_task("Write copy", project_id=project.id, milestone_id=milestone.id)

    body = client.get(f"/api/projects/{project.id}").json()

    assert body["name"] == "Website"
    assert body["status"] == "active"
    assert [(m["name"], m["status"]) for m in body["milestones"]] == [("Design", "planned")]
    assert [t["title"] for t in body["tasks"]] == ["Write copy"]


def test_project_list_filters_by_status(client) -> None:
    create_project("Website")

    assert len(client.get("/api/projects", params={"status": "active"}).json()) == 1
    assert client.get("/api/projects", params={"status": "archived"}).json() == []


def test_milestones_of_an_unknown_project_are_a_404_not_an_empty_list(client) -> None:
    response = client.get("/api/projects/999/milestones")

    assert response.status_code == 404
    assert error_of(response)[0] == "not_found"


# --- Habits --------------------------------------------------------------

def test_habit_list_hides_inactive_habits_by_default(client) -> None:
    habit = create_habit("Run", frequency=HabitFrequency.WEEKLY, target_per_period=3)

    body = client.get("/api/habits").json()
    assert [h["name"] for h in body] == ["Run"]
    assert body[0]["target_per_period"] == 3
    assert client.get(f"/api/habits/{habit.id}").json()["frequency"] == "weekly"


def test_habit_logs_come_back_for_the_requested_range(client) -> None:
    habit = create_habit("Run")
    log_habit_completion(habit.id, MONDAY)
    log_habit_completion(habit.id, MONDAY + timedelta(days=10))

    body = client.get(
        f"/api/habits/{habit.id}/logs",
        params={"start": MONDAY.isoformat(), "end": (MONDAY + timedelta(days=6)).isoformat()},
    ).json()

    assert [log["log_date"] for log in body] == [MONDAY.isoformat()]


# --- Week screen ---------------------------------------------------------

def test_week_reports_goal_progress_and_unplanned_work(client) -> None:
    task = create_task("Write copy")
    other = create_task("Answer email")
    goal = create_weekly_goal(MONDAY, "Ship the copy", task_ids=[task.id])
    complete_task(task.id, completed_at=datetime(2026, 9, 15, tzinfo=timezone.utc))
    complete_task(other.id, completed_at=datetime(2026, 9, 16, tzinfo=timezone.utc))

    body = client.get(f"/api/weeks/{MONDAY.isoformat()}").json()

    assert body["week_end"] == (MONDAY + timedelta(days=6)).isoformat()
    assert body["achieved_count"] == 1
    assert body["measurable_count"] == 1
    (progress,) = body["goals"]
    assert progress["goal"]["id"] == goal.id
    assert progress["achieved"] is True
    assert progress["headline"] == "Ship the copy: 1/1 task(s) done"
    assert [t["title"] for t in progress["tasks"]] == ["Write copy"]
    assert [t["title"] for t in body["unplanned_done"]] == ["Answer email"]
    assert body["review"] is None  # nothing generated yet
    assert "Ship the copy" in body["facts"]


def test_week_carries_its_stored_summary_with_the_counts_it_was_written_against(client) -> None:
    save_week_summary(
        MONDAY, "A decent week.", achieved_count=1, measurable_count=2, unplanned_count=0
    )
    # Work completed after the review was written must not move its numbers.
    task = create_task("Late finish")
    create_weekly_goal(MONDAY, "Ship the copy", task_ids=[task.id])
    complete_task(task.id, completed_at=datetime(2026, 9, 18, tzinfo=timezone.utc))

    body = client.get(f"/api/weeks/{MONDAY.isoformat()}").json()

    assert body["review"]["summary"] == "A decent week."
    assert body["review"]["measurable_count"] == 2  # snapshot
    assert body["measurable_count"] == 1  # live


def test_a_week_start_that_is_not_a_monday_is_rejected(client) -> None:
    response = client.get(f"/api/weeks/{TUESDAY.isoformat()}")

    assert response.status_code == 400
    kind, message = error_of(response)
    assert kind == "invalid_request"
    assert "Monday" in message and "Tuesday" in message


def test_current_week_uses_the_server_date(client, monkeypatch) -> None:
    import api.deps

    monkeypatch.setattr(api.deps, "today", lambda: date(2026, 9, 17))  # a Thursday

    assert client.get("/api/weeks/current").json()["week_start"] == MONDAY.isoformat()


def test_review_history_is_newest_week_first(client) -> None:
    for offset, text in ((0, "This week."), (-7, "Last week."), (-14, "Two weeks ago.")):
        save_week_summary(
            MONDAY + timedelta(days=offset),
            text,
            achieved_count=0,
            measurable_count=0,
            unplanned_count=0,
        )

    body = client.get("/api/reviews").json()
    assert [r["summary"] for r in body] == ["This week.", "Last week.", "Two weeks ago."]
    assert len(client.get("/api/reviews", params={"limit": 2}).json()) == 2


# --- Planning context ----------------------------------------------------

def test_planning_context_shows_what_the_model_would_be_given(client, monkeypatch) -> None:
    import api.deps

    monkeypatch.setattr(api.deps, "today", lambda: date(2026, 9, 16))  # a Wednesday
    create_task("Write copy")
    create_project("Website")
    create_habit("Run")

    body = client.get("/api/planning/context").json()

    assert body["week_start"] == MONDAY.isoformat()  # this week, mid-week
    assert [t["title"] for t in body["backlog"]] == ["Write copy"]
    assert [p["name"] for p in body["projects"]] == ["Website"]
    assert [h["name"] for h in body["habits"]] == ["Run"]
    assert "Write copy" in body["rendered"]


def test_planning_context_excludes_tasks_already_attached_to_a_goal(client) -> None:
    task = create_task("Write copy")
    create_weekly_goal(MONDAY, "Ship the copy", task_ids=[task.id])

    body = client.get("/api/planning/context", params={"week_start": MONDAY.isoformat()}).json()

    assert body["backlog"] == []
    assert [g["description"] for g in body["existing_goals"]] == ["Ship the copy"]


def test_planning_context_rejects_a_non_monday_week(client) -> None:
    response = client.get("/api/planning/context", params={"week_start": TUESDAY.isoformat()})

    assert response.status_code == 400
    assert error_of(response)[0] == "invalid_request"


# --- Error envelope ------------------------------------------------------

def test_a_response_that_fails_to_serialise_is_a_500_not_a_400(client, monkeypatch) -> None:
    """Pydantic's ValidationError subclasses ValueError, which the API
    otherwise treats as a bad request. A response model that can't be built is
    the server's fault and must not be blamed on the caller."""
    import api.routers.tasks

    monkeypatch.setattr(api.routers.tasks, "list_tasks", lambda **_: [object()])

    response = client.get("/api/tasks")

    assert response.status_code == 500
    assert error_of(response)[0] == "internal"
