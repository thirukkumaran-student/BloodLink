"""Contract, lifecycle and RBAC foundation tests (D1, spec §9, §15, §16, §27)."""

from __future__ import annotations

import pytest

from bloodlink_api.core.registry import all_modules
from bloodlink_api.core.routing import collect_contracts_from_app, parse_contract
from bloodlink_contracts.enums import (
    BLOOD_REQUEST_TRANSITIONS,
    TERMINAL_REQUEST_STATUSES,
    BloodRequestStatus,
    Role,
)
from bloodlink_contracts.permissions import CAPABILITIES_BY_ROLE, capabilities_for


def test_every_registered_module_declares_an_owner_and_status():
    modules = all_modules()
    assert len(modules) >= 12
    for module in modules:
        assert module.owner in {"D1", "D2", "D3", "D4"}, module
        assert module.foundation_status in {"COMPLETE", "SCAFFOLD", "IMPLEMENTED"}, module
        assert module.api_prefix.startswith("/")
        assert module.description


def test_every_endpoint_documents_its_contract(app):
    contracts = collect_contracts_from_app(app)
    assert len(contracts) >= 40, f"only found {len(contracts)} routes"

    undocumented = [c for c in contracts if c["owner"] not in {"D1", "D2", "D3", "D4"}]
    assert not undocumented, f"routes missing an OWNER: {[(c['method'], c['path']) for c in undocumented]}"

    missing_purpose = [c for c in contracts if not c["raw"].get("PURPOSE")]
    assert not missing_purpose, f"routes missing PURPOSE: {[(c['method'], c['path']) for c in missing_purpose]}"


def test_ownership_map_matches_the_spec():
    expected = {
        "patient_needs": "D2",
        "blood_requests": "D3",
        "matching": "D4",
        "responses": "D4",
        "notifications": "D4",
        "communication": "D4",
        "donations": "D4",
        "auth": "D1",
        "organizations": "D1",
    }
    by_key = {module.key: module.owner for module in all_modules()}
    for key, owner in expected.items():
        assert by_key.get(key) == owner, f"{key} should be owned by {owner}, found {by_key.get(key)}"


def test_contract_parser_reads_the_canonical_block():
    docstring = """
    POST /blood-requests

    OWNER: D3
    PURPOSE: Create an official BloodRequest from a verified PatientNeed.
    INPUT: CreateBloodRequestDto
    OUTPUT: BloodRequestResponse
    AUTHORIZATION: Hospital users only.
    MUST NOT:
    - perform donor matching
    - send push notifications directly
    """
    parsed = parse_contract(docstring)
    assert parsed["OWNER"] == "D3"
    assert "donor matching" in parsed["MUST NOT"]
    assert parsed["INPUT"] == "CreateBloodRequestDto"


def test_lifecycle_transition_table_is_sound():
    for status, targets in BLOOD_REQUEST_TRANSITIONS.items():
        assert status not in targets, f"{status} must not transition to itself"
        for target in targets:
            assert target in BloodRequestStatus

    # The documented happy path must exist (spec §9).
    happy = [
        BloodRequestStatus.OPEN,
        BloodRequestStatus.RESPONSES_RECEIVED,
        BloodRequestStatus.COVERED,
        BloodRequestStatus.COORDINATING,
        BloodRequestStatus.FULFILLMENT_PENDING,
        BloodRequestStatus.FULFILLMENT_CONFIRMED,
        BloodRequestStatus.FULFILLED,
    ]
    for current, following in zip(happy, happy[1:], strict=False):
        assert following in BLOOD_REQUEST_TRANSITIONS[current], f"{current} -> {following} missing"

    # Failure/backup path.
    assert BloodRequestStatus.BACKUP_REQUIRED in BLOOD_REQUEST_TRANSITIONS[BloodRequestStatus.COORDINATING]
    assert BloodRequestStatus.RESPONSES_RECEIVED in BLOOD_REQUEST_TRANSITIONS[BloodRequestStatus.BACKUP_REQUIRED]

    # Terminal states are terminal.
    for terminal in TERMINAL_REQUEST_STATUSES:
        assert not BLOOD_REQUEST_TRANSITIONS[terminal]


