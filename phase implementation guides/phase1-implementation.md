# Phase 1 — Backlog capture, priority dialog & test interface

## What this achieves

Freeform text → structured `Task` rows in the backlog, with the user rating each new task's importance/urgency (1–4 each) right after capture, exercised through a minimal Streamlit test UI.

## Key decisions

- **Importance/urgency are captured immediately after extraction**, via a dialog, not deferred to weekly planning — reduces the chance ratings never get backfilled.
- **Extraction schema (`ExtractedTask`) is separate from the `Task` DB model** — the LLM only ever produces title/description/project_hint; it never sets `importance`, `urgency`, `id`, or `status`.
- **Test UI built in Streamlit**, a throwaway harness for exercising agent code before any real interface exists — not the eventual production interface.

## Implementation steps

1. Define the extraction schema (`ExtractedTask`, `ExtractedTaskBatch`)
2. Build the extraction chain (`extract_tasks`) using `with_structured_output()`
3. Persist extracted tasks (`capture_backlog_from_text`) via Phase 0's `create_task()`
4. Wrap capture as a LangChain tool (`add_tasks_to_backlog`) for later orchestrator use
5. Add an `update_task_priority()` tool for setting importance/urgency
6. Unit test `capture_backlog_from_text` with a mocked `extract_tasks`
7. Build an eval set (`evals/pm_backlog.yaml`) to check extraction quality against the real model
8. Build the Streamlit test app: chat input + priority dialog, wired to steps 3 and 5

## Code

### Extraction schema

```python
# agents/pm/schemas.py
from pydantic import BaseModel, Field
from typing import Optional

class ExtractedTask(BaseModel):
    """A single actionable task identified in the user's text."""
    title: str = Field(description="Short imperative summary, e.g. 'Fix login bug'")
    description: Optional[str] = Field(default=None, description="Extra detail, only if given")
    project_hint: Optional[str] = Field(
        default=None, description="Project this task belongs to, if implied, else null"
    )

class ExtractedTaskBatch(BaseModel):
    """All tasks identified in one piece of user text."""
    tasks: list[ExtractedTask]
```

### Extraction chain

```python
# agents/pm/extraction.py
from llm.factory import get_chat_model
from .schemas import ExtractedTaskBatch

EXTRACTION_SYSTEM_PROMPT = """You extract actionable tasks from a user's freeform \
description of what they need to do. Split distinct actions into separate tasks — \
don't merge unrelated things into one. If the text mentions a project or area of \
work a task belongs to, capture it as project_hint; otherwise leave it null. Do not \
invent tasks that weren't mentioned."""

def extract_tasks(text: str) -> ExtractedTaskBatch:
    model = get_chat_model()
    structured_model = model.with_structured_output(ExtractedTaskBatch)
    return structured_model.invoke([
        ("system", EXTRACTION_SYSTEM_PROMPT),
        ("human", text),
    ])
```

### Persistence

```python
# agents/pm/backlog.py
from tools.tasks import create_task
from tools.projects import find_project_by_name
from .extraction import extract_tasks

def capture_backlog_from_text(text: str) -> list[Task]:
    batch = extract_tasks(text)
    created = []
    for extracted in batch.tasks:
        project = find_project_by_name(extracted.project_hint) if extracted.project_hint else None
        task = create_task(
            title=extracted.title,
            description=extracted.description,
            project_id=project.id if project else None,
            importance=None,
            urgency=None,
        )
        created.append(task)
    return created
```

### Tool wrapper (for later orchestrator use)

```python
from langchain_core.tools import tool

@tool
def add_tasks_to_backlog(text: str) -> str:
    """Extract and save tasks from the user's freeform description of things
    they need to do. Use this when the user describes new work, not when
    they're asking about existing tasks."""
    tasks = capture_backlog_from_text(text)
    return f"Added {len(tasks)} task(s) to the backlog: " + ", ".join(t.title for t in tasks)
```

### Priority update tool

```python
# tools/tasks.py (addition)
def update_task_priority(task_id: int, importance: int, urgency: int) -> Task:
    if not (1 <= importance <= 4) or not (1 <= urgency <= 4):
        raise ValueError("importance and urgency must be between 1 and 4")
    task = get_task(task_id)
    task.importance = importance
    task.urgency = urgency
    db_session.commit()
    return task
```

### Unit test (mocked LLM)

```python
# tests/test_backlog.py
from unittest.mock import patch
from agents.pm.schemas import ExtractedTask, ExtractedTaskBatch
from agents.pm.backlog import capture_backlog_from_text

def test_capture_backlog_creates_tasks(db_session):
    fake_response = ExtractedTaskBatch(tasks=[
        ExtractedTask(title="Fix login bug", description=None, project_hint=None),
        ExtractedTask(title="Redesign landing page", description=None, project_hint="Website"),
    ])
    with patch("agents.pm.backlog.extract_tasks", return_value=fake_response):
        tasks = capture_backlog_from_text("fix the login bug and redesign the landing page")

    assert len(tasks) == 2
    assert tasks[0].importance is None
```

### Eval fixture (real model, behavior check)

```yaml
# evals/pm_backlog.yaml
- input: "I need to redesign the landing page and fix the login bug"
  expected_task_count: 2
- input: "call the dentist, buy groceries, and finish the Q3 report"
  expected_task_count: 3
- input: "not sure what to do today honestly"
  expected_task_count: 0
```

### Streamlit test app (chat + priority dialog)

```python
# app_test.py
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
        if new_tasks else "I didn't find any tasks in that."
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
```

Run with: `streamlit run app_test.py`

## What "done" looks like

- [x] `capture_backlog_from_text` reliably splits multi-task input into separate rows
- [x] Unrelated info doesn't produce phantom tasks
- [x] Every created task has `importance`/`urgency` as `None` until rated
- [x] Unit tests pass with zero API calls
- [x] Eval set runs against the real provider and results look sane
- [x] Streamlit app: sending a message adds tasks and shows a rating dialog; saving a rating removes that task from the dialog
