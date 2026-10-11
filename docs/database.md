# Database — PostgreSQL in production, SQLite for convenience

**Owner:** D1 · Referenced by `apps/api/bloodlink_api/core/geo.py` and the settings
docs. Covers the SQLAlchemy URL, schema creation, both engines, and what PostGIS
would change (and not change).

---

## 0. Quick start — PostgreSQL only (Postgres already installed)

Five commands from the repo root. `setup_postgres.sh` creates the databases if they
are missing, installs the driver, migrates, writes `.env` (generating a secret key)
and prints the run commands; it is safe to re-run.

```bash
cd bloodlink
python3 -m venv .venv && source .venv/bin/activate    # Windows: py -3.12 -m venv .venv ; .venv\Scripts\Activate.ps1

./scripts/setup_postgres.sh                            # or: make setup-postgres
#   → uses postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink
#   → your own server/role: pass the URL as the first argument
#     ./scripts/setup_postgres.sh "postgresql+psycopg://myuser:mypass@dbhost:5432/bloodlink"
#   → or set it once in .env and re-run with no argument

make api          # terminal 1 · :8000 · first start seeds the demo dataset
make web          # terminal 2 · :5173

make test-postgres  # the full suite against PostgreSQL (uses …_test database)
```

Sign in at <http://localhost:5173> — password `Bloodlink#2026`; guided tour in
[`demo-walkthrough.md`](demo-walkthrough.md).

**On Windows** use the PowerShell equivalents (no `make`, no bash):

```powershell
cd bloodlink
py -3.12 -m venv .venv ; .\.venv\Scripts\Activate.ps1

.\scripts\setup_postgres.ps1                              # or with -DatabaseUrl "postgresql+psycopg://…"
.\scripts\dev.ps1 api                                     # terminal 1 · :8000
.\scripts\dev.ps1 web                                     # terminal 2 · :5173
.\scripts\dev.ps1 test-postgres -TestDatabaseUrl "postgresql+psycopg://user:pw@localhost:5432/bloodlink_test"
```

Full Windows runbook, including installing PostgreSQL, PATH fixes and the common
failure messages: [`windows-setup.md`](windows-setup.md).

**If the script cannot create the database** (your role has no `CREATEDB`), have a
superuser run the two `CREATE DATABASE … OWNER …;` statements it prints, then run
the script again — or run §2 below by hand.

---

## 1. Which engine to use

| | SQLite | PostgreSQL |
| --- | --- | --- |
| Best for | first run, classroom demo, `pytest` default | production, staging, anything multi-process |
| Setup | none — the file is created on start | a server + the `psycopg` driver |
| Default URL | `sqlite:///./bloodlink.db` | `postgresql+psycopg://user:pass@host:5432/bloodlink` |
| Schema creation | `create_all()` on startup (dev only) | `python3 -m alembic upgrade head` |
| Enforcement | foreign keys are off unless pragma'd (the app sets it on) | strict FKs, real types, concurrent writers |

The application code is identical on both. One caveat lives in the models and is
already handled: `users` and `organizations` reference each other, which PostgreSQL
cannot create inline, so `Organization.verified_by_user_id` is declared with
`use_alter=True` and the migration adds that constraint after both tables exist
(SQLite tolerated the cycle silently; PostgreSQL does not).

---

## 2. PostgreSQL by hand (or if you do not want the script)

### 2.1 Server and role (skip if you already have both)

```bash
# Debian/Ubuntu
sudo apt install postgresql postgresql-contrib
sudo -u postgres psql <<'SQL'
CREATE ROLE bloodlink LOGIN PASSWORD 'bloodlink';
CREATE DATABASE bloodlink OWNER bloodlink;
CREATE DATABASE bloodlink_test OWNER bloodlink;   -- for the test suite
SQL

# macOS (Homebrew)
brew install postgresql@17 && brew services start postgresql@17
createuser -P bloodlink        # then createdb bloodlink -O bloodlink
```

Two databases, on purpose: `bloodlink_test` is thrown away by the test suite, so
never point it at real data. (The fixture also refuses unless the database name
contains `test`.)

### 2.2 Driver

```bash
pip install -r requirements-postgres.txt     # requirements.txt + psycopg[binary]
# or: make install-postgres
```

### 2.3 Point the API at it

In `.env` (repo root):

```ini
BLOODLINK_DATABASE_URL=postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink
BLOODLINK_SECRET_KEY=<a long random string>
BLOODLINK_SEED_ON_STARTUP=true     # demo data; set false in production
```

Or per command, without touching `.env`:

```bash
make api-postgres DATABASE_URL="postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink"
```

### 2.4 Create the schema

```bash
# production path — the same revision that runs on SQLite
BLOODLINK_DATABASE_URL="postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink" \
  python3 -m alembic upgrade head

# verify nothing in the models drifted from the revision
BLOODLINK_DATABASE_URL="…" python3 -m alembic check      # → No new upgrade operations detected
```

