# Windows setup — PostgreSQL, no Linux required

**Owner:** D1 · Windows-only runbook (PowerShell). The cross-platform guides are
[`local-setup.md`](local-setup.md) and [`database.md`](database.md); everything here
uses PowerShell and the PostgreSQL you already have. `make` is **not** needed —
`scripts\dev.ps1` replaces every Makefile target.

---

## 0. What you need

| Tool | Check | If missing |
| --- | --- | --- |
| Python **3.12+** | `py -3.12 --version` | `winget install Python.Python.3.12` |
| Node.js **20+** | `node --version` | `winget install OpenJS.NodeJS.LTS` |
| PostgreSQL + `psql` | `psql --version` | `winget install PostgreSQL.PostgreSQL.17` |
| PowerShell | `$PSVersionTable.PSVersion` | built into Windows (5.1 works; 7 is better) |

No Docker, no WSL, no external services.

---

## 1. Get the code and the Python environment

```powershell
cd $HOME\Downloads            # or wherever you keep projects
# unzip / copy the bloodlink folder here, then:
cd bloodlink

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If activation is refused with *"running scripts is disabled on this system"*:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

(PowerShell 5.1 users: `python` may open the Microsoft Store — use `py -3.12`.)

---

## 2. Create the PostgreSQL role and databases (once)

Open **SQL Shell (psql)** from the Start menu, or a terminal:

```powershell
psql -U postgres
```

At the `postgres=#` prompt (change the password if you like — then use the same one
in the URL below):

```sql
CREATE ROLE bloodlink LOGIN PASSWORD 'bloodlink';
CREATE DATABASE bloodlink      OWNER bloodlink;
CREATE DATABASE bloodlink_test OWNER bloodlink;
\q
```

`bloodlink_test` is used by the test suite, which drops and recreates its tables —
keep it separate from real data.

> **Already have a database you want to use instead?** Skip this step and pass its
> URL in step 3. Any role that owns the database works; `CREATEDB` is only needed if
> you want the setup script to create the databases for you.

---

## 3. One command: configure, migrate, write .env

```powershell
.\scripts\setup_postgres.ps1
```

That uses `postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink`. For
another server, role or database name:

```powershell
.\scripts\setup_postgres.ps1 -DatabaseUrl "postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink"
.\scripts\setup_postgres.ps1 -DatabaseUrl "postgresql+psycopg://postgres:secret@localhost:5432/bloodlink"
```

It creates the databases if they are missing, installs `psycopg` if needed, runs the
migrations, writes `BLOODLINK_DATABASE_URL` / `BLOODLINK_SECRET_KEY` /
`BLOODLINK_SEED_ON_STARTUP` into `.env`, and prints the run commands. **Re-running is
safe** — existing databases, an already-migrated schema and existing `.env` keys are
left alone.

Options: `-EnvFile <path>` (write elsewhere), `-NoEnv` (do not touch `.env`),
`-TestDatabaseUrl <url>`.

If `psql` is not on PATH:

```powershell
$env:Path += ';C:\Program Files\PostgreSQL\17\bin'
```

If the script cannot create a database (your role has no `CREATEDB`), it prints the
two `CREATE DATABASE …` statements for an administrator to run, then re-run it.

---

## 4. Run it — two PowerShell windows

```powershell
# Window 1 — API on :8000
.\scripts\dev.ps1 api

# Window 2 — web client on :5173
.\scripts\dev.ps1 web
```

Open **<http://localhost:5173>** and sign in — password **`Bloodlink#2026`**:

| Account | Role |
| --- | --- |
| `apollo.staff@bloodlink.dev` | hospital — review queue, request board |
| `priya@bloodlink.dev` | donor — accept a matched request |
| `redcross.staff@bloodlink.dev` | blood centre — nearby requests, availability |
| `admin@bloodlink.dev` | admin — verification, users, audit |

Guided tour of what to click, with the expected result at each step:
[`demo-walkthrough.md`](demo-walkthrough.md).

The API banner names the database it opened — that is how you confirm you are on
PostgreSQL, not a stray SQLite file:

```
api.starting env=dev database=postgresql target=postgresql+psycopg://bloodlink@localhost:5432/bloodlink geo=haversine pushTransport=log
```

---

## 5. Task reference (replaces `make`)

