# BloodLink

A hospital-centred blood coordination platform: hospitals post verified blood
requirements, the platform matches compatible voluntary donors by distance, and
coordination stays inside request-scoped threads.

**Stack:** FastAPI (modular monolith) · SQLAlchemy 2.0 + Alembic · React 18 + Vite
(plain JavaScript/JSX) · shared Python contracts · one design system.

> BloodLink coordinates. It never performs or replaces donor screening, testing,
> crossmatching, collection, processing, storage, issue or transfusion.

---

## Quick start

New machine, first time? Step-by-step guide (prerequisites, Windows commands,
reset, troubleshooting): [`docs/local-setup.md`](docs/local-setup.md).
Running on PostgreSQL instead of SQLite: [`docs/database.md`](docs/database.md) ·
**Windows (PowerShell, no make/bash): [`docs/windows-setup.md`](docs/windows-setup.md)**.

```bash
cd bloodlink

# 1. Python API — installs deps, creates SQLite, seeds the demo dataset
pip3 install -r requirements.txt
make api            # http://localhost:8000  (docs at /docs)

# 2. Web client — in a second terminal
npm install
make web            # http://localhost:5173  (proxies /api to :8000)
```

Sign in with any demo account — password **`Bloodlink#2026`**:

| Account | Role | Try this |
| --- | --- | --- |
| `priya@bloodlink.dev` | Individual + donor (O-) | Donor dashboard → accept a matched emergency request |
| `apollo.staff@bloodlink.dev` | Hospital (verified) | Request board, review queue, threads |
| `redcross.staff@bloodlink.dev` | Blood centre | Nearby requests, availability offers |
| `admin@bloodlink.dev` | Admin | Verify Sunrise Care, browse accounts and the audit trail |
| `pend.staff@bloodlink.dev` | Hospital (pending) | Watch the verification gate return 403 |

Full walkthrough: [`docs/development.md`](docs/development.md) ·
local machine setup: [`docs/local-setup.md`](docs/local-setup.md).

---

## What works today

| Area | State |
| --- | --- |
| Auth, sessions, RBAC, capability payload | **Complete** |
| Users, organizations, admin (verification, accounts, audit) | **Complete** |
| Donor profile, availability, subscriptions, nearby hospitals | **Complete** |
| Donor acceptance / withdrawal, blood-centre availability offers | **Complete** |
| Tiered notifications (privacy-safe payloads, log/console/webpush) | **Complete** |
| Request-scoped coordination threads | **Complete** |
| Donation confirmation + donor cooldown | **Complete** |
| PatientNeed submission + hospital review (D2) | **Complete** — submit, follow, cancel, hospital review queue |
| BloodRequest lifecycle board (D3) | **Complete** — mint from an approved need, drive the lifecycle, select donors, confirm fulfilment |
| Matching engine (D4) | **Complete** — distance-first tiered outreach, deterministic ordering, standby and backup |

All 70 endpoints are implemented; the module registry reports every module as
`COMPLETE` or `IMPLEMENTED` and no scaffold remains — see "Scaffold vs
implemented" in `AGENTS.md`.

---

## Verify

```bash
make check                       # pytest + web build + regenerate contract docs
python3 scripts/smoke_flow.py    # live end-to-end walk of the seeded demo (API only)
python3 scripts/smoke_web_flow.py  # the same surfaces, through the Vite proxy
node scripts/web_boot_smoke.mjs  # boots the built SPA in a DOM, logs in, paints real data
```

Both smokes require the API (and, for the last two, the Vite dev server) to be
running; `make reset-db` deletes the SQLite database — **stop the API first**, then
restart it to get a pristine seed.

---

## Documentation

| Document | Purpose |
| --- | --- |
| [`LEAD_FOUNDATION_SPEC.md`](../uploads/LEAD_FOUNDATION_SPEC.md) | Product + architecture specification (source of truth) |
| [`AGENTS.md`](AGENTS.md) | Operating rules: architecture, ownership, definition of done |
| [`docs/architecture.md`](docs/architecture.md) | Shape of the system, request path, privacy model |
| [`docs/ownership.md`](docs/ownership.md) | Generated ownership map (D1–D4, modules, paths) |
| [`docs/api-contracts.md`](docs/api-contracts.md) | Generated contract for all 70 endpoints |
| [`docs/rbac.md`](docs/rbac.md) | Generated capability matrix per role |
| [`docs/local-setup.md`](docs/local-setup.md) | **Run it on your own machine** — prerequisites, terminals, reset, troubleshooting |
| [`docs/database.md`](docs/database.md) | **PostgreSQL setup**, migrations, running the tests on Postgres, PostGIS status |
| [`docs/windows-setup.md`](docs/windows-setup.md) | **Windows runbook** — PowerShell scripts, PATH fixes, common errors |
| [`docs/demo-walkthrough.md`](docs/demo-walkthrough.md) | **Click-through of the six demo flows** with expected results per step |
| [`docs/development.md`](docs/development.md) | Setup, demo data, feature-developer entry points |

---

## Repository

```text
apps/api       FastAPI modular monolith (core · db · 12 domain modules)
apps/web       React + Vite SPA (role-aware routes, one client for every role)
packages       contracts · validation · config · ui (design system)
alembic        the single migration history
scripts        smoke_flow.py · smoke_web_flow.py · web_boot_smoke.mjs · export_contracts.py
tests          contracts · privacy · RBAC · lifecycle · architecture · parity
```
