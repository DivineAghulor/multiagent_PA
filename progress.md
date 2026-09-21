# Progress log

Append-only changelog, one entry per completed implementation phase. See
[`CLAUDE.md`](CLAUDE.md) for the required format and workflow. This is a
factual record of what changed, not a design doc — see `implementation-plan.md`
for the plan and `NOTES.md` for open critical issues.

---

## Phase 0 — Bootstrap (2026-08-17, backfilled)

**Scope:** Joint bootstrap phase from `implementation-plan.md` — the shared
contract both tracks build against.

**Changed:**
- Repo skeleton: `agents/`, `tools/`, `db/`, `tests/`, `evals/`
- `db/models.py` — SQLAlchemy models: `Project`, `Milestone`, `Task`, `Habit`,
  `HabitLog`, `WeeklyGoal`, `CalendarEvent`, with enums and the
  propose/confirm/reject reschedule fields on `CalendarEvent`
- Alembic wired up (`alembic.ini`, `alembic/env.py`); initial schema
  migration `89e2870d539b_init.py` added in `c7b9d18`
- `tools/tasks.py`, `tools/projects.py`, `tools/milestones.py`,
  `tools/weekly_goals.py`, `tools/habits.py`, `tools/calendar.py` — typed,
  empty-bodied CRUD stubs (`raise NotImplementedError`) for each entity
- `llm/factory.py` — `get_chat_model` / `get_default_chat_model`,
  config-driven provider selection (anthropic/google_genai/openai/xai)
- `config.py` — pydantic-settings `Settings`, `.env.example` with all known
  variable names
- `docs/database-setup.md`, `SETUP.md` (referenced from README) — local
  Postgres setup instructions
- `evals/README.md`, `evals/pm_backlog.yaml`, `evals/calendar_nl.yaml` —
  eval scaffolding, fixtures not yet filled in
- `tests/test_smoke.py` — smoke test

**Tests:** `pytest` smoke test only; no feature tests yet (nothing
implemented beyond stubs).

**Follow-ups:** See `NOTES.md` for the stub-function tracking entry.

---

## Phase 1 — Backlog capture, priority dialog & test interface (2026-08-18)

**Scope:** Person A / PM track, Phase 1 of `phase implementation
guides/phase1-implementation.md` — freeform text → `Task` rows, immediate
importance/urgency rating, throwaway Streamlit harness.

**Changed:**
- `db/models.py` — added nullable `Task.importance`/`Task.urgency` (1-4 ints),
  separate from the existing `priority` enum (see design-conflict note below)
- `alembic/versions/fc024d63765f_add_task_importance_urgency.py` — migration
  for the two new columns, chained onto the existing `89e2870d539b` init
  migration; applied to the local dev DB
- `tools/tasks.py` — implemented `create_task`, `get_task`; added
  `update_task_priority(task_id, importance, urgency)` with 1-4 range
  validation (shared `_validate_priority_pair` helper)
- `tools/projects.py` — added `find_project_by_name` (case-insensitive exact
  match; returns `None` on no match rather than raising, since an LLM-hinted
  project name may not exist)
- `agents/pm/schemas.py`, `agents/pm/extraction.py`, `agents/pm/backlog.py` —
  `ExtractedTask`/`ExtractedTaskBatch`, `extract_tasks` (structured-output
  chain via `get_default_chat_model()`), `capture_backlog_from_text`,
  `add_tasks_to_backlog` LangChain tool
- `config.py` — **bug fix**: `env_file=".env"` was a relative path, resolved
  against the CWD. Launching from anywhere but the repo root silently found
  no `.env`, so every setting fell back to its default (`llm_provider` ->
  `"anthropic"` with no key) and surfaced as a confusing Anthropic auth
  error instead of a missing-config error. Now anchored to `config.py`'s own
  location. Pre-existing since Phase 0; surfaced when the user ran the
  Streamlit app from a different directory.
- `llm/factory.py` — **bug fix**: `get_chat_model` never forwarded the
  resolved API key from `config.settings` into the provider SDK constructors;
  `pydantic-settings` loading `.env` doesn't populate `os.environ`, so every
  provider's own env-var lookup saw nothing. Now passes `api_key`/
  `google_api_key` explicitly per provider. Pre-existing since Phase 0;
  surfaced when Phase 1 made the first real LLM call.
