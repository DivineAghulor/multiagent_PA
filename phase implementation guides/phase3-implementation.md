# Phase 3 — Decomposition

## What this achieves

Break a project into ordered milestones and concrete tasks. This runs as an
iterative tool-calling loop, not a single structured-output call. The model
builds a draft step by step through tools, inspects the draft, and revises it.
The user can keep refining it in conversation. Nothing is written until the
user confirms. The new tasks then go through the Phase 1 rating dialog.

## Key decisions

- **Tools edit an in-memory draft, never the DB.** The loop's tools
  (`add_milestone`, `add_task`, `attach_existing_task`, `update_*`, `remove_*`,
  `move_milestone`, `view_draft`) mutate a `DecompositionDraft`. Only
  `confirm_decomposition`, triggered by the user, writes rows. This is the same
  propose → confirm principle as Phase 2.
- **Why a loop instead of one call:** big projects decompose badly in one
  shot, with duplicated tasks, vague milestones and lost user constraints.
  Tools let the model build incrementally, check its work (`view_draft`), and
  get immediate error feedback for invalid moves. Tool errors are returned to
  the model as text so it can correct itself. They never crash the loop.
- **Few model calls per turn.** `add_milestone` accepts the milestone's initial
  task titles, and the prompt asks for several tool calls per step. A typical
  breakdown takes about 3–4 model calls (build, view and fix, reply) instead of
  one call per edit. This matters on Gemini's free tier (20 requests/day per
  model), where a call-per-edit loop would use up the daily budget in one or two
  breakdowns.
- **The loop is hand-rolled**, `bind_tools` plus a `while` loop with a hard
  step cap (`MAX_STEPS = 30` model calls per user turn). It is not
  LangGraph's prebuilt agent. That keeps it provider-agnostic through
  `get_default_chat_model()`, trivially mockable, and clear of orchestrator
  territory. Hitting the cap ends the turn with an explicit message, and the
  draft built so far is kept.
- **New and existing projects:**
  - *New:* the user gives a name and description, and the project row is
    created on confirm.
  - *Existing:* the draft is seeded with the project's current milestones
    (read-only: new tasks may be added under them and they may be reordered,
    but they can't be renamed or removed) plus its **eligible** tasks: tasks of
    this project that have no milestone and aren't done or cancelled. The
    model attaches eligible tasks (`attach_existing_task`) instead of
    duplicating them.
- **Ordering:** a new nullable `Milestone.position`. On confirm every milestone
  in the draft gets position 1..n in draft order, including existing ones the
  user may have reordered. `list_milestones` orders by position (nulls last),
  then due date, then id.
- **Guard rails in the draft:** at most 10 milestones, at most 12 tasks per
  milestone, and no two tasks with the same normalized title anywhere in the
  draft (existing tasks included). An existing task can be attached once, and
  due dates must be `YYYY-MM-DD`.
- **Confirming is atomic** for milestones and tasks (one transaction in
  `tools/milestones.py::create_milestones_with_tasks`), and it re-validates
  existing IDs against the live DB. If a new project was created and the
  milestone write then fails, the project is deleted again.
- **Rating:** tasks created on confirm are unrated (the LLM never sets
  importance/urgency) and go straight into the shared rating dialog.
  Attached existing tasks keep their ratings.

## Implementation steps

1. Schema: `Milestone.position` plus an Alembic migration.
2. Tools:
   - `tools/milestones.py`: `create_milestone`, `get_milestone`,
     `list_milestones`, `update_milestone`, `delete_milestone`, and
     `create_milestones_with_tasks(project_id, specs)`, an atomic write of the
     confirmed draft.
   - `tools/projects.py`: `delete_project` (the rollback path for a
     new project).
3. `agents/pm/decomposition.py`:
   - `DecompositionDraft`, `DraftMilestone`, `DraftTask`: the mutable draft
     plus a `render()` text view
   - `start_new_project_draft(name, description)` /
     `start_existing_project_draft(project_id)`
   - `make_draft_tools(draft)`: `StructuredTool`s bound to that draft
   - `run_decomposition_turn(history, draft, today)` → `TurnResult`, the loop
   - `confirm_decomposition(draft)` → `DecompositionResult`
4. Streamlit: a third mode, **Project breakdown** (pick an existing project or
   describe a new one, then chat, see the draft tree with include checkboxes,
   Confirm / Discard). The rating dialog is extracted into a shared helper so
   the new tasks can be rated right after confirming.
5. Unit tests: the draft operations and guard rails, the loop driven by a
   scripted fake model (tool calls, error feedback, step cap), confirm
   (atomicity, re-validation, rollback), and the UI flow.
6. Evals: `evals/pm_decomposition.yaml` plus a runner. This is the phase most
   at risk of bad output, so the eval checks structure, not just counts.

## Code sketch

### Loop

```python
def run_decomposition_turn(history, draft, today, max_steps=MAX_STEPS) -> TurnResult:
    tools = make_draft_tools(draft)
    by_name = {t.name: t for t in tools}
    model = get_default_chat_model().bind_tools(tools)
    messages = [SystemMessage(system_prompt(draft, today)), *history]
    for step in range(1, max_steps + 1):
        ai = model.invoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            return TurnResult(messages[1:], ai.text, step, hit_limit=False)
        for call in ai.tool_calls:
            tool = by_name.get(call["name"])
            result = tool.invoke(call["args"]) if tool else f"Error: unknown tool {call['name']}"
            messages.append(ToolMessage(result, tool_call_id=call["id"]))
    return TurnResult(messages[1:], STEP_LIMIT_REPLY, max_steps, hit_limit=True)
```

The system message is rebuilt every turn from the current draft, so it always
reflects what the user edited through the UI checkboxes between turns.

### Eval fixture shape

```yaml
cases:
  - project: {name: Launch a podcast, description: "..."}   # or existing: <fixture project name>
    turns: ["Break this down. I want the first episode out in 6 weeks."]
    min_milestones: 3
    max_milestones: 7
    max_tasks_per_milestone: 10
    keywords_any: [record, edit, publish]      # at least one appears in some title
    must_attach: []                            # existing-project cases
```

On every case the runner also checks for: no step-limit hit, at least 2 tool
calls (actually iterative), no empty milestones, and no near-duplicate task
titles (difflib ratio ≥ 0.9). New tasks must not near-duplicate an eligible
existing task, which should have been attached instead.

## What "done" looks like

- [x] `Milestone.position` migration applied to the local dev DB
- [x] The model builds the breakdown over several tool calls; tool errors are fed back and self-corrected *(3/5 eval cases pass on gemini-3.6-flash, 2026-09-20)*
- [x] Existing projects: current milestones kept, eligible backlog tasks attached rather than duplicated *(eval case passes on deepseek-flash: all 3 existing tasks attached, none duplicated)*
- [x] Nothing persisted until the user confirms; confirm is atomic and re-validates
- [x] New tasks go through the rating dialog
- [x] Unit tests pass with zero API calls
- [x] Eval set runs against the real provider and results look sane *(3/5 on gemini-3.6-flash 2026-09-20; the remaining 2 cases pass on deepseek-flash 2026-09-21)*
- [x] Streamlit: breakdown chat → draft tree → confirm writes rows → rating dialog; discard writes nothing
