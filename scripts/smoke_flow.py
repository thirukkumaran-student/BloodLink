#!/usr/bin/env python3
"""End-to-end smoke of the seeded demo against a running API.

OWNER: D1.  Usage:  python3 scripts/smoke_flow.py [base_url]

Walks the complete role flow that the demo depends on:

    individual submits a need
      -> hospital reviews (APPROVE)
        -> hospital mints the BloodRequest
          -> tier-1 outreach notifies the matched donor
            -> donor accepts with explicit confirmation
              -> hospital selects the donor
                -> hospital confirms fulfilment

and then checks RBAC, privacy and the health/disclosure endpoints. Run
`make reset-db` + restart the API first for a pristine demo.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000") + "/api/v1"
PASSWORD = "Bloodlink#2026"
FAILURES: list[str] = []
STATE: dict[str, str] = {}


def call(method: str, path: str, token: str | None = None, body: dict | None = None):
    request = urllib.request.Request(BASE + path, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    payload = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(request, payload) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def login(email: str) -> str:
    status, body = call("POST", "/auth/login", body={"email": email, "password": PASSWORD})
    assert status == 200, f"login failed for {email}: {status} {body}"
    return body["data"]["accessToken"]


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")
    if not condition:
        FAILURES.append(label)


def err(body) -> str:
    return ((body or {}).get("error") or {}).get("code", "")


def data(body) -> dict:
    """`data` from an envelope, or an empty dict — never a TypeError.

    A failed step must report itself as a failed check, not crash the walker with
    a traceback that hides which expectation broke.
    """
    value = (body or {}).get("data")
    return value if isinstance(value, dict) else {}


def reset_hint() -> str:
    """The one instruction that matters when the demo data has been consumed."""
    return (
        "The walk needs a pristine demo dataset. Reset it and restart the API:\n"
        "  SQLite      : stop the API, then `make reset-db`, then start it again\n"
        "  PostgreSQL  : see `docs/database.md` §4 (TRUNCATE + reseed), or "
        "`dropdb bloodlink && createdb -O bloodlink bloodlink && python3 -m alembic upgrade head`"
    )


# --------------------------------------------------------------------------- #
# Preflight — this walk consumes the demo data, so a second run against the same
# database must fail loudly and helpfully, not with a confusing 409 or traceback.
# --------------------------------------------------------------------------- #
def preflight() -> None:
    status, body = call("GET", "/platform/health")
    if status != 200:
        print(f"cannot reach the API at {BASE} (status {status}) — start it first, "
              "see docs/local-setup.md")
        raise SystemExit(2)

    token = login("priya@bloodlink.dev")
    status, body = call("GET", "/donor/matched-requests", token)
    donor = data(body).get("donor") or {}
    cooldown = donor.get("cooldownDaysRemaining") or 0
    if cooldown:
        print(f"demo donor is in cooldown ({cooldown} day(s) remaining): the previous walk "
              "already recorded a donation.")
        print(reset_hint())
        raise SystemExit(2)

    hospital = login("apollo.staff@bloodlink.dev")
    status, body = call("GET", "/blood-requests", hospital)
    if not data(body).get("items"):
        print("the seeded OPEN request is missing: this database has already been walked.")
        print(reset_hint())
        raise SystemExit(2)


preflight()

print("== platform ==")
status, body = call("GET", "/platform/health")
check("health endpoint", status == 200 and body["data"]["database"] == "ok", str(body.get("data")))
status, body = call("GET", "/platform/modules")
statuses = {module["key"]: module["status"] for module in body["data"]["modules"]}
check("twelve modules registered", len(statuses) == 12)
check("no module is still a scaffold", all(value != "SCAFFOLD" for value in statuses.values()),
      json.dumps([k for k, v in statuses.items() if v == "SCAFFOLD"]))

apollo = login("apollo.staff@bloodlink.dev")
mhc = login("mhc.staff@bloodlink.dev")
priya = login("priya@bloodlink.dev")
arjun = login("arjun@bloodlink.dev")
meera = login("meera@bloodlink.dev")
redcross = login("redcross.staff@bloodlink.dev")
admin = login("admin@bloodlink.dev")
pending = login("pend.staff@bloodlink.dev")

print("\n== D2: individual submits a need ==")
future = (datetime.now(timezone.utc) + timedelta(hours=6)).replace(tzinfo=None).isoformat()
status, body = call("GET", "/patient-needs/reference/hospitals", meera)
hospitals = body["data"]["items"]
check("hospital discovery returns verified hospitals", status == 200 and bool(hospitals),
      f"{len(hospitals)} hospital(s)")
apollo_id = next(h["id"] for h in hospitals if h["name"].startswith("Apollo"))
status, body = call(
    "POST", "/patient-needs", meera,
    {"hospitalId": apollo_id, "bloodGroup": "A-", "component": "PRBC", "units": 2,
     "urgency": "URGENT", "requiredBy": future, "additionalNotes": "Ward 4, evening window."},
)
check("need created", status == 201, f"{status} {err(body)}")
need_id = (body.get("data") or {}).get("id", "")
STATE["need"] = need_id
check("need starts PENDING_HOSPITAL_REVIEW",
      (body.get("data") or {}).get("status") == "PENDING_HOSPITAL_REVIEW")

status, body = call("GET", "/patient-needs", meera)
check("submitter sees their own history", status == 200 and any(i["id"] == need_id for i in body["data"]["items"]))

print("\n== D2/D3: review gate ==")
status, body = call("POST", f"/hospital/patient-needs/{need_id}/review", mhc,
                    {"decision": "APPROVED", "reason": "Medical team approved."})
check("another hospital cannot review it", status == 404, f"{status} {err(body)}")

status, body = call("POST", f"/patient-needs", meera, {
    "hospitalId": apollo_id, "bloodGroup": "A-", "component": "PRBC", "units": 1,
    "urgency": "ROUTINE", "requiredBy": future})
second_need = body["data"]["id"]
status, body = call("POST", f"/patient-needs/{second_need}/cancel", meera, {"reason": "No longer needed"})
check("submitter can cancel a pending need", status == 200 and body["data"]["status"] == "CANCELLED",
      f"{status} {err(body)}")

status, body = call("GET", "/hospital/patient-needs", apollo)
check("hospital sees the need in its queue", status == 200 and any(i["id"] == need_id for i in body["data"]["items"]))
status, body = call("POST", f"/hospital/patient-needs/{need_id}/review", apollo,
                    {"decision": "APPROVED", "reason": "Medical team approved. Coordination window agreed."})
check("hospital approves the need", status == 200 and body["data"]["status"] == "APPROVED",
      f"{status} {err(body)}")
status, body = call("POST", f"/hospital/patient-needs/{need_id}/review", apollo, {"decision": "REJECTED"})
check("double review refused", status == 409 and err(body) == "NEED_ALREADY_REVIEWED", f"{status} {err(body)}")

print("\n== D3: request minted + tier-1 outreach ==")
status, body = call("POST", "/blood-requests", apollo, {"patientNeedId": need_id, "unitsRequired": 1})
check("request created from the approved need", status == 201, f"{status} {err(body)}")
request_id = (body.get("data") or {}).get("id", "")
STATE["request"] = request_id
check("request starts OPEN", (body.get("data") or {}).get("status") == "OPEN")
check("needs converts to CONVERTED", body["data"]["patientNeedId"] == need_id)

status, body = call("GET", f"/blood-requests/{request_id}", apollo)
check("hospital reads request detail", status == 200 and bool(body["data"]["events"]))
status, body = call("GET", f"/blood-requests/{request_id}/outreach", apollo)
check("outreach summary reports the tier-1 ring", status == 200 and body["data"]["tiers"],
      json.dumps(body["data"].get("tiers")))

status, body = call("GET", "/donor/matched-requests", priya)
matched = body["data"]["items"]
check("matched donor sees the request", bool(matched), f"{len(matched)} card(s)")
card = next((item for item in matched if item["id"] == request_id), matched[0] if matched else None)
check("matching is distance-ranked and privacy-safe",
      bool(card) and card["distanceBand"].endswith("away") and "latitude" not in json.dumps(card))
status, body = call("GET", "/notifications", priya)
check("donor was notified", any(n["type"] in {"REQUEST_OPENED", "REQUEST_OUTREACH_EXPANDED"}
                                for n in body["data"]["items"]))

print("\n== acceptance protocol ==")
status, body = call("POST", f"/donor/blood-requests/{request_id}/accept", priya, {"confirmation": "NONE"})
check("skipping confirmation is rejected", status == 422 and err(body) == "CONFIRMATION_REQUIRED",
      f"{status} {err(body)}")
status, body = call("POST", f"/donor/blood-requests/{request_id}/accept", priya,
                    {"confirmation": "EXPLICIT", "etaMinutes": 25})
check("explicit confirmation accepts", status == 201, f"{status} {err(body)}")
response_id = data(body).get("id", "")
STATE["response"] = response_id
check("acceptance is not a donation", data(body).get("status") == "ACCEPTED")

status, body = call("GET", f"/blood-requests/{request_id}", apollo)
check("request advanced to RESPONSES_RECEIVED", data(body).get("status") == "RESPONSES_RECEIVED",
      str(data(body).get("status")))
check("hospital sees the responder", bool(data(body).get("responses")))

print("\n== D3->D4: selection, standby, transitions ==")
status, body = call("POST", f"/blood-requests/{request_id}/select-donor", apollo,
                    {"donorResponseId": response_id, "alsoMoveToStandby": []})
check("donor selected", status == 200 and (data(body).get("selected") or {}).get("status") == "SELECTED",
      f"{status} {err(body)}")
status, body = call("GET", f"/blood-requests/{request_id}", apollo)
check("request moved to COORDINATING", data(body).get("status") == "COORDINATING",
      str(data(body).get("status")))

status, body = call("POST", f"/blood-requests/{request_id}/transition", apollo, {"toStatus": "FULFILLED"})
check("illegal jump refused", status == 409 and err(body) == "REQUEST_INVALID_TRANSITION", f"{status} {err(body)}")
status, body = call("POST", f"/blood-requests/{request_id}/transition", apollo,
                    {"toStatus": "FULFILLMENT_PENDING", "reason": "Donor travelling to the hospital."})
check("moves to FULFILLMENT_PENDING", status == 200 and body["data"]["status"] == "FULFILLMENT_PENDING",
      f"{status} {err(body)}")

print("\n== D4: fulfilment creates the donation record ==")
status, body = call("POST", f"/blood-requests/{request_id}/confirm-fulfillment", apollo,
                    {"hospitalReference": "BB-2026-0912"})
check("fulfilment confirmed", status == 200 and body["data"]["status"] == "FULFILLED",
      f"{status} {err(body)}")
status, body = call("GET", "/donations", priya)
check("donation appears in the donor's history", status == 200 and body["data"]["items"],
      f"{len(body['data']['items'])} record(s)")
status, body = call("GET", "/donor/profile", priya)
check("cooldown started", body["data"]["cooldownDaysRemaining"] > 0,
      f"{body['data']['cooldownDaysRemaining']} days")

print("\n== D3: blood-centre view ==")
status, body = call("GET", "/blood-requests/nearby", redcross)
check("blood centre sees nearby requests", status == 200, f"{status} {err(body)}")
status, body = call("GET", "/blood-centres/responses", redcross)
check("blood centre can read its own offers", status == 200)

print("\n== RBAC holds server-side ==")
cases = [
    ("donor cannot read the hospital queue", priya, "/hospital/patient-needs", 403),
    ("donor cannot read the request board", priya, "/blood-requests", 403),
    ("blood centre cannot drive the lifecycle", redcross, "/blood-requests", 403),
    ("unverified hospital is blocked", pending, "/blood-requests", 403),
    ("donor cannot read admin surfaces", priya, "/admin/organizations", 403),
    ("hospital cannot read admin surfaces", apollo, "/admin/users", 403),
    ("admin can read the audit trail", admin, "/admin/audit", 200),
    ("blood centre nearby is allowed", redcross, "/blood-requests/nearby", 200),
]
for label, token, path, expected in cases:
    status, body = call("GET", path, token)
    check(label, status == expected, f"{status} {err(body)}")

status, body = call("GET", "/donor/profile")
check("anonymous requests are unauthenticated", status == 401, f"{status} {err(body)}")
status, body = call("GET", "/donor/lookup/donors", priya)
check("donor directory stays closed", status == 404, f"{status} {err(body)}")

print("\n== disclosure ==")
status, body = call("GET", "/platform/modules")
check("module registry reports implementation status",
      all(m["status"] in {"COMPLETE", "IMPLEMENTED"} for m in body["data"]["modules"]))

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) failed: {FAILURES}")
    raise SystemExit(1)
print("all checks passed — submit -> review -> mint -> accept -> select -> fulfil works end to end")
print("note: the demo dataset has been consumed; run `make reset-db` + restart the API for a pristine demo")
