# BloodLink — Architecture

**Owner:** D1 · Source of truth for cross-domain decisions (spec §3, §6, §29).

---

## 1. Shape

```text
                    BROWSER
                       │  HTTPS
                       ▼
        ┌──────────────────────────────┐
        │   Web client (React + Vite)  │   role-aware SPA
        │   portals: individual,       │   D2 · D3 · D4 feature folders
        │   hospital, blood centre,    │
        │   donor, admin               │
        └──────────────┬───────────────┘
                       │  REST  /api/v1  (canonical envelope)
                       ▼
        ┌──────────────────────────────┐
        │   BLOODLINK API (FastAPI)    │   modular monolith
        │                              │
        │  core: settings · security · │
        │  RBAC · geo · routing ·      │
        │  registry · errors · audit   │
        │                              │
        │  modules: auth · users ·     │   D1 owns platform modules
        │  organizations · admin ·     │
        │  patient_needs ·             │   D2 / D3 / D4 own feature modules
        │  blood_requests · matching · │
        │  responses · notifications · │
        │  communication · donations · │
        │  donors                      │
        └──────────────┬───────────────┘
                       │  SQLAlchemy 2.0
                       ▼
        ┌──────────────────────────────┐
        │  PostgreSQL (+ PostGIS)      │   dev/test: SQLite
        │  21 tables, one migration    │
        │  history, one metadata obj   │
        └──────────────────────────────┘
```

Rules that hold everywhere:

- The web client never touches the database; the API never imports the web client.
- Business rules live in the API. The client may mirror a rule for UX, never as the
  authority.
- The backend is a modular monolith. Microservices are out of scope.
- Ownership is by folder, not by process.

---

## 2. Cross-domain interfaces

Feature modules never reach into another owner's tables or routers. They call the
providing module's `service` or its frozen `interfaces.py`:

| Caller | Interface | Provided by |
| --- | --- | --- |
| D3 (request lifecycle) | `matching.interfaces.request_outreach`, `eligible_candidates`, `expand_request_outreach` | D4 |
| D3 (selection) | `responses.service.select_donor`, `activate_standby`, `responses_for_request` | D4 |
| D3 (fulfilment) | `donations.service.confirm_donations` | D4 |
| D4 (responses) | `notifications.service.create_notification` | D4 (internal) |
| D2 → D3 | none: the need is reviewed, then D3 mints the request through `POST /blood-requests` | boundary by design |
| Any → D1 | `bloodlink_contracts`, `bloodlink_validation`, `core.geo`, `core.context` | D1 |

`tests/test_architecture.py` fails a build where a module imports another owner's
`router` or `schemas`.

---

## 3. The request path

```text
Individual
  │  POST /patient-needs                    (D2)  status: PENDING_HOSPITAL_REVIEW
  ▼
Hospital review
  │  POST /hospital/patient-needs/{id}/review (D3) APPROVED | REJECTED
  ▼
BloodRequest created
  │  POST /blood-requests                    (D3)  status: OPEN
  ▼
Tiered outreach                            (D4)  matching + notifications
  │  OPEN → RESPONSES_RECEIVED → COVERED → COORDINATING
  ▼
Fulfilment
  │  POST /blood-requests/{id}/confirm-fulfillment (D3 → D4) FULFILLED
  ▼
DonationRecord + cooldown starts

Failure path (spec §9):
COORDINATING → BACKUP_REQUIRED → standby activation | expanded outreach | reopened coordination
```

Transitions are validated against `bloodlink_contracts.enums.BLOOD_REQUEST_TRANSITIONS`
by the API, and the table itself is covered by a test, so an illegal move cannot be
smuggled in through a new endpoint.

---

## 4. Matching (deterministic, distance-first)

Inputs: the request, donor profiles, hospital location.

1. **Compatibility filter** — red-cell compatibility (plasma uses the inverse rule)
   from `bloodlink_validation.blood`. This targets outreach only; it is not a medical
   eligibility decision.
2. **Availability** — `isAvailable`, and the donor's notification preference
   (`acceptsNotifications`, `notifyEmergencyOnly`).
3. **Donation state** — donors inside the post-donation cooldown
   (`BLOODLINK_DONOR_COOLDOWN_DAYS`, default 90) are excluded from outreach.
4. **Distance** — haversine via a bounding-box pre-filter, ascending. Distance is the
   fundamental ranking criterion; district boundaries are hints, never hard walls.
5. **Tiers** — tier 1 (`MATCH_TIER1_RADIUS_KM`) for every request; tier 2 on the
   BACKUP_REQUIRED path; tier 3 = verified alternatives. Emergency requests widen
   immediately. Already-notified donors are skipped per tier.

No ML, no scoring model, no hidden weights: the ordering is explainable to a hospital
coordinator, which is what a clinical-adjacent workflow needs.

---

## 5. Privacy model

| Data | Stored | Exposed to |
| --- | --- | --- |
| Donor coordinates | yes (internal matching data) | nobody — not even the donor's own read endpoint; the donor sees a ~5 km grid label |
| Distance | computed per request | hospitals and donors as a band ("~4 km away") |
| Patient identity | never stored by BloodLink | nobody |
| Clinical detail (diagnosis, tests, screening) | never stored | nobody — out of scope (spec §2) |
| Notification payloads | ids, group, component, urgency, distance band | subscribed devices |
| Contact details | the account owner's own | the owner; never another donor |

Three enforcement points, not three conventions:

1. `bloodlink_validation.assert_privacy_safe_payload` runs at send time and raises on
   forbidden keys.
2. Serialisers return explicit projections; there is no `to_dict()` on any model that
   could leak coordinates.
3. `tests/test_privacy.py` walks real API responses and fails on forbidden keys.

---

## 6. Authentication and authorization

- JWT access tokens (120 min default) + rotating, revocable refresh tokens stored as
  SHA-256 digests. Passwords are bcrypt (cost 12).
- `Principal` is resolved from the database on every request, so a deactivated account
  or suspended organization loses access immediately — claims alone are never trusted.
- RBAC is a capability matrix in `packages/contracts/bloodlink_contracts/permissions.py`.
  `GET /auth/me` returns the caller's capabilities so the SPA can build navigation;
  every endpoint re-checks server-side.
- Organization context guards (`require_hospital_context`,
  `require_blood_centre_context`) also enforce the organization's verification state:
  unverified → `403 ORGANIZATION_NOT_VERIFIED`, suspended → `403 ORGANIZATION_SUSPENDED`.

---

## 7. API conventions

- Base path `/api/v1`; JSON; camelCase on the wire, snake_case in Python.
- One envelope for success and failure (see `docs/api-contracts.md`).
- Status codes: 200, 201, 204, 400, 401, 403, 404, 409, 422, 500. Stack traces are never
  exposed; unhandled errors return a request id the operator can correlate.
- Every endpoint carries an `OWNER`/`PURPOSE`/… contract docstring; the docs are
  generated from those docstrings, and a test fails an endpoint that lacks them.
- Pagination: `?page=&pageSize=` with `meta.pagination` (`total`, `pages`, `hasNext`).

---

## 8. Foundation status

`GET /api/v1/platform/modules` returns the live map. At the end of the foundation
sprint:

| Status | Modules |
| --- | --- |
| `COMPLETE` | auth, users, organizations, admin, donors, responses, notifications, communication, donations |
| `SCAFFOLD` | patient_needs (D2), blood_requests (D3), matching engine internals (D4) |

Scaffolded endpoints carry their full contract, their authorization guard and a `501`
body naming the owner. That is deliberate: the foundation fixes boundaries, feature
developers implement behaviour (spec §26.13, §27).
