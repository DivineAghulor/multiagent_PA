# Database setup (deep dive)

Companion to [`SETUP.md`](../SETUP.md)'s quick-start. Covers installing
Postgres locally, creating the shared database convention, wiring
`DATABASE_URL`, and troubleshooting.

## Why native Postgres, not Docker

Both devs run Postgres directly on their machine (see `implementation-plan.md`
locked-in decisions) — simpler for two people pairing without needing to
sync container state, and closer to how a lightweight personal-assistant app
would actually run.

## 1. Install Postgres

Agree on a major version first (e.g. 16) — pick whichever is current stable
when you do this, but both machines MUST match.

### Windows
- Installer: https://www.postgresql.org/download/windows/ (EDB installer)
- or `winget install PostgreSQL.PostgreSQL`
- During install you'll set a password for the `postgres` superuser — this
  is the `DATABASE_URL` password in step 4 below. Note the port (default
  `5432`).
- Add `<install-dir>\bin` to PATH if `psql`/`createdb` aren't found in a new
  terminal (see Troubleshooting).

### macOS
```
brew install postgresql@16
brew services start postgresql@16
```

### Linux (Debian/Ubuntu)
```
sudo apt update && sudo apt install postgresql postgresql-contrib
sudo systemctl enable --now postgresql
```

### Linux (Fedora)
```
sudo dnf install postgresql-server postgresql-contrib
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql
```

## 2. Verify the server is running

```
pg_isready
```
On Windows, you can also check the "postgresql-x64-16" service in
`Services.msc`.

## 3. Create the database

This project's convention is to use the default `postgres` superuser role
locally (no separate app role) and a database named `personal_assistant_dev`:

```
createdb personal_assistant_dev
```

If `createdb` prompts for a password, use the one you set for the `postgres`
role during install (on Linux, you may need `sudo -u postgres createdb personal_assistant_dev`
instead, since the OS `postgres` user owns the default peer-auth connection).

## 4. Set `DATABASE_URL` in `.env`

```
DATABASE_URL=postgresql+psycopg://postgres:<your-postgres-password>@localhost:5432/personal_assistant_dev
```

Note the `+psycopg` — this project uses psycopg3, not psycopg2; without the
`+psycopg` suffix SQLAlchemy may try to load psycopg2 and fail if it isn't
installed.

## 5. Apply the schema

```
alembic upgrade head
```

If `alembic/versions/` is empty (very first run ever, before anyone has
generated a migration), run:

```
alembic revision --autogenerate -m "init"
alembic upgrade head
```

and commit the generated migration file so everyone else can just run
`alembic upgrade head`.

## 6. Troubleshooting

- **`createdb: command not found`** (Windows): the `bin/` directory of your
  Postgres install isn't on PATH. Add it, open a new terminal, or use the
  full path (`"C:\Program Files\PostgreSQL\16\bin\createdb.exe"`).
- **Port 5432 already in use**: another Postgres instance (or WSL) is bound
  to it. `pg_isready -p 5432` to check, or run the new instance on a
  different port and update `DATABASE_URL` accordingly.
- **`password authentication failed for user "postgres"`**: check
  `pg_hba.conf`'s auth method for local connections (`scram-sha-256`/`md5`
  vs `trust`), or reset the password:
  `ALTER ROLE postgres WITH PASSWORD '...';` (run via `psql` as an admin).
- **`FATAL: database "personal_assistant_dev" does not exist`**: you skipped
  step 3, or ran `createdb` before the server finished starting.
- **Windows service won't start**: check Services.msc for
  `postgresql-x64-<version>`, or run `pg_ctl start -D "<data-dir>"` manually
  and read the log in `<data-dir>/log`.

## 7. Connecting to the shared Neon/Supabase DB (pairing sessions)

Swap `DATABASE_URL` to the Neon/Supabase connection string shared via the
password manager. Neon requires `sslmode=require`:

```
DATABASE_URL=postgresql+psycopg://<user>:<password>@<neon-host>/<db>?sslmode=require
```

Don't run `alembic upgrade head` against the shared DB casually — coordinate
with your pairing partner, since migrations there affect both of you.
