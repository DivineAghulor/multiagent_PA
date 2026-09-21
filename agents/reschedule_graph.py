"""Phase 4: reschedule + confirmation as a LangGraph interrupt.

Flow: propose_node stages the reschedule (via tools.calendar.propose_reschedule)
and PAUSES execution with interrupt(), surfacing the proposed change to
whatever's driving the graph (a CLI, Streamlit, etc). That caller resumes with
Command(resume=True/False), and resolve_node applies confirm_reschedule or
reject_reschedule accordingly.

Uses an in-memory checkpointer for now -- fine for local dev/testing, since a
graph run only needs to survive from "propose" to the human's next message,
not a server restart. Swap for a persistent checkpointer before deployment.
"""
from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from tools.calendar import confirm_reschedule, propose_reschedule, reject_reschedule


class RescheduleState(TypedDict):
    event_id: int
    new_start_time: datetime
    new_end_time: datetime
    reason: str
    approved: bool | None
    result: dict | None


def propose_node(state: RescheduleState) -> dict:
    """Stage the reschedule locally, then pause and wait for a human decision."""
    staged = propose_reschedule(
        event_id=state["event_id"],
        new_start_time=state["new_start_time"],
        new_end_time=state["new_end_time"],
        reason=state["reason"],
    )

    approved = interrupt(
        {
            "event_id": staged.id,
            "title": staged.title,
            "current_start_time": staged.start_time.isoformat(),
            "current_end_time": staged.end_time.isoformat(),
            "proposed_start_time": staged.proposed_start_time.isoformat(),
            "proposed_end_time": staged.proposed_end_time.isoformat(),
            "reason": staged.reschedule_reason,
        }
    )

    return {"approved": approved}


def resolve_node(state: RescheduleState) -> dict:
    """Apply the human's decision now that the graph has resumed."""
    if state["approved"]:
        event = confirm_reschedule(state["event_id"])
    else:
        event = reject_reschedule(state["event_id"])

    return {
        "result": {
            "status": event.status.value,
            "start_time": event.start_time.isoformat(),
            "end_time": event.end_time.isoformat(),
        }
    }


def build_reschedule_graph():
    builder = StateGraph(RescheduleState)
    builder.add_node("propose", propose_node)
    builder.add_node("resolve", resolve_node)
    builder.add_edge(START, "propose")
    builder.add_edge("propose", "resolve")
    builder.add_edge("resolve", END)
    return builder.compile(checkpointer=InMemorySaver())


_graph = build_reschedule_graph()


def start_reschedule_proposal(
    event_id: int,
    new_start_time: datetime,
    new_end_time: datetime,
    reason: str,
    thread_id: str,
) -> dict:
    """Kick off a reschedule proposal. Runs until the interrupt, then returns
    the proposal payload for a UI to show the human. Call
    resume_reschedule_decision(...) with the same thread_id once they respond.
    """
    config = {"configurable": {"thread_id": thread_id}}
    initial_state: RescheduleState = {
        "event_id": event_id,
        "new_start_time": new_start_time,
        "new_end_time": new_end_time,
        "reason": reason,
        "approved": None,
        "result": None,
    }
    _graph.invoke(initial_state, config)
    state = _graph.get_state(config)
    return state.tasks[0].interrupts[0].value


def resume_reschedule_decision(thread_id: str, approved: bool) -> dict:
    """Resume a paused proposal with the human's decision. Returns the final result."""
    config = {"configurable": {"thread_id": thread_id}}
    final_state = _graph.invoke(Command(resume=approved), config)
    return final_state["result"]