- `tests/conftest.py` — `db_session` fixture: isolated in-memory SQLite
  (monkeypatches `db.session.SessionLocal`) rather than the local Postgres
  dev DB, so unit tests stay fast and don't depend on local DB state. Uses
  `StaticPool`/`check_same_thread=False` so the AppTest harness, which runs
  the app script off the main thread, shares the same in-memory DB
- `tests/test_app_ui.py` — new: 3 tests driving `app_test.py` through
  Streamlit's `AppTest` harness (chat submit -> rating dialog -> save ->
  task drops out; zero-task input shows no dialog), `extract_tasks` mocked
- `tests/test_backlog.py` — 5 tests: multi-task extraction, zero-task input,
  known-project-hint resolution, priority rating, out-of-range rejection —
  `extract_tasks` mocked throughout
- `evals/pm_backlog.yaml` — filled in the 3 fixtures from the phase doc
- `evals/run_pm_backlog.py` — new: runs the yaml fixtures against the real
  configured provider, prints pass/fail per case
- `pyproject.toml` — added `streamlit`, `pyyaml`
- `app_test.py` — Streamlit chat + rating-dialog harness, per the phase doc

**Tests:** `pytest` — 12/12 passed (5 backlog + 3 UI + 4 existing smoke
tests), zero live API calls. `uv sync` (rerun by the user with network
access) installed
`streamlit`/`pyyaml` successfully; booted `app_test.py` headless
(`streamlit run ... --server.headless true`) and confirmed it serves HTTP
200 with a clean startup log — no import or runtime errors.

Once a real `GOOGLE_API_KEY` was configured (`LLM_PROVIDER=google_genai`,
`LLM_MODEL=gemini-2.5-flash`) and a local TLS-interception issue was fixed
(see below), ran `evals/run_pm_backlog.py` against the real model — **3/3
passed**. Also ran a direct end-to-end smoke test bypassing the Streamlit
UI: `capture_backlog_from_text` (real Gemini call) correctly split a
two-action sentence into two `Task` rows in the real local Postgres DB, and
`update_task_priority`/`get_task` correctly wrote and re-read
importance/urgency. Test rows were deleted afterward.

The Streamlit flow was then driven through Streamlit's `AppTest` harness
against the real model + real DB: chat submit captured 2 tasks, the rating
dialog rendered 4 selectboxes / 2 save buttons, saving a rating persisted
importance=3/urgency=4 and dropped that task from the dialog while the
unrated one remained. Rows cleaned up. Only the visual browser rendering
itself has never been eyeballed.

**Design conflict surfaced (flagged, not fully resolved):** the phase doc
introduces a 1-4 `importance`/`urgency` pair on `Task`, but Phase 0's schema
already models "how important is this task" via a single `priority` enum
(`LOW/MEDIUM/HIGH/URGENT`). `implementation-plan.md` shows the *Calendar*
track's Phase 3 priority engine is the intended consumer of the
importance/urgency pair — so this is a cross-track decision, not just a PM
detail. Resolved additively for now (both fields coexist, `priority` unused
by Phase 1); needs an actual decision before Person B builds the priority
engine: does `priority` get deprecated, derived from importance×urgency, or
serve a genuinely separate purpose?

**Follow-ups:**
- Local machine note (not project code): Python HTTPS calls were failing
  with `CERTIFICATE_VERIFY_FAILED` due to Avast/AVG's HTTPS-scanning driver
  (TLS interception trusted by Windows/curl but not by Python's bundled
  `certifi`). Fixed by installing `pip-system-certs` into this machine's
  venv only (`uv pip install --system-certs pip-system-certs`) — not added
  to `pyproject.toml`, since it's a local trust-store workaround, not an
  application dependency. The other dev may hit the same class of error if
  they run similar endpoint-protection software; same fix applies.
- `LLM_PROVIDER`/`LLM_MODEL` in `.env` were switched from the
  `anthropic`/`claude-sonnet-4-5` default to `google_genai`/`gemini-2.5-flash`
  to match the key the user provided. Anthropic/OpenAI/XAI keys are still
  empty — switch back or add one of those keys if a different provider is
  wanted later.
- The Streamlit flow is verified programmatically (`AppTest`, plus
  `tests/test_app_ui.py` as permanent mocked coverage); nobody has visually
  eyeballed the rendered page in a browser yet. Note for whoever does: after
  restarting the server, hard-refresh the tab — Streamlit keeps the previous
  render, so a stale error can persist in the browser well after the
  underlying bug is fixed (this cost real debugging time in this phase).
