# Run BloodLink on your own machine

**Owner:** D1 · Everything you need to run the full app locally — no Docker, no
database server, no cloud services. SQLite is created on first start and seeded
with the demo dataset.

> If you are reading this in the sandbox preview, this page is the guide for your
> **local** machine specifically. Nothing here depends on the sandbox.

---

## 0. What you need

| Requirement | Check | Notes |
| --- | --- | --- |
| Python **3.12+** | `python3 --version` | `pyproject.toml` declares `requires-python = ">=3.12"` |
| Node.js **20+** with npm | `node --version` | only used for the React/Vite client |
| `make` (optional) | `make --version` | macOS/Linux convenience. Windows: use the raw commands below |
| Free ports | — | `8000` (API) and `5173` (web dev server), `4173` (built preview) |

No Docker, no Postgres, no Redis, no external services. The API creates
`bloodlink.db` next to the repo root on first run.

---

## 1. Get the code onto your machine

Download/copy the project folder from the workspace (everything under
`bloodlink/`) into a directory of your choice.

**Do not bother copying** — all of it is regenerated:

```
node_modules/      # npm install rebuilds it
dist/              # npm run build rebuilds it
bloodlink.db       # recreated + reseeded on API start
.venv/ __pycache__/ .pytest_cache/
```

Then:

```bash
cd bloodlink
```

---

## 2. Install dependencies (once)

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install                # repo root — installs the web app + design system workspaces
```

Shortcut once the venv is active: `make install` (runs both installs for you).

### Windows (PowerShell)

> Windows-only workflow with helper scripts (`scripts\setup_postgres.ps1`,
> `scripts\dev.ps1`) and a troubleshooting table:
> [`windows-setup.md`](windows-setup.md). The manual commands below still apply.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
npm install
```

> Behind a proxy? `npm install` and `pip install` both need network access the
> first time. After that the app runs fully offline.

---

## 3. Configuration (optional)

The defaults work as-is. To change anything:

```bash
cp .env.example .env          # Windows: copy .env.example .env
```

Every setting is prefixed `BLOODLINK_` and is read from `.env` in the repo root
(see `apps/api/bloodlink_api/core/settings.py`). The ones you might touch:

| Setting | Default | Meaning |
| --- | --- | --- |
| `BLOODLINK_SECRET_KEY` | dev placeholder | **set a long random string** for anything real |
| `BLOODLINK_DATABASE_URL` | `sqlite:///./bloodlink.db` | any SQLAlchemy URL; Postgres shown in the template |
| `BLOODLINK_GEO_BACKEND` | `haversine` | `postgis` to use GeoAlchemy2 instead |
| `BLOODLINK_SEED_ON_STARTUP` | `true` | demo data; keep `false` in production |
| `BLOODLINK_PUSH_TRANSPORT` | `log` | `log` / `console` / `webpush` |

---

## 4. Run it — two terminals

### Terminal 1 — the API

macOS / Linux:

```bash
PYTHONPATH=apps/api:packages/config:packages/contracts:packages/validation \
  python3 -m uvicorn bloodlink_api.main:app --reload --host 0.0.0.0 --port 8000
```

or simply `make api` (same command, plus `--reload`).

Windows (PowerShell) — note the `;` separators:

```powershell
$env:PYTHONPATH="apps/api;packages/config;packages/contracts;packages/validation"
python -m uvicorn bloodlink_api.main:app --reload --host 0.0.0.0 --port 8000
```

Wait for:

```
api.ready modules=12 routers=13 prefix=/api/v1
seed.complete users=8 organizations=4 requests=1
```

Useful URLs: API root <http://localhost:8000>, interactive docs
<http://localhost:8000/docs>, health
<http://localhost:8000/api/v1/platform/health>.

### Terminal 2 — the web client

```bash
npm run dev            # or: make web
```

Open **<http://localhost:5173>**. The dev server proxies `/api` to
`http://127.0.0.1:8000`, so the browser talks to a single origin and you never
configure CORS during development.

**Ports and proxy target are environment-driven** (see `apps/web/vite.config.js`),
so a second copy of the app — or any other service on 5173/8000 — costs you one
variable, not an edit:

```bash
# API on another port
make api API_PORT=8010                       # or add --port 8010 to the uvicorn command

# web client on another port, pointed at that API
make web WEB_PORT=5174 API_PORT=8010
# equivalent raw command:
BLOODLINK_WEB_PORT=5174 BLOODLINK_API_URL=http://127.0.0.1:8010 npm run dev
```

`BLOODLINK_PREVIEW_PORT` does the same for the built bundle (§6). Section 10 covers
the whole "two apps from the same spec" situation, including databases.

---

## 5. Sign in

Password for every demo account: **`Bloodlink#2026`**

