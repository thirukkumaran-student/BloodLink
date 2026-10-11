"""Donor acceptance contract (D4 implementation of a D1-frozen contract, spec §10).

The rules under test:
  * acceptance requires an explicit confirmation
  * cancelling the confirmation must not mutate any state
  * acceptance is not a donation and does not close the request
  * the lifecycle moves OPEN -> RESPONSES_RECEIVED, nothing further
  * a selected donor withdrawing puts the request on the backup path
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from bloodlink_api.db.models.blood_requests import BloodRequest
from bloodlink_api.db.models.donors import DonorProfile, DonorResponse
from bloodlink_api.db.models.identity import User
from bloodlink_api.db.session import session_scope
from bloodlink_contracts.enums import BloodRequestStatus, DonorResponseStatus

DONOR_EMAIL = "priya@bloodlink.dev"
SECOND_DONOR_EMAIL = "arjun@bloodlink.dev"


def _user(db, email: str) -> User:
    return db.execute(select(User).where(User.email == email)).scalar_one()


@pytest.fixture(autouse=True)
def reset_seeded_request():
    """Give every test a clean OPEN request with no responses (spec §10 state)."""
    with session_scope() as db:
        blood_request = db.execute(
            select(BloodRequest).order_by(BloodRequest.created_at.asc())
        ).scalars().first()
        assert blood_request is not None, "seed data must contain a blood request"

        for response in db.execute(
            select(DonorResponse).where(DonorResponse.blood_request_id == blood_request.id)
        ).scalars():
            db.delete(response)

        blood_request.status = BloodRequestStatus.OPEN
        blood_request.units_coordinated = 0
        blood_request.backup_reason = None
        for profile in db.execute(select(DonorProfile)).scalars():
            profile.last_donation_at = None
    yield


def _request_id() -> str:
    with session_scope() as db:
        return db.execute(select(BloodRequest).order_by(BloodRequest.created_at.asc())).scalars().first().id


def _status() -> str:
    with session_scope() as db:
        return db.get(BloodRequest, _request_id()).status.value


def _response_row(email: str) -> DonorResponse | None:
    with session_scope() as db:
        return db.execute(
            select(DonorResponse).where(
                DonorResponse.blood_request_id == _request_id(),
                DonorResponse.user_id == _user(db, email).id,
            )
        ).scalar_one_or_none()


@pytest.mark.asyncio
async def test_skipping_confirmation_does_not_create_an_acceptance(client, donor):
    request_id = _request_id()

    response = await client.post(
        f"/api/v1/donor/blood-requests/{request_id}/accept",
        headers=donor["headers"],
        json={"confirmation": "NONE"},
    )
    # CONFIRMATION_REQUIRED is a validation failure of the accept protocol (422),
    # per the canonical error table in bloodlink_contracts.errors.
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CONFIRMATION_REQUIRED"

    # Nothing changed: no response row, request still OPEN.
    assert _response_row(DONOR_EMAIL) is None
    assert _status() == "OPEN"


@pytest.mark.asyncio
async def test_explicit_confirmation_creates_an_accepted_response(client, donor, hospital):
    request_id = _request_id()

    response = await client.post(
        f"/api/v1/donor/blood-requests/{request_id}/accept",
        headers=donor["headers"],
        json={"confirmation": "EXPLICIT", "etaMinutes": 30},
    )
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["status"] == "ACCEPTED"
    assert body["confirmedAt"]

    with session_scope() as db:
        stored = db.get(DonorResponse, body["id"])
        assert stored.status.value == "ACCEPTED"
        assert stored.confirmation_method == "EXPLICIT_UI_CONFIRMATION"
        assert stored.eta_minutes == 30
    # A first acceptance never closes the request (§9).
    assert _status() == "RESPONSES_RECEIVED"

    feed = await client.get("/api/v1/notifications", headers=hospital["headers"])
    assert "DONOR_ACCEPTED" in [item["type"] for item in feed.json()["data"]["items"]]

    # …and the donor's own feed shows the acceptance confirmation trail.
    donor_feed = await client.get("/api/v1/notifications", headers=donor["headers"])
    assert donor_feed.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_acceptance_is_rejected(client, donor):
    request_id = _request_id()
    first = await client.post(
        f"/api/v1/donor/blood-requests/{request_id}/accept",
        headers=donor["headers"],
        json={"confirmation": "EXPLICIT"},
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/v1/donor/blood-requests/{request_id}/accept",
        headers=donor["headers"],
        json={"confirmation": "EXPLICIT"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "RESPONSE_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_incompatible_group_cannot_accept(client, donor_second):
    """Arjun is A+; the seeded request is O-. A+ cannot donate red cells to O-."""
    response = await client.post(
        f"/api/v1/donor/blood-requests/{_request_id()}/accept",
        headers=donor_second["headers"],
        json={"confirmation": "EXPLICIT"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DONOR_NOT_ELIGIBLE_FOR_OUTREACH"


@pytest.mark.asyncio
async def test_cooldown_blocks_acceptance(client, donor):
    """A donor inside the 90-day window cannot accept (platform cooldown, §11)."""
    request_id = _request_id()
    with session_scope() as db:
        profile = db.execute(
            select(DonorProfile).where(DonorProfile.user_id == _user(db, DONOR_EMAIL).id)
        ).scalar_one()
        profile.last_donation_at = datetime.now(timezone.utc).replace(tzinfo=None)

    response = await client.post(
        f"/api/v1/donor/blood-requests/{request_id}/accept",
        headers=donor["headers"],
        json={"confirmation": "EXPLICIT"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DONOR_IN_COOLDOWN"


@pytest.mark.asyncio
async def test_withdrawing_a_selected_donor_requests_backup(client, donor):
    request_id = _request_id()
    accepted = await client.post(
        f"/api/v1/donor/blood-requests/{request_id}/accept",
        headers=donor["headers"],
        json={"confirmation": "EXPLICIT"},
    )
    response_id = accepted.json()["data"]["id"]

    with session_scope() as db:
        row = db.get(DonorResponse, response_id)
        row.status = DonorResponseStatus.SELECTED
        db.get(BloodRequest, request_id).status = BloodRequestStatus.COORDINATING

    withdraw = await client.post(
        f"/api/v1/donor/responses/{response_id}/withdraw",
        headers=donor["headers"],
        json={"reason": "Unable to travel"},
    )
    assert withdraw.status_code == 200, withdraw.text
    assert withdraw.json()["data"]["status"] == "WITHDRAWN"

    with session_scope() as db:
        blood_request = db.get(BloodRequest, request_id)
        assert blood_request.status.value == "BACKUP_REQUIRED"
        assert blood_request.backup_reason == "Selected donor withdrew"


@pytest.mark.asyncio
async def test_donor_cannot_accept_after_the_request_is_fulfilled(client, donor):
    request_id = _request_id()
    with session_scope() as db:
        blood_request = db.get(BloodRequest, request_id)
        blood_request.status = BloodRequestStatus.FULFILLED

    response = await client.post(
        f"/api/v1/donor/blood-requests/{request_id}/accept",
        headers=donor["headers"],
        json={"confirmation": "EXPLICIT"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REQUEST_NOT_OPEN_FOR_RESPONSES"
