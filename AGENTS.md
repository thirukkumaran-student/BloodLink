# AGENTS.md — BloodLink operating rules for coding agents

**Owner:** D1 (Lead / platform foundation)
**Status:** authoritative for every agent or developer working in this repository
**Source of truth for scope:** `LEAD_FOUNDATION_SPEC.md` (v1.0)

---

## 1. What BloodLink is

BloodLink is a hospital-centred blood coordination platform. It connects hospitals
with authorised blood centres and voluntary donors through hospital-verified blood
requests, location-aware matching, tiered notifications, donor networks and
structured coordination.

**BloodLink does not** perform or replace donor medical screening, blood testing,
crossmatching, blood collection, blood processing, blood storage, blood issue,
transfusion, or medical eligibility determination. Those remain with authorised
hospitals and blood centres. Never add a feature that decides, records or implies a
clinical determination.

---

## 2. Non-negotiable architecture

| Rule | Where it is enforced |
| --- | --- |
| Web and API never touch each other's internals | `tests/test_architecture.py` |
| The web client never imports the database layer | `tests/test_architecture.py` |
| The API never imports the web client | `tests/test_architecture.py` |
| Domain modules do not import another owner's `router`/`schemas` | `tests/test_architecture.py` |
| One response envelope, one error-code catalogue | `packages/contracts/` |
| One design system, no local colour/spacing decisions | `packages/ui/`, `tests/test_architecture.py` |
| One migration history, generated only by D1 | `alembic/`, `tests/test_architecture.py` |

The backend is a **modular monolith**. Microservices are explicitly out of scope.
The web client is a **React + Vite** SPA that talks to the FastAPI app over REST.

---

## 3. Ownership

| Owner | Domain | Feature folders |
| --- | --- | --- |
| **D1** | Platform foundation: auth, RBAC, users, organizations, admin, contracts, validation, config, design system, shells, schema integration | `apps/api/bloodlink_api/{core,db,app.py,seed.py,modules/{auth,users,organizations,admin}}`, `packages/*`, `apps/web/src/{app,api,components,features/{auth,admin}}`, `alembic/` |
| **D2** | Individual & PatientNeed | `apps/api/bloodlink_api/modules/patient_needs/`, `apps/web/src/features/individual/` |
| **D3** | Hospital & BloodRequest | `apps/api/bloodlink_api/modules/blood_requests/`, `apps/web/src/features/hospital/` |
| **D4** | Donor & coordination | `apps/api/bloodlink_api/modules/{matching,responses,notifications,communication,donations,donors}/`, `apps/web/src/features/{donor,blood-centre}/` |

`docs/ownership.md` is generated from the live registry — regenerate it with
`python3 scripts/export_contracts.py` instead of editing it by hand.

**Do not modify another owner's feature folder** without explicit coordination, and
never edit files in the shared-file list (`packages/ui`, `packages/contracts`,
`alembic/`, root config, application shells) without Lead review.

---

## 3b. Local machine setup

`docs/local-setup.md` is the single source for "how do I run this locally"
(Windows users: `docs/windows-setup.md`, with `scripts\setup_postgres.ps1` and
`scripts\dev.ps1` as the PowerShell equivalents of `make`):
Python 3.12+, Node 20+, `pip install -r requirements.txt`, `npm install` from the
repo root, then the API and the Vite dev server in two terminals. Point users
there instead of inventing steps.

---

## 4. Definition of done for a feature change

Run all four, and paste the results into the PR description:

```bash
# 1. Python tests (contracts, privacy, architecture, RBAC, acceptance)
cd /home/user/bloodlink
PYTHONPATH=apps/api:packages/config:packages/contracts:packages/validation python3 -m pytest -q

# 2. Web production build (Vite; the client is plain JS/JSX — no type-check step)
npm run build

# 3. Regenerate contract/ownership docs (fails the review if it produces a diff you
#    cannot explain)
PYTHONPATH=apps/api:packages/config:packages/contracts:packages/validation \
  python3 scripts/export_contracts.py

# 4. Boot both processes
PYTHONPATH=apps/api:packages/config:packages/contracts:packages/validation \
  python3 -m uvicorn bloodlink_api.main:app --host 0.0.0.0 --port 8000
npm run dev            # http://localhost:5173, proxies /api to :8000
```

A feature is not done when the UI looks right. It is done when:

- the endpoint's contract docstring matches the behaviour,
- the server-side authorization is present (the UI hiding a link is never enough),
- privacy rules in §7 below hold,
- tests cover the rule you added, not just the happy path.

---

## 5. Endpoint contract format (required)

Every endpoint carries a docstring in this exact shape. `scripts/export_contracts.py`
parses it into `docs/api-contracts.md`, and `tests/test_contracts.py` fails any
endpoint that is missing an `OWNER` or a `PURPOSE`.

