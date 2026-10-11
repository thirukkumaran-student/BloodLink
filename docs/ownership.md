# BloodLink — Ownership Map

_Generated from the running application by `scripts/export_contracts.py` on 2026-10-11 15:17 UTC._

> Feature developers own domain implementation. The Lead owns cross-domain
> architecture and integration (spec §6).

## Modules

| Module | Owner | API prefix | Foundation status | Depends on | Scope |
| --- | --- | --- | --- | --- | --- |
| `auth` | **D1** | `/auth` | COMPLETE | — | Registration, sign-in, token rotation, account context. |
| `users` | **D1** | `/users` | COMPLETE | auth | Self-service profile and personal donation history. |
| `organizations` | **D1** | `/organizations` | COMPLETE | auth | Organization directory, own-organization context and profile maintenance. |
| `admin` | **D1** | `/admin` | COMPLETE | auth | Organization verification, user administration, audit, platform introspection. |
| `patient_needs` | **D2** | `/patient-needs` | IMPLEMENTED | auth, organizations | Individual hospital discovery + PatientNeed submission and history. |
| `blood_requests` | **D3** | `/blood-requests` | IMPLEMENTED | auth, patient_needs, responses, notifications, matching | BloodRequest lifecycle, responder management, donor selection, fulfilment. |
| `donors` | **D4** | `/donor/profile` | COMPLETE | auth, notifications | Donor profile, availability, hospital subscriptions, nearby hospitals. |
| `responses` | **D4** | `/donor` | COMPLETE | auth, matching, notifications | Donor acceptance/withdrawal, blood-centre availability responses, standby handling. |
| `matching` | **D4** | `/matching` | IMPLEMENTED | notifications | Deterministic distance-first matching, tiering and outreach expansion. |
| `notifications` | **D4** | `/notifications` | COMPLETE | auth | Operational notification feed, device subscriptions and the push transport. |
| `communication` | **D4** | `/conversations` | COMPLETE | auth, responses, notifications | Request-scoped coordination threads and messages (REST only). |
| `donations` | **D4** | `/donations` | COMPLETE | auth, responses, notifications | Donation confirmation records and donor history (cooldown source). |

## Owned paths

### D1 — Lead / platform foundation — architecture, auth, RBAC, contracts, design system, shells, schema integration, CI rules.

- `AGENTS.md`
- `packages/ui/`
- `packages/contracts/`
- `packages/validation/`
- `packages/config/`
- `apps/api/bloodlink_api/core/`
- `apps/api/bloodlink_api/db/`
- `apps/api/bloodlink_api/app.py`
- `apps/api/bloodlink_api/main.py`
- `apps/api/bloodlink_api/seed.py`
- `apps/api/bloodlink_api/modules/auth|users|organizations|admin/`
- `apps/web/src/app/`
- `apps/web/src/api/`
- `apps/web/src/components/`
- `apps/web/src/features/admin/`
- `apps/web/src/features/auth/`
- `alembic/`
- `root configuration`

### D2 — Individual & PatientNeed — hospital discovery, submission, individual history.

- `apps/api/bloodlink_api/modules/patient_needs/`
- `apps/web/src/features/individual/`

### D3 — Hospital & BloodRequest — review gate, request lifecycle, responders, fulfilment.

- `apps/api/bloodlink_api/modules/blood_requests/`
- `apps/web/src/features/hospital/`

### D4 — Donor & coordination — matching, responses, notifications, threads, donations, subscriptions.

- `apps/api/bloodlink_api/modules/matching/`
- `apps/api/bloodlink_api/modules/responses/`
- `apps/api/bloodlink_api/modules/notifications/`
- `apps/api/bloodlink_api/modules/communication/`
- `apps/api/bloodlink_api/modules/donations/`
- `apps/api/bloodlink_api/modules/donors/`
- `apps/web/src/features/donor/`
- `apps/web/src/features/blood-centre/`

## Shared-file rule

The following require Lead review (spec §24): shared UI components, design
tokens, API contracts, global types/enums, authentication, authorization,
database architecture, schema/migration integration, root configuration,
package dependencies, application shells and cross-domain interfaces.

## Feature-folder rule

Once a module is marked `SCAFFOLD`, the owner replaces the scaffold bodies
with real service calls, flips the status to `IMPLEMENTED`, and removes the
`NotImplemented` marker from the contract docstring. The endpoint paths, DTOs
and error codes do not change without a contract review.
