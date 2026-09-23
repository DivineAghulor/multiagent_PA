"""W2's write surface: capture, task CRUD, project/habit/milestone management.

Capture is the only model-backed endpoint here, and the agent entry point is
mocked at the router (T-1) — no provider is contacted.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import app
from db.models import HabitFrequency, TaskStatus
from tools.habits import create_habit, get_habit_logs
from tools.milestones import create_milestone
from tools.projects import create_project
from tools.tasks import complete_task, create_task, get_task

TODAY = date(2026, 9, 16)  # a Wednesday


@pytest.fixture()
def client(db_session, monkeypatch):
    import api.deps

    monkeypatch.setattr(api.deps, "today", lambda: TODAY)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def key_configured(monkeypatch):
    import llm.factory

    monkeypatch.setattr(llm.factory, "provider_key_configured", lambda provider=None: True)


def error_of(response) -> tuple[str, str]:
    body = response.json()["error"]
    return body["type"], body["message"]


# --- Capture (model call, mocked) ----------------------------------------

def test_capture_returns_the_created_tasks(client, key_configured, monkeypatch) -> None:
    import api.routers.backlog

    seen = {}

    def fake_capture(text):
        seen["text"] = text
        return [create_task("Fix login bug"), create_task("Email Sam")]

    monkeypatch.setattr(api.routers.backlog, "capture_backlog_from_text", fake_capture)

    response = client.post("/api/backlog/capture", json={"text": "  fix login, email sam  "})

    assert response.status_code == 201
    assert [t["title"] for t in response.json()] == ["Fix login bug", "Email Sam"]
    assert all(t["importance"] is None for t in response.json())  # unrated until FR-2
    assert seen["text"] == "fix login, email sam"


def test_capture_rejects_blank_text_without_calling_the_model(client, key_configured, monkeypatch) -> None:
    import api.routers.backlog

    def must_not_run(text):
        raise AssertionError("model called")

    monkeypatch.setattr(api.routers.backlog, "capture_backlog_from_text", must_not_run)

    response = client.post("/api/backlog/capture", json={"text": "   "})

    assert response.status_code == 422
    assert error_of(response)[0] == "validation"


def test_capture_provider_failure_is_typed_and_redacted(client, key_configured, monkeypatch) -> None:
    import api.routers.backlog

    def boom(text):
        raise RuntimeError("401 Incorrect API key provided: sk-ab***yz9876")

    monkeypatch.setattr(api.routers.backlog, "capture_backlog_from_text", boom)

    response = client.post("/api/backlog/capture", json={"text": "fix login"})

    assert response.status_code == 502
    kind, message = error_of(response)
    assert kind == "provider"
    assert "RuntimeError" in message
    assert "sk-ab" not in message and "yz9876" not in message


def test_capture_without_a_key_is_a_503_and_never_reaches_the_agent(client, monkeypatch) -> None:
    import api.routers.backlog
    import llm.factory

    monkeypatch.setattr(llm.factory, "provider_key_configured", lambda provider=None: False)
    monkeypatch.setattr(
        api.routers.backlog,
        "capture_backlog_from_text",
        lambda text: (_ for _ in ()).throw(AssertionError("model called")),
    )

    response = client.post("/api/backlog/capture", json={"text": "fix login"})

    assert response.status_code == 503
    assert error_of(response)[0] == "provider"


def test_capture_malformed_model_output_is_a_provider_error(client, key_configured, monkeypatch) -> None:
    """Structured output that fails validation is the provider's failure, not
    the caller's — it must not come back as a 400 or a 500."""
    import api.routers.backlog
    from agents.pm.schemas import ExtractedTaskBatch

    def malformed(text):
        ExtractedTaskBatch.model_validate({"tasks": "not a list"})

    monkeypatch.setattr(api.routers.backlog, "capture_backlog_from_text", malformed)

    response = client.post("/api/backlog/capture", json={"text": "fix login"})

    assert response.status_code == 502
    assert error_of(response)[0] == "provider"


# --- Tasks ---------------------------------------------------------------

def test_rating_a_task_derives_its_priority(client) -> None:
    task = create_task("Fix login bug")

    body = client.patch(f"/api/tasks/{task.id}/priority", json={"importance": 4, "urgency": 1}).json()

    assert (body["importance"], body["urgency"], body["priority"]) == (4, 1, "high")


