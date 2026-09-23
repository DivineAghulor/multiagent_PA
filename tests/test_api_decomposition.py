"""W4's decomposition sessions over HTTP + SSE. The chat model is a scripted
fake that emits real tool calls, so the loop, the draft edits, the progress
stream and confirmation all run for real — with no provider contacted."""
from __future__ import annotations

import itertools
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from api.main import app
from api.sessions import InMemoryDraftStore, get_draft_store
from tools.milestones import create_milestone, list_milestones
from tools.projects import create_project, list_projects
from tools.tasks import create_task, get_task, list_tasks

TODAY = date(2026, 9, 18)
_ids = itertools.count(1)


def call(tool_name: str, **args) -> dict:
    return {"name": tool_name, "args": args, "id": f"call_{next(_ids)}"}


class ScriptedModel:
    """bind_tools returns itself; invoke replays responses (or raises them)."""

    def __init__(self) -> None:
        self.responses: list[AIMessage | Exception] = []
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture()
def store() -> InMemoryDraftStore:
    return InMemoryDraftStore()


@pytest.fixture()
def model(monkeypatch) -> ScriptedModel:
    import agents.pm.decomposition

    fake = ScriptedModel()
    monkeypatch.setattr(agents.pm.decomposition, "get_default_chat_model", lambda **_: fake)
    return fake


@pytest.fixture()
def client(db_session, store, monkeypatch):
    import api.deps
    import llm.factory

    monkeypatch.setattr(api.deps, "today", lambda: TODAY)
    monkeypatch.setattr(llm.factory, "provider_key_configured", lambda provider=None: True)
    app.dependency_overrides[get_draft_store] = lambda: store
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_draft_store, None)


def events_of(response) -> list[tuple[str, dict]]:
    """Parse an SSE body into (event, data) pairs."""
    out = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def error_of(response) -> tuple[str, str]:
    body = response.json()["error"]
    return body["type"], body["message"]


def new_session(client, **body) -> dict:
    response = client.post("/api/decomposition/sessions", json=body or {"name": "Podcast", "description": "A weekly show"})
    assert response.status_code == 201, response.text
    return response.json()


def send(client, sid: str, text: str = "break it down"):
    return client.post(f"/api/decomposition/sessions/{sid}/messages", json={"text": text})


BUILD_TURN = [
    AIMessage(
        content="",
        tool_calls=[
            call("add_milestone", name="Pilot recorded", tasks=["Buy a microphone", "Record episode 1"]),
            call("add_milestone", name="Launched", tasks=["Publish on Spotify"]),
        ],
    ),
    AIMessage(content="", tool_calls=[call("view_draft")]),
    AIMessage(content="Two milestones. Want a marketing one?"),
]


# --- Starting --------------------------------------------------------------

def test_a_new_project_draft_starts_empty_and_writes_nothing(client) -> None:
    session = new_session(client)

    draft = session["draft"]
    assert (draft["project_name"], draft["project_id"], draft["milestones"]) == ("Podcast", None, [])
    assert session["last_turn"] is None
    assert list_projects() == []


def test_an_existing_project_draft_preloads_milestones_and_attachable_tasks(client) -> None:
    project = create_project("Website")
    milestone = create_milestone(project.id, "Design approved", position=1)
    create_task("Draft wireframes", project_id=project.id, milestone_id=milestone.id)
    loose = create_task("Write copy", project_id=project.id)

    draft = new_session(client, project_id=project.id)["draft"]

    (m,) = draft["milestones"]
    assert (m["ref"], m["existing_id"], m["existing_task_titles"]) == ("M1", milestone.id, ["Draft wireframes"])
    assert draft["eligible_tasks"] == [{"id": loose.id, "title": "Write copy"}]


@pytest.mark.parametrize(
    "body,status_code",
    [({"project_id": 999}, 404), ({}, 422), ({"project_id": 1, "name": "x"}, 422), ({"name": "  "}, 422)],
)
def test_start_rejects_bad_targets(client, body, status_code) -> None:
    assert client.post("/api/decomposition/sessions", json=body).status_code == status_code


# --- Turns -----------------------------------------------------------------