| Account | Role | What to try |
| --- | --- | --- |
| `priya@bloodlink.dev` | Individual + donor (O-) | donor dashboard → accept the matched emergency request |
| `apollo.staff@bloodlink.dev` | Hospital (verified) | request board → open the request → drive the lifecycle |
| `redcross.staff@bloodlink.dev` | Blood centre | nearby requests → offer availability |
| `admin@bloodlink.dev` | Admin | verify organizations, accounts, audit trail |
| `mhc.staff@bloodlink.dev` | Hospital (verified) | the review queue with the pending requirement |
| `pend.staff@bloodlink.dev` | Hospital (pending) | the verification gate returning 403 |
| `arjun@bloodlink.dev` / `meera@bloodlink.dev` | Donors / individual | additional profiles |

The login screen has one-click buttons for four of them. For a guided tour of what
to click and what should happen at each step, see
[`demo-walkthrough.md`](demo-walkthrough.md).

---

## 6. Optional: production-style run (no dev server)

```bash
npm run build      # writes apps/web/dist
npm run preview    # serves the built bundle on http://localhost:4173
```

`npm run preview` uses the same `/api` proxy as the dev server
(`apps/web/vite.config.js`), so this works without extra setup.

Serving `dist/` from a **different** origin (nginx, another port) is supported
too: build with an absolute API base and tighten CORS:

```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1 npm run build
# and in .env: BLOODLINK_CORS_ORIGINS=http://localhost:8080
```

---

## 7. Verify your local install

```bash
make test          # 70 Python tests (contracts, privacy, RBAC, lifecycle, parity)
make check         # tests + web build + regenerate docs/api-contracts.md

# live smokes (API running; the web ones also need the dev server)
python3 scripts/smoke_flow.py          # submit → review → mint → accept → select → fulfil
python3 scripts/smoke_web_flow.py      # every screen's API calls, through the Vite proxy
node scripts/web_boot_smoke.mjs        # boots the SPA, logs in via the form, paints real data
```

Without `make`, prefix the Python commands with
`PYTHONPATH=apps/api:packages/config:packages/contracts:packages/validation`.

---

## 8. Reset the demo data

The demo dataset is consumed as you click through the flows (and
`smoke_flow.py` consumes it immediately). To start clean:

1. **Stop the API** (Ctrl-C). Deleting the SQLite file while uvicorn is running
   leaves the server writing to a deleted file — you get 500s.
2. `make reset-db` (or `rm bloodlink.db`; Windows: `del bloodlink.db`)
3. Start the API again — it recreates and re-seeds the database.

Any browser tab that was still open is holding a token for the old database. The
client notices the rejected token on its next request, clears it and returns to the
sign-in screen (you will see a "Session ended" toast) — no need to clear site data
by hand. Sign in again and the fresh demo data is there.

---

## 9. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `ModuleNotFoundError: No module named 'bloodlink_api'` | `PYTHONPATH` is not set in that terminal, or you are not in the repo root. |
| `Error: listen EADDRINUSE :::5173` (or 8000) | Port taken. Change `--port` for uvicorn and `server.port` in `apps/web/vite.config.js`. |
| Page loads but every request fails | The API is not running. Note the Vite proxy answers **500** (not 502) when the backend is down. |
| `npm install` fails to link `@bloodlink/ui` | Run it from the **repo root**, not `apps/web` — the design system is an npm workspace. |
| Login fails with an unexpected error | The database was deleted/replaced under the running API. Stop it, `make reset-db`, start it again. |
| `python3: command not found` on Windows | Use `python` (and `py -3.12` to create the venv). |
| `make` not found on Windows | Use the raw commands in §2 and §4. |
| Package install errors on Python 3.11 or older | `pyproject.toml` requires **3.12+**; install a newer Python. |
| Prefer PostgreSQL to SQLite (or have no SQLite) | Nothing is missing: `make install-postgres`, set `BLOODLINK_DATABASE_URL` to your Postgres URL, `alembic upgrade head`, then `make api-postgres`. Full walkthrough incl. running the tests on Postgres: [`docs/database.md`](database.md). PostGIS is not required. |

---

## 10. Running alongside another app built from the same document

Two applications generated from the same specification share **names**: the package
`bloodlink`, the Python modules `bloodlink_api` / `bloodlink_contracts`, the npm
scope `@bloodlink/*`, the table names, the `BLOODLINK_` environment prefix, the demo
accounts, and the default ports **8000 / 5173 / 4173**. None of that breaks anything
by itself — as long as each app gets its own database, its own ports and its own
process tree.

### What is shared, and how to separate it