def test_rbac_capability_matrix_is_coherent():
    assert set(CAPABILITIES_BY_ROLE) == set(Role)
    for role, capabilities in CAPABILITIES_BY_ROLE.items():
        assert len(capabilities) == len(set(capabilities)), f"duplicate capability for {role}"
        assert all(isinstance(capability, str) and "." in capability for capability in capabilities)

    # Individuals and organizations must not silently share donor/clinical powers.
    assert "blood_request.create" not in capabilities_for(Role.INDIVIDUAL)
    assert "response.select_donor" not in capabilities_for(Role.BLOOD_CENTRE)
    assert "patient_need.review" not in capabilities_for(Role.INDIVIDUAL)
    assert "donor.profile_manage" in capabilities_for(Role.INDIVIDUAL)
    assert "donor.profile_manage" in capabilities_for(Role.HOSPITAL)


@pytest.mark.asyncio
async def test_platform_endpoints_are_public_and_describe_the_platform(client):
    modules = await client.get("/api/v1/platform/modules")
    assert modules.status_code == 200
    keys = {module["key"] for module in modules.json()["data"]["modules"]}
    assert {"auth", "patient_needs", "blood_requests", "matching"} <= keys

    version = await client.get("/api/v1/platform/version")
    assert version.json()["data"]["apiPrefix"] == "/api/v1"


@pytest.mark.asyncio
async def test_no_foundation_scaffold_remains(client, individual, hospital):
    """Every domain flow is implemented — nothing may answer 501 any more.

    The foundation sprint shipped D2/D3 as documented 501 scaffolds; this test is
    the guard that they were genuinely replaced rather than silently re-scaffolded.
    """
    probes = [
        ("/api/v1/patient-needs", individual["headers"]),
        ("/api/v1/patient-needs/reference/hospitals", individual["headers"]),
        ("/api/v1/hospital/patient-needs", hospital["headers"]),
        ("/api/v1/blood-requests", hospital["headers"]),
        ("/api/v1/matching/config", hospital["headers"]),
    ]
    for path, headers in probes:
        response = await client.get(path, headers=headers)
        assert response.status_code != 501, f"{path} is still scaffolded: {response.text}"
        assert response.status_code in (200, 403), f"{path} -> {response.status_code} {response.text}"


@pytest.mark.asyncio
async def test_admin_can_inspect_module_registry_and_verify_organizations(client, admin):
    registry = await client.get("/api/v1/admin/platform/modules", headers=admin["headers"])
    assert registry.status_code == 200
    assert len(registry.json()["data"]["modules"]) >= 12

    pending = await client.get(
        "/api/v1/admin/organizations", headers=admin["headers"], params={"verificationStatus": "PENDING"}
    )
    assert pending.status_code == 200
    items = pending.json()["data"]["items"]
    assert items, "seed data should include a pending organization"

    target = next(item for item in items if item["name"] == "Sunrise Care Hospital")
    verified = await client.post(
        f"/api/v1/admin/organizations/{target['id']}/verify", headers=admin["headers"]
    )
    assert verified.status_code == 200
    assert verified.json()["data"]["verificationStatus"] == "VERIFIED"

    suspended = await client.post(
        f"/api/v1/admin/organizations/{target['id']}/suspend", headers=admin["headers"]
    )
    assert suspended.json()["data"]["verificationStatus"] == "SUSPENDED"


@pytest.mark.asyncio
async def test_non_admin_cannot_read_the_audit_trail(client, hospital):
    response = await client.get("/api/v1/admin/audit", headers=hospital["headers"])
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_blood_centre_cannot_use_hospital_endpoints(client, blood_centre):
    response = await client.get("/api/v1/blood-requests", headers=blood_centre["headers"])
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_donor_directory_is_deliberately_unavailable(client, hospital):
    """A browsable donor directory would break §21 — the route must not exist."""
    response = await client.get("/api/v1/donor/lookup/donors", headers=hospital["headers"])
    assert response.status_code == 404
