# Phase 4 — Weekly review

## What this achieves

At the end of a week, compare what was planned (Phase 2's `WeeklyGoal`s and
their linked tasks) against what actually happened, and produce a written
summary. The comparison is arithmetic done in code; the model only writes the
prose. Runs either from a manually-triggered script or from a new Streamlit
tab.

This phase also closes the gap that made the review meaningless: until now
nothing could mark a task done or log a habit.

## Key decisions

- **A "This week" tab supplies the completion data.** It lists the week's
  goals with their tasks (tick to complete) and, for habit goals, one tick box
  per day of the week. It implements `complete_task`, `reopen_task`,
  `log_habit_completion` and `remove_habit_log`. Days after today can't be
  ticked. No model calls at all, so it's free to exercise.
- **Counting is deterministic.** `build_week_review(week_start)` reads the DB
  and produces the numbers. The LLM sees those numbers as facts and never
  counts anything itself:
  - *Habit goal:* completions = `HabitLog` rows in the week with
    `completed=True`. Target = `target_count`, else the habit's
    `target_per_period`.
  - *Task goal:* completions = linked tasks with status `DONE`. Target =
    `target_count`, else the number of linked tasks.
  - *Qualitative goal* (no habit, no tasks, no target): not measurable, so no
    status is inferred. The review says so instead of guessing.
- **Status is set from the count, notes from the model.** A goal reaching its
  target becomes `ACHIEVED`, otherwise `MISSED`; unmeasurable goals keep their
  current status. `record_weekly_review` stores a factual per-goal note
  ("3/4 tasks done; outstanding: …") plus `reviewed_at`. Re-running a review
  for the same week overwrites its own notes and status, so it's repeatable.
- **The narrative isn't persisted.** There is no `WeeklyReview` table, and a
  per-goal `review_notes` column is the wrong home for a whole-week summary.
  The script prints it and the tab shows it. If the monthly email report later
  needs week summaries on record, that's a schema addition and a decision for
  then.
- **Carry-over is an explicit, confirmed action.** Missed goals may be copied
  into next week with their unfinished tasks, via
  `tools/weekly_goals.py::carry_over_weekly_goal` (one transaction: create next
  week's goal, move the not-done tasks onto it, mark the original
  `CARRIED_OVER`). Nothing is carried over unless the user asks for it. Already
  completed tasks stay with the original week, so the history stays truthful.
- **Unplanned work is reported, not hidden.** Tasks completed during the week
  that belong to no goal are listed separately, so a productive week spent off
  plan doesn't read as a failure.
- **One model call per review**, a plain text generation (no structured
  output), which keeps the review usable on the free tier.

## Implementation steps

1. Tools:
   - `tools/tasks.py`: `complete_task` (status `DONE` + `completed_at`),
     `reopen_task` (back to `TODO`, clears `completed_at`)
   - `tools/habits.py`: `log_habit_completion` (idempotent on the
     `(habit_id, log_date)` unique constraint), `remove_habit_log`,
     `get_habit_logs`
   - `tools/weekly_goals.py`: `record_weekly_review`, `carry_over_weekly_goal`
2. `agents/pm/review.py`:
   - `current_week_start(today)` — Monday of the week containing today (note:
     *not* `planning_week_start`, which rolls to next week on a weekend)
   - `GoalReview` / `WeekReview` dataclasses, `build_week_review(week_start)`
   - `render_review_facts(review)` — the text block the model sees
   - `summarize_week(review)` — the one model call, returns prose
   - `save_review(review, summary)` — per-goal notes + status
3. `scripts/weekly_review.py` — manual trigger:
   `--week YYYY-MM-DD` (default: last week), `--no-llm` (facts only, no API
   call), `--no-save` (don't write back).
4. Streamlit: a fourth mode, **This week** — completion ticking, a "Generate
   weekly review" button, the summary, and carry-over checkboxes with a button.
5. Unit tests: the arithmetic (every goal kind, partial/over-target, week
   boundaries), the tools, `save_review`, carry-over, `summarize_week` with a
   mocked model, and the UI flow.
6. Evals: `evals/pm_weekly_review.yaml` — fixed weeks with known outcomes; the
   summary must state the real numbers and must not claim a missed goal was
   achieved.

## Code sketch

### Facts

```python
@dataclass
class GoalReview:
    goal: WeeklyGoal
    kind: str                    # "habit" | "tasks" | "qualitative"
    completed: int
    target: int | None
    done: list[str]              # task titles, or logged dates for a habit
    outstanding: list[str]
    status: WeeklyGoalStatus | None   # None when not measurable

@dataclass
class WeekReview:
    week_start: date
    goals: list[GoalReview]
    unplanned_done: list[Task]   # completed this week, not linked to a goal
```

### Summary call

```python
def summarize_week(review: WeekReview) -> str:
    model = get_default_chat_model()
    return model.invoke([
        ("system", REVIEW_SYSTEM_PROMPT),
        ("human", render_review_facts(review)),
    ]).text.strip()
```

`REVIEW_SYSTEM_PROMPT` forbids inventing numbers, asks for what went well,
what slipped and why it might have, and one or two concrete suggestions for
next week, in a few short paragraphs addressed to the user.

### Eval fixture shape

```yaml
cases:
  - name: mixed week
    week_start: 2026-09-14
    goals:
      - {description: Gym three times, habit: Gym, target: 3, logged_days: 2}
      - {description: Ship pricing page, tasks: [Update copy, Fix form], done: [Update copy]}
    must_mention: ["2", "3", "pricing"]     # real numbers appear
    must_not_mention: ["all goals", "everything"]
```

## What "done" looks like

- [x] Tasks can be completed/reopened and habits logged/unlogged from the UI
- [x] Counts are computed in code and match the DB for every goal kind
- [x] A qualitative goal is reported as unmeasurable rather than guessed
- [x] Review saves per-goal notes + ACHIEVED/MISSED, and re-running is idempotent
- [x] Carry-over moves only unfinished tasks and marks the original CARRIED_OVER
- [x] `scripts/weekly_review.py` runs standalone, with `--no-llm` working offline
- [x] Unit tests pass with zero API calls
- [x] Eval set runs against the real provider and the summary states true numbers *(4/4 on deepseek-flash, 2026-09-21)*
