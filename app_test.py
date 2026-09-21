"""Throwaway Streamlit harness for exercising PM agent code end-to-end.
Not the eventual production interface. Run with: streamlit run app_test.py"""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

from agents.pm.backlog import capture_backlog_from_text
from agents.pm.decomposition import (
    confirm_decomposition,
    run_decomposition_turn,
    start_existing_project_draft,
    start_new_project_draft,
)
from agents.pm.planning import (
    confirm_weekly_plan,
    describe_proposal,
    load_planning_context,
    planning_week_start,
    propose_weekly_plan,
    sanitize_proposal,
)
from agents.pm import review as pm_review
from agents.pm.review import (
    build_week_review,
    current_week_start,
    missed_goals,
    save_review,
    summarize_week,
)
from db.models import ProjectStatus, TaskStatus
from tools.habits import log_habit_completion, remove_habit_log
from tools.projects import list_projects
from tools.tasks import complete_task, reopen_task, update_task_priority
from tools.weekly_goals import carry_over_weekly_goal

BACKLOG_MODE = "Backlog capture"
PLANNING_MODE = "Weekly planning"
BREAKDOWN_MODE = "Project breakdown"
REVIEW_MODE = "This week"
NEW_PROJECT = "➕ New project"


def _init_rating_state() -> None:
    if "pending_tasks" not in st.session_state:
        st.session_state.pending_tasks = []
    if "rated_ids" not in st.session_state:
        st.session_state.rated_ids = set()


def render_rating_dialog() -> None:
    """Shared by every page that creates tasks: rate each new task right after it's created."""
    _init_rating_state()
    unrated = [t for t in st.session_state.pending_tasks if t.id not in st.session_state.rated_ids]
    if unrated:
        st.subheader("Rate the new tasks")
        for task in unrated:
            st.write(f"**{task.title}**")
            col1, col2 = st.columns(2)
            importance = col1.selectbox(
                "Importance (1 = lowest, 4 = highest)", [1, 2, 3, 4], key=f"imp_{task.id}"
            )
            urgency = col2.selectbox("Urgency (1 = lowest, 4 = highest)", [1, 2, 3, 4], key=f"urg_{task.id}")
            if st.button(f"Save — {task.title}", key=f"save_{task.id}"):
                update_task_priority(task.id, importance, urgency)
                st.session_state.rated_ids.add(task.id)
                st.rerun()


def backlog_page() -> None:
    st.title("Personal Assistant — Test Chat")

    if "history" not in st.session_state:
        st.session_state.history = []
    _init_rating_state()

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

    render_rating_dialog()


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


def _reset_breakdown() -> None:
    st.session_state.bd_draft = None
    st.session_state.bd_history = []
    st.session_state.bd_draft_no = st.session_state.get("bd_draft_no", 0) + 1


def breakdown_page() -> None:
    st.title("Project breakdown")
    if "bd_draft" not in st.session_state:
        _reset_breakdown()
    if notice := st.session_state.pop("bd_notice", None):
        st.success(notice)

    draft = st.session_state.bd_draft
    if draft is None:
        projects = {p.name: p.id for p in list_projects(status=ProjectStatus.ACTIVE)}
        source = st.selectbox("Project", [NEW_PROJECT, *projects], key="bd_source")
        if source == NEW_PROJECT:
            name = st.text_input("Project name", key="bd_name")
            description = st.text_area("What is it about? Goals, constraints, deadline", key="bd_desc")
        if st.button("Start breakdown", key="bd_start"):
            try:
                st.session_state.bd_draft = (
                    start_new_project_draft(name, description or None)
                    if source == NEW_PROJECT
                    else start_existing_project_draft(projects[source])
                )
            except ValueError as e:
                st.error(str(e))
            else:
                st.rerun()
        render_rating_dialog()
        return

    st.caption(f"Breaking down **{draft.project_name}**" + (" (new project)" if draft.project_id is None else ""))
    for msg in st.session_state.bd_history:
        if isinstance(msg, HumanMessage):
            with st.chat_message("user"):
                st.write(msg.text)
        elif isinstance(msg, AIMessage) and not msg.tool_calls and msg.text:
            with st.chat_message("assistant"):
                st.write(msg.text)

    # Unticked items are dropped from the draft before the next turn and on confirm.
    n = st.session_state.bd_draft_no
    excluded_m: set[str] = set()
    excluded_t: set[str] = set()
    if draft.milestones:
        st.subheader("Draft")
    for i, m in enumerate(draft.milestones, 1):
        label = f"{i}. {m.name}" + (f" — due {m.due_date.isoformat()}" if m.due_date else "")
        if m.existing_id is not None:
            label += " (existing)"
        if not st.checkbox(label, value=True, key=f"bd_m_{n}_{m.ref}", disabled=m.existing_id is not None):
            excluded_m.add(m.ref)
        for title in m.existing_task_titles:
            st.caption(f"      ✓ {title} (already in this milestone)")
        for t in m.tasks:
            tag = " (existing task)" if t.existing_task_id else ""
            if not st.checkbox(f"      {t.title}{tag}", value=True, key=f"bd_t_{n}_{t.ref}"):
                excluded_t.add(t.ref)

    if draft.milestones:
        col1, col2 = st.columns(2)
        if col1.button("Confirm breakdown", key="bd_confirm"):
            try:
                result = confirm_decomposition(draft.without(excluded_m, excluded_t))
            except ValueError as e:
                st.error(str(e))
            else:
                _init_rating_state()
                st.session_state.pending_tasks.extend(result.new_tasks)
                st.session_state.bd_notice = (
                    f"Saved {len(result.milestones)} milestone(s) and {len(result.new_tasks)} new task(s) "
                    f"for {result.project.name}."
                )
                _reset_breakdown()
                st.rerun()
        if col2.button("Discard draft", key="bd_discard"):
            _reset_breakdown()
            st.rerun()

    user_input = st.chat_input("How should it be broken down, or what should change?")
    if user_input:
        draft = draft.without(excluded_m, excluded_t)
        history = [*st.session_state.bd_history, HumanMessage(user_input)]
        try:
            with st.spinner("Working on the breakdown..."):
                result = run_decomposition_turn(history, draft, date.today())
        except Exception as e:  # provider/network errors (e.g. quota): keep the draft, show why
            st.error(f"The model call failed, so the draft is unchanged: {e}")
            return
        st.session_state.bd_draft = draft
        st.session_state.bd_history = result.history
        st.rerun()

    render_rating_dialog()


