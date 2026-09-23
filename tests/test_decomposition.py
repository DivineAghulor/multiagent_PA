"""Unit tests for project decomposition. The model is a scripted fake that emits
real tool calls, so the loop runs end to end with zero live API calls."""
from __future__ import annotations

import itertools
from datetime import date
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agents.pm.decomposition import (
    MAX_MILESTONES,
    STEP_LIMIT_REPLY,
    confirm_decomposition,
    run_decomposition_turn,
    start_existing_project_draft,
    start_new_project_draft,
)
from db.models import TaskStatus
from tools.milestones import create_milestone, delete_milestone, list_milestones
from tools.projects import create_project, list_projects
from tools.tasks import create_task, get_task, list_tasks, update_task_status

TODAY = date(2026, 9, 18)
_ids = itertools.count(1)


def call(tool_name: str, **args) -> dict:
    return {"name": tool_name, "args": args, "id": f"call_{next(_ids)}"}


class ScriptedModel:
    """Stands in for a chat model: bind_tools returns itself, invoke replays responses."""

    def __init__(self, responses: list[AIMessage]):
        self.responses = list(responses)
        self.seen: list[list] = []

    def bind_tools(self, tools):
        self.tool_names = [t.name for t in tools]
        return self

    def invoke(self, messages):
        self.seen.append(list(messages))
        return self.responses.pop(0) if self.responses else AIMessage(content="", tool_calls=[call("view_draft")])


def run_turn(model: ScriptedModel, draft, text: str = "break it down", history=None, **kwargs):
    with patch("agents.pm.decomposition.get_default_chat_model", return_value=model):
        return run_decomposition_turn([*(history or []), HumanMessage(text)], draft, TODAY, **kwargs)


@pytest.fixture()
def existing(db_session):
    """A project with one positioned milestone, eligible and ineligible tasks."""
    project = create_project("Website", "Company site relaunch")
    other = create_project("Other")
    ms = create_milestone(project.id, "Design approved", position=1)
    in_ms = create_task("Draft wireframes", project_id=project.id, milestone_id=ms.id)
    eligible = create_task("Fix broken signup form", project_id=project.id)
    done = create_task("Buy domain", project_id=project.id)
    update_task_status(done.id, TaskStatus.DONE)
    foreign = create_task("Other project task", project_id=other.id)
    return {"project": project, "milestone": ms, "in_ms": in_ms, "eligible": eligible, "done": done, "foreign": foreign}


# --- draft operations ----------------------------------------------------------


def test_draft_edits_and_render() -> None:
    d = start_new_project_draft("Podcast", "Weekly show")
    m1 = d.add_milestone("Pilot recorded", None, "2026-10-01", TODAY)
    m2 = d.add_milestone("Launched", None, None, TODAY)
    t = d.add_task(m1.ref, "Buy a microphone", None)
    d.update_task(t.ref, "Buy a USB microphone", None)
    d.move_milestone(m2.ref, 1)

    assert [m.name for m in d.milestones] == ["Launched", "Pilot recorded"]
    text = d.render()
    assert "Podcast (new project)" in text
    assert "2. [M1] Pilot recorded (due 2026-10-01)" in text
    assert "Buy a USB microphone" in text
    assert d.new_task_count == 1


@pytest.mark.parametrize(
    "action",
    [
        lambda d, m: d.add_task(m.ref, "buy a microphone.", None),  # normalized duplicate
        lambda d, m: d.add_task("M99", "Anything", None),
        lambda d, m: d.add_task(m.ref, "   ", None),
        lambda d, m: d.add_milestone("pilot RECORDED", None, None, TODAY),
        lambda d, m: d.add_milestone("Later", None, "2026-09-18", TODAY),  # not after today
        lambda d, m: d.add_milestone("Later", None, "next week", TODAY),
        lambda d, m: d.move_milestone(m.ref, 5),
        lambda d, m: d.attach_existing_task(m.ref, 1),  # nothing eligible on a new project
    ],
)
def test_draft_rejects_invalid_edits(action) -> None:
    d = start_new_project_draft("Podcast")
    m = d.add_milestone("Pilot recorded", None, None, TODAY)
    d.add_task(m.ref, "Buy a microphone", None)
    with pytest.raises(ValueError):
        action(d, m)