- `find_project_by_name` is an exact case-insensitive match; a hint like
  "the website thing" won't resolve to a project named "Website" and will
  silently leave `project_id` null. Fine for Phase 1's scope, worth
  revisiting if project-hint misses turn out to be common in practice.
- Resolve the `priority` vs. `importance`/`urgency` question above before
  Person B's Phase 3 priority engine.

**Completion pass (2026-09-18):** audited the build against the phase doc's
"done" list and closed the gaps.
- `llm/factory.py` — **security fix**: removed debug `print`s (added while
  diagnosing the provider-routing issue, committed in `c6aeebe`) that wrote
  the first 6 + last 4 characters of the API key to stdout / the Streamlit
  server log on every model call. Replaced with `logging.debug` recording
  provider, model and key *presence* only.
- `agents/pm/backlog.py` — `add_tasks_to_backlog` returned
  `"Added 0 task(s) to the backlog: "` on empty input; now returns an
  explicit no-tasks message, since an orchestrator LLM will read it verbatim.
- `tests/test_backlog.py` — +3 tests: the `add_tasks_to_backlog` tool wrapper
  (persists + summarizes; empty input), `update_task_priority` on an unknown
  task id.
- `evals/pm_backlog.yaml` — 3 → 8 cases: added past-tense/non-actionable
  input, a real task buried in unrelated chatter, a second 3-way split, and
  two `project_hint` cases. `evals/run_pm_backlog.py` checks the new optional
  `expected_project_hints` field.
- `phase implementation guides/phase1-implementation.md` — done-list ticked.

Tests: `pytest` 15/15, zero live API calls. Eval 8/8 against
`gemini-2.5-flash`. Observation: the model attaches `project_hint` loosely
("Q3 report", "conference"). Harmless today because unmatched hints resolve
to `project_id=None`, but it'll become noise if hint matching ever gets fuzzy
(see the `find_project_by_name` follow-up above).

---

## Phase 2 — Weekly planning (2026-09-18)

**Scope:** Person A / PM track, Phase 2 of `implementation-plan.md`, specified
in `phase implementation guides/phase2-implementation.md` (written this
session from the roadmap + decisions confirmed with the user: `habit_id` +
`target_count` on `WeeklyGoal`, propose-then-confirm, planning links backlog
tasks to goals).

**Changed:**
- `db/models.py` — `WeeklyGoal.habit_id` (FK → `habits`, `SET NULL`),
  `WeeklyGoal.target_count`, `habit` relationship
- `alembic/versions/78f764046e7d_add_weekly_goal_habit_and_target.py` —
  autogenerated; FK given an explicit name (`weekly_goals_habit_id_fkey`)
  because autogenerate left it `None`, which breaks `downgrade()`. Upgrade →
  downgrade → upgrade verified on the local dev DB, now at head
- `tools/weekly_goals.py` — implemented `create_weekly_goal` (now also takes
  `habit_id`/`target_count`/`task_ids`; validates Monday week_start,
  project-xor-habit, positive target, task still in unassigned backlog; creates
  goal + links tasks `BACKLOG → TODO` in one transaction), `get_weekly_goal`,
  `list_weekly_goals` (relationships eager-loaded), `update_weekly_goal_status`,
  `delete_weekly_goal` (unstarted tasks go back to the backlog).
  `record_weekly_review` left as a Phase 4 stub
- `tools/tasks.py` — `get_backlog`, `list_tasks`, `update_task_status`
- `tools/projects.py` — `create_project`, `get_project`, `list_projects`
- `tools/habits.py` — `create_habit`, `get_habit`, `list_habits`
- `agents/pm/schemas.py` — `ProposedGoal`, `WeeklyPlanProposal`
- `agents/pm/planning.py` — new: `planning_week_start`,
  `load_planning_context`, `render_planning_context`, `propose_weekly_plan`
  (structured output via `get_default_chat_model()`, full history each turn,
  full plan returned each turn), `sanitize_proposal` (drops hallucinated /
  duplicate IDs with warnings), `describe_proposal`, `confirm_weekly_plan`
  (re-validates against live DB; rejects a stale plan rather than writing it)
- `app_test.py` — sidebar mode switch; Phase 1 page unchanged under "Backlog
  capture"; new "Weekly planning" page: week picker, existing goals, planning
  chat, editable proposal (include/description/target), Confirm / Discard
- `evals/pm_weekly_planning.yaml`, `evals/run_pm_weekly_planning.py` — new:
  fixed backlog seeded into in-memory SQLite, 5 cases incl. one multi-turn
  revision; fails on any sanitizer fix or unmet expectation

