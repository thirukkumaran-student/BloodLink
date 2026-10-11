# BloodLink — Development Guide

**Owner:** D1 · Companion to `AGENTS.md` and `LEAD_FOUNDATION_SPEC.md`.

---

## 1. Stack (web-only Python build)

The specification assumed three clients (NestJS API, Next.js web, React Native
mobile). This build keeps the architecture and the ownership model, and maps the
technology onto a Python + React stack:

| Spec | This build | Why |
| --- | --- | --- |
| NestJS + TypeScript API | **FastAPI + Pydantic v2** (modular monolith) | Same modular monolith, same REST contracts, Python ecosystem |
| Prisma ORM | **SQLAlchemy 2.0 + Alembic** | Model registry + a single migration history |
| PostgreSQL + PostGIS | **PostgreSQL + PostGIS in production, SQLite for dev/test** | Geo helpers expose one call site; see `core/geo.py` |
| Next.js + TS web | **React 18 + Vite (plain JavaScript/JSX)** | Same role-aware SPA, no server-side rendering requirement |
| Tailwind CSS | **Design tokens + shared component CSS** (`packages/ui`) | One visual language, enforced by a test |
| React Native + Expo mobile | **removed** | Web-only build: every role uses the web client |
| TanStack Query / RHF / Zod | **TanStack Query / controlled forms / Zod** in the web app | Unchanged in spirit |

Everything else from the spec is preserved: the canonical response envelope, the
endpoint contract docstrings, the module registry, RBAC, privacy rules, the
BloodRequest lifecycle and the DonorResponse acceptance protocol.

---

## 2. Repository layout

```text
bloodlink/
├── apps/
│   ├── api/bloodlink_api/        FastAPI application (modular monolith)
│   │   ├── core/                 settings, security, RBAC context, geo, routing, registry
│   │   ├── db/                   base, session, models/ (one file per domain area)
│   │   ├── modules/              auth, users, organizations, admin (D1)
│   │   │                         patient_needs (D2)
│   │   │                         blood_requests (D3)
│   │   │                         matching, responses, notifications,
│   │   │                         communication, donations, donors (D4)
│   │   ├── app.py                application factory + platform endpoints
│   │   └── seed.py               idempotent demo dataset
│   └── web/                      React + Vite client
│       └── src/{app,api,components,lib,features/{auth,individual,hospital,donor,blood-centre,admin,messages}}
├── packages/
│   ├── contracts/                enums, error codes, envelope, permissions, DTO base
│   ├── validation/               pure validation + blood compatibility + privacy guard
│   ├── config/                   logging, env loading, paths
│   └── ui/                       design tokens + shared React primitives
├── alembic/                      the single migration history
├── docs/                         ownership, api-contracts, rbac, this guide, architecture
├── scripts/export_contracts.py   generates the docs above from the live app
└── tests/                        contracts, privacy, RBAC, acceptance, architecture, parity
```

---

## 2b. Running on your own machine

Step-by-step runbooks for macOS, Linux and Windows (prerequisites, venv, the two
terminals, ports, demo reset, troubleshooting) live in
[`local-setup.md`](local-setup.md).

---

## 3. First run

```bash
cd bloodlink
cp .env.example .env                 # optional: SQLite + demo seeding are the defaults
pip3 install -r requirements.txt
npm install

# terminal 1 — API on :8000 (docs at http://localhost:8000/docs)
make api

# terminal 2 — web client on :5173, proxying /api to :8000
make web
```

The API creates the SQLite schema and seeds demo data on first boot
(`BLOODLINK_SEED_ON_STARTUP=true`, ignored in production).

### Demo accounts

Password for every demo account: **`Bloodlink#2026`**

| Account | Role | What to look at |
| --- | --- | --- |
| `priya@bloodlink.dev` | INDIVIDUAL + donor (O-) | Donor dashboard, matched requests, acceptance flow, commitments |
| `arjun@bloodlink.dev` | INDIVIDUAL + donor (A+) | Incompatible-group behaviour |
| `meera@bloodlink.dev` | INDIVIDUAL (A-) | Author of the pending PatientNeed |
| `apollo.staff@bloodlink.dev` | HOSPITAL (verified) | Review queue, request board, coordination threads |
| `mhc.staff@bloodlink.dev` | HOSPITAL (verified) | Holds the pending need |
| `pend.staff@bloodlink.dev` | HOSPITAL (pending) | Sees the verification banner and 403s |
| `redcross.staff@bloodlink.dev` | BLOOD_CENTRE (verified) | Nearby requests, availability responses |
| `admin@bloodlink.dev` | ADMIN | Organization verification, accounts, audit trail |