def test_draft_milestone_limit() -> None:
    d = start_new_project_draft("Big")
    for i in range(MAX_MILESTONES):
        d.add_milestone(f"Stage {i}", None, None, TODAY)
    with pytest.raises(ValueError, match="at most"):
        d.add_milestone("One too many", None, None, TODAY)


def test_without_drops_only_new_items(existing) -> None:
    d = start_existing_project_draft(existing["project"].id)
    old = d.milestones[0]
    new = d.add_milestone("Launched", None, None, TODAY)
    t = d.add_task(old.ref, "Review copy", None)

    trimmed = d.without({old.ref, new.ref}, {t.ref})

    assert [m.ref for m in trimmed.milestones] == [old.ref]  # existing milestone can't be excluded
    assert trimmed.milestones[0].tasks == []
    assert len(d.milestones) == 2  # original untouched


# --- existing projects ---------------------------------------------------------------


def test_existing_project_draft_seeds_milestones_and_eligible_tasks(existing) -> None:
    d = start_existing_project_draft(existing["project"].id)

    assert [(m.name, m.existing_id) for m in d.milestones] == [("Design approved", existing["milestone"].id)]
    assert d.milestones[0].existing_task_titles == ["Draft wireframes"]
    assert d.eligible_tasks == {existing["eligible"].id: "Fix broken signup form"}


def test_existing_items_are_protected(existing) -> None:
    d = start_existing_project_draft(existing["project"].id)
    ref = d.milestones[0].ref
    with pytest.raises(ValueError, match="existing milestone"):
        d.remove_milestone(ref)
    with pytest.raises(ValueError, match="existing milestone"):
        d.update_milestone(ref, "Renamed", None, None, TODAY)
    with pytest.raises(ValueError, match="use attach_existing_task"):
        d.add_task(ref, "Fix broken signup form", None)
    with pytest.raises(ValueError, match="already exists under"):
        d.add_task(ref, "draft wireframes", None)

    t = d.attach_existing_task(ref, existing["eligible"].id)
    with pytest.raises(ValueError, match="already attached"):
        d.attach_existing_task(ref, existing["eligible"].id)
    with pytest.raises(ValueError, match="existing task"):
        d.update_task(t.ref, "Renamed", None)


# --- the loop ------------------------------------------------------------------------


def test_loop_builds_draft_over_several_tool_calls_and_feeds_back_errors() -> None:
    d = start_new_project_draft("Podcast")
    model = ScriptedModel(
        [
            AIMessage(content="", tool_calls=[call("add_milestone", name="Pilot recorded")]),
            AIMessage(
                content="",
                tool_calls=[
                    call("add_task", milestone_ref="M1", title="Buy a microphone"),
                    call("add_task", milestone_ref="M1", title="Buy a microphone"),  # duplicate -> error
                    call("add_task", milestone_ref="M1", title="Record episode 1"),
                ],
            ),
            AIMessage(content="", tool_calls=[call("view_draft")]),
            AIMessage(content="One milestone with two tasks. Want a launch milestone too?"),
        ]
    )

    result = run_turn(model, d)

    assert not result.hit_limit
    assert (result.steps, result.tool_calls) == (4, 5)
    assert result.reply.startswith("One milestone")
    assert [t.title for t in d.milestones[0].tasks] == ["Buy a microphone", "Record episode 1"]
    tool_results = [m.content for m in result.history if isinstance(m, ToolMessage)]
    assert tool_results[2].startswith("Error:") and "already task" in tool_results[2]
    assert "[M1] Pilot recorded" in tool_results[4]  # view_draft output
    # the model saw the error before its next step, and the system prompt isn't kept in history
    assert any(isinstance(m, ToolMessage) and "Error" in m.content for m in model.seen[2])
    assert not any(isinstance(m, SystemMessage) for m in result.history)
    assert "add_milestone" in model.tool_names and "attach_existing_task" in model.tool_names


