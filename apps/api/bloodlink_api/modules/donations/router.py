"""Donation confirmation + history — OWNER: D4 (spec §5, §7, §10).

Key rule: ``DonorResponse = ACCEPTED`` is **not** a donation. A ``DonationRecord``
is created only when the hospital confirms fulfilment (D3's
``POST /blood-requests/{id}/confirm-fulfillment``) — this module owns that write
path via :func:`service.confirm_donations`.
"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from bloodlink_api.core.clock import iso
from bloodlink_api.core.context import CurrentPrincipal
from bloodlink_api.core.envelope import success
from bloodlink_api.core.errors import ForbiddenError
from bloodlink_api.core.registry import ModuleSpec, register_module
from bloodlink_api.core.routing import api_router
from bloodlink_api.db.models.donors import DonationRecord, DonorProfile
from bloodlink_api.db.session import get_db

router = api_router(owner="D4", domain="donations", prefix="/donations")


@router.get("", summary="My donation history")
def my_donations(
    request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)
) -> dict:
    """Return the caller's confirmed donations.

    OWNER: D4
    PURPOSE: Personal history + cooldown context (spec §5, §12).
    INPUT: none
    OUTPUT: { items: [DonationView], totalUnits: int }
    AUTHORIZATION: Self only.
    STATE CHANGES: none
    ERRORS: 401 UNAUTHENTICATED
    DEPENDENCIES: DonationRecord
    MUST NOT: include screening results or medical clearance — BloodLink never
              receives them (§2)
    PRIVACY: hospital name, date, component, units only
    """
    profile = db.execute(
        select(DonorProfile).where(DonorProfile.user_id == principal.user_id)
    ).scalar_one_or_none()
    if profile is None:
        return success(request, {"items": [], "totalUnits": 0})

    rows = db.execute(
        select(DonationRecord)
        .where(DonationRecord.donor_profile_id == profile.id)
        .order_by(DonationRecord.confirmed_at.desc())
    ).scalars()
    items = [
        {
            "id": row.id,
            "confirmedAt": iso(row.confirmed_at),
            "bloodGroup": row.blood_group.value,
            "component": row.component.value,
            "units": row.units,
            "hospitalReference": row.hospital_reference,
        }
        for row in rows
    ]
    return success(request, {"items": items, "totalUnits": sum(item["units"] for item in items)})


@router.get("/requests/{request_id}", summary="Donations recorded against a request")
def request_donations(
    request_id: str, request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)
) -> dict:
    """Return confirmed donations for a request the caller is involved in.

    OWNER: D4
    PURPOSE: Let hospitals and the donor see what was actually recorded.
    INPUT: path requestId
    OUTPUT: { items: [{ donorProfileId, displayName, units, confirmedAt }] }
    AUTHORIZATION: Hospital coordinators of the request, the donors involved, ADMIN.
    STATE CHANGES: none
    ERRORS: 403 NOT_A_PARTICIPANT
    MUST NOT: allow a blood centre to enumerate donors of a request
    PRIVACY: display name + units only; no location, no contact details
    """
    from bloodlink_api.db.models.blood_requests import BloodRequest
    from bloodlink_api.db.models.donors import DonorResponse

    blood_request = db.get(BloodRequest, request_id)
    if blood_request is None:
        raise ForbiddenError("You are not a participant in this request", code=None)

    is_hospital_staff = principal.organization_id == blood_request.hospital_id
    owns_response = db.execute(
        select(DonorResponse).where(
            DonorResponse.blood_request_id == request_id,
            DonorResponse.user_id == principal.user_id,
        )
    ).scalar_one_or_none() is not None
    if not (is_hospital_staff or owns_response or principal.is_admin):
        raise ForbiddenError("You are not a participant in this request")

    rows = db.execute(
        select(DonationRecord).where(DonationRecord.blood_request_id == request_id)
    ).scalars()
    items = []
    for row in rows:
        profile = db.get(DonorProfile, row.donor_profile_id)
        items.append(
            {
                "donorProfileId": row.donor_profile_id,
                "displayName": profile.display_name if profile else "Donor",
                "bloodGroup": row.blood_group.value,
                "component": row.component.value,
                "units": row.units,
                "confirmedAt": iso(row.confirmed_at),
            }
        )
    return success(request, {"items": items})


MODULE = register_module(
    ModuleSpec(
        key="donations",
        owner="D4",
        domain="donations",
        api_prefix="/donations",
        description="Donation confirmation records and donor history (cooldown source).",
        foundation_status="COMPLETE",
        router=router,
        depends_on=("auth", "responses", "notifications"),
    )
)
