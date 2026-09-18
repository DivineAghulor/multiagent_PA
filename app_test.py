"""Throwaway Streamlit harness for exercising PM agent code end-to-end.
Not the eventual production interface. Run with: streamlit run app_test.py"""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from agents.pm.backlog import capture_backlog_from_text
from agents.pm.planning import (
    confirm_weekly_plan,
    describe_proposal,
    load_planning_context,
    planning_week_start,
    propose_weekly_plan,
    sanitize_proposal,
)
from tools.tasks import update_task_priority

BACKLOG_MODE = "Backlog capture"
PLANNING_MODE = "Weekly planning"


def backlog_page() -> None:
    st.title("Personal Assistant — Test Chat")

    if "history" not in st.session_state:
        st.session_state.history = []
    if "pending_tasks" not in st.session_state:
        st.session_state.pending_tasks = []
    if "rated_ids" not in st.session_state:
        st.session_state.rated_ids = set()

    for role, text in st.session_state.history:
        with st.chat_message(role):
            st.write(text)

    user_input = st.chat_input("Tell me what you need to do")
    if user_input:
        st.session_state.history.append(("user", user_input))
        new_tasks = capture_backlog_from_text(user_input)
        st.session_state.pending_tasks.extend(new_tasks)
        reply = (
            f"Added {len(new_tasks)} task(s) to the backlog."
            if new_tasks
            else "I didn't find any tasks in that."
        )
        st.session_state.history.append(("assistant", reply))
        st.rerun()

    unrated = [t for t in st.session_state.pending_tasks if t.id not in st.session_state.rated_ids]
    if unrated:
        st.subheader("Rate the new tasks")
        for task in unrated:
            st.write(f"**{task.title}**")
            col1, col2 = st.columns(2)
            importance = col1.selectbox("Importance (1-4)", [1, 2, 3, 4], key=f"imp_{task.id}")
            urgency = col2.selectbox("Urgency (1-4)", [1, 2, 3, 4], key=f"urg_{task.id}")
            if st.button(f"Save — {task.title}", key=f"save_{task.id}"):
                update_task_priority(task.id, importance, urgency)
                st.session_state.rated_ids.add(task.id)
                st.rerun()


def _reset_plan() -> None:
    st.session_state.plan_proposal = None
    st.session_state.plan_warnings = []
    st.session_state.plan_version = st.session_state.get("plan_version", 0) + 1


def planning_page() -> None:
    st.title("Weekly planning")

    picked = st.date_input("Week starting", value=planning_week_start(date.today()), key="plan_week")
    week_start = picked - timedelta(days=picked.weekday())
    if picked != week_start:
        st.caption(f"Planning the week of Monday {week_start.isoformat()}")

    # A proposal is only valid for the week it was made for.
    if st.session_state.get("plan_for") != week_start:
        st.session_state.plan_for = week_start
        st.session_state.plan_history = []
        _reset_plan()

    ctx = load_planning_context(week_start)
    if ctx.existing_goals:
        st.subheader("Already planned for this week")
        for g in ctx.existing_goals:
            target = f" — target {g.target_count}" if g.target_count else ""
            st.write(f"- {g.description}{target} ({len(g.tasks)} task(s))")

    for role, text in st.session_state.plan_history:
        with st.chat_message(role):
            st.text(text)

    user_input = st.chat_input("What do you want to get out of this week?")
    if user_input:
        st.session_state.plan_history.append(("user", user_input))
        proposal, warnings = sanitize_proposal(
            propose_weekly_plan(st.session_state.plan_history, ctx), ctx
        )
        _reset_plan()
        st.session_state.plan_proposal = proposal
        st.session_state.plan_warnings = warnings
        st.session_state.plan_history.append(("assistant", describe_proposal(proposal, ctx)))
        st.rerun()

    proposal = st.session_state.plan_proposal
    if proposal is None or not proposal.goals:
        return

    st.subheader("Proposed goals — edit, then confirm")
    for w in st.session_state.plan_warnings:
        st.warning(w)

    names = {
        **{("task", t.id): t.title for t in ctx.backlog},
        **{("habit", h.id): h.name for h in ctx.habits},
        **{("project", p.id): p.name for p in ctx.projects},
    }
    v = st.session_state.plan_version
    edited = []
    for i, g in enumerate(proposal.goals):
        with st.container(border=True):
            keep = st.checkbox("Include", value=True, key=f"keep_{v}_{i}")
            desc = st.text_input("Goal", value=g.description, key=f"desc_{v}_{i}")
            target = st.number_input(
                "Target (0 = none)", min_value=0, value=g.target_count or 0, step=1, key=f"target_{v}_{i}"
            )
            if g.habit_id is not None:
                st.caption(f"Habit: {names.get(('habit', g.habit_id), g.habit_id)}")
            if g.project_id is not None:
                st.caption(f"Project: {names.get(('project', g.project_id), g.project_id)}")
            for tid in g.task_ids:
                st.caption(f"• {names.get(('task', tid), f'task {tid}')}")
        if keep:
            edited.append(g.model_copy(update={"description": desc, "target_count": int(target) or None}))

    col1, col2 = st.columns(2)
    if col1.button("Confirm plan", key="plan_confirm"):
        if not edited:
            st.warning("No goals selected — nothing to save.")
            return
        try:
            created = confirm_weekly_plan(week_start, edited)
        except ValueError as e:
            st.error(str(e))
            return
        st.session_state.plan_history.append(
            ("assistant", f"Saved {len(created)} goal(s) for the week of {week_start.isoformat()}.")
        )
        _reset_plan()
        st.rerun()
    if col2.button("Discard proposal", key="plan_discard"):
        _reset_plan()
        st.rerun()


mode = st.sidebar.radio("Mode", [BACKLOG_MODE, PLANNING_MODE], key="mode")
if mode == PLANNING_MODE:
    planning_page()
else:
    backlog_page()
