"""Project decomposition: an iterative tool-calling loop in which the model
builds a milestone -> task breakdown in an in-memory draft. Nothing touches the
DB until confirm_decomposition, which runs only on user confirmation (see
phase3-implementation.md)."""
from __future__ import annotations

import copy
import functools
import re
from dataclasses import dataclass, field
from datetime import date

from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

from db.models import Milestone, Project, Task, TaskStatus
from llm.factory import get_default_chat_model
from tools.milestones import MilestoneSpec, NewTaskSpec, create_milestones_with_tasks, list_milestones
from tools.projects import create_project, delete_project, get_project
from tools.tasks import list_tasks

MAX_MILESTONES = 10
MAX_TASKS_PER_MILESTONE = 12
MAX_STEPS = 30  # model calls per user turn
STEP_LIMIT_REPLY = (
    "I hit my step limit for this turn. The draft so far is kept; tell me what to change or ask me to continue."
)

DECOMPOSITION_SYSTEM_PROMPT = """You break a project down into milestones and tasks \
by editing a draft plan with your tools. Build it step by step, then check it.

Guidelines:
- Milestones are meaningful checkpoints with a clear outcome, in the order they'd \
happen. A typical project has 3-7. Name them by outcome ("Prototype tested with 5 \
users"), not by category ("Testing").
- Tasks are concrete and actionable: imperative titles, each doable in one sitting. \
Usually 2-8 per milestone. Don't pad.
- Never duplicate work. If one of the existing tasks listed below fits, attach it with \
attach_existing_task instead of adding a new task.
- Existing milestones can't be renamed or removed; add tasks under them or add new \
milestones around them.
- Only set due dates when the user gives a timeline. Dates are YYYY-MM-DD and after today.
- Work in few steps: you can make several tool calls in one step, and add_milestone \
takes the milestone's initial tasks. A good first step adds every milestone with its \
tasks at once.
- When the draft looks complete, call view_draft, fix anything wrong, then reply to \
the user in 2-4 sentences: a short summary or a question. Don't repeat the whole \
plan; the user can see the draft.
- On later turns, apply the user's feedback by editing the current draft (update, \
remove, move). Don't rebuild from scratch unless asked.
- If the request is too vague to break down sensibly, ask a clarifying question \
instead of guessing."""


