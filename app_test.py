"""Throwaway Streamlit harness for exercising PM agent code end-to-end.
Not the eventual production interface. Run with: streamlit run app_test.py"""
from __future__ import annotations

import streamlit as st

from agents.pm.backlog import capture_backlog_from_text
from tools.tasks import update_task_priority

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