**Tests:** `pytest` 43/43 (28 new: 13 tools in `test_weekly_goals.py`, 12
planning in `test_planning.py`, 3 planning UI in `test_app_ui.py`), zero live
API calls. Eval 5/5 against `gemini-2.5-flash`.

**Follow-ups:**
- Confirmation lives in the Streamlit layer; there is deliberately no `@tool`
  that writes goals. When the orchestrator is built, planning confirmation
  should move onto Calendar Phase 4's interrupt pattern.
- `confirm_weekly_plan` validates everything up front, but writes one goal per
  transaction. A DB error mid-way (not a validation failure) could leave a
  partial plan. Acceptable for a single-user harness; revisit if it matters.
- `Task.scheduled_for` (day-level assignment) is untouched, as it belongs to
  the Calendar track's priority engine.

---

## Phase 3 — Decomposition (2026-09-18, open: eval pending)

**Scope:** Person A / PM track, Phase 3 of `implementation-plan.md`, specified
in `phase implementation guides/phase3-implementation.md` (written this
session; decisions confirmed with the user: tools edit an in-memory draft then
confirm, new + existing projects, rating dialog after confirm,
`Milestone.position`).

**Changed:**
- `db/models.py` — `Milestone.position` (nullable int)
- `alembic/versions/7fe27842b9ef_add_milestone_position.py` — autogenerated;
  upgrade → downgrade → upgrade verified on the local dev DB, now at head
- `tools/milestones.py` — all functions implemented, plus `MilestoneSpec` /
  `NewTaskSpec` and `create_milestones_with_tasks` (atomic write of a
  confirmed draft: positions 1..n, new tasks unrated in `BACKLOG`, attached
  tasks re-validated). `list_milestones` orders by position, then due date, then id
- `tools/projects.py` — `delete_project` (rollback path for a new project)
- `agents/pm/decomposition.py` — new: `DecompositionDraft` (guard rails: ≤10
  milestones, ≤12 tasks each, normalized-title dedupe incl. existing tasks,
  existing milestones read-only, due dates `YYYY-MM-DD` after today),
  `make_draft_tools` (9 `StructuredTool`s; invalid calls return `Error: ...`
  to the model), hand-rolled `run_decomposition_turn` loop (`bind_tools`,
  30-step cap, system prompt rebuilt from the draft each turn),
  `confirm_decomposition`
- `app_test.py` — third mode "Project breakdown" (new or existing project,
  chat, draft tree with include checkboxes, Confirm / Discard; provider errors
  keep the draft and show the message). Rating dialog extracted into a shared
  `render_rating_dialog()`, so tasks created on confirm are rated immediately
- `evals/pm_decomposition.yaml`, `evals/run_pm_decomposition.py` — new: 5
  cases (new project with timeline, hard deadline, existing project must
  attach backlog tasks, multi-turn shrink, too-vague → should ask). Fresh
  in-memory DB per case; structural checks (near-duplicate titles, empty
  milestones, attach-not-duplicate, due-date bounds) and a real confirm of
  each final draft. Runner reports provider errors per case and stops on quota

**Tests:** `pytest` 72/72 (29 new: 25 in `test_decomposition.py` driving the
loop with a scripted fake model that emits real tool calls, 4 breakdown UI
tests in `test_app_ui.py`), zero live API calls.

**Eval: not yet run successfully.** The first run hit Gemini's free-tier cap
(`generate_content_free_tier_requests`, 20/day for `gemini-2.5-flash`) partway
through, with no usable output. In response, `add_milestone` now accepts
initial task titles and the prompt asks for batched tool calls (≈3–4 model
calls per breakdown instead of one per edit). Rerun
`uv run python evals/run_pm_decomposition.py` after the quota resets. Phase 3
stays open until it passes.

**Follow-ups:**
- The 20 requests/day free-tier cap is a real constraint for this loop in
  normal use too, not just evals: a few breakdowns plus planning turns
  exhaust it. Options are a paid Gemini tier, or `LLM_PROVIDER`/`LLM_MODEL`
  pointing at a model with more quota. That's a user decision (keys/billing).
- Existing milestones can't be renamed/removed from a breakdown (by design,
  additive only); editing them needs `update_milestone`/`delete_milestone`
  wired into a UI later.

