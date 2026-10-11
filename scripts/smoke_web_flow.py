#!/usr/bin/env python3
"""Browser-shaped smoke test: drives the API through the Vite dev server.

The SPA never talks to the API directly in development — it calls relative
``/api/v1/...`` URLs and the Vite proxy forwards them to FastAPI. This script
reproduces exactly that path (default: http://127.0.0.1:5173) and asserts the
field names each screen reads, so a contract drift breaks here instead of in the
browser console.

    python3 scripts/smoke_web_flow.py [base_url] [--password ...]

It is read-only by design: log in, read the boards, check the shapes. Run it
against a pristine demo database so the seeded request is still discoverable.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:5173"
PASSWORD = "Bloodlink#2026"

ACCOUNTS = {
    "hospital": "apollo.staff@bloodlink.dev",
    "blood_centre": "redcross.staff@bloodlink.dev",
    "donor": "priya@bloodlink.dev",
    "individual": "meera@bloodlink.dev",
}

CHECKS = 0
FAILURES: list[str] = []


def call(path: str, *, method: str = "GET", token: str | None = None, body: dict | None = None):
    url = f"{BASE_URL}/api/v1{path}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        payload = error.read()
        try:
            return error.code, json.loads(payload or b"{}")
        except json.JSONDecodeError:
            return error.code, {"raw": payload.decode(errors="replace")}


def login(email: str) -> str:
    status, payload = call("/auth/login", method="POST", body={"email": email, "password": PASSWORD})
    check(status == 200, f"login {email}", f"status {status}")
    data = payload.get("data") or {}
    token = data.get("accessToken")
    check(bool(token), f"login {email} returned an access token")
    check("capabilities" in (data.get("user") or {}), f"login {email} returned capabilities")
    return token or ""


def check(condition: bool, label: str, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  ok  {label}")
    else:
        FAILURES.append(f"{label} {detail}".strip())
        print(f"FAIL  {label} {detail}".rstrip())


def expect_keys(payload: dict, keys: list[str], label: str) -> None:
    data = payload.get("data")
    missing = [key for key in keys if not isinstance(data, dict) or key not in data]
    check(not missing, f"{label} exposes {keys}", f"missing {missing}" if missing else "")


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else BASE_URL
    globals()["BASE_URL"] = base
    print(f"web smoke via {base}")

    print("\n[hospital] request board, detail, outreach")
    hospital = login(ACCOUNTS["hospital"])
    status, board = call("/blood-requests", token=hospital)
    check(status == 200, "GET /blood-requests", f"status {status}")
    expect_keys(board, ["items", "pagination"], "request board")
    items = (board.get("data") or {}).get("items") or []
    check(bool(items), "hospital sees at least the seeded request")
    item_keys = {"id", "reference", "bloodGroup", "component", "unitsRequired", "urgency",
                 "status", "requiredBy", "outreachTier", "responders"}
    if items:
        missing = sorted(item_keys - set(items[0]))
        check(not missing, "board row exposes the columns RequestsPage renders", f"missing {missing}")
        responders = items[0].get("responders") or {}
        check("accepted" in responders and "standby" in responders, "responder counts present")

    request_id = items[0]["id"] if items else None
    if request_id:
        status, detail = call(f"/blood-requests/{request_id}", token=hospital)
        check(status == 200, "GET /blood-requests/{id}", f"status {status}")
        expect_keys(detail, ["events", "responses", "outreach", "unitsCoordinated", "backupReason"],
                    "request detail")
        data = detail.get("data") or {}
        events = data.get("events") or []
        check(bool(events) and "eventType" in events[0], "lifecycle journal renders")
        for response in data.get("responses") or []:
            check("donorName" in response and "distanceBand" in response,
                  "responder row exposes name + distance band")
            check("latitude" not in response and "longitude" not in response,
                  "responder row never carries coordinates")
            break

        status, outreach = call(f"/blood-requests/{request_id}/outreach", token=hospital)
        check(status == 200, "GET /blood-requests/{id}/outreach", f"status {status}")
        expect_keys(outreach, ["tiers", "notified", "candidates", "unitsOutstanding"], "outreach summary")

    status, approved = call("/hospital/patient-needs", token=hospital)
    check(status == 200, "GET /hospital/patient-needs", f"status {status}")
    status, approved = call("/hospital/patient-needs?status=APPROVED", token=hospital)
    expect_keys(approved, ["items"], "approved needs (mint source)")

    print("\n[blood centre] nearby requests + offers")
    centre = login(ACCOUNTS["blood_centre"])
    status, nearby = call("/blood-requests/nearby?radiusKm=250", token=centre)
    check(status == 200, "GET /blood-requests/nearby", f"status {status}")
    expect_keys(nearby, ["items", "radiusKm", "centre"], "nearby view")
    for row in (nearby.get("data") or {}).get("items") or []:
        check("hasResponded" in row and "distanceBand" in row, "nearby row exposes band + hasResponded")
        check("latitude" not in row, "nearby row never carries coordinates")
        break

    status, offers = call("/blood-centres/responses", token=centre)
    check(status == 200, "GET /blood-centres/responses", f"status {status}")
    expect_keys(offers, ["items"], "blood-centre offers")

    print("\n[donor] matched requests")
    donor = login(ACCOUNTS["donor"])
    status, matched = call("/donor/matched-requests", token=donor)
    check(status == 200, "GET /donor/matched-requests", f"status {status}")
    expect_keys(matched, ["items", "donor"], "donor discovery")
    for row in (matched.get("data") or {}).get("items") or []:
        check("id" in row and "hospital" in row, "matched card exposes id + hospital")
        break

    print("\n[individual] my needs")
    individual = login(ACCOUNTS["individual"])
    status, needs = call("/patient-needs", token=individual)
    check(status == 200, "GET /patient-needs", f"status {status}")
    expect_keys(needs, ["items"], "individual needs list")

    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
    if FAILURES:
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("web flow smoke: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