def _norm(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().strip(".!").lower()


@dataclass
class DraftTask:
    ref: str
    title: str
    description: str | None = None
    existing_task_id: int | None = None  # attached existing task; not created on confirm


@dataclass
class DraftMilestone:
    ref: str
    name: str
    description: str | None = None
    due_date: date | None = None
    existing_id: int | None = None  # already in the DB: read-only apart from new tasks/order
    existing_task_titles: list[str] = field(default_factory=list)
    tasks: list[DraftTask] = field(default_factory=list)


@dataclass
class DecompositionDraft:
    project_name: str
    project_description: str | None = None
    project_id: int | None = None  # None = new project, created on confirm
    milestones: list[DraftMilestone] = field(default_factory=list)
    eligible_tasks: dict[int, str] = field(default_factory=dict)  # existing tasks that may be attached
    _counter: int = 0

    # --- lookups ------------------------------------------------------------

    def _ref(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}{self._counter}"

    def _milestone(self, ref: str) -> DraftMilestone:
        for m in self.milestones:
            if m.ref == ref:
                return m
        valid = ", ".join(m.ref for m in self.milestones) or "none yet"
        raise ValueError(f"no milestone {ref!r} (milestones: {valid})")

    def _task(self, ref: str) -> tuple[DraftMilestone, DraftTask]:
        for m in self.milestones:
            for t in m.tasks:
                if t.ref == ref:
                    return m, t
        raise ValueError(f"no task {ref!r} in the draft")

    def _attached_ids(self) -> set[int]:
        return {t.existing_task_id for m in self.milestones for t in m.tasks if t.existing_task_id}

    def _check_new_title(self, title: str, ignore: DraftTask | None = None) -> str:
        title = title.strip()
        if not title:
            raise ValueError("task title is empty")
        key = _norm(title)
        for task_id, existing in self.eligible_tasks.items():
            if _norm(existing) == key and task_id not in self._attached_ids():
                raise ValueError(f"{title!r} already exists as task {task_id}; use attach_existing_task")
        for m in self.milestones:
            if key in {_norm(t) for t in m.existing_task_titles}:
                raise ValueError(f"{title!r} already exists under milestone {m.ref}")
            for t in m.tasks:
                if t is not ignore and _norm(t.title) == key:
                    raise ValueError(f"{title!r} is already task {t.ref} in milestone {m.ref}")
        return title

    @staticmethod
    def _parse_due(due_date: str | None, today: date) -> date | None:
        if not due_date:
            return None
        try:
            parsed = date.fromisoformat(due_date)
        except ValueError:
            raise ValueError(f"due date {due_date!r} is not YYYY-MM-DD") from None
        if parsed <= today:
            raise ValueError(f"due date {due_date} is not after today ({today.isoformat()})")
        return parsed

    # --- edits (each raises ValueError with a message meant for the model) ---

    def add_milestone(self, name: str, description: str | None, due_date: str | None, today: date) -> DraftMilestone:
        if len(self.milestones) >= MAX_MILESTONES:
            raise ValueError(f"at most {MAX_MILESTONES} milestones; merge or remove some first")
        if not name.strip():
            raise ValueError("milestone name is empty")
        if _norm(name) in {_norm(m.name) for m in self.milestones}:
            raise ValueError(f"a milestone named {name!r} already exists")
        m = DraftMilestone(self._ref("M"), name.strip(), description, self._parse_due(due_date, today))
        self.milestones.append(m)
        return m

    def update_milestone(
        self, ref: str, name: str | None, description: str | None, due_date: str | None, today: date
    ) -> DraftMilestone:
        m = self._milestone(ref)
        if m.existing_id is not None:
            raise ValueError(f"{ref} is an existing milestone and can't be edited; only tasks can be added to it")
        if name is not None:
            if not name.strip():
                raise ValueError("milestone name is empty")
            m.name = name.strip()
        if description is not None:
            m.description = description
        if due_date is not None:
            m.due_date = self._parse_due(due_date, today)
        return m

    def remove_milestone(self, ref: str) -> DraftMilestone:
        m = self._milestone(ref)
        if m.existing_id is not None:
            raise ValueError(f"{ref} is an existing milestone and can't be removed")
        self.milestones.remove(m)
        return m

    def move_milestone(self, ref: str, position: int) -> None:
        m = self._milestone(ref)
        if not 1 <= position <= len(self.milestones):
            raise ValueError(f"position must be between 1 and {len(self.milestones)}")
        self.milestones.remove(m)
        self.milestones.insert(position - 1, m)

    def add_task(self, milestone_ref: str, title: str, description: str | None) -> DraftTask:
        m = self._milestone(milestone_ref)
        if len(m.tasks) >= MAX_TASKS_PER_MILESTONE:
            raise ValueError(f"at most {MAX_TASKS_PER_MILESTONE} tasks per milestone; split the milestone")
        t = DraftTask(self._ref("T"), self._check_new_title(title), description)
        m.tasks.append(t)
        return t

    def attach_existing_task(self, milestone_ref: str, task_id: int) -> DraftTask:
        m = self._milestone(milestone_ref)
        if task_id not in self.eligible_tasks:
            raise ValueError(f"task {task_id} is not one of the existing tasks available to attach")
        if task_id in self._attached_ids():
            raise ValueError(f"task {task_id} is already attached")
        if len(m.tasks) >= MAX_TASKS_PER_MILESTONE:
            raise ValueError(f"at most {MAX_TASKS_PER_MILESTONE} tasks per milestone; split the milestone")
        t = DraftTask(self._ref("T"), self.eligible_tasks[task_id], existing_task_id=task_id)
        m.tasks.append(t)
        return t

    def update_task(self, ref: str, title: str | None, description: str | None) -> DraftTask:
        _, t = self._task(ref)
        if t.existing_task_id is not None:
            raise ValueError(f"{ref} is an existing task and can't be edited; remove it to detach it")
        if title is not None:
            t.title = self._check_new_title(title, ignore=t)
        if description is not None:
            t.description = description
        return t

    def remove_task(self, ref: str) -> DraftTask:
        m, t = self._task(ref)
        m.tasks.remove(t)
        return t

    def without(self, milestone_refs: set[str], task_refs: set[str]) -> DecompositionDraft:
        """Copy with the given new milestones/tasks left out (UI include checkboxes)."""
        clone = copy.deepcopy(self)
        clone.milestones = [m for m in clone.milestones if m.existing_id is not None or m.ref not in milestone_refs]
        for m in clone.milestones:
            m.tasks = [t for t in m.tasks if t.ref not in task_refs]
        return clone

    # --- views -----------------------------------------------------------------

    @property
    def new_task_count(self) -> int:
        return sum(1 for m in self.milestones for t in m.tasks if t.existing_task_id is None)

    def render(self) -> str:
        kind = f"existing project id {self.project_id}" if self.project_id else "new project"
        lines = [f"Project: {self.project_name} ({kind})"]
        if not self.milestones:
            lines.append("(no milestones yet)")
        for i, m in enumerate(self.milestones, 1):
            head = f"{i}. [{m.ref}] {m.name}"
            if m.existing_id is not None:
                head += " [existing milestone]"
            if m.due_date:
                head += f" (due {m.due_date.isoformat()})"
            lines.append(head)
            lines.extend(f"     already in DB: {title}" for title in m.existing_task_titles)
            for t in m.tasks:
                suffix = f" [existing task {t.existing_task_id}]" if t.existing_task_id else ""
                lines.append(f"     [{t.ref}] {t.title}{suffix}")
        return "\n".join(lines)


def start_new_project_draft(name: str, description: str | None = None) -> DecompositionDraft:
    if not name.strip():
        raise ValueError("project name is empty")
    return DecompositionDraft(project_name=name.strip(), project_description=description)


def start_existing_project_draft(project_id: int) -> DecompositionDraft:
    project = get_project(project_id)
    if project is None:
        raise ValueError(f"Project {project_id} not found")
    draft = DecompositionDraft(
        project_name=project.name, project_description=project.description, project_id=project.id
    )
    for m in list_milestones(project_id=project.id):
        draft.milestones.append(
            DraftMilestone(
                ref=draft._ref("M"),
                name=m.name,
                description=m.description,
                due_date=m.due_date,
                existing_id=m.id,
                existing_task_titles=[t.title for t in m.tasks],
            )
        )
    draft.eligible_tasks = {
        t.id: t.title
        for t in list_tasks(project_id=project.id)
        if t.milestone_id is None and t.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)
    }
    return draft


