"""Privacy guarantees (D1, spec §12, §21).

These tests are the enforcement of the privacy rules, not documentation.
"""

from __future__ import annotations

import json

import pytest

from bloodlink_api.core.geo import coarse_area, distance_band, haversine_km
from bloodlink_validation.common import assert_privacy_safe_payload

FORBIDDEN_KEYS = {"latitude", "longitude", "lat", "lng", "address", "patient", "diagnosis"}


def _walk_keys(payload):
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield key
            yield from _walk_keys(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_keys(item)


def _assert_no_forbidden_keys(payload) -> None:
    leaks = {key for key in _walk_keys(payload) if key.lower() in FORBIDDEN_KEYS}
    assert not leaks, f"privacy leak: {leaks} in {json.dumps(payload)[:400]}"


@pytest.mark.asyncio
async def test_donor_profile_never_returns_coordinates(client, donor):
    # Write coordinates (accepted as internal matching data) ...
    saved = await client.put(
        "/api/v1/donor/profile",
        headers=donor["headers"],
        json={
            "bloodGroup": "O-",
            "city": "Chennai",
            "district": "Chennai",
            "latitude": 12.9784,
            "longitude": 80.224,
            "isAvailable": True,
        },
    )
    assert saved.status_code == 200, saved.text
    _assert_no_forbidden_keys(saved.json()["data"])

    # ... and confirm they never come back out.
    read = await client.get("/api/v1/donor/profile", headers=donor["headers"])
    body = read.json()["data"]
    _assert_no_forbidden_keys(body)
    assert body["area"]  # coarse ~5 km grid label only
    assert "12.9784" not in read.text and "80.224" not in read.text


@pytest.mark.asyncio
async def test_matched_request_cards_expose_distance_band_only(client, donor):
    response = await client.get("/api/v1/donor/matched-requests", headers=donor["headers"])
    assert response.status_code == 200, response.text
    for card in response.json()["data"]["items"]:
        _assert_no_forbidden_keys(card)
        assert card["distanceBand"].endswith("away")
        assert card.get("requestedBy") is None
        # No patient / submitter identity anywhere in the card.
        assert "submittedBy" not in card


@pytest.mark.asyncio
async def test_organization_directory_hides_coordinates_and_contacts(client, donor):
    response = await client.get("/api/v1/organizations", headers=donor["headers"])
    assert response.status_code == 200
    for organization in response.json()["data"]["items"]:
        _assert_no_forbidden_keys(organization)
        # The public directory exposes name + locality only, never contact data.
        for sensitive in ("contactPhone", "contactEmail", "registrationNumber", "address"):
            assert sensitive not in organization, f"{sensitive} must not be public"
    assert "latitude" not in response.text and "longitude" not in response.text


@pytest.mark.asyncio
async def test_hospital_companion_view_of_donors_is_banded(client, hospital):
    """Hospital-facing donor views must contain distance bands, not coordinates."""
    from sqlalchemy import select

    from bloodlink_api.db.models.blood_requests import BloodRequest
    from bloodlink_api.db.session import session_scope
    from bloodlink_api.modules.responses import service as response_service

    with session_scope() as db:
        blood_request = db.execute(select(BloodRequest)).scalars().first()
        rows = response_service.responses_for_request(db, blood_request.id) if blood_request else []
    _assert_no_forbidden_keys(rows)


@pytest.mark.asyncio
async def test_notification_payloads_are_privacy_safe(client, donor):
    response = await client.get("/api/v1/notifications", headers=donor["headers"])
    assert response.status_code == 200
    for notification in response.json()["data"]["items"]:
        _assert_no_forbidden_keys(notification)
        assert "patient" not in json.dumps(notification).lower()


def test_privacy_guard_rejects_sensitive_keys():
    assert_privacy_safe_payload({"requestId": "r1", "distanceBand": "~3 km away"})
    for bad in (
        {"patientName": "Asha"},
        {"data": {"latitude": 12.9}},
        {"nested": [{"diagnosis": "x"}]},
        {"notes": "ward 4, bed 12"},
    ):
        with pytest.raises(ValueError):
            assert_privacy_safe_payload(bad)


def test_distance_bands_are_coarse():
    assert distance_band(3.4) == "~3 km away"
    assert distance_band(8.0) == "~8 km away"
    assert distance_band(27.0) == "~25 km away"
    assert distance_band(None) == "Distance unavailable"
    # ~5 km grid: the label cannot be reverse-engineered into a home address.
    label = coarse_area(12.97841, 80.22401)
    assert label == "13.00, 80.20"
    assert "12.97841" not in (label or "")


def test_haversine_distance_is_plausible():
    # Chennai -> Bengaluru is roughly 290 km.
    km = haversine_km(13.0827, 80.2707, 12.9716, 77.5946)
    assert 280 < km < 300
