# Web app — requirements

Requirements for the web interface that replaces `app_test.py` as the real
front end to this personal-assistant system. Written before any web code
exists; the phased build plan is at the bottom. Read alongside
[`implementation-plan.md`](../implementation-plan.md) (system goal, locked-in
decisions) and [`NOTES.md`](../NOTES.md) (current stubs).

## 1. What the web app is for

The system's goal is a personal assistant that runs the loop *capture → plan →
decompose → do → review*, with an LLM doing the language work and the database
holding the truth. Four PM-track phases already implement that loop as library
code (`agents/pm/*`, `tools/*`). What is missing is an interface a person
actually uses daily: `app_test.py` is labelled a throwaway harness in its own
docstring, keeps multi-turn agent state in Streamlit session state, and calls
agent functions directly from widget callbacks.

The web app exists to:

1. Give the PM loop a usable daily home — backlog, weekly plan, project
   breakdown, week review.
2. Put a stable API boundary between the interface and the agents, so the same
   backend later serves the Calendar sub-agent, the orchestrator, and the
   daily/monthly email jobs without a second integration.
3. Close the data-entry gaps that only exist because the harness never needed
   them (no way to create a project or habit outside a decomposition, no way
   to edit or delete a task).

## 2. Locked-in decisions

| Area | Decision | Consequence |
|---|---|---|
| Users | **Single user, no auth** | No `User` table, no `user_id` columns, no login. The DB schema is unchanged. The app must never be exposed on a public URL as-is (see §9). |
| Stack | **FastAPI backend + React/Next frontend** | Python stays on the server with the agents; the frontend only speaks HTTP/SSE. |
| Scope | **PM track only** | Backlog, planning, decomposition, review. No calendar, no orchestrator, no email in v1. |
| Interaction | **Structured screens, each with its own chat** | Mirrors how the agents are actually built: one agent entry point per screen. No routing layer is needed, so nothing here is gated on the orchestrator milestone. |
| Draft durability | **Losing an unconfirmed draft on restart is acceptable** | The draft session store stays in-process for all of v1 (§5). No `drafts` table, no checkpointer. |
| Review history | **A `weekly_reviews` table is added now** | The week's narrative is persisted rather than displayed and thrown away, so the web app can show review history and the monthly email has data to read (§6.7). |
| Task priority | **`importance`/`urgency` is the rating system; `priority` is derived from it** | The Phase 1 duplication is closed by making the enum a computed projection of the pair, never set by a caller (§6.7). |
| Frontend | **Next.js (app router) + TypeScript + Tailwind, in this repo under `web/`** | Read screens are server components, so the browser never holds the API base URL and reads need no CORS. One repo keeps an API change and its consumer in a single diff. |
| Components | **Tailwind + shadcn-style primitives copied into `web/components/ui/`** | Owned in-repo rather than imported, so the rating widget, draft outline and week grid can be changed directly when W2–W4 need them. |

Unchanged project rules apply to the backend: `uv` only, all LLM access
through `llm/factory.py`, all settings through `config.py`, any schema change
paired with an Alembic migration, and confirmation flows never auto-applied.

## 3. Scope

**In scope (v1)**

- Backlog capture from freeform text, plus the importance/urgency rating step.
- Task list with filters, status changes, completion, edit and delete.
- Weekly planning conversation producing `WeeklyGoal` rows on confirmation.
- Project decomposition conversation producing milestones and tasks on
  confirmation.
- Current-week screen: per-goal progress, task ticking, per-day habit logging,
  generated week review, carry-over.
- Project and habit management (create, edit, archive/deactivate).
- Health/status endpoint and a visible indication when the LLM provider is
  misconfigured.

**Out of scope (v1), by dependency**

