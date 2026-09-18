# Phase 2 — Weekly planning

## What this achieves

A planning conversation that reads the current backlog, active projects and
active habits, and turns what the user says they want out of the coming week
into `WeeklyGoal` rows. Each goal has a measurable target and, where it makes
sense, specific backlog tasks attached to it. Nothing is written until the user
confirms the proposed plan.

## Key decisions

- **Goals carry a measurable target.** `WeeklyGoal` gains a nullable `habit_id`
  (FK → `habits`) and a nullable `target_count`. Phase 4's review compares
  these targets against real completions, so a goal can't be free text only:
  - *Habit goal* (`habit_id` set): `target_count` = number of completed
    `HabitLog`s in the week (e.g. "gym 3x" → 3).
  - *Task goal* (`task_ids` linked): `target_count` = how many of the linked
    tasks should be done. It defaults to all of them when left empty.
  - *Qualitative goal* (neither): `target_count` stays null and the review
    judges it from `description` alone.
  - A goal is about a project **or** a habit, never both. The tool layer
    enforces this, not a DB constraint.
- **Propose, then confirm.** The model only ever produces a
  `WeeklyPlanProposal`. The user edits it (include/exclude, reword, change
  targets) and presses Confirm, and only then do `WeeklyGoal` rows get written
  and tasks get linked. This is the same human-in-the-loop principle as the
  calendar reschedule flow, done at the UI layer because there's no LangGraph
  interrupt yet. When the orchestrator lands, confirmation should move onto
  the shared interrupt pattern from Calendar Phase 4.
- **Planning links backlog tasks to goals.** On confirm, each linked task gets
  `weekly_goal_id` set and moves `BACKLOG → TODO`. Only tasks still in
  `BACKLOG` can be linked, and a task belongs to at most one goal. Assigning
  tasks to specific *days* (`Task.scheduled_for`) is out of scope, since that's
  the Calendar track's priority engine.
- **Every turn returns the whole plan.** Each chat turn sends the full
  conversation plus a fresh render of the backlog/habits/projects, and the
  model returns the complete revised goal set (plus a short reply to the user),
  never a diff. This keeps the UI simple: it always shows the latest proposal.
- **Model-produced IDs are never trusted.** The prompt shows the model real
  task/project/habit IDs. `sanitize_proposal` drops any ID that isn't in the
  context, deduplicates tasks across goals and returns human-readable warnings.
  `confirm_weekly_plan` re-validates against the live DB before writing.
- **The target week is a Monday** (`WeeklyGoal.week_start`). The default is the
  current week's Monday, or next Monday when planning on a Saturday or Sunday.
  The UI lets the user pick another week.
- **No `@tool` wrapper that writes goals this phase.** A tool the orchestrator
  could call to write goals directly would bypass the confirmation step. That
  wiring waits for the interrupt pattern.

## Implementation steps

1. Schema: `WeeklyGoal.habit_id`, `WeeklyGoal.target_count`, and a `habit`
   relationship. Alembic migration generated with `--autogenerate`.
2. Tools:
   - `tools/weekly_goals.py`: `create_weekly_goal` (now takes `habit_id`,
     `target_count`, `task_ids`, and creates the goal and links its tasks in one
     transaction), `get_weekly_goal`, `list_weekly_goals`,
     `update_weekly_goal_status`, `delete_weekly_goal`. `record_weekly_review`
     stays a stub for Phase 4.
   - `tools/tasks.py`: `get_backlog`, `list_tasks`, `update_task_status`.
   - `tools/projects.py`: `get_project`, `list_projects`, `create_project`.
   - `tools/habits.py`: `create_habit`, `get_habit`, `list_habits`.
3. `agents/pm/schemas.py`: `ProposedGoal`, `WeeklyPlanProposal`, which are
   LLM-facing and separate from the DB model.