def make_draft_tools(draft: DecompositionDraft, today: date) -> list[BaseTool]:
    """Tools bound to one draft. Invalid calls return 'Error: ...' so the model can correct itself."""

    def safe(fn):
        @functools.wraps(fn)  # keeps fn's signature, which the tool's arg schema is built from
        def wrapper(**kwargs) -> str:
            try:
                return fn(**kwargs)
            except ValueError as e:
                return f"Error: {e}"

        return wrapper

    def add_milestone(
        name: str, description: str | None = None, due_date: str | None = None, tasks: list[str] | None = None
    ) -> str:
        """Append a milestone to the end of the plan, optionally with its initial task titles.
        due_date is YYYY-MM-DD or omitted. Returns the milestone's and tasks' refs."""
        m = draft.add_milestone(name, description, due_date, today)
        lines = [f"Added milestone {m.ref}: {m.name}"]
        for title in tasks or []:
            try:
                t = draft.add_task(m.ref, title, None)
                lines.append(f"  added task {t.ref}: {t.title}")
            except ValueError as e:
                lines.append(f"  Error adding {title!r}: {e}")
        return "\n".join(lines)

    def update_milestone(
        milestone_ref: str, name: str | None = None, description: str | None = None, due_date: str | None = None
    ) -> str:
        """Change a new milestone's name, description or due date (YYYY-MM-DD). Omitted fields are unchanged."""
        m = draft.update_milestone(milestone_ref, name, description, due_date, today)
        return f"Updated milestone {m.ref}: {m.name}"

    def remove_milestone(milestone_ref: str) -> str:
        """Remove a new milestone and all of its tasks from the plan."""
        m = draft.remove_milestone(milestone_ref)
        return f"Removed milestone {m.ref} and its {len(m.tasks)} task(s)"

    def move_milestone(milestone_ref: str, position: int) -> str:
        """Move a milestone to a 1-based position in the sequence."""
        draft.move_milestone(milestone_ref, position)
        return f"Moved {milestone_ref} to position {position}"

    def add_task(milestone_ref: str, title: str, description: str | None = None) -> str:
        """Add a new task under a milestone. Returns its ref (e.g. T7)."""
        t = draft.add_task(milestone_ref, title, description)
        return f"Added task {t.ref} to {milestone_ref}: {t.title}"

    def attach_existing_task(milestone_ref: str, task_id: int) -> str:
        """Put one of the listed existing tasks under a milestone instead of creating a duplicate."""
        t = draft.attach_existing_task(milestone_ref, task_id)
        return f"Attached existing task {task_id} as {t.ref} under {milestone_ref}: {t.title}"

    def update_task(task_ref: str, title: str | None = None, description: str | None = None) -> str:
        """Change a new task's title or description. Omitted fields are unchanged."""
        t = draft.update_task(task_ref, title, description)
        return f"Updated task {t.ref}: {t.title}"

    def remove_task(task_ref: str) -> str:
        """Remove a task from the plan (an attached existing task is just detached)."""
        t = draft.remove_task(task_ref)
        return f"Removed task {t.ref}: {t.title}"

    def view_draft() -> str:
        """Show the whole current plan with its refs. Use it to check your work before replying."""
        return draft.render()

    fns = [
        add_milestone,
        update_milestone,
        remove_milestone,
        move_milestone,
        add_task,
        attach_existing_task,
        update_task,
        remove_task,
        view_draft,
    ]
    return [StructuredTool.from_function(safe(fn), name=fn.__name__, description=fn.__doc__) for fn in fns]


