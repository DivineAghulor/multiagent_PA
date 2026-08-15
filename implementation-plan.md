# Personal assistant — implementation plan

## Locked-in decisions

| Area | Decision |
|---|---|
| Database (local) | Postgres installed natively by both (no Docker) — align on the same major version and a shared local DB name/role convention |
| Database (shared/integration) | Neon (or Supabase) free-tier Postgres, used for pairing sessions and eventually production |
| Migrations | Alembic from the first schema commit |
| LLM provider | Abstracted via LangChain's `BaseChatModel` — Anthropic, Gemini, OpenAI, Grok (`langchain-xai`) selectable by config, never hardcoded in agent code |
| API keys | Shared, distributed via a password manager, never committed |
| Email | Gmail + app password |
| Deployment | Not immediate, but planned — revisit the deployment mechanism (containerized or not) once closer; not a local dev concern for now |
| Package manager | `uv` |
| Observability | Shared LangSmith project from day one |
| Testing | pytest + mocks locally; shared eval set (fixed prompts + expected outputs) run by both; live pairing sessions for integration |

---

## Phase 0 — Bootstrap (do together, one sitting)

This phase is joint because it's the contract everything else builds against. Target deliverables:

1. **Repo skeleton** — `agents/`, `tools/`, `db/`, `tests/`, `evals/`
2. **Local Postgres alignment** — confirm both of you are on the same major Postgres version, agree on a DB name/role convention (e.g. `personal_assistant_dev`), and each create that local database
3. **`.env.example`** — every variable name needed (DB URL, `ANTHROPIC_API_KEY`, `LLM_PROVIDER`, `GOOGLE_CLIENT_ID`/`SECRET`, `GMAIL_APP_PASSWORD`, `LANGSMITH_API_KEY`), no real values
4. **`SETUP.md`** — the initialization guide, kept up to date as the source of truth:
   ```
   1. git clone <repo> && cd <repo>
   2. cp .env.example .env        # fill in values from shared password manager
   3. uv sync                     # installs locked dependencies
   4. createdb personal_assistant_dev   # local Postgres must already be running
   5. alembic upgrade head        # applies schema
   6. pytest                      # confirms the environment works
   ```
5. **Schema + tool signatures** — `db/models.py` (Task, Project, Milestone, Habit, WeeklyGoal, CalendarEvent as SQLAlchemy models) and `tools/` with typed, empty-bodied CRUD functions (`create_task()`, `get_backlog()`, `schedule_event()`, etc.) that both sub-agents will import
6. **LLM factory** — `llm/factory.py`: `get_chat_model(provider: str, model: str) -> BaseChatModel`, config-driven via `LLM_PROVIDER`/`LLM_MODEL`
7. **Accounts** — create the Neon/Supabase project, the Google Cloud project + OAuth consent screen for Calendar API, and the LangSmith project; share credentials once

Once this merges to `main`, split.

---

## Person A — Project management sub-agent

Depends only on the Phase 0 schema/tools — build against them directly, no stubs needed since they're first.

**Phase 1: Backlog capture**
- NL parser tool: freeform text → one or more `Task` rows
- Unit tests with mocked LLM responses
- Add fixtures to the shared eval set (`evals/pm_backlog.yaml`)

**Phase 2: Weekly planning**
- Chat loop reading current backlog, capturing target progress per project/habit → `WeeklyGoal` rows
- Test with the eval set: does it produce sane goals from a known backlog?

**Phase 3: Decomposition**
- Project → milestone → task breakdown as an iterative tool-calling loop (not single-shot)
- This is the highest-risk-of-bad-output phase — lean on the eval set here especially

**Phase 4: Weekly review**
- Compares `WeeklyGoal` targets to actual completions, generates a written summary
- Can run as a manually-triggered script before it's wired to a scheduler

---

## Person B — Calendar & tasks sub-agent

Also builds directly against Phase 0's tools. Google Calendar work can start with a personal test calendar before the shared OAuth app is fully configured.

**Phase 1: Calendar integration**
- Wrap Google Calendar API (read/write/delete/reschedule) as LangChain tools
- Mock the API in unit tests — never hit live Calendar in CI

**Phase 2: NL event creation**
- "Dinner at 5pm" → `CalendarEvent`
- Add to eval set (`evals/calendar_nl.yaml`)

**Phase 3: Priority engine**
- Deterministic (not LLM-driven) logic: importance/urgency pair + current calendar state → schedule now vs. leave in backlog
- Pure function, easiest thing in the whole project to unit test exhaustively — do so

**Phase 4: Reschedule + confirmation**
- LangGraph interrupt: agent proposes a move, execution pauses, waits for human confirmation, resumes
- This is the piece worth a joint session even before full integration testing, since the interrupt pattern here sets the precedent for anything else that needs confirmation later

---

## Joint work (after both tracks reach a stable point)

**Orchestrator**
- Supervisor node routing between sub-agents, shared conversation state
- Build once both sub-agents expose stable tool interfaces — not before

**Integration testing sessions**
- Run against the shared Neon/Supabase instance, seeded with known data before each session
- Screen-share, not async — walk through end-to-end scenarios: add a task → appears in backlog → gets scheduled → reschedule triggers confirmation → calendar updates
- Pull up LangSmith traces together when something misbehaves

**Email sub-agent**
- Lightweight enough to go to whoever finishes their track first; natural fit for Person A given the monthly report extends PM's completion tracking
- Daily job: query today's tasks/events, send via Gmail
- Monthly job: pull a month of completion data, generate the "what went well / what to improve" analysis — this is the one place a longer, more reflective prompt is worth it
- Trigger manually (CLI command) during development; decide the always-on scheduler mechanism only once you're closer to deployment

---

## Suggested cadence

- Daily/every-other-day: 10-minute async check-in (schema changes, blockers, tool signature changes)
- Weekly: joint session — early on for Phase 0 follow-ups, later for orchestrator work and integration testing
- Before deployment: revisit the scheduler question (where the daily/monthly jobs actually run) — not a blocker for building, but don't leave it until the last week either