def test_a_turn_streams_progress_then_the_whole_session(client, model) -> None:
    model.responses += BUILD_TURN
    sid = new_session(client)["session_id"]

    response = send(client, sid)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = events_of(response)
    progress = [data for name, data in events if name == "progress"]
    assert progress[0] == {"phase": "step", "step": 1, "tool_calls": 0, "tool": None}
    assert {"phase": "tool", "step": 1, "tool_calls": 2, "tool": "add_milestone"} in progress
    assert [p["step"] for p in progress if p["phase"] == "step"] == [1, 2, 3]

    name, session = events[-1]
    assert name == "result"
    assert session["last_turn"] == {"steps": 3, "tool_calls": 3, "hit_limit": False}
    assert [(m["ref"], m["name"]) for m in session["draft"]["milestones"]] == [("M1", "Pilot recorded"), ("M4", "Launched")]
    assert [t["title"] for t in session["draft"]["milestones"][0]["tasks"]] == ["Buy a microphone", "Record episode 1"]
    assert session["messages"][-1] == {"role": "assistant", "text": "Two milestones. Want a marketing one?"}
    assert list_projects() == []  # still nothing written


def test_refs_stay_stable_across_turns(client, model) -> None:
    model.responses += BUILD_TURN
    sid = new_session(client)["session_id"]
    send(client, sid)

    # The second turn names M1 and T2 from the first; they must still resolve.
    model.responses += [
        AIMessage(content="", tool_calls=[call("add_task", milestone_ref="M1", title="Edit episode 1"),
                                          call("remove_task", task_ref="T2")]),
        AIMessage(content="Swapped the mic for editing."),
    ]
    session = events_of(send(client, sid, "drop the mic, add editing"))[-1][1]

    titles = [t["title"] for t in session["draft"]["milestones"][0]["tasks"]]
    assert titles == ["Record episode 1", "Edit episode 1"]


def test_a_failed_turn_reports_in_band_and_leaves_the_draft_untouched(client, model) -> None:
    model.responses += BUILD_TURN
    sid = new_session(client)["session_id"]
    before = events_of(send(client, sid))[-1][1]["draft"]

    # This turn edits the draft, then the provider fails before it finishes.
    model.responses += [
        AIMessage(content="", tool_calls=[call("remove_milestone", milestone_ref="M1")]),
        RuntimeError("503 from provider, key sk-proj-abcdef123456"),
    ]
    events = events_of(send(client, sid, "change it"))

    name, error = events[-1]
    assert name == "error" and error["type"] == "provider"
    assert "sk-proj" not in error["message"]
    after = client.get(f"/api/decomposition/sessions/{sid}").json()
    assert after["draft"] == before  # the half-finished turn was never committed
    assert len(after["messages"]) == 2


def test_hitting_the_step_limit_is_reported_as_such(client, model, monkeypatch) -> None:
    import functools

    import api.routers.decomposition
    from agents.pm.decomposition import run_decomposition_turn

    monkeypatch.setattr(
        api.routers.decomposition,
        "run_decomposition_turn",
        functools.partial(run_decomposition_turn, max_steps=2),
    )
    model.responses += [AIMessage(content="", tool_calls=[call("view_draft")])] * 2
    sid = new_session(client)["session_id"]

    session = events_of(send(client, sid))[-1][1]

    assert session["last_turn"] == {"steps": 2, "tool_calls": 2, "hit_limit": True}
    assert "step limit" in session["messages"][-1]["text"]


def test_a_busy_session_reports_a_conflict_in_band(client, store) -> None:
    sid = new_session(client)["session_id"]
    with store.exclusive(store.get(sid, "decomposition")):
        events = events_of(send(client, sid))
    assert events == [("error", {"type": "conflict", "message": events[0][1]["message"]})]


def test_missing_session_and_missing_key_fail_before_streaming(client, monkeypatch) -> None:
    import llm.factory

    lost = send(client, "not-a-session")
    assert lost.status_code == 404 and error_of(lost)[0] == "session_expired"

    sid = new_session(client)["session_id"]
    monkeypatch.setattr(llm.factory, "provider_key_configured", lambda provider=None: False)
    no_key = send(client, sid)
    assert no_key.status_code == 503 and error_of(no_key)[0] == "provider"


# --- Confirm ---------------------------------------------------------------