@pytest.mark.parametrize("pair", [{"importance": 0, "urgency": 2}, {"importance": 2, "urgency": 5}])
def test_ratings_outside_1_to_4_are_rejected(client, pair) -> None:
    task = create_task("Fix login bug")
    response = client.patch(f"/api/tasks/{task.id}/priority", json=pair)
    assert response.status_code == 422


def test_priority_cannot_be_set_directly(client) -> None:
    task = create_task("Fix login bug")
    response = client.patch(f"/api/tasks/{task.id}", json={"priority": "urgent"})
    assert response.status_code == 422


def test_patch_edits_only_the_fields_sent_and_null_clears(client) -> None:
    project = create_project("Website")
    task = create_task("Draft copy", description="homepage", project_id=project.id, due_date=date(2026, 10, 1))

    body = client.patch(f"/api/tasks/{task.id}", json={"title": "Write copy", "due_date": None}).json()

    assert body["title"] == "Write copy"
    assert body["description"] == "homepage"
    assert body["project_id"] == project.id
    assert body["due_date"] is None


def test_patch_rejects_a_null_title(client) -> None:
    task = create_task("Write copy")
    response = client.patch(f"/api/tasks/{task.id}", json={"title": None})
    assert response.status_code == 422


def test_patch_rejects_a_milestone_from_another_project(client) -> None:
    website = create_project("Website")
    garden = create_project("Garden")
    milestone = create_milestone(garden.id, "Beds")
    task = create_task("Write copy", project_id=website.id)

    response = client.patch(f"/api/tasks/{task.id}", json={"milestone_id": milestone.id})

    assert response.status_code == 400
    assert "belongs to project" in error_of(response)[1]


def test_status_changes_keep_completed_at_consistent(client) -> None:
    task = create_task("Write copy")

    done = client.put(f"/api/tasks/{task.id}/status", json={"status": "done"}).json()
    assert done["status"] == "done" and done["completed_at"] is not None

    blocked = client.put(f"/api/tasks/{task.id}/status", json={"status": "blocked"}).json()
    assert blocked["status"] == "blocked" and blocked["completed_at"] is None


def test_complete_and_reopen(client) -> None:
    task = create_task("Write copy")

    assert client.post(f"/api/tasks/{task.id}/complete").json()["status"] == "done"
    reopened = client.post(f"/api/tasks/{task.id}/reopen").json()
    assert (reopened["status"], reopened["completed_at"]) == ("todo", None)


def test_schedule_and_unschedule(client) -> None:
    task = create_task("Write copy")

    assert client.put(f"/api/tasks/{task.id}/schedule", json={"scheduled_for": "2026-09-17"}).json()[
        "scheduled_for"
    ] == "2026-09-17"
    assert client.put(f"/api/tasks/{task.id}/schedule", json={"scheduled_for": None}).json()[
        "scheduled_for"
    ] is None


def test_delete_task(client) -> None:
    task = create_task("Write copy")

    assert client.delete(f"/api/tasks/{task.id}").status_code == 204
    assert get_task(task.id) is None
    assert client.delete(f"/api/tasks/{task.id}").status_code == 404


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("patch", "/api/tasks/999", {"title": "x"}),
        ("patch", "/api/tasks/999/priority", {"importance": 1, "urgency": 1}),
        ("put", "/api/tasks/999/status", {"status": "todo"}),
        ("post", "/api/tasks/999/complete", None),
        ("post", "/api/tasks/999/reopen", None),
        ("put", "/api/tasks/999/schedule", {"scheduled_for": None}),
        ("patch", "/api/projects/999", {"name": "x"}),
        ("post", "/api/projects/999/archive", None),
        ("patch", "/api/milestones/999", {"status": "done"}),
        ("patch", "/api/habits/999", {"name": "x"}),
        ("post", "/api/habits/999/deactivate", None),
        ("post", "/api/habits/999/logs", {"date": "2026-09-14"}),
    ],
)
def test_writes_to_a_missing_row_are_404s(client, method, path, body) -> None:
    response = client.request(method.upper(), path, json=body)
    assert response.status_code == 404
    assert error_of(response)[0] == "not_found"