| Shared thing | What goes wrong if it is shared | How to separate |
| --- | --- | --- |
| **SQLite file** | Both apps write the same `bloodlink.db`: each one's tables and demo data land in the other's app. | Nothing to do — the default `sqlite:///./bloodlink.db` resolves against **each app's own root**, so two folders = two files. Rename for clarity: `BLOODLINK_DATABASE_URL=sqlite:///./bloodlink_appb.db`. |
| **PostgreSQL database** | One `alembic_version`, one `users` table, one seed. App B's migration rewrites app A's schema, and app B *silently looks already-seeded* (the seeder returns early once it finds `admin@bloodlink.dev`). | **One database per app** — not one schema. `createdb bloodlink_b` and point B at it: `postgresql+psycopg://user:pass@localhost:5432/bloodlink_b`. PostGIS is per-database too: `CREATE EXTENSION postgis;` in each. |
| **Auth secret** | Identical default `BLOODLINK_SECRET_KEY` plus a shared database means a token minted by app A is accepted by app B (same user ids). | Give each app its own long random `BLOODLINK_SECRET_KEY` in its own `.env`. (With separate databases the ids differ anyway, so tokens stop working across apps — treat that as defence in depth.) |
| **Ports** | The second app fails to bind (`EADDRINUSE`), or its browser talks to the first app's API. | `make api API_PORT=8010` + `make web WEB_PORT=5174 API_PORT=8010`, or set `BLOODLINK_WEB_PORT` / `BLOODLINK_API_URL` (see §4 note below). |
| **Python modules** | Two copies of `bloodlink_api` on one `PYTHONPATH` — only one is ever imported. | Each app runs from its own folder with its own `PYTHONPATH` (the exact command in §4), so this is already isolated. Keep **one virtualenv per app** if you also install the API as a package. |
| **npm workspaces** | App B placed *inside* app A's folder joins A's workspace, and `npm install` hoists confusing packages. | Keep the two copies as **sibling** folders, never nested. |
| **`.env` file** | A shared environment variable leaking between apps. | Each app reads `.env` from its **own** project root and never `os.environ` directly, so files cannot cross-talk. Avoid exporting `BLOODLINK_*` globally in your shell profile. |
| **Demo accounts** | Same emails and the same password (`Bloodlink#2026`) in both apps — easy to sign into the wrong one. | Expected; separate databases make them independent records. Set `BLOODLINK_SEED_ON_STARTUP=false` on the copy that should stay empty. |

### Ready-made recipe for the second copy

```bash
# copy the app to a sibling folder, never inside the first one
cp -r bloodlink bloodlink-b && cd bloodlink-b

# its own virtualenv + deps
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && npm install

# its own identity in .env
cat >> .env <<'EOF'
BLOODLINK_SECRET_KEY=<a different long random string>
BLOODLINK_DATABASE_URL=sqlite:///./bloodlink-b.db
EOF

# terminal 1 — API on 8010
make api API_PORT=8010

# terminal 2 — web on 5174, proxying to the 8010 API
make web WEB_PORT=5174 API_PORT=8010
```

Open <http://localhost:5173> for app A and <http://localhost:5174> for app B. Each
frontend proxies `/api` to its own API:

```bash
curl -s localhost:5173/api/v1/platform/health | python3 -m json.tool   # app A
curl -s localhost:5174/api/v1/platform/health | python3 -m json.tool   # app B
```

Verified shape of this arrangement: `web :5173 -> env=dev` and
`web :5174 -> env=sidecar-b`, each with its own SQLite file, and logins on one never
appear in the other.

### How to tell the two instances apart

- Each API prints its identity at startup:
  `api.starting env=dev database=sqlite target=/…/bloodlink.db geo=haversine …`
  — `env` and `target` are the fastest way to confirm which app you are hitting.
- `GET /api/v1/platform/health` returns the same `env` value in the browser's
  network tab.
- On the web side, the Vite banner shows the port it bound, and
  `apps/web/vite.config.js` logs neither — check the terminal you started it from.

### If you would rather rename everything

Nothing stops you: the Python package names, the npm scope and the table names are
strings, not magic. But renaming touches imports in ~120 files, the contract
exporter, the tests and the docs — **the isolation above is one `.env` line per
concern**, so rename only if you intend to publish the two apps separately.

---

## 11. What you are running

```text
apps/api       FastAPI modular monolith — 12 modules (D1 auth/users/orgs/admin,
               D2 patient needs, D3 blood requests, D4 donors/matching/notifications/
               communication/donations). /api/v1, one response envelope.
apps/web       React 18 + Vite SPA (plain JS/JSX) — one role-aware client for
               individuals, hospitals, blood centres, donors and admins.
packages/      contracts · config · validation (Python) and ui (design system).
alembic/       the single migration history (D1 owns it).
tests/         70 tests; scripts/ holds the exporters and the three smokes.
```

BloodLink coordinates only: hospital verification, distance-based matching,
tiered notifications, donor acceptance and coordination threads. Screening,
testing, crossmatching, collection, storage, issue and transfusion always stay
with the hospital or blood centre.