def test_confirm_writes_the_project_and_ends_the_session(client, model) -> None:
    model.responses += BUILD_TURN
    sid = new_session(client)["session_id"]
    send(client, sid)

    response = client.post(f"/api/decomposition/sessions/{sid}/confirm", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["name"] == "Podcast"
    assert [m["name"] for m in body["milestones"]] == ["Pilot recorded", "Launched"]
    assert [t["title"] for t in body["new_tasks"]] == ["Buy a microphone", "Record episode 1", "Publish on Spotify"]
    assert all(t["status"] == "backlog" and t["importance"] is None for t in body["new_tasks"])
    assert client.get(f"/api/decomposition/sessions/{sid}").status_code == 404


def test_confirm_leaves_out_excluded_items(client, model) -> None:
    model.responses += BUILD_TURN
    sid = new_session(client)["session_id"]
    send(client, sid)

    body = client.post(
        f"/api/decomposition/sessions/{sid}/confirm",
        json={"exclude_milestone_refs": ["M4"], "exclude_task_refs": ["T2"]},
    ).json()

    assert [m["name"] for m in body["milestones"]] == ["Pilot recorded"]
    assert [t["title"] for t in body["new_tasks"]] == ["Record episode 1"]


def test_confirm_guard_errors_are_actionable_and_keep_the_session(client, model) -> None:
    model.responses += [
        AIMessage(content="", tool_calls=[call("add_milestone", name="Pilot recorded")]),
        AIMessage(content="Added an empty milestone."),
    ]
    sid = new_session(client)["session_id"]

    nothing = client.post(f"/api/decomposition/sessions/{sid}/confirm", json={})
    assert nothing.status_code == 400 and "adds nothing" in error_of(nothing)[1]

    send(client, sid)
    empty = client.post(f"/api/decomposition/sessions/{sid}/confirm", json={})
    assert empty.status_code == 400 and "without tasks" in error_of(empty)[1]

    assert client.get(f"/api/decomposition/sessions/{sid}").status_code == 200
    assert list_projects() == []


def test_confirm_on_an_existing_project_attaches_and_adds(client, model) -> None:
    project = create_project("Website")
    loose = create_task("Write copy", project_id=project.id)
    model.responses += [
        AIMessage(
            content="",
            tool_calls=[
                call("add_milestone", name="Content ready", tasks=["Pick photos"]),
                call("attach_existing_task", milestone_ref="M1", task_id=loose.id),
            ],
        ),
        AIMessage(content="Done."),
    ]
    sid = new_session(client, project_id=project.id)["session_id"]
    send(client, sid)

    body = client.post(f"/api/decomposition/sessions/{sid}/confirm", json={}).json()

    (milestone,) = list_milestones(project_id=project.id)
    assert body["project"]["id"] == project.id
    assert get_task(loose.id).milestone_id == milestone.id
    assert [t.title for t in list_tasks(project_id=project.id)] == ["Write copy", "Pick photos"]


def test_cancel_discards_the_draft(client) -> None:
    sid = new_session(client)["session_id"]
    assert client.delete(f"/api/decomposition/sessions/{sid}").status_code == 204
    assert client.get(f"/api/decomposition/sessions/{sid}").status_code == 404


def test_sessions_of_the_other_kind_are_not_visible(client, store) -> None:
    planning = store.create("planning", None)
    assert client.get(f"/api/decomposition/sessions/{planning.id}").status_code == 404


def test_unticked_items_are_dropped_before_the_next_turn(client, model) -> None:
    model.responses += BUILD_TURN
    sid = new_session(client)["session_id"]
    send(client, sid)

    seen = {}
    real_invoke = model.invoke

    def spy(messages):
        seen["system"] = messages[0].content
        return real_invoke(messages)

    model.invoke = spy
    model.responses.append(AIMessage(content="Kept what you ticked."))
    response = client.post(
        f"/api/decomposition/sessions/{sid}/messages",
        json={"text": "carry on", "exclude_milestone_refs": ["M4"], "exclude_task_refs": ["T2"]},
    )

    session = events_of(response)[-1][1]
    assert [m["name"] for m in session["draft"]["milestones"]] == ["Pilot recorded"]
    assert [t["title"] for t in session["draft"]["milestones"][0]["tasks"]] == ["Record episode 1"]
    assert "Launched" not in seen["system"] and "Buy a microphone" not in seen["system"]


def test_exclusions_are_not_applied_when_the_turn_fails(client, model) -> None:
    model.responses += BUILD_TURN
    sid = new_session(client)["session_id"]
    before = events_of(send(client, sid))[-1][1]["draft"]

    model.responses.append(RuntimeError("provider down"))
    client.post(
        f"/api/decomposition/sessions/{sid}/messages",
        json={"text": "carry on", "exclude_milestone_refs": ["M4"]},
    )

    assert client.get(f"/api/decomposition/sessions/{sid}").json()["draft"] == before

