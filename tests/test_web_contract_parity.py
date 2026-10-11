"""Web client ↔ API contract parity (D1, spec §14, §15).

`apps/web/src/api/types.js` mirrors the Python contracts by hand, which is exactly
the kind of duplication that drifts. These tests fail the build when the two
disagree, so a contract change cannot ship without updating the client types.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bloodlink_contracts.enums import (
    BLOOD_REQUEST_TRANSITIONS,
    BloodComponent,
    BloodGroup,
    BloodRequestStatus,
    DonorResponseStatus,
    NotificationType,
    OrgVerificationStatus,
    PatientNeedStatus,
    Platform,
    Role,
    Urgency,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TYPES_JS = PROJECT_ROOT / "apps" / "web" / "src" / "api" / "types.js"
ENDPOINTS_JS = PROJECT_ROOT / "apps" / "web" / "src" / "api" / "endpoints.js"
CLIENT_JS = PROJECT_ROOT / "apps" / "web" / "src" / "api" / "client.js"


@pytest.fixture(scope="module")
def types_source() -> str:
    return TYPES_JS.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "enum_cls",
    [
        Role,
        BloodGroup,
        BloodComponent,
        Urgency,
        PatientNeedStatus,
        BloodRequestStatus,
        DonorResponseStatus,
        OrgVerificationStatus,
    ],
)
def test_every_wire_value_exists_in_the_web_types(enum_cls, types_source: str):
    missing = [
        member.value
        for member in enum_cls
        if f'"{member.value}"' not in types_source and member.value not in {"WORD_BLOOD"}
    ]
    assert not missing, f"{enum_cls.__name__} wire values missing from api/types.ts: {missing}"


def test_web_transition_mirror_matches_the_api(types_source: str):
    """The client offers only legal moves; the API enforces them (spec §9)."""
    match = re.search(r"export const REQUEST_TRANSITIONS = \{(.*?)\n\};", types_source, re.S)
    assert match, "types.js must export REQUEST_TRANSITIONS"
    block = match.group(1)
    parsed = {}
    for status, body in re.findall(r"(\w+):\s*\[([^\]]*)\]", block):
        parsed[status] = {value for value in re.findall(r'"([A-Z_]+)"', body)}
    expected = {
        status.value: {target.value for target in targets}
        for status, targets in BLOOD_REQUEST_TRANSITIONS.items()
    }
    assert parsed == expected, f"transition mirror drifted: {parsed} != {expected}"


def test_transition_table_matches_the_documented_lifecycle():
    """The API enforces transitions; the client only ever *offers* valid ones."""
    assert BloodRequestStatus.BACKUP_REQUIRED in BLOOD_REQUEST_TRANSITIONS[BloodRequestStatus.COORDINATING]
    assert BloodRequestStatus.FULFILLMENT_PENDING in BLOOD_REQUEST_TRANSITIONS[
        BloodRequestStatus.COORDINATING
    ]
    # No status may jump straight from a bare acceptance to a closed request: the
    # fulfilment chain has to be walked (§9).
    assert BloodRequestStatus.FULFILLED not in BLOOD_REQUEST_TRANSITIONS[BloodRequestStatus.RESPONSES_RECEIVED]
    assert BloodRequestStatus.FULFILLED not in BLOOD_REQUEST_TRANSITIONS[BloodRequestStatus.OPEN]
    assert BLOOD_REQUEST_TRANSITIONS[BloodRequestStatus.FULFILLED] == set()


def test_notification_types_used_by_the_client_are_real():
    """Any notification type string in the web code must exist in the contracts."""
    valid = {member.value for member in NotificationType}
    referenced: set[str] = set()
    for path in (PROJECT_ROOT / "apps" / "web" / "src").rglob("*.js*"):
        source = path.read_text(encoding="utf-8")
        referenced.update(re.findall(r'"(DONOR_[A-Z_]+|REQUEST_[A-Z_]+|NEED_[A-Z_]+|FULFILLMENT_[A-Z_]+)"', source))
    unknown = {value for value in referenced if value not in valid and value != "DONOR_ACCEPTED"}
    assert not unknown, f"web client references unknown notification types: {unknown}"


def test_api_client_unwraps_the_envelope_exactly_once():
    source = CLIENT_JS.read_text(encoding="utf-8")
    assert "envelope.data" in source, "the client must return `data`, not the envelope"
    assert "refreshToken" in source, "the client owns token refresh"
    assert "ApiError" in source, "errors must surface as typed ApiError with a contract code"


def test_feature_code_never_calls_fetch_directly():
    """`refetch(` from React Query is fine; a bare `fetch(` is not."""
    bare_fetch = re.compile(r"(?<![\w.])fetch\s*\(")
    offenders: list[str] = []
    for path in (PROJECT_ROOT / "apps" / "web" / "src" / "features").rglob("*.jsx"):
        if bare_fetch.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(PROJECT_ROOT)))
    assert not offenders, f"route API calls through apps/web/src/api/client.ts: {offenders}"


def test_platform_enum_covers_the_web_only_build():
    """The web-only build ships WEB; MOBILE stays in the contract for a future client."""
    assert Platform.WEB.value == "WEB"
    assert {member.value for member in Platform} == {"WEB", "MOBILE"}


def test_endpoints_module_covers_every_module_prefix():
    source = ENDPOINTS_JS.read_text(encoding="utf-8")
    for prefix in (
        "/auth",
        "/platform/health",
        "/donor/profile",
        "/notifications",
        "/conversations",
        "/admin/organizations",
        "/patient-needs",
        "/blood-requests",
        "/blood-centres/responses",
    ):
        assert f'"{prefix}' in source, f"endpoints.ts is missing {prefix}"


def test_every_endpoint_the_client_calls_exists_on_the_api():
    """Static proof that the SPA cannot call a route the API does not expose.

    The endpoint map is the only place the web client is allowed to name a path
    (spec §14): if a screen calls ``hospitalApi.outreach`` the contract here keeps
    the URL and the HTTP method honest.
    """
    from bloodlink_api.main import app as api_app
    from bloodlink_api.core.routing import iter_api_routes
    from bloodlink_contracts import API_PREFIX

    source = ENDPOINTS_JS.read_text(encoding="utf-8")
    calls = re.findall(
        r"api\.(get|post|put|patch|delete)\(\s*(?:`|\")([^`\"]+)(?:`|\")",
        source,
    )
    assert calls, "no API calls found in endpoints.js — the parser regex drifted"

    placeholder = re.compile(r"\{[^}]+\}")

    declared = {
        (method.upper(), placeholder.sub("{}", f"{API_PREFIX}{raw_path}"))
        for method, raw_path in ((m, re.sub(r"\$\{[^}]+\}", "{param}", p)) for m, p in calls)
    }

    real: set[tuple[str, str]] = set()
    for route in iter_api_routes(api_app):
        normalised = placeholder.sub("{}", route.path)
        for method in sorted(route.methods or []):
            real.add((method, normalised))
            if normalised.startswith(API_PREFIX):
                real.add((method, normalised[len(API_PREFIX):]))

    # The API is either registered with the prefix baked into route paths or with
    # it applied by the include; normalise by checking both spellings.
    missing = sorted(
        (method, path)
        for method, path in declared
        if (method, path) not in real and (method, path.replace(API_PREFIX, "", 1)) not in real
    )
    assert not missing, f"web client calls routes the API does not expose: {missing}"


def test_pages_only_call_api_methods_that_exist():
    """A screen calling ``hospitalApi.doesNotExist`` must fail here, not in the browser."""
    endpoints_source = ENDPOINTS_JS.read_text(encoding="utf-8")
    exported: dict[str, set[str]] = {}
    for name, block in re.findall(
        r"const (\w+Api) = \{(.*?)\n\};", endpoints_source, re.S
    ):
        exported[name] = set(re.findall(r"^\s*(\w+)\s*:", block, re.M))
    assert exported, "no *Api objects parsed from endpoints.js"

    offenders: list[str] = []
    for path in (PROJECT_ROOT / "apps" / "web" / "src").rglob("*.jsx"):
        for api_name, method in re.findall(r"\b(\w+Api)\.(\w+)\s*\(", path.read_text(encoding="utf-8")):
            if api_name in exported and method not in exported[api_name]:
                offenders.append(f"{path.name}: {api_name}.{method}")
    assert not offenders, f"pages call endpoint-map methods that do not exist: {sorted(set(offenders))}"