```python
@router.post("", status_code=201, summary="Create a BloodRequest")
def create_request(...) -> dict:
    """Create the official BloodRequest from an APPROVED PatientNeed.

    OWNER: D3
    PURPOSE: One sentence on the user-visible outcome.
    INPUT: CreateBloodRequestRequest
    OUTPUT: 201 BloodRequestResponse
    AUTHORIZATION: Who may call this, and under which organization state.
    STATE CHANGES: Tables and fields that change.
    ERRORS: 404 NEED_NOT_FOUND, 409 NEED_ALREADY_REVIEWED
    DEPENDENCIES: Other modules or contracts this relies on.
    MUST NOT: The tempting things this endpoint must never do.
    PRIVACY: What must not appear in the response or in notifications.
    """
```

Declare the router with `api_router(owner="D3", domain="blood-requests", prefix="/blood-requests")`
and register it in the module's `ModuleSpec` (see `apps/api/bloodlink_api/core/registry.py`).

---

## 6. Scaffold vs implemented

The foundation sprint shipped some endpoints as `SCAFFOLD`: contract, authorization
guard and a loud `501` body naming the owner, so the boundaries were fixed before
feature work started (spec §27). **All 70 endpoints are now implemented — the
registry reports `COMPLETE` or `IMPLEMENTED` for every module and no route returns
`501`.** Endpoint implementation status is resolved from the module registry
(`ModuleSpec.foundation_status`), so keeping docs honest means:

1. implementing the service call in place of a `_scaffold(...)` raise (never fake a
   success response),
2. flipping the module's `foundation_status` in its `ModuleSpec`,
3. regenerating `docs/ownership.md` and `docs/api-contracts.md`.

An individual endpoint may still override the module status with a docstring
`STATUS:` line when it genuinely lags or leads its module.

---

## 7. Privacy rules (hard requirements)

- A donor's precise location is **internal matching data**. Coordinates are accepted
  on write and must never be returned by any read endpoint.
- Distance is exposed only through `bloodlink_api.core.geo.distance_band` ("~4 km away").
- Nothing in a notification payload may identify a patient, describe a diagnosis, or
  contain an address. This is enforced at send time by
  `bloodlink_validation.assert_privacy_safe_payload` — payload keys such as
  `patientName`, `diagnosis`, `notes`, `latitude`, `phone` raise immediately.
- There is no donor directory. Matching is request-scoped and driven by an open
  BloodRequest; `GET /api/v1/donor/lookup/donors` intentionally 404s.
- Communication is request-scoped. Never add generic chat, and never add
  attachments or file uploads to a thread in the MVP.

---

## 8. Data and schema rules

- Models live in `apps/api/bloodlink_api/db/models/`, one file per domain area, all
  re-exported from `db/models/__init__.py`.
- IDs are UUID4 strings; timestamps are naive UTC from `bloodlink_api.core.clock`.
- Enums use the **wire values** from `bloodlink_contracts.enums`; use `enum_column()`
  so SQLite and PostgreSQL behave identically.
- Reuse the shared validation rules in `packages/validation` — never restate a rule
  (units range, required-by lead time, password strength, phone format) inside a
  router or a React component.
- Schema changes: propose the model change, then ask D1 to regenerate the single
  Alembic revision (`alembic revision --autogenerate`). Do not create parallel
  migration branches.

---

## 9. Frontend rules

- Compose `@bloodlink/ui` primitives. If you need a new global component, propose it
  to D1 rather than creating a competing one.
- Never hard-code colours, spacing, radii or fonts in feature code: use `var(--bl-*)`
  tokens (`tests/test_architecture.py` rejects hex literals in `features/`).
- Map API statuses to badge tones with `statusTone()` from `@bloodlink/ui`; extend
  that function if a new status appears.
- All network access goes through `apps/web/src/api/client.ts` (envelope unwrapping,
  token refresh, typed `ApiError`). Feature code must not call `fetch` directly.
- Registration, sign-in and the acceptance confirmation flow are D1-owned shells;
  change them only with Lead review.

---

## 10. Git rules

Feature branches from the current stable `main`:

```text
feat/d1-foundation
feat/d2-patient-needs
feat/d3-blood-requests
feat/d4-matching
```

1. Keep commits focused; do not mix unrelated refactors into a feature PR.
2. Rebase on the latest `main` before merging.
3. Run the §4 checks before opening the PR.
4. Shared-file changes need Lead review.
5. Merge only validated work into `main`.

---

## 11. Environment

Copy `.env.example` to `.env`. Notable settings:

| Variable | Purpose |
| --- | --- |
| `BLOODLINK_DATABASE_URL` | SQLite for development; PostgreSQL for production |
| `BLOODLINK_GEO_BACKEND` | `haversine` (default) or `postgis` |
| `BLOODLINK_PUSH_TRANSPORT` | `log`, `console` or `webpush` |
| `BLOODLINK_MATCH_TIER*_RADIUS_KM` | Tier 1/2 outreach radii |
| `BLOODLINK_DONOR_COOLDOWN_DAYS` | Post-donation recovery window |
| `BLOODLINK_SEED_ON_STARTUP` | Demo data on boot (never in production) |

Demo accounts (password `Bloodlink#2026`) are listed in `docs/development.md`.
