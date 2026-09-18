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
- Alembic wired up (`alembic.ini`, `alembic/env.py`) — no migrations
  generated yet (`alembic/versions/` empty)
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

**Follow-ups:** No migration has been generated/applied yet — first schema
migration is needed before any tool implementation that touches the DB. See
`NOTES.md` for the stub-function tracking entry.

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
- `pyproject.toml` — added `streamlit`, `pyyaml` (declared only — see
  Follow-ups, `uv add` couldn't reach PyPI from this environment)
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
