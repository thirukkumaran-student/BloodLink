# Demo walkthrough — the six flows worth seeing

**Owner:** D1 · For a reviewer who wants to see the platform work, not just read
about it. Assumes the app is running (see [`local-setup.md`](local-setup.md) for
SQLite, [`database.md`](database.md) for PostgreSQL) and the demo data is pristine.

Password for every account: **`Bloodlink#2026`**. The login screen has one-click
buttons for four of them.

Two rules to keep in mind while clicking:

- **A requirement is not a request.** Nothing is matched or notified until a
  hospital reviews a PatientNeed *and* mints the BloodRequest from it.
- **Nobody's exact location is ever shown.** Responses carry a distance band
  (`~4 km away`); notifications carry no patient identity. Watch for that.

---

## Flow 1 — Individual submits, hospital reviews (D2 → D3 gate)

1. Open <http://localhost:5173>, sign in as **`meera@bloodlink.dev`** (INDIVIDUAL).
2. **My blood requests → New request.** Pick Apollo General, O+, PRBC, 2 units,
   URGENT, required-by tomorrow, and a coordination note. Submit.
3. You land on the list with the new row at **PENDING_HOSPITAL_REVIEW**. Notice the
   matching engine has done *nothing* yet — no donor was notified.
4. Try **Cancel** on a second request you create: allowed while pending, refused
   (`409 NEED_NOT_CANCELLABLE`) once reviewed.
5. Sign out, sign in as **`mhc.staff@bloodlink.dev`** (a different verified
   hospital): the request is **not** in their queue — needs are addressed to one
   hospital and cannot be read by another.

Expected: `201` on submit, staff notification to the hospital, `403/404` for the
wrong hospital.

---

## Flow 2 — Review, then mint the request (the gate)

1. Sign in as **`apollo.staff@bloodlink.dev`** (Dr. Kavitha Rao, HOSPITAL).
2. **Review queue** shows the seeded pending requirement (O+, 2 units, URGENT).
   Click **Approve** — the reason box is coordination context, never clinical.
3. **Request board** now shows an "Approved requirements are waiting" banner.
   Click **Create O·2u request**, set urgency, confirm.
4. The new request opens in **COORDINATING-ready state OPEN**, and outreach fires:
   tier-1 donors within 15 km are notified. Open the request → **Outreach** card
   shows `tier 1, N candidates, M notified`. This is where matching happens.

Expected: `201`, status `OPEN`, `outreachTier = 1`, one `REQUEST_OPENED`
notification for the matched donor.

---

## Flow 3 — Donor accepts (explicit confirmation, D4)

1. Sign in as **`priya@bloodlink.dev`** (individual **and** donor, O−).
2. **Donor dashboard** lists the seeded emergency request from Apollo General with
   a distance band, never an address.
3. **Accept** → a confirmation modal appears. Cancelling that modal must not call
   the API — the endpoint requires `confirmation: "EXPLICIT"` and returns
   `422 CONFIRMATION_REQUIRED` otherwise.
4. Confirm. The request moves to **RESPONSES_RECEIVED**; the hospital is notified.
5. **My commitments** shows the response and lets you withdraw — withdrawing a
   *selected* donor pushes the request to **BACKUP_REQUIRED** with a reason.

Expected: `201`, `ACCEPTED`, and hospital-side status change.

---

## Flow 4 — Hospital coordinates and closes (D3)

1. Back as **`apollo.staff@bloodlink.dev`** → **Request board → Open** the request.
2. **Responders** card lists Priya with a distance band → **Select** → optionally
   keep another responder as **standby** → confirm.
   Status auto-advances to **COORDINATING**; the donor is told they were selected.
3. **Change status** offers only legal moves (`REQUEST_TRANSITIONS`):
   `FULFILLMENT_PENDING` → then **Confirm fulfilment** records the donation,
   starts the donor's 90-day cooldown, and closes the request (`FULFILLED`).
4. Try an illegal jump (e.g. OPEN → FULFILLED): the UI never offers it, and the
   API answers `409 REQUEST_INVALID_TRANSITION` if called directly.

Expected: `200`, request `FULFILLED`, one `donation_records` row, donor in cooldown.

---

## Flow 5 — Blood centre offers availability

1. Sign in as **`redcross.staff@bloodlink.dev`** (BLOOD CENTRE).
2. **Nearby requests** lists open requests within the radius as **distance bands**,
   with patient details absent. Widen the radius to 250 km.
3. **Offer availability** on a request (Available / Partial / Unavailable + units
   + note). The button flips to "Offer sent"; the offering hospital is notified
   (`ORGANIZATION_RESPONDED`).
4. **Your offers** shows the outcome column; the offer never changes the request
   lifecycle — D3 owns that.

Expected: `201`, repeat offers refused with `409 ORGANIZATION_RESPONSE_EXISTS`.

---

## Flow 6 — Admin, verification gate and audit

1. Sign in as **`admin@bloodlink.dev`** (ADMIN).
2. **Organizations**: verify *Sunrise Care* (pending), optionally suspend one.
3. **Users**: deactivate a user. **Audit trail**: every action above is recorded
   with actor, entity, and timestamp.
4. Verification gate demo: sign in as **`pend.staff@bloodlink.dev`** (pending
   hospital) — the workspace loads with a warning banner and every request-board
   call returns `403 ORGANIZATION_NOT_VERIFIED`. Approve the org as admin, reload,
   and the same account can now work.

Expected: `200` for admin, `403` with the specific code for the unverified org,
`401 UNAUTHENTICATED` for anonymous calls.

---

## Coordination threads (any flow, any time)

Request-scoped conversations keep contact inside the platform: open **Messages**
as the donor or the hospital after a selection, and note that the thread is keyed
to the request — no phone numbers, no addresses, and messages are plain text.

---

## What the demo deliberately does not do

Screening, testing, crossmatching, collection, processing, storage, issue and
transfusion stay with the hospital or blood centre. BloodLink coordinates:
verification, distance-first matching, tiered notifications, explicit acceptance
and coordination threads. No clinical data is stored anywhere in the system.

---

## Resetting between runs

Flows 1–4 consume the seeded dataset (the donor ends up in a 90-day cooldown).
Reset and start over:

- **SQLite:** stop the API → `make reset-db` → start the API (it re-seeds).
- **PostgreSQL:** `docs/database.md §4` — one `TRUNCATE … RESTART IDENTITY CASCADE`
  plus a reseed, or `dropdb`/`createdb` + `alembic upgrade head`.

Cheaper than clicking: `python3 scripts/smoke_flow.py` runs this whole walk
headlessly and prints `PASS`/`FAIL` per step. It refuses to start on an
already-consumed dataset and tells you how to reset.
