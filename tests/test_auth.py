"""Auth foundation tests (D1, spec §16)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_reports_database_ok(client):
    response = await client.get("/api/v1/platform/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] is None
    assert payload["data"]["status"] == "ok"
    assert payload["data"]["database"] == "ok"
    assert payload["meta"]["requestId"]


@pytest.mark.asyncio
async def test_every_response_uses_the_canonical_envelope(client, hospital):
    response = await client.get("/api/v1/auth/me", headers=hospital["headers"])
    body = response.json()
    assert set(body) == {"data", "meta", "error"}
    assert body["error"] is None
    assert body["data"]["role"] == "HOSPITAL"
    assert body["data"]["organization"]["name"] == "Apollo General Hospital"


@pytest.mark.asyncio
async def test_unauthorized_requests_return_401_envelope(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert body["data"] is None
    assert body["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_register_individual_then_login(client):
    payload = {
        "email": "created.user@example.org",
        "password": "StrongPass123",
        "fullName": "Created User",
        "phone": "9876543210",
        "role": "INDIVIDUAL",
    }
    created = await client.post("/api/v1/auth/register", json=payload)
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    assert data["user"]["role"] == "INDIVIDUAL"
    assert data["accessToken"] and data["refreshToken"]
    assert "patient_need.submit" in data["user"]["capabilities"]

    duplicate = await client.post("/api/v1/auth/register", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


@pytest.mark.asyncio
async def test_register_hospital_requires_organization_and_starts_pending(client):
    missing_org = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "noorg@example.org",
            "password": "StrongPass123",
            "fullName": "No Org",
            "role": "HOSPITAL",
        },
    )
    assert missing_org.status_code in (409, 422)

    created = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newhospital@example.org",
            "password": "StrongPass123",
            "fullName": "New Hospital Admin",
            "role": "HOSPITAL",
            "organization": {
                "name": "New Hospital",
                "orgType": "HOSPITAL",
                "city": "Chennai",
                "district": "Chennai",
                "latitude": 13.01,
                "longitude": 80.25,
            },
        },
    )
    assert created.status_code == 201, created.text
    user = created.json()["data"]["user"]
    assert user["organization"]["verificationStatus"] == "PENDING"
    assert user["organization"]["isOperational"] is False
    assert user["organization"]["orgType"] == "HOSPITAL"


@pytest.mark.asyncio
async def test_admin_cannot_self_register(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "sneaky.admin@example.org",
            "password": "StrongPass123",
            "fullName": "Sneaky Admin",
            "role": "ADMIN",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_weak_password_rejected(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.org",
            "password": "short",
            "fullName": "Weak Password",
            "role": "INDIVIDUAL",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_wrong_password_and_unknown_email_look_identical(client):
    wrong = await client.post(
        "/api/v1/auth/login", json={"email": "priya@bloodlink.dev", "password": "WrongPass123"}
    )
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "ghost@bloodlink.dev", "password": "WrongPass123"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


@pytest.mark.asyncio
async def test_refresh_rotates_and_revokes_the_old_token(client):
    session = await client.post(
        "/api/v1/auth/login", json={"email": "priya@bloodlink.dev", "password": "Bloodlink#2026"}
    )
    refresh_token = session.json()["data"]["refreshToken"]

    rotated = await client.post("/api/v1/auth/refresh", json={"refreshToken": refresh_token})
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["data"]["accessToken"]

    replay = await client.post("/api/v1/auth/refresh", json={"refreshToken": refresh_token})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client):
    session = await client.post(
        "/api/v1/auth/login", json={"email": "arjun@bloodlink.dev", "password": "Bloodlink#2026"}
    )
    refresh_token = session.json()["data"]["refreshToken"]

    logout = await client.post("/api/v1/auth/logout", json={"refreshToken": refresh_token})
    assert logout.status_code == 204

    after = await client.post("/api/v1/auth/refresh", json={"refreshToken": refresh_token})
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_pending_hospital_is_blocked_from_operations(client):
    session = await client.post(
        "/api/v1/auth/login", json={"email": "pend.staff@bloodlink.dev", "password": "Bloodlink#2026"}
    )
    headers = {"Authorization": f"Bearer {session.json()['data']['accessToken']}"}

    response = await client.get("/api/v1/hospital/patient-needs", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORGANIZATION_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_wrong_role_is_forbidden_not_hidden(client, donor):
    response = await client.get("/api/v1/hospital/patient-needs", headers=donor["headers"])
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_password_change_requires_current_password(client):
    session = await client.post(
        "/api/v1/auth/login", json={"email": "meera@bloodlink.dev", "password": "Bloodlink#2026"}
    )
    headers = {"Authorization": f"Bearer {session.json()['data']['accessToken']}"}

    bad = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"currentPassword": "not-the-password", "newPassword": "AnotherPass123"},
    )
    assert bad.status_code == 401