### Seeded situation

- One PatientNeed awaiting **Meridian Health City** review (individual → hospital gate).
- One approved need already converted into an **OPEN EMERGENCY** BloodRequest at
  **Apollo General** (O-, PRBC, 1 unit) with tier-1 outreach to Priya and a privacy-safe
  `REQUEST_OPENED` notification.
- Two hospital subscriptions, four organizations (one deliberately `PENDING`).

---

## 4. Validation commands

```bash
make check          # pytest + web build + regenerate contract docs
make test           # Python test suite
make test-privacy   # the privacy guarantees only
make build          # production bundle (Vite)
make export-contracts
```

Live smokes (API + Vite dev server running):

```bash
python3 scripts/smoke_flow.py       # API-only end-to-end lifecycle walk
python3 scripts/smoke_web_flow.py   # every screen's API call, through the Vite proxy
node scripts/web_boot_smoke.mjs     # boots the SPA in jsdom, logs in, paints real data
```

CI-equivalent one-liner:

```bash
PYTHONPATH=apps/api:packages/config:packages/contracts:packages/validation python3 -m pytest -q \
  && npm run build \
  && PYTHONPATH=apps/api:packages/config:packages/contracts:packages/validation python3 scripts/export_contracts.py
```

---

## 5. Where to plug in (feature developers)

The foundation sprint's scaffolds are all implemented. These are the surfaces each
owner now extends — read the file before changing behaviour, the contracts live in
the docstrings:

| Owner | First file to open | Surface |
| --- | --- | --- |
| **D2** | `apps/api/bloodlink_api/modules/patient_needs/router.py` | `POST /patient-needs`, `GET /patient-needs`, `GET /patient-needs/{id}`, `POST /patient-needs/{id}/cancel`, `GET /patient-needs/reference/hospitals` |
| **D3** | `apps/api/bloodlink_api/modules/blood_requests/router.py` + `review.py` | review queue + request board, transitions, donor selection, fulfilment confirmation, outreach summary |
| **D4** | `apps/api/bloodlink_api/modules/matching/service.py` | `_load_candidates`, `expand_outreach`, `eligible_donor_count`, tier expansion |
| **D4** | `apps/web/src/features/{donor,blood-centre}/` | donor discovery/commitments and nearby-request + availability screens |

Every D2/D3/D4 surface is now a real screen: `patient-needs` pages in
`apps/web/src/features/individual`, the review queue and request board (plus the
request detail workspace) in `features/hospital`, and donor discovery /
availability in `features/donor` and `features/blood-centre`. There is no
scaffold panel left to replace — a new endpoint gets a real screen that handles
loading, empty and error states from `packages/ui`.

---

## 6. Adding a database column

1. Propose the model change (D2/D3/D4 design it, D1 integrates it — spec §23).
2. Edit the model in `apps/api/bloodlink_api/db/models/<area>.py`.
3. Regenerate the single revision:

```bash
make migrate-new m="add hospital reference to donation record"
make migrate
```

Never create a second migration root, and never hand-edit a revision that has
already been applied outside your branch.

---

## 7. Moving to PostgreSQL + PostGIS

> Step-by-step version, including how to run the whole test suite against
> PostgreSQL and what PostGIS would (and would not) change:
> [`docs/database.md`](database.md).

```bash
pip3 install -e '.[prod]'         # psycopg + geoalchemy2
export BLOODLINK_DATABASE_URL="postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink"
export BLOODLINK_GEO_BACKEND=postgis
make migrate
```

`core/geo.py` keeps the haversine fallback so SQLite development and the test suite
run the same code paths; swap `distance_km_expr` for `ST_Distance` when PostGIS is
available. Distance bands and privacy rules do not change with the backend.

---

## 8. Push notifications

`BLOODLINK_PUSH_TRANSPORT`:

| Value | Behaviour |
| --- | --- |
| `log` (default) | Structured log line, no external service |
| `console` | JSON lines appended to `var/notifications.log` |
| `webpush` | Real Web Push over VAPID — requires `pywebpush` from the `prod` extra |

Registering a browser subscription is implemented end to end
(`POST /api/v1/notifications/subscriptions`), and every outbound payload passes the
privacy guard first: a payload containing `patientName`, `diagnosis`, `latitude` or a
phone number raises instead of sending.
