# CLAUDE.md

Instructions for Claude Code when working in this repository. This is a
two-person (Person A, Person B) project built in phases per
[`implementation-plan.md`](implementation-plan.md). Read that file for the
full plan and locked-in technical decisions before doing any nontrivial work.

## Required workflow for every implementation task

This project is built phase by phase, with a short design doc ("the
implementation plan for this phase") dropped into the repo or pasted by the
user before each phase of coding begins. Follow this sequence every time,
without skipping steps:

1. **Check [`NOTES.md`](NOTES.md) first.** It's short by design — read all of
   it. It may describe stubs, mocks, or known gaps in exactly the area you're
   about to touch. Treat anything relevant there as a constraint on your plan.
2. **Analyze the dropped implementation plan(s)** for this phase. If more than
   one doc is relevant (e.g. the top-level `implementation-plan.md` plus a
   phase-specific note), read all of them before forming a plan. Ask about any
   real ambiguity rather than guessing at intent for anything affecting
   schema, external APIs, or the human-confirmation flow.
3. **Write a todo plan before writing code.** Use the todo-list tool to break
   the phase into concrete steps (models/migrations touched, tools
   implemented, tests added, eval fixtures added). Do this even for
   small-looking phases — it's what makes the `progress.md` entry accurate
   afterward.
4. **Implement**, following the conventions below.
5. **Update [`progress.md`](progress.md)** with a new entry for the phase (see
   format below) once the phase's code is in a working, tested state.
6. **Update [`NOTES.md`](NOTES.md)** if the phase introduced, resolved, or
   changed anything in its scope (new stub, closed-out mock, discovered
   vulnerability, etc.) — see rules below. If nothing changed, leave it alone.
7. **Flag any required human action** (see "Human input required" below)
   explicitly in your final summary to the user — don't bury it.

Do not start writing implementation code for a phase before step 3's todo
plan exists and, for anything ambiguous, the user has confirmed direction.

## Project conventions

- **Package manager**: `uv` only. Don't use bare `pip`/`venv`. Add deps with
  `uv add <package>`, dev-only deps with `uv add --dev <package>`.
- **Schema changes**: SQLAlchemy models live in `db/models.py`. Any schema
  change requires an Alembic migration (`alembic revision --autogenerate -m
  "..."`) committed alongside the model change — never hand-edit the DB out
  of band. Follow existing patterns: `Base` + `TimestampMixin`, `str, enum.Enum`
  for Postgres enums, integer identity PKs.
- **Tool functions** (`tools/*.py`): typed signatures, one clear docstring
  line when behavior isn't obvious from the name, grouped by entity matching
  `db/models.py`. Stub functions raise `NotImplementedError` until
  implemented — see [`NOTES.md`](NOTES.md) rules on tracking these.
- **LLM access**: always through `llm/factory.py`'s `get_chat_model` /
  `get_default_chat_model`. Never import a provider SDK or hardcode a model
  name/provider directly in agent or tool code — provider selection is
  config-driven via `LLM_PROVIDER`/`LLM_MODEL` (`config.py`).
- **Config/secrets**: all settings go through `config.py`'s `Settings`
  (pydantic-settings). Add new variables there and to `.env.example` (name
  only, no real value) — never commit real secrets, and never print/log
  secret values. Real values are distributed via the shared password manager.
- **Testing**: pytest + mocks. Never hit a live LLM API, Google Calendar API,
  or Gmail in tests — mock the client/tool boundary. Unit tests belong next to
  the feature in `tests/`; when a phase's plan calls for it, also add fixtures
  to the relevant `evals/*.yaml` file (fixed prompt + expected output) rather
  than only ad hoc unit tests, since the eval set is shared between both devs.
- **Human-in-the-loop / confirmation flows**: any action that mutates a
  external system, or the calendar reschedule flow, must go through the
  proposed/confirm/reject pattern already modeled on `CalendarEvent`
  (`propose_reschedule` / `confirm_reschedule` / `reject_reschedule`,
  `awaiting_confirmation`). Don't silently auto-apply a change that this
  pattern is meant to gate.
- **Database**: local dev uses native Postgres (`personal_assistant_dev`), per
  [`docs/database-setup.md`](docs/database-setup.md). Never run migrations or
  destructive queries against the shared Neon/Supabase instance without
  explicit user confirmation for that specific action.
- **Orchestrator/agent code**: don't build the LangGraph supervisor/orchestrator
  or wire sub-agents together until both sub-agent tracks (PM, Calendar) are
  explicitly declared stable by the user — this is a joint-work milestone in
  `implementation-plan.md`, not something to start opportunistically.

## `progress.md` format

One entry per completed phase, appended in chronological order, most recent
last. Each entry:

```markdown
## Phase <N> — <phase name> (<YYYY-MM-DD>)

**Scope:** <one line — which track/phase from implementation-plan.md>

**Changed:**
- <files/modules touched, what they now do>

**Tests:** <what was added/run, pass/fail state>

**Follow-ups:** <anything deferred — link to NOTES.md if it belongs there>
```

Keep entries factual and short — this is a changelog, not a design doc. If a
phase spans multiple sessions, it's fine to append to the same entry rather
than creating a new one, as long as the phase itself is still open.

## `NOTES.md` — critical-notes discipline

`NOTES.md` is deliberately narrow-scope. It is **not** a general dev log
(that's `progress.md`) and **not** a design doc. Only add an entry if it is
one of:

- A known security vulnerability or weakness (including anything intentionally
  introduced for testing purposes, e.g. a debug bypass, hardcoded test
  credential, disabled auth check) that is not yet fixed.
- A "backdoor" or bypass added temporarily during development/testing that
  must be removed before anything resembling production use.
- An empty/mock/stub function or hardcoded fake response that other code now
  depends on (e.g. a `tools/*.py` function still raising `NotImplementedError`
  or returning canned data that a caller treats as real).
- A direct/unmediated access path to something that should eventually go
  through an abstraction but currently can't (e.g. code reaching past
  `llm/factory.py` or straight at an external API) because the abstraction
  isn't built yet.

Do not log routine TODOs, style preferences, or anything already obvious from
reading the code with fresh eyes (e.g. don't log "Phase 0 stubs raise
NotImplementedError" for every single stub — log it once, generically, and
remove the entry once the phase that implements them lands). Remove/close an
entry the moment its underlying issue is resolved — a stale `NOTES.md` is
worse than a missing one.

This file must be read in full at the start of every implementation task
(step 1 above) and reconsidered at the end of every task (step 6 above).

## Human input required

Flag these to the user explicitly whenever they're relevant to the current
task — do not attempt to do them yourself:

- **Creating external accounts/projects**: Neon/Supabase project, Google Cloud
  project + OAuth consent screen for Calendar API, LangSmith project.
- **Generating/rotating real secrets**: API keys, the Gmail app password,
  Google OAuth client secret — and distributing them via the shared password
  manager.
- **Completing an OAuth consent flow** (browser-based user consent for Google
  Calendar access) — this cannot be scripted.
- **Local Postgres setup on each machine**: installing Postgres, agreeing the
  major version matches between both devs, running `createdb
  personal_assistant_dev` locally.
- **Running migrations against the shared Neon/Supabase database**, since it
  affects both devs' pairing sessions — always confirm before doing this,
  even though local-DB migrations are routine.
- **Confirming/rejecting a proposed calendar reschedule** at runtime (the
  LangGraph interrupt pattern in Phase 4 of the Calendar track) — this is a
  product feature, not a dev-time step, but the agent must never auto-confirm
  on the human's behalf.
- **Declaring a sub-agent track "stable"** before orchestrator work starts —
  a judgment call reserved for the user(s), not something to infer from tests
  passing.
- **Deployment/scheduler mechanism decisions** — explicitly deferred in
  `implementation-plan.md`; don't make this choice unilaterally when it comes
  up.
- Any **destructive or hard-to-reverse action** in general (force-push,
  dropping tables, `git reset --hard`, etc.) per standard practice — confirm
  first regardless of phase.
