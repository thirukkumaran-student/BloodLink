"""Routing conventions (owner: D1, spec §14, §15).

Feature developers declare a domain router with :func:`api_router` and annotate
each endpoint with the canonical contract docstring. The docstring blocks are
parsed by ``scripts/export_contracts.py`` and rendered into
``docs/api-contracts.md`` + ``docs/ownership.md``, so the published contracts can
never silently drift from the code the way hand-written docs do.

Contract block format (all sections optional except OWNER):

    POST /blood-requests

    OWNER: D3
    PURPOSE: ...
    INPUT: CreateBloodRequestDto
    OUTPUT: BloodRequestResponse
    AUTHORIZATION: Hospital users in a verified hospital organization.
    STATE CHANGES: BloodRequest(OPEN)
    ERRORS: 403 ORGANIZATION_NOT_VERIFIED, 404 NEED_NOT_FOUND, 409 CONFLICT
    DEPENDENCIES: Verified PatientNeed
    MUST NOT: perform donor matching, send push notifications directly
    PRIVACY: no patient identity in responses to donors
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable

from fastapi import APIRouter

OWNERS = ("D1", "D2", "D3", "D4")

_SECTION_RE = re.compile(r"^\s{0,8}([A-Z][A-Z ()/&'-]{2,}):\s*(.*)$")


def api_router(*, owner: str, domain: str, prefix: str, foundation_status: str = "SCAFFOLD") -> APIRouter:
    """Build a domain router with consistent tagging and ownership metadata.

    ``owner`` must be one of D1..D4; ownership is part of the contract (spec §22).
    """
    if owner not in OWNERS:
        raise ValueError(f"Unknown owner {owner!r}; expected one of {OWNERS}")
    return APIRouter(
        prefix=prefix,
        tags=[domain, f"owner:{owner}", f"status:{foundation_status}"],
        responses={
            401: {"description": "Missing or invalid bearer token"},
            403: {"description": "Authenticated but not authorized"},
            422: {"description": "Validation error"},
        },
    )


def parse_contract(docstring: str | None) -> dict[str, Any]:
    """Parse a canonical endpoint contract block into a dict."""
    sections: dict[str, str] = {}
    current: str | None = None
    for line in (docstring or "").splitlines():
        match = _SECTION_RE.match(line)
        if match:
            current = match.group(1).strip().upper()
            rest = match.group(2).strip()
            sections[current] = rest
        elif current and line.strip():
            sections[current] = f"{sections[current]} {line.strip()}".strip()
    return sections


_OWNER_TOKEN_RE = re.compile(r"^\s*(D[1-4])\b")


def _registry_status_for_path(path: str) -> str | None:
    """Resolve a route's implementation status from the module registry.

    The registry owns the status (``ModuleSpec.foundation_status``); the router's
    ``status:`` tag is only a fallback for routes that belong to no module. This
    keeps ``docs/api-contracts.md`` honest without asking every endpoint to repeat
    the status line.
    """
    from bloodlink_contracts import API_PREFIX

    from bloodlink_api.core.registry import all_modules

    relative = path[len(API_PREFIX) :] if path.startswith(API_PREFIX) else path
    best: tuple[int, str] | None = None
    for module in all_modules():
        prefixes = [module.api_prefix]
        prefixes.extend(getattr(extra, "prefix", "") for extra in module.extra_routers)
        for prefix in prefixes:
            if not prefix or not (relative == prefix or relative.startswith(f"{prefix}/")):
                continue
            if best is None or len(prefix) > best[0]:
                best = (len(prefix), module.foundation_status)
    return best[1] if best else None


def endpoint_contract(route: Any) -> dict[str, Any]:
    contract = parse_contract(getattr(route.endpoint, "__doc__", None))
    # `OWNER: D3 (route) — D4 owns the data` etc.: keep the leading token only,
    # and leave anything unrecognised as UNASSIGNED so the contract test fails
    # loudly instead of silently attributing a route to the wrong developer.
    owner_raw = contract.get("OWNER", "")
    owner_match = _OWNER_TOKEN_RE.match(owner_raw)
    owner = owner_match.group(1) if owner_match else "UNASSIGNED"
    # The module registry is the single source of truth for implementation status:
    # `api_router(foundation_status=...)` tags every route it builds, so an endpoint
    # only documents STATUS when it needs to differ from its module.
    tag_status = next(
        (
            tag.split(":", 1)[1]
            for tag in (getattr(route, "tags", None) or [])
            if tag.startswith("status:")
        ),
        None,
    )
    registry_status = _registry_status_for_path(route.path)
    return {
        "method": ",".join(sorted(route.methods or [])),
        "path": route.path,
        "name": route.name,
        "summary": contract.get("PURPOSE") or route.summary or route.name.replace("_", " ").title(),
        "owner": owner,
        "ownerNote": owner_raw.strip() or None,
        "status": contract.get("STATUS") or registry_status or tag_status or "IMPLEMENTED",
        "authorization": contract.get("AUTHORIZATION"),
        "input": contract.get("INPUT"),
        "output": contract.get("OUTPUT"),
        "stateChanges": contract.get("STATE CHANGES"),
        "errors": contract.get("ERRORS"),
        "dependencies": contract.get("DEPENDENCIES"),
        "mustNot": contract.get("MUST NOT"),
        "privacy": contract.get("PRIVACY"),
        "raw": contract,
    }


def collect_contracts(routers: Iterable[APIRouter]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for router in routers:
        for route in router.routes:
            if getattr(route, "methods", None) and getattr(route, "endpoint", None):
                contracts.append(endpoint_contract(route))
    return sorted(contracts, key=lambda item: (item["owner"], item["path"], item["method"]))


# --------------------------------------------------------------------------- #
# Route introspection
# --------------------------------------------------------------------------- #
def _mount_prefix(included) -> str:
    """Recover the prefix a router was mounted under (FastAPI >= 0.140)."""
    context = getattr(included, "include_context", None)
    prefix = getattr(context, "prefix", None)
    if isinstance(prefix, str):
        return prefix
    if isinstance(context, dict):
        return str(context.get("prefix") or "")
    return ""


def iter_api_routes(app_or_router, *, prefix: str = "") -> list[Any]:
    """Return every concrete API route with its *effective* path.

    FastAPI >= 0.140 keeps included routers as a single ``_IncludedRouter`` object
    on ``app.routes`` instead of copying each endpoint up, so the mount prefix has
    to be threaded through manually. Both shapes are handled, which keeps the
    contract exporter, the docs generator and the tests pointing at the same list.
    """
    from fastapi.routing import APIRoute

    collected: list[Any] = []
    stack: list[tuple[Any, str]] = [(route, prefix) for route in getattr(app_or_router, "routes", [])]
    while stack:
        route, current_prefix = stack.pop(0)
        if isinstance(route, APIRoute):
            collected.append(_with_path_prefix(route, current_prefix))
            continue
        nested = getattr(route, "original_router", None) or getattr(route, "router", None)
        if nested is not None and hasattr(nested, "routes"):
            nested_prefix = current_prefix + _mount_prefix(route)
            stack = [(child, nested_prefix) for child in nested.routes] + stack
            continue
        if hasattr(route, "routes"):
            stack = [(child, current_prefix) for child in route.routes] + stack
    return collected


def _with_path_prefix(route: Any, prefix: str) -> Any:
    """Return the route with its effective path, so consumers see `/api/v1/...`."""
    if not prefix:
        return route
    clone = copy.copy(route)
    clone.path = f"{prefix.rstrip('/')}{route.path}"
    return clone


def collect_contracts_from_app(app) -> list[dict[str, Any]]:
    """Collect canonical endpoint contracts from a mounted application."""
    contracts = [endpoint_contract(route) for route in iter_api_routes(app)]
    return sorted(contracts, key=lambda item: (item["owner"], item["path"], item["method"]))