In `BLOODLINK_ENV=dev` (the default) the API also runs `create_all()` and the seed
on startup, which is convenient locally. **In production (`BLOODLINK_ENV=production`)
neither happens** — run `alembic upgrade head` yourself and leave
`BLOODLINK_SEED_ON_STARTUP=false`. That's also the point where `BLOODLINK_SECRET_KEY`
matters: the default is a dev placeholder.

### 2.5 Run everything

```bash
make api-postgres                     # terminal 1 — API on :8000, Postgres behind it
make web                              # terminal 2 — web client on :5173
```

The startup log names the database it opened, which is how you confirm at a glance
that you are on Postgres:

```
api.starting env=dev database=postgresql target=postgresql+psycopg://bloodlink@localhost:5432/bloodlink geo=haversine pushTransport=log
```

### 2.6 Start using it

Sign in at <http://localhost:5173> with any demo account (`Bloodlink#2026`). The
six-step guided tour — individual submits → hospital reviews → request minted →
donor accepts → hospital selects/fulfils → blood-centre offer — with the expected
result at each step is in [`demo-walkthrough.md`](demo-walkthrough.md).

---

## 3. Running the test suite against PostgreSQL

```bash
make test-postgres TEST_DATABASE_URL="postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink_test"
# equivalent:
BLOODLINK_TEST_DATABASE_URL="postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink_test" \
  python3 -m pytest -q
```

The same 70 tests run unchanged; the fixture drops and recreates every table in the
test database instead of deleting a file. Default (`make test`) stays on SQLite so
the suite runs with zero infrastructure — run it against Postgres before a release,
since that's where FKs, types and concurrency are actually enforced.

Verified on PostgreSQL 17.11: `alembic upgrade head` → seed → `pytest` (70 passed) →
`scripts/smoke_flow.py` (full lifecycle) → `scripts/smoke_web_flow.py` (37/37) →
`scripts/web_boot_smoke.mjs` (17/17).

---

## 4. Reset, backup and inspect

```bash
# wipe the demo data and start over (SQLite)
#   stop the API first — deleting the file under a live server breaks it
make reset-db && make api

# wipe and re-seed PostgreSQL
psql "postgresql://bloodlink:bloodlink@localhost:5432/bloodlink" \
  -c "TRUNCATE TABLE audit_logs, blood_request_events, blood_requests, conversations, donation_records, donor_outreach, donor_profiles, donor_responses, hospital_subscriptions, idempotency_records, messages, notification_deliveries, notifications, organization_memberships, organization_responses, organizations, patient_needs, push_subscriptions, refresh_tokens, users, verification_documents RESTART IDENTITY CASCADE;"
# then restart the API (dev) — or: python3 -m bloodlink_api.seed

# nuclear option
dropdb bloodlink && createdb -O bloodlink bloodlink && python3 -m alembic upgrade head

# backups
pg_dump -Fc -O -f bloodlink.dump "postgresql://bloodlink:bloodlink@localhost:5432/bloodlink"
pg_restore -O -d bloodlink bloodlink.dump

# inspect
psql "postgresql://bloodlink:bloodlink@localhost:5432/bloodlink" -c "\dt"
psql "…" -c "select reference, status, units_required from blood_requests order by opened_at desc limit 5;"
```

Compose/CI note: `postgres:17-alpine` with `POSTGRES_USER=bloodlink`,
`POSTGRES_PASSWORD=bloodlink`, `POSTGRES_DB=bloodlink`, plus a second database for
tests, is enough — no extensions required.

---

## 5. PostGIS: not required, and currently not used

Coordinates (`organizations.latitude/longitude`, `donor_profiles.latitude/longitude`)
are plain `Float` columns and all distance math goes through the haversine adapter in
`core/geo.py`, **on every engine**. Consequences:

- Running on PostgreSQL needs no PostGIS extension — nothing to install, nothing to
  `CREATE EXTENSION`.
- Matching results are engine-independent: the same tier radii produce the same
  donors on SQLite and PostgreSQL.
- `BLOODLINK_GEO_BACKEND=postgis` is **reserved**. It is accepted and validated, but
  the engine still uses haversine, and the API logs a warning at startup instead of
  pretending otherwise:

  ```
  geo.backend_reserved requested=postgis in_use=haversine — coordinates are stored as plain
  Float columns and need no PostGIS extension; see docs/database.md
  ```

What an actual PostGIS upgrade would involve (not scheduled; keep the setting at
`haversine` until then):

1. store a `geography(Point, 4326)` column alongside (or instead of) the Float pair,
   backfilled from it;
2. a GiST index on that column;
3. a `distance_km_expr()` SQL expression using `ST_Distance`, wired into the matching
   queries in `apps/api/bloodlink_api/modules/matching/service.py`;
4. a migration that keeps SQLite working (the Float columns stay the source of truth
   for the test suite).

Until then the current approach is correct and plenty fast: tier radii are ≤15 km and
candidate sets are small (spec §11), so the distance filter is not the bottleneck.

---

## 6. Two apps from the same specification

If another BloodLink build from the same spec runs on the same server, give each app
**its own database** — never share one, not even a schema. `docs/local-setup.md §10`
covers the full picture (ports, secret key, workspace folders).