def test_loop_reports_unknown_tool() -> None:
    d = start_new_project_draft("Podcast")
    model = ScriptedModel([AIMessage(content="", tool_calls=[call("delete_everything")]), AIMessage(content="ok")])
    result = run_turn(model, d)
    assert "unknown tool" in [m for m in result.history if isinstance(m, ToolMessage)][0].content


def test_loop_stops_at_step_limit_and_keeps_draft() -> None:
    d = start_new_project_draft("Podcast")
    model = ScriptedModel([AIMessage(content="", tool_calls=[call("add_milestone", name="Pilot recorded")])])

    result = run_turn(model, d, max_steps=3)  # afterwards the fake keeps calling view_draft

    assert result.hit_limit and result.steps == 3
    assert result.reply == STEP_LIMIT_REPLY
    assert [m.name for m in d.milestones] == ["Pilot recorded"]


def test_system_prompt_is_rebuilt_from_current_draft_each_turn(existing) -> None:
    d = start_existing_project_draft(existing["project"].id)
    first = run_turn(ScriptedModel([AIMessage(content="Hi")]), d)
    d.add_milestone("Launched", None, None, TODAY)  # e.g. changed between turns

    model = ScriptedModel([AIMessage(content="Noted")])
    run_turn(model, d, "continue", history=first.history)

    system = model.seen[0][0]
    assert isinstance(system, SystemMessage)
    assert "Launched" in system.content
    assert f"[task {existing['eligible'].id}] Fix broken signup form" in system.content
    assert "Today is 2026-09-18" in system.content
    assert [type(m) for m in model.seen[0][1:]] == [HumanMessage, AIMessage, HumanMessage]


# --- confirm ----------------------------------------------------------------------------


def test_confirm_new_project_writes_ordered_milestones_and_unrated_tasks(db_session) -> None:
    d = start_new_project_draft("Podcast", "Weekly show")
    m1 = d.add_milestone("Pilot recorded", None, "2026-10-01", TODAY)
    m2 = d.add_milestone("Launched", None, None, TODAY)
    d.add_task(m1.ref, "Buy a microphone", None)
    d.add_task(m2.ref, "Publish episode 1", "On all platforms")

    result = confirm_decomposition(d)

    assert result.project.name == "Podcast"
    milestones = list_milestones(project_id=result.project.id)
    assert [(m.name, m.position) for m in milestones] == [("Pilot recorded", 1), ("Launched", 2)]
    assert milestones[0].due_date == date(2026, 10, 1)
    assert len(result.new_tasks) == 2
    for t in result.new_tasks:
        assert (t.status, t.importance, t.urgency) == (TaskStatus.BACKLOG, None, None)
        assert t.project_id == result.project.id
    assert get_task(result.new_tasks[1].id).milestone_id == milestones[1].id


def test_confirm_existing_project_attaches_adds_and_reorders(existing) -> None:
    d = start_existing_project_draft(existing["project"].id)
    old = d.milestones[0]
    new = d.add_milestone("Research done", None, None, TODAY)
    d.move_milestone(new.ref, 1)
    d.attach_existing_task(new.ref, existing["eligible"].id)
    d.add_task(new.ref, "Interview 3 users", None)
    d.add_task(old.ref, "Review mockups", None)

    result = confirm_decomposition(d)

    milestones = list_milestones(project_id=existing["project"].id)
    assert [(m.name, m.position) for m in milestones] == [("Research done", 1), ("Design approved", 2)]
    assert get_task(existing["eligible"].id).milestone_id == milestones[0].id
    assert sorted(t.title for t in result.new_tasks) == ["Interview 3 users", "Review mockups"]
    assert len(list_projects()) == 2  # no new project


def test_confirm_rejects_empty_or_no_op_drafts(existing) -> None:
    with pytest.raises(ValueError, match="adds nothing"):
        confirm_decomposition(start_existing_project_draft(existing["project"].id))
    d = start_new_project_draft("Podcast")
    d.add_milestone("Pilot recorded", None, None, TODAY)
    with pytest.raises(ValueError, match="without tasks"):
        confirm_decomposition(d)
    assert [p.name for p in list_projects()] == ["Website", "Other"]