def review_page() -> None:
    st.title("This week")

    picked = st.date_input("Week starting", value=current_week_start(pm_review.today()), key="rv_week")
    week_start = current_week_start(picked)
    week_end = week_start + timedelta(days=6)
    st.caption(f"Week of Monday {week_start.isoformat()} to {week_end.isoformat()}")
    if st.session_state.get("rv_for") != week_start:
        st.session_state.rv_for = week_start
        st.session_state.rv_summary = None

    review = build_week_review(week_start)
    if not review.goals:
        st.info("No goals for this week yet — set some in the Weekly planning tab.")
        return

    # via the module, so "now" is patchable in tests (AppTest runs this script
    # with its own globals, so patching app_test.date wouldn't reach here)
    today = pm_review.today()
    key = week_start.isoformat()
    for g in review.goals:
        with st.container(border=True):
            st.write(f"**{g.headline()}**")
            if g.kind == "habit":
                logged = set(g.done)
                cols = st.columns(7)
                for i, col in enumerate(cols):
                    day = week_start + timedelta(days=i)
                    iso = day.isoformat()
                    was = iso in logged
                    now = col.checkbox(
                        day.strftime("%a")[:2] + f" {day.day}",
                        value=was,
                        key=f"rv_h_{key}_{g.goal.id}_{i}",
                        disabled=day > today,
                    )
                    if now != was:
                        if now:
                            log_habit_completion(g.goal.habit_id, day)
                        else:
                            remove_habit_log(g.goal.habit_id, day)
                        st.rerun()
            elif g.kind == "tasks":
                for task in g.goal.tasks:
                    was = task.status == TaskStatus.DONE
                    now = st.checkbox(task.title, value=was, key=f"rv_t_{key}_{task.id}")
                    if now != was:
                        complete_task(task.id) if now else reopen_task(task.id)
                        st.rerun()
            else:
                st.caption("No habit or tasks attached, so this one can't be measured automatically.")

    if review.unplanned_done:
        st.subheader("Also done this week (not part of a goal)")
        for task in review.unplanned_done:
            st.write(f"- {task.title}")

    st.subheader("Weekly review")
    if st.button("Generate weekly review", key="rv_generate"):
        try:
            with st.spinner("Writing the review..."):
                summary = summarize_week(review)
        except Exception as e:  # provider/network errors: nothing is saved
            st.error(f"The model call failed, so no review was saved: {e}")
        else:
            save_review(review)
            st.session_state.rv_summary = summary
            st.rerun()

    if st.session_state.get("rv_summary"):
        st.write(st.session_state.rv_summary)
        st.caption("Per-goal notes and achieved/missed status have been saved.")

    if missed := missed_goals(review):
        st.subheader("Carry into next week")
        chosen = [
            g.goal.id
            for g in missed
            if st.checkbox(g.goal.description, value=False, key=f"rv_c_{key}_{g.goal.id}")
        ]
        if st.button("Carry selected goals to next week", key="rv_carry"):
            if not chosen:
                st.warning("Nothing selected.")
            else:
                for goal_id in chosen:
                    carry_over_weekly_goal(goal_id, week_start + timedelta(days=7))
                st.success(f"Carried {len(chosen)} goal(s) into the week of {(week_start + timedelta(days=7)).isoformat()}.")
                st.session_state.rv_summary = None
                st.rerun()


mode = st.sidebar.radio("Mode", [BACKLOG_MODE, PLANNING_MODE, BREAKDOWN_MODE, REVIEW_MODE], key="mode")
if mode == PLANNING_MODE:
    planning_page()
elif mode == BREAKDOWN_MODE:
    breakdown_page()
elif mode == REVIEW_MODE:
    review_page()
else:
    backlog_page()
