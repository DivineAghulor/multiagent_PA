# Setup

Quick-start reference. For the full Postgres walkthrough (install, database
creation, troubleshooting) see [`docs/database-setup.md`](docs/database-setup.md).

## One-time manual steps (do once, before anything below)

These can't be scripted — do them together, then share credentials via the
team password manager:

- [ ] Install `uv` (see below).
- [ ] Install Postgres locally; confirm you and your pairing partner are on
      the same major version.
- [ ] Create the shared Neon (or Supabase) free-tier Postgres project (used
      for pairing sessions and eventually production).
- [ ] Create the Google Cloud project + OAuth consent screen + Calendar API
      credentials (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`).
- [ ] Create the shared LangSmith project.

### Install uv

`uv` bootstraps its own Python if needed — no separate Python install required.

**Windows (PowerShell):**
```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS / Linux:**
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Open a new terminal afterward and confirm with `uv --version`. See
https://docs.astral.sh/uv/getting-started/installation/ for other install
methods (`winget`, `brew`, `pipx`, etc.) if these don't fit your setup.

## Local environment

```
1. git clone <repo> && cd <repo>
2. cp .env.example .env        # fill in values from the shared password manager
3. uv sync                     # creates .venv and installs locked dependencies into it
4. createdb personal_assistant_dev   # local Postgres must already be running — see docs/database-setup.md
5. uv run alembic upgrade head # applies schema
6. uv run pytest               # confirms the environment works
```

## Notes

- `uv sync` creates `.venv` for you — no manual `python -m venv` step needed.
- `uv run <cmd>` runs a command inside `.venv` without activating it; that's
  the pattern used throughout this doc. If you'd rather activate the venv
  once per shell session instead, run `.venv\Scripts\Activate.ps1`
  (PowerShell) or `source .venv/bin/activate` (macOS/Linux), then drop the
  `uv run` prefix from the commands above.
- `uv sync` installs both runtime and dev dependencies (pytest, pytest-mock).
- `pytest` at this stage runs only the Phase 0 smoke test — it needs no live
  database connection or API keys.
- First time only: if `alembic/versions/` is still empty, generate the
  initial migration against your running local DB with
  `uv run alembic revision --autogenerate -m "init"`, then commit it before
  anyone else runs `uv run alembic upgrade head`.
- LangSmith tracing turns on via `LANGCHAIN_TRACING_V2=true` +
  `LANGSMITH_API_KEY` in `.env`.