```powershell
.\scripts\dev.ps1 help

.\scripts\dev.ps1 api [-Port 8010] [-DatabaseUrl URL]   # API (uvicorn --reload)
.\scripts\dev.ps1 web [-WebPort 5174]                   # web client (Vite)
.\scripts\dev.ps1 setup-postgres [-DatabaseUrl URL]     # databases + migrate + .env
.\scripts\dev.ps1 test                                  # pytest (uses .env)
.\scripts\dev.ps1 test-postgres [-TestDatabaseUrl URL]  # pytest against PostgreSQL
.\scripts\dev.ps1 migrate                               # alembic upgrade head
.\scripts\dev.ps1 seed                                  # seed the demo dataset
.\scripts\dev.ps1 smoke                                 # headless end-to-end walk
.\scripts\dev.ps1 reset-db                              # wipe demo data
.\scripts\dev.ps1 build                                 # production bundle
.\scripts\dev.ps1 check                                 # tests + build + regenerate docs
```

`-DatabaseUrl` overrides `.env` for that command only. Ports default to 8000 (API)
and 5173 (web).

---

## 6. Reset the demo data

The walkthrough consumes the seed (the donor ends up in a 90-day cooldown):

```powershell
# stop the API first (Ctrl-C in window 1)
.\scripts\dev.ps1 reset-db
.\scripts\dev.ps1 api                 # restart — demo data is re-seeded
```

---

## 7. Tests

```powershell
.\scripts\dev.ps1 test-postgres -TestDatabaseUrl "postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink_test"
```

The suite refuses to run against a database whose name does not contain `test`, since
it drops every table in it.

---

## 8. Windows-specific troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| *"running scripts is disabled on this system"* | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, or run `powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 api` |
| `python` opens the Microsoft Store | Use `py -3.12` (the launcher) — that is what the scripts try first, in order `py`, `python`, `python3` |
| `ModuleNotFoundError: No module named 'bloodlink_api'` | `dev.ps1` sets `PYTHONPATH` for you; if you run `python -m uvicorn` by hand, set `$env:PYTHONPATH = 'apps/api;packages/config;packages/contracts;packages/validation'` from the repo root — **semicolons** on Windows, not colons |
| `psql` not recognised | Add `C:\Program Files\PostgreSQL\17\bin` to PATH, or set it for the session as shown in §3 |
| `psql: error: connection to server at "localhost" (::1) failed` | The PostgreSQL **service** is not running: `Get-Service postgresql*` then `Start-Service postgresql-x64-17` |
| `password authentication failed for user "bloodlink"` | The password in the URL differs from the role's. Reset it: `psql -U postgres -c "ALTER ROLE bloodlink PASSWORD 'bloodlink';"` |
| `EADDRINUSE` on 8000 / 5173 | Something already listens there: `.\scripts\dev.ps1 api -Port 8010` and `.\scripts\dev.ps1 web -WebPort 5174`, then open 5174 |
| Windows Firewall prompt on first `api` run | It only listens on your machine; allow it for **private** networks (or block it — localhost still works) |
| Every request fails in the browser but the API is up | Open <http://localhost:8000/api/v1/platform/health> directly; if that works, check you did not close the web window (Vite proxies `/api`) |
| Browser keeps saying "Session ended" | The API restarted with a different/cleared database; sign in again (the client clears the stale token automatically) |
| Slow, flaky file operations, weird permission errors | Move the project **out of** OneDrive/Dropbox-synced folders (`C:\dev\bloodlink` is ideal) |
| `alembic` command not found | Use the module form the scripts use: `.\scripts\dev.ps1 migrate` (i.e. `python -m alembic …`) |
| Want the Linux/bash workflow | Use Git Bash or WSL and follow [`local-setup.md`](local-setup.md); the `Makefile` and `scripts\setup_postgres.sh` work there |

---

## 9. Manual equivalent (no scripts at all)

```powershell
# 1. driver
.\.venv\Scripts\Activate.ps1
pip install -r requirements-postgres.txt

# 2. .env  (copy the template, then edit the URL)
Copy-Item .env.example .env

# 3. schema
$env:BLOODLINK_DATABASE_URL = 'postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink'
python -m alembic upgrade head
python -m alembic check

# 4. API
$env:PYTHONPATH = 'apps/api;packages/config;packages/contracts;packages/validation'
python -m uvicorn bloodlink_api.main:app --reload --host 0.0.0.0 --port 8000

# 5. web, second window
npm install
npm run dev
```