def test_confirm_is_atomic_when_an_attached_task_went_stale(existing) -> None:
    d = start_existing_project_draft(existing["project"].id)
    new = d.add_milestone("Launched", None, None, TODAY)
    d.add_task(new.ref, "Announce launch", None)
    d.attach_existing_task(new.ref, existing["eligible"].id)
    update_task_status(existing["eligible"].id, TaskStatus.DONE)  # changed after drafting

    with pytest.raises(ValueError, match="can no longer be attached"):
        confirm_decomposition(d)

    assert [m.name for m in list_milestones(project_id=existing["project"].id)] == ["Design approved"]
    assert "Announce launch" not in [t.title for t in list_tasks()]


def test_confirm_deletes_new_project_if_milestone_write_fails(db_session) -> None:
    d = start_new_project_draft("Podcast")
    m = d.add_milestone("Pilot recorded", None, None, TODAY)
    d.add_task(m.ref, "Buy a microphone", None)

    with patch("agents.pm.decomposition.create_milestones_with_tasks", side_effect=RuntimeError("db down")):
        with pytest.raises(RuntimeError):
            confirm_decomposition(d)
    assert list_projects() == []


# --- milestone tools -------------------------------------------------------------------


def test_list_milestones_orders_by_position_then_due_date(db_session) -> None:
    p = create_project("P")
    create_milestone(p.id, "Unpositioned late", due_date=date(2026, 12, 1))
    create_milestone(p.id, "Second", position=2)
    create_milestone(p.id, "Unpositioned early", due_date=date(2026, 10, 1))
    create_milestone(p.id, "First", position=1)

    assert [m.name for m in list_milestones(project_id=p.id)] == [
        "First",
        "Second",
        "Unpositioned early",
        "Unpositioned late",
    ]


def test_delete_milestone_keeps_its_tasks(existing) -> None:
    delete_milestone(existing["milestone"].id)
    assert get_task(existing["in_ms"].id).milestone_id is None
    with pytest.raises(ValueError):
        create_milestone(999, "Orphan")


def test_add_milestone_can_seed_tasks_in_one_call() -> None:
    d = start_new_project_draft("Podcast")
    model = ScriptedModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    call("add_milestone", name="Pilot recorded", tasks=["Buy a microphone", "buy a microphone", "Record"]),
                    call("add_milestone", name="Launched", tasks=["Publish episode 1"]),
                ],
            ),
            AIMessage(content="Done."),
        ]
    )

    result = run_turn(model, d)

    assert result.steps == 2
    assert [[t.title for t in m.tasks] for m in d.milestones] == [["Buy a microphone", "Record"], ["Publish episode 1"]]
    first = [m for m in result.history if isinstance(m, ToolMessage)][0].content
    assert "Error adding 'buy a microphone'" in first


# --- progress callback (NFR-2) ---------------------------------------------

def test_progress_is_reported_per_model_step_and_per_tool_call() -> None:
    from agents.pm.decomposition import TurnProgress

    d = start_new_project_draft("Podcast")
    model = ScriptedModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    call("add_milestone", name="Pilot recorded"),
                    call("add_task", milestone_ref="M1", title="Record episode 1"),
                ],
            ),
            AIMessage(content="Done."),
        ]
    )
    events: list[TurnProgress] = []

    result = run_turn(model, d, on_progress=events.append)

    assert [(e.phase, e.step, e.tool_calls, e.tool) for e in events] == [
        ("step", 1, 0, None),
        ("tool", 1, 1, "add_milestone"),
        ("tool", 1, 2, "add_task"),
        ("step", 2, 2, None),
    ]
    assert (result.steps, result.tool_calls) == (2, 2)


def test_raising_from_the_progress_callback_stops_the_turn() -> None:
    class Stop(Exception):
        pass

    d = start_new_project_draft("Podcast")
    model = ScriptedModel([AIMessage(content="", tool_calls=[call("add_milestone", name="Pilot recorded")])])

    def stop_on_second_step(event) -> None:
        if event.phase == "step" and event.step == 2:
            raise Stop

    with pytest.raises(Stop):
        run_turn(model, d, on_progress=stop_on_second_step)

    assert len(model.seen) == 1  # no model call after the stop