**Added 2026-09-20 (same phase, manual-testing support):**
- `scripts/seed_dev_data.py` — seeds projects, habits and rated backlog tasks
  into the dev DB so weekly planning and the existing-project breakdown flow
  are testable (the UI can't create projects or habits). Idempotent by name;
  `--wipe` clears every table first.
- `scripts/dump_dev_state.py` — prints projects, milestones, habits, weekly
  goals and tasks, for checking what a flow persisted (and that an unconfirmed
  proposal/draft persisted nothing) while clicking through Streamlit.
- Importance/urgency scale made explicit as **1 = lowest, 4 = highest** —
  previously undefined anywhere, though both the planning prompt and the
  existing data assumed it. Updated in the rating dialog's labels
  (`app_test.py`), in the backlog block the planning model sees
  (`agents/pm/planning.py`), and in the `Task.importance` comment in
  `db/models.py`.

Tests: `pytest` 72/72 still passing.

**Phase 3 eval run (2026-09-20):** `gemini-2.5-flash` now returns
404 NOT_FOUND — *"no longer available to new users… use models/gemini-3.6-flash"*.
So the 2026-09-18 failure was a retired model, not only quota. Reran against
`gemini-3.6-flash` (via a `LLM_MODEL=` env override for the run only; `.env`
still names the dead model and **needs updating by the user**): **3/5 passed**,
each breakdown taking 3 steps / 4-5 tool calls, confirming the batching change
works.
- "existing project reuses backlog tasks" — transient 503, then the day's
  quota ran out on retry. Still unverified by eval, but the user's dev DB shows
  a real browser run attaching all three seeded tasks to milestones without
  duplicating them.
- "revision shrinks the plan" — the plan was correct (cut to 3 milestones on
  request); the case failed only because its `keywords_any` list
  (`move`/`register`) didn't match good output ("housing", "Registration").
  Keywords fixed; rerun needed.
- `evals/run_pm_decomposition.py` — added `--case` filtering and a retry for
  transient 503s.

---

## Phase 4 — Weekly review (2026-09-20, open: eval pending)

**Scope:** Person A / PM track, Phase 4 of `implementation-plan.md`, specified
in `phase implementation guides/phase4-implementation.md` (written this
session; decisions confirmed with the user: a "This week" tab supplies
completions, review writes notes + status automatically, carry-over is an
explicit confirmed action).

**Changed:**
- `tools/tasks.py` — `complete_task` (DONE + `completed_at`, backdatable for
  tests/imports), `reopen_task` (back to TODO, clears `completed_at`)
- `tools/habits.py` — `log_habit_completion` (idempotent against the
  `(habit_id, log_date)` unique constraint), `remove_habit_log`,
  `get_habit_logs` (inclusive range)
- `tools/weekly_goals.py` — `record_weekly_review` (notes + status +
  `reviewed_at`, overwrites so re-review is idempotent),
  `carry_over_weekly_goal` (one transaction: copy the goal into a later week,
  move only not-done tasks, mark the original `CARRIED_OVER`)
- `agents/pm/review.py` — new: `current_week_start` (Monday of *this* week,
  deliberately unlike `planning_week_start`), `today()` indirection so the UI
  and tests agree on the date, `GoalReview`/`WeekReview`,
  `build_week_review` (habit logs in-window, task completions, unplanned
  completions, ACHIEVED/MISSED per goal, qualitative goals left unmeasured),
  `render_review_facts`, `summarize_week` (the phase's single model call),
  `goal_note`, `save_review`, `missed_goals`
- `app_test.py` — fourth mode "This week": per-goal progress, task tick boxes
  (complete/reopen), 7 day boxes per habit goal (future days disabled),
  unplanned completions, "Generate weekly review" (saves notes/status; provider
  errors save nothing), carry-over checkboxes + button
- `scripts/weekly_review.py` — manual trigger with `--week`, `--no-llm`,
  `--no-save`; prints facts, summary, and carry-over candidates
- `evals/pm_weekly_review.yaml`, `evals/run_pm_weekly_review.py` — 4 cases
  (mixed week, all achieved, nothing done, unmeasurable only) checking the
  prose states true numbers, doesn't claim a missed goal was achieved, and
  stays prose. Supports `--case` and `--facts-only` (no API call)

**Tests:** `pytest` 101/101 (29 new: 23 in `test_review.py`, 6 "This week" UI
tests), zero live API calls. Eval fixtures verified offline via `--facts-only`;
`scripts/weekly_review.py` exercised end-to-end on a throwaway SQLite DB with
`--no-llm`, both with and without `--no-save`.

**Eval: not yet run.** The day's free-tier quota (20 requests/day, and it's
per-model) went to the Phase 3 rerun. Run
`uv run python evals/run_pm_weekly_review.py` after reset — one call per case,
4 total.

**Follow-ups:**
- **`.env` still sets `LLM_MODEL=gemini-2.5-flash`, which now 404s.** Every
  eval run this session used an env override. The user needs to change it
  (`gemini-3.6-flash` works) or the app will fail on any model call.
- The week's narrative summary isn't persisted anywhere (no `WeeklyReview`
  table). The monthly email report in the joint phase will want this — decide
  then whether to add one.
- `tests/test_app_ui.py::test_ticking_a_task_completes_it_and_unticking_reopens_it`
  failed twice early in this phase with a `DetachedInstanceError`
  (`Task.calendar_events` lazy load), then passed 10 consecutive runs including
  3 full-suite runs. Most likely pytest's failure *reporting* touching an
  unloaded relationship and masking the real assertion, not a product bug —
  but if it resurfaces, the fix is to keep ORM objects out of the failure path
  (compare plain values) rather than to retry.
- Remaining stubs after this phase: `schedule_task`, `update_task`,
  `delete_task`, `update_project`, `archive_project`, `deactivate_habit`, and
  all of `tools/calendar.py` (Person B's track).

**Provider switch to DeepSeek + Phase 4 eval (2026-09-21):**
- `llm/factory.py` — added the `deepseek` provider (`langchain-deepseek`,
  `ChatDeepSeek`); `config.py` gained `deepseek_api_key`, and `.env.example`
  `DEEPSEEK_API_KEY`. `.env` now selects `deepseek` / `deepseek-flash`.
  The account's models are `deepseek-flash` and `deepseek-v4-pro` — *not*
  `deepseek-chat`, which the docs usually name.
- **TLS fix:** `pip-system-certs` (the Avast-interception workaround noted in
  Phase 1) sends the OpenAI-compatible SDKs into infinite recursion during SSL
  setup, so every DeepSeek call died with `APIConnectionError`/`RecursionError`.
  Removing it made *all* Python HTTPS fail with `CERTIFICATE_VERIFY_FAILED`, so
  it was genuinely needed. Replaced with `truststore` (now a real dependency),
  injected at `llm/factory.py` import: it verifies against the OS trust store,
  fixes every provider, and doesn't recurse. Don't reintroduce
  `pip-system-certs`.
- **Structured output needed a provider-aware path.** Both DeepSeek models are
  "thinking" models and reject the forced `tool_choice` that LangChain's
  `with_structured_output` uses (`400 Thinking mode does not support this
  tool_choice`), for `function_calling` and `json_schema` alike. Plain
  `json_mode` returns valid JSON of the wrong shape, because it never shows the
  model the schema. New `llm/factory.py::get_structured_model(schema)` keeps
  that decision in the factory (per CLAUDE.md): default providers use
  `with_structured_output`, JSON-mode providers get `json_mode` plus the JSON
  schema appended as a system message. `agents/pm/extraction.py` and
  `agents/pm/planning.py` now call it instead of building the model themselves;
  their tests patch `get_structured_model`.
  Tool calling itself (Phase 3's loop) works on DeepSeek unchanged, as long as
  no tool_choice is forced.
- **Phase 4 eval: 4/4 on `deepseek-flash`.** The first run scored 1/4 purely on
  bad assertions of mine — the model wrote "twice out of three" rather than
  "2/3", and said "no missed target to explain" / "zero were achieved", which
  tripped blunt `must_not_mention` substrings. `must_mention` entries can now be
  a list of alternatives (any one counts), and the negative checks target real
  false claims ("goal achieved") rather than bare words. All four summaries were
  factually correct on both runs.

**Tests:** `pytest` 101/101 after the factory change.

**All PM-track evals re-run on `deepseek-flash` (2026-09-21):** Phase 1 backlog
**8/8**, Phase 2 planning **5/5**, Phase 4 review **4/4**, and the two Phase 3
cases that were outstanding **2/2** — including "existing project reuses
backlog tasks", which attached all three existing tasks to milestones without
duplicating any. Phase 3's other 3 cases remain verified on `gemini-3.6-flash`
only; rerun them on DeepSeek if provider-consistent coverage matters.

Cost note: the decomposition loop is chattier on DeepSeek than on Gemini —
5 steps / 14 calls for one breakdown, and 6 steps / 22 calls for a revision
turn, versus 3 steps / 4-5 calls on `gemini-3.6-flash`. Same quality of output,
but budget for it now that the provider bills per token rather than per day.