# --- Projects and milestones ---------------------------------------------

def test_create_edit_and_archive_a_project(client) -> None:
    created = client.post("/api/projects", json={"name": "  Website ", "description": "Rebuild"})
    assert created.status_code == 201
    project = created.json()
    assert (project["name"], project["status"]) == ("Website", "active")

    edited = client.patch(
        f"/api/projects/{project['id']}", json={"target_date": "2026-12-01", "description": None}
    ).json()
    assert (edited["target_date"], edited["description"]) == ("2026-12-01", None)

    assert client.post(f"/api/projects/{project['id']}/archive").json()["status"] == "archived"
    assert client.get("/api/projects", params={"status": "active"}).json() == []

    restored = client.patch(f"/api/projects/{project['id']}", json={"status": "active"}).json()
    assert restored["status"] == "active"


def test_project_name_is_required(client) -> None:
    assert client.post("/api/projects", json={"name": "   "}).status_code == 422
    project = create_project("Website")
    assert client.patch(f"/api/projects/{project.id}", json={"name": None}).status_code == 422


def test_milestone_status_update(client) -> None:
    project = create_project("Website")
    milestone = create_milestone(project.id, "Design")

    body = client.patch(f"/api/milestones/{milestone.id}", json={"status": "in_progress"}).json()

    assert (body["name"], body["status"]) == ("Design", "in_progress")


# --- Habits --------------------------------------------------------------

def test_create_edit_deactivate_and_reactivate_a_habit(client) -> None:
    created = client.post("/api/habits", json={"name": "Run", "frequency": "weekly", "target_per_period": 3})
    assert created.status_code == 201
    habit = created.json()
    assert (habit["frequency"], habit["target_per_period"], habit["active"]) == ("weekly", 3, True)

    edited = client.patch(f"/api/habits/{habit['id']}", json={"target_per_period": 4}).json()
    assert edited["target_per_period"] == 4

    assert client.post(f"/api/habits/{habit['id']}/deactivate").json()["active"] is False
    assert client.get("/api/habits").json() == []
    assert len(client.get("/api/habits", params={"active_only": False}).json()) == 1

    assert client.patch(f"/api/habits/{habit['id']}", json={"active": True}).json()["active"] is True


def test_habit_target_must_be_positive(client) -> None:
    assert client.post("/api/habits", json={"name": "Run", "target_per_period": 0}).status_code == 422


def test_habit_day_ticking_is_idempotent_and_reversible(client) -> None:
    habit = create_habit("Run", frequency=HabitFrequency.DAILY)
    monday = TODAY - timedelta(days=2)

    for _ in range(2):
        assert client.post(f"/api/habits/{habit.id}/logs", json={"date": monday.isoformat()}).status_code == 201
    assert len(get_habit_logs(habit.id, monday, monday)) == 1

    assert client.delete(f"/api/habits/{habit.id}/logs/{monday.isoformat()}").status_code == 204
    assert get_habit_logs(habit.id, monday, monday) == []
    # unticking an unlogged day is a no-op, not an error
    assert client.delete(f"/api/habits/{habit.id}/logs/{monday.isoformat()}").status_code == 204


def test_a_future_day_cannot_be_ticked(client) -> None:
    habit = create_habit("Run")

    response = client.post(
        f"/api/habits/{habit.id}/logs", json={"date": (TODAY + timedelta(days=1)).isoformat()}
    )

    assert response.status_code == 400
    assert "future" in error_of(response)[1]


# --- Error envelope ------------------------------------------------------

def test_an_unexpected_error_keeps_the_envelope(client, monkeypatch) -> None:
    import api.routers.tasks

    def boom(task_id):
        raise RuntimeError("secret internals")

    monkeypatch.setattr(api.routers.tasks, "get_task", boom)

    response = client.get("/api/tasks/1")

    assert response.status_code == 500
    kind, message = error_of(response)
    assert kind == "internal"
    assert "secret internals" not in message


def test_status_is_a_known_value(client) -> None:
    task = create_task("Write copy")
    complete_task(task.id)
    response = client.put(f"/api/tasks/{task.id}/status", json={"status": "finished"})
    assert response.status_code == 422
    assert get_task(task.id).status == TaskStatus.DONE