def system_prompt(draft: DecompositionDraft, today: date) -> str:
    eligible = "\n".join(f"- [task {i}] {title}" for i, title in draft.eligible_tasks.items()) or "(none)"
    about = f"{draft.project_name}" + (f": {draft.project_description}" if draft.project_description else "")
    return (
        f"{DECOMPOSITION_SYSTEM_PROMPT}\n\nToday is {today.isoformat()}.\n\n"
        f"Project: {about}\n\nCurrent draft:\n{draft.render()}\n\n"
        f"Existing tasks available to attach:\n{eligible}"
    )


@dataclass
class TurnResult:
    history: list[BaseMessage]  # conversation without the system message, incl. tool traffic
    reply: str
    steps: int  # model calls this turn
    tool_calls: int
    hit_limit: bool


def run_decomposition_turn(
    history: list[BaseMessage], draft: DecompositionDraft, today: date, max_steps: int = MAX_STEPS
) -> TurnResult:
    """Run the tool-calling loop until the model replies without tool calls or hits
    the step cap. `history` must end with the user's new message; `draft` is edited in place."""
    tools = make_draft_tools(draft, today)
    by_name = {t.name: t for t in tools}
    model = get_default_chat_model().bind_tools(tools)
    # System message is rebuilt each turn so it reflects edits made outside the loop.
    messages: list[BaseMessage] = [SystemMessage(system_prompt(draft, today)), *history]
    calls = 0
    for step in range(1, max_steps + 1):
        ai = model.invoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            return TurnResult(messages[1:], ai.text.strip() or "I've updated the draft.", step, calls, False)
        for call in ai.tool_calls:
            calls += 1
            tool = by_name.get(call["name"])
            result = tool.invoke(call["args"]) if tool else f"Error: unknown tool {call['name']!r}"
            messages.append(ToolMessage(result, tool_call_id=call["id"]))
    return TurnResult(messages[1:], STEP_LIMIT_REPLY, max_steps, calls, True)


@dataclass
class DecompositionResult:
    project: Project
    milestones: list[Milestone]
    new_tasks: list[Task]


def confirm_decomposition(draft: DecompositionDraft) -> DecompositionResult:
    """Persist a user-confirmed draft. Milestone/task writes are one transaction;
    a project created here is deleted again if they fail."""
    if not any(m.existing_id is None or m.tasks for m in draft.milestones):
        raise ValueError("The draft adds nothing: no new milestones or tasks.")
    empty = [m.name for m in draft.milestones if m.existing_id is None and not m.tasks]
    if empty:
        raise ValueError(f"New milestone(s) without tasks: {', '.join(empty)}")

    specs = [
        MilestoneSpec(
            name=m.name,
            description=m.description,
            due_date=m.due_date,
            existing_milestone_id=m.existing_id,
            new_tasks=[NewTaskSpec(t.title, t.description) for t in m.tasks if t.existing_task_id is None],
            attach_task_ids=[t.existing_task_id for t in m.tasks if t.existing_task_id is not None],
        )
        for m in draft.milestones
    ]

    if draft.project_id is None:
        project = create_project(draft.project_name, draft.project_description)
        try:
            milestones, new_tasks = create_milestones_with_tasks(project.id, specs)
        except Exception:
            delete_project(project.id)
            raise
    else:
        project = get_project(draft.project_id)
        if project is None:
            raise ValueError(f"Project {draft.project_id} no longer exists")
        milestones, new_tasks = create_milestones_with_tasks(project.id, specs)
    return DecompositionResult(project, milestones, new_tasks)