4. `agents/pm/planning.py`:
   - `planning_week_start(today)`
   - `load_planning_context(week_start)` → `PlanningContext` (backlog, active
     projects, active habits, goals already set for that week)
   - `render_planning_context(ctx)` → the text block the model sees
   - `propose_weekly_plan(history, ctx)`: a structured-output call through
     `get_default_chat_model()`
   - `sanitize_proposal(proposal, ctx)` → `(clean proposal, warnings)`
   - `confirm_weekly_plan(week_start, goals)`: re-validates, then writes
5. Streamlit harness: a sidebar mode switch between **Backlog capture** (the
   Phase 1 page, unchanged) and **Weekly planning** (week picker, existing
   goals, planning chat, editable proposal, Confirm / Discard).
6. Unit tests, with the LLM mocked throughout: tools, planning logic, and the
   UI flow via `AppTest`.
7. Eval set `evals/pm_weekly_planning.yaml` plus runner
   `evals/run_pm_weekly_planning.py`. It seeds a fixed backlog into an
   in-memory SQLite DB (never the dev DB), runs real-model planning turns, and
   checks the proposals are sane.

## Code sketch

### Schema

```python
# db/models.py — WeeklyGoal additions
habit_id: Mapped[int | None] = mapped_column(ForeignKey("habits.id", ondelete="SET NULL"))
target_count: Mapped[int | None] = mapped_column(Integer)
habit: Mapped["Habit | None"] = relationship()
```

### Proposal schema

```python
class ProposedGoal(BaseModel):
    description: str          # "Ship the pricing page"
    project_id: int | None    # from the context, or null
    habit_id: int | None      # from the context, or null; never both
    target_count: int | None  # habit: completions; tasks: how many to finish
    task_ids: list[int] = []  # backlog task IDs from the context

class WeeklyPlanProposal(BaseModel):
    reply: str                # conversational message shown to the user
    goals: list[ProposedGoal] # the complete plan as of this turn
```

### Planning turn

```python
def propose_weekly_plan(history: list[tuple[str, str]], ctx: PlanningContext) -> WeeklyPlanProposal:
    model = get_default_chat_model().with_structured_output(WeeklyPlanProposal)
    system = PLANNING_SYSTEM_PROMPT + "\n\n" + render_planning_context(ctx)
    return model.invoke([("system", system), *history])
```

### Confirm

```python
def confirm_weekly_plan(week_start: date, goals: list[ProposedGoal]) -> list[WeeklyGoal]:
    clean, warnings = sanitize_proposal(WeeklyPlanProposal(reply="", goals=goals),
                                        load_planning_context(week_start))
    if warnings:
        raise ValueError("; ".join(warnings))   # stale proposal — backlog changed underneath it
    return [create_weekly_goal(week_start, g.description, g.project_id, g.habit_id,
                               g.target_count, g.task_ids) for g in clean.goals]
```

### Eval fixture shape

```yaml
fixture:            # seeded into in-memory SQLite before the run
  projects: [...]
  habits: [...]
  tasks: [...]
cases:
  - input: "This week I want to ship the pricing page and hit the gym 3 times"
    min_goals: 2
    max_goals: 4
    habit_targets: {Gym: 3}             # habit goal must exist with that target
    linked_tasks: ["Update pricing page copy"]
    unlinked_tasks: ["Write literature review"]
    forbidden_habits: []
```

The runner fails a case if `sanitize_proposal` produced any warnings
(hallucinated IDs or a task used twice) or if any expectation above fails.

## What "done" looks like

- [x] Migration adds `habit_id` / `target_count`; local dev DB upgraded
- [x] Planning reads backlog + projects + habits + the week's existing goals
- [x] The model proposes; nothing is persisted until the user confirms
- [x] Confirm writes `WeeklyGoal` rows and links tasks (`weekly_goal_id`, `BACKLOG → TODO`)
- [x] Hallucinated or duplicated IDs never reach the DB
- [x] Unit tests pass with zero API calls
- [x] Eval set runs against the real provider and results look sane
- [x] Streamlit: planning chat → editable proposal → confirm writes goals; discard writes nothing
