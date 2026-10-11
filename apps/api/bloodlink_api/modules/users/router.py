"""User-facing account endpoints (owner: D1)."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from bloodlink_api.core.clock import iso
from bloodlink_api.core.context import CurrentPrincipal
from bloodlink_api.core.envelope import success
from bloodlink_api.core.registry import ModuleSpec, register_module
from bloodlink_api.core.routing import api_router
from bloodlink_api.db.models.donors import DonationRecord
from bloodlink_api.db.session import get_db
from bloodlink_contracts.dto import APIModel

router = api_router(owner="D1", domain="users", prefix="/users", foundation_status="COMPLETE")


class ProfileUpdateRequest(APIModel):
    full_name: str | None = None
    phone: str | None = None


@router.get("/me/profile", summary="Read own profile")
def read_profile(request: Request, principal: CurrentPrincipal) -> dict:
    """Return the caller's account profile.

    OWNER: D1
    PURPOSE: Profile screen.
    INPUT: none
    OUTPUT: UserProfile
    AUTHORIZATION: Any authenticated user (self only).
    STATE CHANGES: none
    ERRORS: 401 UNAUTHENTICATED
    MUST NOT: read another user's profile from this endpoint
    PRIVACY: no donor coordinates; phone is the user's own
    """
    user = principal.user
    return success(
        request,
        {
            "id": user.id,
            "fullName": user.full_name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role.value,
            "initials": user.initials,
            "emailVerified": user.email_verified,
            "createdAt": iso(user.created_at),
            "organization": {
                "id": principal.organization.id,
                "name": principal.organization.name,
                "orgType": principal.organization.org_type.value,
                "verificationStatus": principal.organization.verification_status.value,
            }
            if principal.organization
            else None,
        },
    )


@router.patch("/me/profile", summary="Update own profile")
def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Update the caller's own display name / phone.

    OWNER: D1
    PURPOSE: Let users keep contact details current.
    INPUT: ProfileUpdateRequest
    OUTPUT: UserProfile
    AUTHORIZATION: Any authenticated user (self only).
    STATE CHANGES: User.fullName, User.phone
    ERRORS: 422 VALIDATION_ERROR
    MUST NOT: change role, organization or verification state
    PRIVACY: email changes require a separate verification flow (not in MVP)
    """
    from bloodlink_validation.common import clean_text, validate_person_name, validate_phone

    user = principal.user
    if payload.full_name is not None:
        user.full_name = validate_person_name(payload.full_name, field="Full name")
    if payload.phone is not None:
        user.phone = validate_phone(payload.phone) if payload.phone else None
    if payload.full_name is None and payload.phone is None:
        pass
    db.commit()
    return success(request, {"id": user.id, "fullName": user.full_name, "phone": user.phone})


@router.get("/me/donations", summary="Own donation history")
def donation_history(
    request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)
) -> dict:
    """Return the caller's own confirmed donation history.

    OWNER: D1 (route) / D4 (data meaning)
    PURPOSE: Personal donation record and cooldown context.
    INPUT: none
    OUTPUT: { items: [DonationRecordView] }
    AUTHORIZATION: Self only.
    STATE CHANGES: none
    ERRORS: 401 UNAUTHENTICATED
    DEPENDENCIES: DonationRecord (D4)
    MUST NOT: expose screening or clinical outcome data (BloodLink does not hold it)
    PRIVACY: hospital name + date + component only
    """
    from bloodlink_api.db.models.donors import DonorProfile

    profile = db.execute(
        select(DonorProfile).where(DonorProfile.user_id == principal.user_id)
    ).scalar_one_or_none()
    if profile is None:
        return success(request, {"items": []})

    rows = db.execute(
        select(DonationRecord)
        .where(DonationRecord.donor_profile_id == profile.id)
        .order_by(DonationRecord.confirmed_at.desc())
    ).scalars()
    return success(
        request,
        {
            "items": [
                {
                    "id": record.id,
                    "confirmedAt": iso(record.confirmed_at),
                    "bloodGroup": record.blood_group.value,
                    "component": record.component.value,
                    "units": record.units,
                    "hospitalReference": record.hospital_reference,
                }
                for record in rows
            ]
        },
    )


MODULE = register_module(
    ModuleSpec(
        key="users",
        owner="D1",
        domain="users",
        api_prefix="/users",
        description="Self-service profile and personal donation history.",
        foundation_status="COMPLETE",
        router=router,
        depends_on=("auth",),
    )
)
