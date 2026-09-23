"""W3's planning conversation over HTTP. The model is mocked at the planning
agent's boundary (propose_weekly_plan), so sanitising, history handling and
confirmation all run for real against the in-memory DB."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from agents.pm.schemas import ProposedGoal, WeeklyPlanProposal
from api.main import app
from api.sessions import InMemoryDraftStore, get_draft_store
from db.models import HabitFrequency, TaskStatus
from tools.habits import create_habit
from tools.projects import create_project
from tools.tasks import create_task, delete_task, get_task
from tools.weekly_goals import list_weekly_goals

WEDNESDAY = date(2026, 9, 16)
THIS_MONDAY = date(2026, 9, 14)
NEXT_MONDAY = date(2026, 9, 21)


@pytest.fixture()
def store() -> InMemoryDraftStore:
    return InMemoryDraftStore()


@pytest.fixture()
def client(db_session, store, monkeypatch):
    import api.deps
    import llm.factory

    monkeypatch.setattr(api.deps, "today", lambda: WEDNESDAY)
    monkeypatch.setattr(llm.factory, "provider_key_configured", lambda provider=None: True)
    app.dependency_overrides[get_draft_store] = lambda: store
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_draft_store, None)


@pytest.fixture()
def seeded(db_session):
    website = create_project("Website")
    gym = create_habit("Gym", frequency=HabitFrequency.WEEKLY, target_per_period=3)
    pricing = create_task("Update pricing page", project_id=website.id)
    dentist = create_task("Call the dentist")
    return {"website": website, "gym": gym, "pricing": pricing, "dentist": dentist}


@pytest.fixture()
def model(monkeypatch):
    """Replays proposals in order and records the history each call was given."""
    import agents.pm.planning

    class Model:
        def __init__(self) -> None:
            self.proposals: list[WeeklyPlanProposal | Exception] = []
            self.histories: list[list[tuple[str, str]]] = []

        def __call__(self, history, ctx):
            self.histories.append(list(history))
            item = self.proposals.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    fake = Model()
    monkeypatch.setattr(agents.pm.planning, "propose_weekly_plan", fake)
    return fake


def error_of(response) -> tuple[str, str]:
    body = response.json()["error"]
    return body["type"], body["message"]


def start(client, **body) -> dict:
    response = client.post("/api/planning/sessions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_a_session_defaults_to_the_planning_week_and_shows_its_context(client, seeded) -> None:
    session = start(client)

    assert session["week_start"] == THIS_MONDAY.isoformat()  # mid-week plans this week
    assert [t["title"] for t in session["context"]["backlog"]] == ["Update pricing page", "Call the dentist"]
    assert session["messages"] == [] and session["proposal"] is None


def test_the_week_is_selectable_but_must_be_a_monday(client, seeded) -> None:
    assert start(client, week_start=NEXT_MONDAY.isoformat())["week_start"] == NEXT_MONDAY.isoformat()

    response = client.post("/api/planning/sessions", json={"week_start": "2026-09-22"})
    assert response.status_code == 400


def test_a_turn_returns_the_sanitised_plan_with_names_and_warnings(client, seeded, model) -> None:
    model.proposals.append(
        WeeklyPlanProposal(
            reply="Pricing page and the gym.",
            goals=[
                ProposedGoal(
                    description="Ship pricing",
                    project_id=seeded["website"].id,
                    task_ids=[seeded["pricing"].id, 999],
                ),
                ProposedGoal(description="Gym", habit_id=seeded["gym"].id, target_count=3),
            ],
        )
    )
    session = start(client)

    body = client.post(
        f"/api/planning/sessions/{session['session_id']}/messages", json={"text": "website and gym"}
    ).json()

    assert body["messages"] == [
        {"role": "user", "text": "website and gym"},
        {"role": "assistant", "text": "Pricing page and the gym."},
    ]
    pricing, gym = body["proposal"]["goals"]
    assert pricing["project_name"] == "Website"
    assert pricing["tasks"] == [{"id": seeded["pricing"].id, "title": "Update pricing page"}]
    assert (gym["habit_name"], gym["target_count"]) == ("Gym", 3)
    assert any("999" in w for w in body["warnings"])
    assert list_weekly_goals() == []  # nothing written before confirmation (FR-9)


def test_later_turns_send_the_whole_conversation(client, seeded, model) -> None:
    model.proposals += [
        WeeklyPlanProposal(reply="First.", goals=[]),
        WeeklyPlanProposal(reply="Second.", goals=[]),
    ]
    sid = start(client)["session_id"]

    client.post(f"/api/planning/sessions/{sid}/messages", json={"text": "one"})
    body = client.post(f"/api/planning/sessions/{sid}/messages", json={"text": "two"}).json()

    roles = [role for role, _ in model.histories[1]]
    assert roles == ["user", "assistant", "user"]
    assert model.histories[1][-1] == ("user", "two")
    assert [m["text"] for m in body["messages"]] == ["one", "First.", "two", "Second."]


def test_a_provider_failure_leaves_the_conversation_untouched(client, seeded, model) -> None:
    model.proposals += [WeeklyPlanProposal(reply="First.", goals=[]), RuntimeError("provider down")]
    sid = start(client)["session_id"]
    client.post(f"/api/planning/sessions/{sid}/messages", json={"text": "one"})

    response = client.post(f"/api/planning/sessions/{sid}/messages", json={"text": "two"})

    assert response.status_code == 502
    assert error_of(response)[0] == "provider"
    after = client.get(f"/api/planning/sessions/{sid}").json()
    assert [m["text"] for m in after["messages"]] == ["one", "First."]


def test_each_turn_sees_the_current_backlog(client, seeded, model) -> None:
    model.proposals += [WeeklyPlanProposal(reply="ok", goals=[]), WeeklyPlanProposal(reply="ok", goals=[])]
    sid = start(client)["session_id"]
    client.post(f"/api/planning/sessions/{sid}/messages", json={"text": "one"})

    create_task("Captured mid-conversation")
    body = client.post(f"/api/planning/sessions/{sid}/messages", json={"text": "two"}).json()

    assert "Captured mid-conversation" in [t["title"] for t in body["context"]["backlog"]]


def test_confirm_writes_goals_links_tasks_and_ends_the_session(client, seeded, model) -> None:
    model.proposals.append(
        WeeklyPlanProposal(
            reply="ok",
            goals=[ProposedGoal(description="Ship pricing", project_id=seeded["website"].id, task_ids=[seeded["pricing"].id])],
        )
    )
    sid = start(client)["session_id"]
    client.post(f"/api/planning/sessions/{sid}/messages", json={"text": "pricing"})

    response = client.post(f"/api/planning/sessions/{sid}/confirm")

    assert response.status_code == 200
    (goal,) = response.json()
    assert (goal["description"], goal["week_start"]) == ("Ship pricing", THIS_MONDAY.isoformat())
    pricing = get_task(seeded["pricing"].id)
    assert (pricing.weekly_goal_id, pricing.status) == (goal["id"], TaskStatus.TODO)

    gone = client.get(f"/api/planning/sessions/{sid}")
    assert gone.status_code == 404 and error_of(gone)[0] == "session_expired"


def test_confirm_without_a_plan_is_rejected(client, seeded) -> None:
    sid = start(client)["session_id"]
    response = client.post(f"/api/planning/sessions/{sid}/confirm")
    assert response.status_code == 400
    assert client.get(f"/api/planning/sessions/{sid}").status_code == 200


def test_a_stale_plan_is_rejected_whole_and_the_session_survives(client, seeded, model) -> None:
    model.proposals.append(
        WeeklyPlanProposal(
            reply="ok",
            goals=[
                ProposedGoal(description="Admin", task_ids=[seeded["dentist"].id]),
                ProposedGoal(description="Ship pricing", task_ids=[seeded["pricing"].id]),
            ],
        )
    )
    sid = start(client)["session_id"]
    client.post(f"/api/planning/sessions/{sid}/messages", json={"text": "both"})
    delete_task(seeded["dentist"].id)  # the plan now references a task that's gone

    response = client.post(f"/api/planning/sessions/{sid}/confirm")

    assert response.status_code == 400
    assert "out of date" in error_of(response)[1]
    assert list_weekly_goals() == []  # not half-applied
    assert client.get(f"/api/planning/sessions/{sid}").status_code == 200


def test_cancel_discards_the_session(client, seeded) -> None:
    sid = start(client)["session_id"]
    assert client.delete(f"/api/planning/sessions/{sid}").status_code == 204
    assert client.get(f"/api/planning/sessions/{sid}").status_code == 404
    assert client.delete(f"/api/planning/sessions/{sid}").status_code == 204


def test_a_lost_session_says_so(client) -> None:
    """What the client sees after a backend restart (S-3)."""
    response = client.post("/api/planning/sessions/not-a-session/messages", json={"text": "hi"})
    assert response.status_code == 404
    kind, message = error_of(response)
    assert kind == "session_expired"
    assert "Start again" in message


def test_a_busy_session_is_a_conflict(client, seeded, store) -> None:
    sid = start(client)["session_id"]
    session = store.get(sid, "planning")
    with store.exclusive(session):
        response = client.post(f"/api/planning/sessions/{sid}/confirm")
    assert response.status_code == 409
    assert error_of(response)[0] == "conflict"


def test_blank_messages_are_rejected(client, seeded, model) -> None:
    sid = start(client)["session_id"]
    assert client.post(f"/api/planning/sessions/{sid}/messages", json={"text": "  "}).status_code == 422
    assert model.histories == []


def test_confirm_writes_only_the_goals_kept_with_the_users_edits(client, seeded, model) -> None:
    model.proposals.append(
        WeeklyPlanProposal(
            reply="ok",
            goals=[
                ProposedGoal(description="Admin", task_ids=[seeded["dentist"].id]),
                ProposedGoal(description="Gym", habit_id=seeded["gym"].id, target_count=3),
            ],
        )
    )
    sid = start(client)["session_id"]
    client.post(f"/api/planning/sessions/{sid}/messages", json={"text": "both"})

    response = client.post(
        f"/api/planning/sessions/{sid}/confirm",
        json={"goals": [{"index": 1, "description": "Gym, properly", "target_count": 2}]},
    )

    assert response.status_code == 200
    (goal,) = response.json()
    assert (goal["description"], goal["target_count"], goal["habit_id"]) == ("Gym, properly", 2, seeded["gym"].id)
    assert get_task(seeded["dentist"].id).weekly_goal_id is None  # the unticked goal wrote nothing


def test_confirm_edits_are_validated(client, seeded, model) -> None:
    model.proposals.append(WeeklyPlanProposal(reply="ok", goals=[ProposedGoal(description="Admin")]))
    sid = start(client)["session_id"]
    client.post(f"/api/planning/sessions/{sid}/messages", json={"text": "admin"})
    confirm = f"/api/planning/sessions/{sid}/confirm"

    assert client.post(confirm, json={"goals": [{"index": 5, "description": "x"}]}).status_code == 400
    assert client.post(confirm, json={"goals": []}).status_code == 400
    assert client.post(confirm, json={"goals": [{"index": 0, "description": " "}]}).status_code == 422
    assert client.post(confirm, json={"goals": [{"index": 0, "description": "x", "target_count": 0}]}).status_code == 422
    # a goal can't be re-pointed at another project or task through an edit
    assert client.post(confirm, json={"goals": [{"index": 0, "description": "x", "task_ids": [1]}]}).status_code == 422
    assert list_weekly_goals() == []

