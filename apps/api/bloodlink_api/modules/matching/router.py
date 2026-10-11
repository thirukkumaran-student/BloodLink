"""Matching endpoints — OWNER: D4 (spec §11).

The matching *engine* is a service (``matching/service.py``) rather than a
public API surface: candidates are pushed to donors through notifications and
inspected by hospitals through the request detail endpoint (D3). What remains
here is configuration introspection plus the outreach-expansion trigger used by
D3's backup path.
"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from bloodlink_api.core.context import (
    CurrentPrincipal,
    require_authenticated,
    require_hospital_context,
)
from bloodlink_api.core.envelope import success
from bloodlink_api.core.errors import NotFoundError
from bloodlink_api.core.registry import ModuleSpec, register_module
from bloodlink_api.core.routing import api_router
from bloodlink_api.core.settings import get_settings
from bloodlink_api.db.models.blood_requests import BloodRequest
from bloodlink_api.db.session import get_db
from bloodlink_api.modules.matching import service as matching_service
from bloodlink_contracts.errors import ErrorCode

router = api_router(owner="D4", domain="matching", prefix="/matching")
#: Config is readable by any signed-in user; expansion is hospital-scoped in-body.
router.dependencies.append(Depends(require_authenticated))


@router.get("/config", summary="Active matching tiers and limits")
def matching_config(request: Request, principal: CurrentPrincipal) -> dict:
    """Return the deterministic matching configuration currently in force.

    OWNER: D4
    PURPOSE: Makes the tiering explicit to hospital staff ("should I widen the net?").
    INPUT: none
    OUTPUT: { tiers: [{ tier, radiusKm, limit }], cooldownDays, ranking }
    AUTHORIZATION: Any authenticated user (non-sensitive configuration).
    STATE CHANGES: none
    ERRORS: 401 UNAUTHENTICATED
    DEPENDENCIES: Settings (D1)
    MUST NOT: reveal donor counts or identities
    PRIVACY: configuration only
    """
    settings = get_settings()
    return success(
        request,
        {
            "ranking": "distance_first",
            "tiers": [
                {"tier": 1, "radiusKm": settings.match_tier1_radius_km, "limit": settings.match_tier1_limit},
                {"tier": 2, "radiusKm": settings.match_tier2_radius_km, "limit": settings.match_tier2_limit},
                {"tier": 3, "radiusKm": None, "limit": settings.match_tier3_limit},
            ],
            "cooldownDays": settings.donor_cooldown_days,
            "notes": [
                "Physical distance is the fundamental ranking criterion; district boundaries are not hard boundaries.",
                "Compatibility filters outreach only — BloodLink does not determine medical eligibility.",
                "Tier 2/3 outreach is triggered by the hospital's BACKUP_REQUIRED path.",
            ],
        },
    )


@router.post("/blood-requests/{request_id}/expand-outreach", summary="Widen outreach to the next tier")
def expand_outreach(
    request_id: str,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    hospital_principal=Depends(require_hospital_context),
) -> dict:
    """Escalate matching to the next tier for a request that needs backup.

    OWNER: D4
    PURPOSE: Failure path recovery (spec §9): standby -> expanded outreach.
    INPUT: path requestId
    OUTPUT: { tier, notified: int }
    AUTHORIZATION: Hospital users of the requesting organization.
    STATE CHANGES: DonorOutreach rows for the new tier; notifications dispatched
    ERRORS: 404 REQUEST_NOT_FOUND, 403 FORBIDDEN
    DEPENDENCIES: matching service, notifications service
    MUST NOT: notify the same donor twice for the same tier; bypass the privacy guard
    PRIVACY: payload contains group/component/urgency/distance band only
    """
    blood_request = db.get(BloodRequest, request_id)
    if blood_request is None:
        raise NotFoundError("Blood request not found", code=ErrorCode.REQUEST_NOT_FOUND)
    principal.require_own_organization(blood_request.hospital_id)

    next_tier = min(3, (blood_request.outreach_tier or 1) + 1)
    records = matching_service.expand_outreach(db, blood_request, next_tier=next_tier)
    from bloodlink_api.modules.notifications import service as notification_service

    notified = notification_service.notify_outreach_records(db, blood_request, records)
    blood_request.outreach_tier = next_tier
    db.commit()
    return success(request, {"tier": next_tier, "notified": notified})


MODULE = register_module(
    ModuleSpec(
        key="matching",
        owner="D4",
        domain="matching",
        api_prefix="/matching",
        description="Deterministic distance-first matching, tiering and outreach expansion.",
        foundation_status="IMPLEMENTED",
        router=router,
        depends_on=("notifications",),
    )
)
