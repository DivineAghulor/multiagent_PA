# Setup

Quick-start reference. For the full Postgres walkthrough (install, database
creation, troubleshooting) see [`docs/database-setup.md`](docs/database-setup.md).

## One-time manual steps (do once, before anything below)

These can't be scripted — do them together, then share credentials via the
team password manager:

- [ ] Install Postgres locally; confirm you and your pairing partner are on
      the same major version.
- [ ] Create the shared Neon (or Supabase) free-tier Postgres project (used
      for pairing sessions and eventually production).
- [ ] Create the Google Cloud project + OAuth consent screen + Calendar API
      credentials (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`).
- [ ] Create the shared LangSmith project.

## Local environment

```
1. git clone <repo> && cd <repo>
2. cp .env.example .env        # fill in values from the shared password manager
3. uv sync                     # installs locked dependencies into .venv
4. createdb personal_assistant_dev   # local Postgres must already be running — see docs/database-setup.md
5. alembic upgrade head        # applies schema
6. pytest                      # confirms the environment works
```

## Notes

- `uv sync` installs both runtime and dev dependencies (pytest, pytest-mock).
- `pytest` at this stage runs only the Phase 0 smoke test — it needs no live
  database connection or API keys.
- First time only: if `alembic/versions/` is still empty, generate the
  initial migration against your running local DB with
  `alembic revision --autogenerate -m "init"`, then commit it before anyone
  else runs `alembic upgrade head`.
- LangSmith tracing turns on via `LANGCHAIN_TRACING_V2=true` +
  `LANGSMITH_API_KEY` in `.env`.
