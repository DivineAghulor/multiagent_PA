# Critical notes

Narrow-scope, high-signal only: known security issues, intentional
dev/test-time bypasses ("backdoors"), stub/mock functions other code depends
on, and unavoidable direct-access paths that skip an abstraction. See
`CLAUDE.md` for exactly what belongs here and the required
read-at-start/update-at-end workflow. Remove an entry the moment it's
resolved — this file should stay short.

---

## Open

### The web API has no authentication at all

- **What:** Every endpoint under `api/` is unauthenticated and unscoped. Any
  request that reaches the process can read and write the whole database,
  delete tasks, and spend the provider key (capture, planning, decomposition
  and review all make model calls — a decomposition turn is many). This is a
  deliberate v1 decision (single user, no `User` table —
  `docs/webapp-requirements.md` §2), not an oversight, but it means the only
  thing protecting the data is where the process is listening.
- **Why it's here:** The mitigation is configuration, so it can be undone
  silently. `API_HOST` defaults to `127.0.0.1` and CORS admits only
  `WEB_ORIGIN`; changing either in a `.env`, or putting a tunnel or reverse
  proxy in front of it, exposes everything with no code change and no warning.
  Anyone deploying this anywhere but their own machine must read SEC-1 first.
  **This becomes live with the planned Railway deployment** (decided
  2026-09-22): a Railway service gets a public URL by default, so auth, or at
  minimum a private network / access gate in front of the API, has to land
  before or with that deploy.
- **Resolve when:** Authentication exists, or the app is retired. Note that
  adding it is a schema change (a `User` table plus a `user_id` FK on every
  model and scoping in every `tools/*` query), not a middleware drop-in.

### `tools/calendar.py` is still all stubs

- **What:** Every function in `tools/calendar.py` raises
  `NotImplementedError` (Calendar track, Person B). The PM-side modules
  (`tasks`, `projects`, `milestones`, `weekly_goals`, `habits`) are now fully
  implemented — web track W2 filled in the last of them. No implemented code
  path calls a calendar stub, so this isn't masking a bug today; anything that
  imports one early fails loudly by design.
- **Why it's here:** The web app and any orchestrator work must not assume
  calendar functions exist because every other `tools/` module is complete.
- **Resolve when:** The Calendar track implements them (see its entries in
  `progress.md`).

### Unconfirmed drafts live only in the API process's memory

- **What:** Planning conversations and decomposition drafts are held in
  `api/sessions.py`'s `InMemoryDraftStore`, a dict inside the FastAPI process.
  The planning and decomposition endpoints depend on it. A restart or
  redeploy, running more than one worker/replica, 12 hours idle, or the
  20-session cap each lose drafts; the client then gets `session_expired` and
  the UI says "this draft was lost, start again" (requirements §5 S-3).
- **Why it's here:** Accepted for all of v1 (S-4), but it is in-memory state
  other code depends on, and it constrains deployment: on Railway the API must
  run as a **single process with one replica**, or drafts will randomly 404
  depending on which instance a request lands on. Every redeploy drops every
  open draft.
- **Resolve when:** A persistent `DraftStore` (a `drafts` table or a LangGraph
  checkpointer) replaces it — a v2 decision, not to be taken on quietly.

---

## Resolved

### `llm/factory.py` printed partial API keys on every model call

Fixed 2026-09-18. Debug `print`s added while diagnosing provider routing
(committed in `c6aeebe`) wrote the key's first 6 + last 4 characters to
stdout, which lands in terminal scrollback and the Streamlit server log.
10 of 39 characters doesn't make the key usable, but it shouldn't be
logged at all. Replaced with presence-only `logging.debug`. The key value
itself was never committed. Rule for future debugging: log `bool(key)`,
never slices of it.

### ~~No Alembic migration generated yet~~

Turned out to be a false alarm caused by a truncated directory listing, not
an actual gap: `alembic/versions/89e2870d539b_init.py` (the real, complete
Phase 0 schema migration) was already committed in `c7b9d18` — it just
wasn't visible in an early broad repo scan. The local dev DB was already
correctly migrated and stamped at that revision; there was no drift. Phase 1
added `fc024d63765f_add_task_importance_urgency.py` on top of it normally.
Noted here as a reminder: don't trust a truncated file listing over `git
ls-files`/`git log` when judging whether something exists in the repo.

### `app_test.py`'s widget flow was unverified

(The harness itself was retired in web track W4, once the web app reached
parity.)

Resolved: driven end-to-end through Streamlit's `AppTest` harness against the
real model + real local Postgres (chat submit -> 2 tasks captured -> rating
dialog -> save -> task drops out of the dialog, values persisted), and now
covered permanently by `tests/test_app_ui.py` with `extract_tasks` mocked.
Only the visual browser rendering itself has never been eyeballed.

### Extraction was unverified against a real model

Resolved once a real `GOOGLE_API_KEY` was configured: `evals/run_pm_backlog.py`
now passes 3/3 against `gemini-2.5-flash`, and a direct end-to-end run of
`capture_backlog_from_text` correctly split a multi-action sentence into
separate `Task` rows in the real local Postgres DB.

### `config.py` loaded `.env` relative to the CWD

Fixed in Phase 1 (see `progress.md`). `env_file=".env"` resolved against the
current working directory, so launching from anywhere but the repo root
silently loaded no config at all and fell back to field defaults — presenting
as an Anthropic auth failure even with `LLM_PROVIDER=google_genai` correctly
set in `.env`. Now anchored to `config.py`'s own path. Worth remembering as a
failure signature: *"wrong provider / missing key despite `.env` being
correct"* usually means `.env` wasn't found at all.

### `llm/factory.py` never forwarded API keys to provider SDKs

Fixed in Phase 1 (see `progress.md`). `get_chat_model` built each LangChain
client with no `api_key`, relying on the SDK's own `os.environ` lookup —
which never saw `.env` values, since `pydantic-settings` loads those into
`config.settings` only, not the process environment. Affected all four
providers, not just the one in use. Now passes the resolved key explicitly
per provider.