- Anything touching `tools/calendar.py` — every function there is still a stub
  (Person B's Phases 1–4).
- A single conversational surface routed by a supervisor — the orchestrator is
  a joint milestone gated on both tracks being declared stable.
- Email digests and any always-on scheduler — the scheduler mechanism is
  explicitly deferred in `implementation-plan.md`.
- Multi-user, sharing, mobile apps, offline mode.

## 4. Architecture

```
Next.js (React)  ──HTTP/JSON + SSE──▶  FastAPI  ──▶  agents/pm/*  ──▶  llm/factory
                                          │
                                          └──▶  tools/*  ──▶  db/session ──▶ Postgres
```

**A-1.** The frontend never imports Python and never talks to Postgres. Every
read and write goes through the API.

**A-2.** FastAPI route handlers contain no business logic and no model
prompts. A handler validates input, calls one function in `agents/pm/*` or
`tools/*`, and serialises the result. Anything a handler needs that doesn't
exist yet gets added to `agents/` or `tools/`, not to the web layer — the
email jobs and the future orchestrator call the same functions.

**A-3.** Pydantic response models live in a new `api/schemas.py` and are
distinct from `agents/pm/schemas.py` (which is LLM-facing). ORM objects are
never returned directly: `expire_on_commit=False` makes it tempting, but
lazy-loading a relationship outside a session is exactly the
`DetachedInstanceError` already recorded in `progress.md` Phase 4.

**A-4.** Suggested layout, consistent with existing top-level packages:

```
api/          main.py, deps.py, schemas.py, sessions.py,
              routers/{tasks,projects,habits,planning,decomposition,weeks}.py
web/          Next.js app (its own package.json; not managed by uv)
```

**A-5.** The backend is a single process serving one user. Concurrency
requirements are limited to: one browser, possibly two tabs, and one long
model call in flight per screen.

## 5. Conversational state — the hard part

Two of the four screens are multi-turn and hold state that is *not* in the
database until the user confirms:

- **Planning:** `history: list[tuple[str, str]]` plus a `WeeklyPlanProposal`
  and a `PlanningContext`. The history is plain tuples of strings — trivially
  serialisable.
- **Decomposition:** a `DecompositionDraft` dataclass (with a `_counter` that
  generates the `M1`/`T3` refs the model references by name) plus a LangChain
  `list[BaseMessage]` history that includes tool calls and tool results. Not
  trivially serialisable, and the refs must stay stable across turns or the
  model's next tool call breaks.

Streamlit kept both in `st.session_state`. HTTP has no equivalent, so:

**S-1.** The backend owns a **draft session store**: `create(kind, payload) →
session_id`, `get(session_id)`, `update`, `delete`, with a TTL and a cap on
live sessions.

**S-2.** v1 implementation is an in-process dict behind a `DraftStore`
protocol. Justified by the single-user, single-process decision, and it keeps
`DecompositionDraft` and `BaseMessage` as live objects with no serialisation
layer to get wrong.

**S-3.** The cost of S-2 is explicit and must be surfaced in the UI: **an
unconfirmed draft does not survive a backend restart.** The frontend shows a
clear "this draft was lost, start again" state on a 404 from a session
endpoint, rather than a generic error.

**S-4.** Draft loss on restart is accepted for the whole of v1 — persisting
drafts (a `drafts` table holding JSON, or a LangGraph checkpointer) is a v2
question and no v1 phase should quietly take it on. S-3's in-memory store is
still a `NOTES.md` entry when it lands, since it is in-memory state other code
depends on; the entry is removed if a persistent store ever replaces it.

**S-5.** Session IDs are opaque UUIDs. A session is deleted on confirm, on
explicit cancel, and on TTL expiry.

**S-6.** Model output is never trusted to reference real rows.
`sanitize_proposal` already drops hallucinated project/habit/task IDs and
returns warnings; the API must call it on every planning turn and return those
warnings to the client, which displays them. The decomposition draft tools
apply the same discipline by returning `"Error: ..."` strings to the model
instead of raising.

## 6. Functional requirements

### 6.1 Backlog

- **FR-1.** Capture: user submits freeform text; the API calls
  `capture_backlog_from_text` and returns the created `Task` rows. One model
  call. Multi-action sentences split into separate tasks (already covered by
  `evals/pm_backlog.yaml`).
- **FR-2.** After a capture, the newly created tasks are presented for
  importance/urgency rating (1–4 each, via `update_task_priority`). Rating is
  skippable, per task; skipped tasks stay unrated and drop out of the queue.
- **FR-3.** Task list with filters on status, project and milestone; sorting
  at minimum by created date and by importance/urgency. Importance/urgency is
  the rating the UI sorts, filters and groups on — the derived `priority` enum
  (§6.7) is display shorthand only, never an independent input.
- **FR-4.** Per-task actions: complete, reopen, change status, edit
  (title/description/due date/project/milestone), delete. Delete asks for
  confirmation.
- **FR-5.** Capture failures (provider error, malformed output) create
  nothing and surface the error text. No partial writes.

### 6.2 Weekly planning

- **FR-6.** Opening the screen creates a planning session for
  `planning_week_start(today)` — **next** week's Monday — and shows the
  rendered planning context (backlog, active projects, habits) the model will
  see. The target week is selectable.
- **FR-7.** Each user message runs one `propose_weekly_plan` turn and returns
  the reply, the full sanitised proposal, and any sanitisation warnings. The
  proposal always represents the whole plan as of that turn, not a delta.
- **FR-8.** The proposal is rendered as structured goals (description, linked
  project/habit, target count, linked tasks) — not only as the model's prose.
- **FR-9.** Confirming calls `confirm_weekly_plan`, writes the `WeeklyGoal`
  rows, links tasks, ends the session, and navigates to the week screen.
  Nothing is written before confirmation.
- **FR-10.** A goal may target a project or a habit, never both; the API
  rejects violations rather than relying on the model to obey.

### 6.3 Project decomposition

- **FR-11.** Start a draft for a new project (name + description) or an
  existing one (`start_existing_project_draft` pre-loads its milestones and
  attachable backlog tasks).
- **FR-12.** Each turn runs `run_decomposition_turn` and returns the reply,
  the current draft tree, and the turn's `steps` / `tool_calls` / `hit_limit`.
  `hit_limit` is shown as a distinct state, not as a normal reply.
- **FR-13.** The draft tree is rendered as a milestone/task outline, marking
  which milestones and tasks already exist in the DB versus which are new.
- **FR-14.** Confirming calls `confirm_decomposition`. Its two guard errors —
  "the draft adds nothing" and "new milestone(s) without tasks" — are shown as
  actionable messages, since both are fixable by another turn.
- **FR-15.** The decomposition loop is the expensive screen (measured at 14
  model calls for a first breakdown and 22 for a revision turn on
  `deepseek-flash`). The UI shows live progress during a turn (see NFR-2) and
  the turn's call count afterwards.

### 6.4 This week / review

- **FR-16.** Week screen for `current_week_start(today)` — **this** week's
  Monday — with navigation to past weeks. Per goal: headline progress
  (`3/4 tasks done`), its tasks with tick boxes, and for habit goals seven day
  boxes with future days disabled.
- **FR-17.** Ticking completes a task (`complete_task`) or logs a habit
  (`log_habit_completion`, idempotent); unticking reopens or removes the log.
  No model calls anywhere in this flow.
- **FR-18.** Unplanned completions (tasks finished in the week but linked to
  no goal) are listed separately.
- **FR-19.** "Generate review" builds the facts deterministically
  (`build_week_review`), then makes one model call for the prose
  (`summarize_week`). Facts are viewable without generating prose. A provider
  error saves nothing.
- **FR-20.** Saving a review writes per-goal notes, ACHIEVED/MISSED status and
  `reviewed_at` (`save_review`); re-running a week's review overwrites its own
  output and is safe to repeat.
- **FR-21.** Missed goals can be carried into a chosen later week
  (`carry_over_weekly_goal`), one at a time or in a batch, only on explicit
  user action.
- **FR-22.** Saving a review also persists the narrative summary to
  `weekly_reviews` (§6.7), one row per week, overwritten on re-run. The week
  screen shows the stored summary when one exists, with its generation
  timestamp, and offers to regenerate.
- **FR-22a.** Past weeks are browsable as review history: each week with a
  stored summary shows that summary alongside the numbers it was written
  against, not recomputed numbers (see §6.7 on why the counts are snapshotted).

### 6.5 Projects and habits

- **FR-23.** Project list and detail (milestones, tasks, status, target date);
  create, edit, archive.
- **FR-24.** Habit list; create, edit (frequency, `target_per_period`),
  deactivate. **This has no equivalent in the harness at all** — habits can
  currently only be created through direct tool calls or the seed script, yet
  weekly planning and review both depend on them existing.
- **FR-25.** Milestone list per project with status updates.

### 6.6 Stubs this requires

These `tools/*.py` functions still raise `NotImplementedError` and are
prerequisites, not follow-ups: `update_task`, `delete_task`, `schedule_task`,
`update_project`, `archive_project`, `deactivate_habit`. `tools/habits.py`
also has no `update_habit`, which FR-24 needs. Each lands with its endpoint.

### 6.7 Schema changes this requires

Two changes, one Alembic migration, both landing before W1 rather than inside
it. Neither is optional for the web app, and both close questions that have
been open since earlier phases.

**`weekly_reviews` — new table.** One row per reviewed week.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | identity, per convention |
| `week_start` | date, **unique**, indexed | Monday; matches `WeeklyGoal.week_start` |
| `summary` | text, not null | the model's narrative from `summarize_week` |
| `achieved_count` | integer, not null | snapshot at generation time |
| `measurable_count` | integer, not null | snapshot at generation time |
| `unplanned_count` | integer, not null | snapshot at generation time |
| `generated_at` | timestamptz, not null | when the prose was produced |
| `created_at` / `updated_at` | timestamptz | `TimestampMixin` |

- **SCH-1.** Writing a review for a week that already has one overwrites it
  (upsert on `week_start`), matching `record_weekly_review`'s existing
  re-runnable behaviour. There is no review version history in v1.
- **SCH-2.** The counts are **snapshotted, not recomputed on read.** A task
  completed after the review was written would change a recomputed count and
  leave the stored prose contradicting the numbers beside it. Storing them
  keeps the narrative and its evidence consistent; the live week screen still
  shows current numbers from `build_week_review`.
- **SCH-3.** The summary is written only as part of an explicit save
  (`save_review`), never as a side effect of generating prose for display. A
  provider error still saves nothing.
- **SCH-4.** This is the table the monthly email report will read. It is added
  now for the web app's history view, which also settles the Phase 4 follow-up
  rather than deferring it again.

**`Task.priority` — becomes derived.** The column and the `task_priority` enum
stay; what changes is that nothing sets them directly.

- **SCH-5.** `derive_priority(importance, urgency) -> TaskPriority` is a pure
  function, the single place the mapping lives:

  | | urgency 1–2 | urgency 3–4 |
  |---|---|---|
  | **importance 3–4** | `HIGH` | `URGENT` |
  | **importance 1–2** | `LOW` | `MEDIUM` |

  Either value unset → `MEDIUM`, the existing column default. That does mean
  `MEDIUM` covers both "unrated" and "urgent but not important"; the pair
  itself distinguishes them, and nothing may treat `priority` as sufficient to
  tell those apart.
- **SCH-6.** The derived value is recomputed and stored on every write that
  touches `importance` or `urgency` (`create_task`, `update_task_priority`,
  `update_task`). Storing it rather than computing it on read keeps SQL
  sorting and filtering available.
- **SCH-7.** `priority` is removed from the signatures of `create_task` and
  the `update_task` stub — no caller passes it today, so this breaks nothing.
  A caller that wants a different priority changes the pair.
- **SCH-8.** The migration backfills `priority` for existing rows from their
  pair, so no row is left with a stale hand-set value.
- **SCH-9.** This is cross-track. `progress.md` Phase 1 names the Calendar
  track's Phase 3 priority engine as the intended consumer of whichever field
  survived. It now has both: the pair as the real signal, and a single enum
  when a coarse bucket is enough. Person B should be told before building it.

## 7. API surface

JSON over HTTP; SSE for the two conversational endpoints. Dates are ISO
`YYYY-MM-DD`; timestamps are ISO 8601 with offset.

As built (W1–W4). The OpenAPI document at `/docs` is the exhaustive reference.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | DB reachable, provider/model configured. Reports `bool(key)`, never a key or a slice of one. |
| GET | `/api/tasks` · `/api/tasks/{id}` | filters: `status`, `project_id`, `milestone_id`, `weekly_goal_id` |
| POST | `/api/backlog/capture` | `{text}` → created tasks, unrated. **Model call.** |
| PATCH | `/api/tasks/{id}` | title/description/due date/project/milestone; omitted = unchanged, `null` = clear |
| PATCH | `/api/tasks/{id}/priority` | `{importance, urgency}`, 1–4 each |
| PUT | `/api/tasks/{id}/status` | any status; `completed_at` kept consistent |
| POST | `/api/tasks/{id}/complete` · `/reopen` | |
| PUT | `/api/tasks/{id}/schedule` | `{scheduled_for}`, `null` unschedules |
| DELETE | `/api/tasks/{id}` | |
| GET | `/api/planning/context` | `?week_start=` |
| POST | `/api/planning/sessions` | `{week_start?}` → the whole session |
| GET | `/api/planning/sessions/{id}` | the whole session: context, messages, proposal, warnings |
| POST | `/api/planning/sessions/{id}/messages` | `{text}` → the whole session. **Model call.** Plain JSON, not SSE: one call, a pending state is enough (NFR-2) |
| POST | `/api/planning/sessions/{id}/confirm` | `{goals?: [{index, description, target_count}]}` → created goals; ends session |
| DELETE | `/api/planning/sessions/{id}` | cancel |
| POST | `/api/decomposition/sessions` | `{project_id}` or `{name, description}` |
| GET | `/api/decomposition/sessions/{id}` | draft, messages, `last_turn` |
| POST | `/api/decomposition/sessions/{id}/messages` | `{text, exclude_*_refs}`; **SSE, many model calls**: `progress` events, then `result` (the whole session) or `error` |
| POST | `/api/decomposition/sessions/{id}/confirm` | `{exclude_milestone_refs, exclude_task_refs}` → project, milestones, new tasks |
| DELETE | `/api/decomposition/sessions/{id}` | cancel |
| GET | `/api/weeks/current` · `/api/weeks/{week_start}` | goals + progress facts + stored summary if any, no model call |
| POST | `/api/weeks/{week_start}/review/draft` | → `{summary}`. **Model call.** Writes nothing |
| POST | `/api/weeks/{week_start}/review` | `{summary?}` → the week. Saves verdicts and notes, and the prose when given; no model call. Split from drafting so what's stored is exactly what the user read |
| GET | `/api/reviews` | stored week summaries, newest first (history view) |
| POST | `/api/weekly-goals/{id}/carry-over` | `{new_week_start}` |
| GET/POST | `/api/projects` · `/api/habits` | list, create |
| PATCH | `/api/projects/{id}` · `/api/habits/{id}` | edit (incl. restoring status / `active`) |
| POST | `/api/projects/{id}/archive` · `/api/habits/{id}/deactivate` | |
| PATCH | `/api/milestones/{id}` | status (FR-25), name, description, due date |
| POST · DELETE | `/api/habits/{id}/logs` · `/api/habits/{id}/logs/{date}` | tick `{date}` (future days rejected) · untick |

**API-1.** Every endpoint that triggers a model call is documented as such and
returns a typed error (provider unreachable, quota, malformed output) the
frontend can distinguish from a validation error.

**API-2.** Confirmation endpoints are the only ones that write agent-proposed
data. `GET`s never mutate.

**API-3.** "Today" comes from `agents/pm/review.py::today()` on the server, not
from the browser clock, so the UI and tests agree on dates.

## 8. Non-functional requirements

- **NFR-1.** Model calls block for seconds to minutes. Every such request is
  async on the server and non-blocking in the UI, with a cancel affordance.
- **NFR-2.** Decomposition turns stream progress. `run_decomposition_turn`
  currently returns only when the loop finishes; it gains an optional progress
  callback (invoked per model step and per tool call) rather than the web layer
  reimplementing the loop. Planning and review may stream tokens or simply show
  a pending state.
- **NFR-3.** Cost is visible. Per-turn call counts are returned by the API and
  shown in the UI, because the provider bills per token and the decomposition
  loop is chatty.
- **NFR-4.** No partial writes on model failure, on every screen. Already true
  of the underlying functions; the API must not weaken it.
- **NFR-5.** LangSmith tracing stays on and covers calls made through the API.
- **NFR-6.** The app is usable on a laptop browser; mobile layout is
  nice-to-have, not a requirement.
- **NFR-7.** Configuration comes from `config.py` only. No new secret reading
  in the web layer, no secrets in frontend bundles or client-visible responses.
- **NFR-8.** A misconfigured or unreachable provider degrades cleanly: the
  non-model screens (task list, week screen, ticking, habit logging, project
  and habit CRUD) keep working.

## 9. Security

No authentication is a deliberate v1 decision, so the boundary is deployment,
not code:

- **SEC-1.** The backend binds to localhost by default. Any non-local
  deployment requires a decision recorded in `implementation-plan.md` first —
  an unauthenticated instance on a public URL exposes the whole DB and burns
  the shared provider key by request.
- **SEC-2.** CORS allows only the configured frontend origin.
- **SEC-3.** No secret value is ever returned by an endpoint, rendered in the
  UI, or logged — including partial values (see the resolved `NOTES.md` entry
  about logging key slices).
- **SEC-4.** All input is validated by Pydantic at the boundary; DB access
  stays parameterised through SQLAlchemy.
- **SEC-5.** Adding auth later is a schema change (a `User` table plus a
  `user_id` FK on every model and scoping on every query), not a middleware
  drop-in. Nothing in v1 should assume otherwise or make it harder — keep
  queries funnelled through `tools/*`.

## 10. Testing

- **T-1.** API tests use FastAPI's `TestClient` against a test database, with
  `agents/pm/*` entry points mocked. No live LLM, Calendar or Gmail call in any
  test — unchanged rule.
- **T-2.** The draft session store has its own unit tests: TTL expiry, cap,
  404 on a missing session, and ref stability across turns for a decomposition
  draft.
- **T-3.** Existing PM tests (101 passing) must keep passing untouched. If the
  web layer needs a change in `agents/` or `tools/`, that change comes with its
  own tests.
- **T-4.** The `evals/*.yaml` sets remain the quality gate for model behaviour.
  The web app adds no eval fixtures — it changes no prompts.
- **T-5.** Frontend: component tests for the rating flow, the proposal
  renderer, the draft outline and the week grid; one end-to-end smoke test
  against a seeded DB with the model mocked at the API layer. *The component
  tests exist (`npm test`); the browser end-to-end test does not yet.*
- **T-6.** `app_test.py` and `tests/test_app_ui.py` stay until the web app
  reaches parity on all four screens, then both are deleted in one commit.
  Streamlit leaves `pyproject.toml` at that point. *Done in W4.*

## 11. Suggested phasing

Each phase ends in a working, tested state and gets a `progress.md` entry.

- **W0 — Schema.** The two changes in §6.7 (`weekly_reviews`,
  `derive_priority`) with one Alembic migration, wired into `save_review` and
  the task write paths. No web code. Done before W1 so the API is built
  against the final shape.
- **W1 — Backend skeleton + read-only data.** FastAPI app, `api/schemas.py`,
  health check, task/project/habit/week reads. Next.js shell with the four
  screens rendering real data. No model calls yet.
- **W2 — Backlog + CRUD.** Capture, rating flow, task edit/delete, project and
  habit management. Implements the stubs in §6.6. First model calls.
- **W3 — Planning.** Draft session store, planning session endpoints,
  confirmation, sanitisation warnings in the UI.
- **W4 — Decomposition + review.** The progress callback in
  `run_decomposition_turn`, SSE streaming, draft outline UI, week screen
  ticking, review generation and carry-over. Parity reached; retire
  `app_test.py`.

## 12. Open questions

None open. Closed:

- **Ownership** (2026-09-22): the web app is Person A's, for demo purposes, as
  its own track on branch `pa-web-app`. Person B doesn't review it for now.
- **Provider budget** (2026-09-22): the web app uses whatever
  `LLM_PROVIDER`/`LLM_MODEL` is configured, with no per-turn call cap (a cap
  would cost quality); spend is capped on the provider's dashboard.
- Earlier, recorded in §2: draft loss on restart is acceptable for v1 (§5),
  `weekly_reviews` is added now (§6.7), importance/urgency is the rating
  system with `priority` derived from it (§6.7), and the frontend is Next.js
  app router plus Tailwind in this repo.

## 13. Human input required

Settled 2026-09-22: Node 22 is the agreed toolchain; the PM track is declared
stable; Person B has been told about SCH-5/SCH-9; ownership and budget (§12).

Still open:

- **Railway deployment** is the chosen target after the web app. Before the
  API gets a public URL, SEC-1 needs an answer — auth, or a private network or
  access gate in front of it (NOTES.md). The API must also run as one process
  and one replica while drafts are in memory (§5, NOTES.md).
- **The scheduler mechanism** for the email jobs is still deferred in
  `implementation-plan.md`; Railway may answer it, but it's a separate call.
- **Running the migrations against the shared Neon/Supabase DB** (or a Railway
  Postgres) when that instance comes into use — local is routine, shared is
  not, and each run needs its own confirmation.
