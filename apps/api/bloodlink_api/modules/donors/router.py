"""Donor profile + hospital subscription endpoints — OWNER: D4."""

from __future__ import annotations

from fastapi import Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from bloodlink_api.core.audit import record
from bloodlink_api.core.clock import iso, utcnow
from bloodlink_api.core.context import CurrentPrincipal, require_donor_profile
from bloodlink_api.core.envelope import success
from bloodlink_api.core.errors import ConflictError, NotFoundError
from bloodlink_api.core.geo import coarse_area, distance_band, distance_km
from bloodlink_api.core.registry import ModuleSpec, register_module
from bloodlink_api.core.routing import api_router
from bloodlink_api.db.models.donors import DonorProfile, HospitalSubscription
from bloodlink_api.db.models.identity import Organization, User
from bloodlink_api.db.session import get_db
from bloodlink_contracts.dto import APIModel
from bloodlink_contracts.enums import BloodGroup, OrgVerificationStatus, Urgency
from bloodlink_contracts.errors import ErrorCode
from bloodlink_validation.blood import COMPATIBLE_RECIPIENTS_FOR, cooldown_remaining_days
from bloodlink_validation.common import clean_text, validate_coordinates
from bloodlink_api.core.settings import get_settings

router = api_router(owner="D4", domain="donor-profile", prefix="/donor")


class DonorProfileRequest(APIModel):
    """INPUT DTO for PUT /donor/profile.

    Coordinates are accepted here and stored as internal matching data. They are
    never echoed back by any read endpoint (spec §21).
    """

    blood_group: BloodGroup
    date_of_birth: str | None = None  # ISO date
    weight_kg: float | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    pincode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    is_available: bool = True
    accepts_notifications: bool = True
    notify_emergency_only: bool = False
    acknowledged_screening_notice: bool = True
    notes: str | None = None


class AvailabilityRequest(APIModel):
    is_available: bool
    accepts_notifications: bool | None = None


class SubscriptionRequest(APIModel):
    hospital_id: str
    blood_groups: list[BloodGroup] = []
    max_urgency: Urgency | None = None


def _serialise_profile(profile: DonorProfile) -> dict:
    """Privacy-safe donor profile view — no coordinates, ever."""
    return {
        "id": profile.id,
        "bloodGroup": profile.blood_group.value,
        "city": profile.city,
        "district": profile.district,
        "state": profile.state,
        "area": coarse_area(profile.latitude, profile.longitude),
        "isAvailable": profile.is_available,
        "acceptsNotifications": profile.accepts_notifications,
        "notifyEmergencyOnly": profile.notify_emergency_only,
        "lastDonationAt": iso(profile.last_donation_at),
        "totalDonations": profile.total_donations,
        "cooldownDaysRemaining": cooldown_remaining_days(
            profile.last_donation_at, get_settings().donor_cooldown_days, as_of=utcnow()
        ),
        "canDonateTo": sorted(group.value for group in COMPATIBLE_RECIPIENTS_FOR[profile.blood_group]),
    }


@router.get("/profile", summary="Read my donor profile")
def read_profile(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    profile: DonorProfile = Depends(require_donor_profile),
) -> dict:
    """Return the caller's donor profile (privacy-safe projection).

    OWNER: D4
    PURPOSE: Donor settings screen.
    INPUT: none
    OUTPUT: DonorProfileView
    AUTHORIZATION: Authenticated donor.
    STATE CHANGES: none
    ERRORS: 403 DONOR_PROFILE_REQUIRED
    MUST NOT: return latitude/longitude (spec §21)
    """
    return success(request, _serialise_profile(profile))


@router.put("/profile", summary="Create or update my donor profile")
def upsert_profile(
    payload: DonorProfileRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Create or replace the caller's donor profile.

    OWNER: D4
    PURPOSE: Opt into donation and manage matching inputs.
    INPUT: DonorProfileRequest
    OUTPUT: DonorProfileView
    AUTHORIZATION: Any authenticated user (creates the capability on first save).
    STATE CHANGES: DonorProfile(created|updated)
    ERRORS: 422 VALIDATION_ERROR (coordinates / fields)
    DEPENDENCIES: ``bloodlink_validation.validate_coordinates``
    MUST NOT: determine medical eligibility; store screening data; return the
              coordinates that were submitted
    PRIVACY: coordinates stored as internal matching data only; ``area`` in the
             response is a ~5 km grid label
    """
    profile = db.execute(
        select(DonorProfile).where(DonorProfile.user_id == principal.user_id)
    ).scalar_one_or_none()
    created = profile is None
    if profile is None:
        profile = DonorProfile(user_id=principal.user_id)
        db.add(profile)

    latitude = payload.latitude
    longitude = payload.longitude
    if latitude is not None or longitude is not None:
        latitude, longitude = validate_coordinates(latitude, longitude)

    from datetime import date

    profile.blood_group = payload.blood_group
    profile.weight_kg = float(payload.weight_kg) if payload.weight_kg else None
    if payload.date_of_birth:
        try:
            profile.date_of_birth = date.fromisoformat(payload.date_of_birth)
        except ValueError as exc:
            raise ConflictError(
                "Date of birth must be an ISO date (YYYY-MM-DD)", code=ErrorCode.VALIDATION_ERROR
            ) from exc
    profile.city = clean_text(payload.city, max_length=80)
    profile.district = clean_text(payload.district, max_length=80)
    profile.state = clean_text(payload.state, max_length=80)
    profile.pincode = clean_text(payload.pincode, max_length=10)
    if latitude is not None:
        profile.latitude = latitude
        profile.longitude = longitude
    profile.is_available = payload.is_available
    profile.accepts_notifications = payload.accepts_notifications
    profile.notify_emergency_only = payload.notify_emergency_only
    profile.acknowledged_screening_notice = payload.acknowledged_screening_notice
    profile.notes = clean_text(payload.notes, max_length=500)

    record(
        db,
        action="donor.profile.created" if created else "donor.profile.updated",
        actor=principal,
        entity_type="donor_profile",
        entity_id=profile.id,
        detail={"bloodGroup": profile.blood_group.value},
    )
    db.commit()
    return success(request, _serialise_profile(profile))


@router.patch("/availability", summary="Toggle donor availability")
def set_availability(
    payload: AvailabilityRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    profile: DonorProfile = Depends(require_donor_profile),
) -> dict:
    """Turn outreach on/off for this donor.

    OWNER: D4
    PURPOSE: Donors control when they can be matched (§11 notification preference).
    INPUT: AvailabilityRequest
    OUTPUT: DonorProfileView
    AUTHORIZATION: Authenticated donor.
    STATE CHANGES: DonorProfile.isAvailable / acceptsNotifications
    ERRORS: 403 DONOR_PROFILE_REQUIRED
    MUST NOT: affect responses the donor already committed to
    """
    profile.is_available = payload.is_available
    if payload.accepts_notifications is not None:
        profile.accepts_notifications = payload.accepts_notifications
    db.commit()
    return success(request, _serialise_profile(profile))


@router.get("/subscriptions", summary="Hospitals I follow")
def list_subscriptions(
    request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)
) -> dict:
    """List the donor's hospital subscriptions (alert preferences).

    OWNER: D4
    PURPOSE: Donor alert management (HospitalSubscription, spec §5, §12).
    INPUT: none
    OUTPUT: { items: [HospitalSubscriptionView] }
    AUTHORIZATION: Self only.
    STATE CHANGES: none
    PRIVACY: hospital name/locality only
    """
    rows = db.execute(
        select(HospitalSubscription).where(HospitalSubscription.user_id == principal.user_id)
    ).scalars()
    items = []
    for row in rows:
        hospital = db.get(Organization, row.hospital_id)
        items.append(
            {
                "id": row.id,
                "hospitalId": row.hospital_id,
                "hospitalName": hospital.name if hospital else None,
                "locationLabel": hospital.location_label if hospital else None,
                "bloodGroups": (row.blood_groups or "").split(",") if row.blood_groups else [],
                "maxUrgency": row.max_urgency.value if row.max_urgency else None,
                "isActive": row.is_active,
            }
        )
    return success(request, {"items": items})


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED, summary="Follow a hospital")
def create_subscription(
    payload: SubscriptionRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Subscribe to a hospital's future requests.

    OWNER: D4
    PURPOSE: Donor networks (§2): follow a hospital and get alerts for matching
             requests.
    INPUT: SubscriptionRequest { hospitalId, bloodGroups[], maxUrgency? }
    OUTPUT: 201 HospitalSubscriptionView
    AUTHORIZATION: Any authenticated user; hospital must be VERIFIED.
    STATE CHANGES: HospitalSubscription(created), alert notification queued
    ERRORS: 404 ORGANIZATION_NOT_FOUND, 409 CONFLICT on duplicate
    DEPENDENCIES: notifications module
    MUST NOT: subscribe a user to a suspended organization
    PRIVACY: the hospital does not receive the follower's location
    """
    hospital = db.get(Organization, payload.hospital_id)
    if hospital is None or hospital.org_type.value != "HOSPITAL":
        raise NotFoundError("Hospital not found", code=ErrorCode.ORGANIZATION_NOT_FOUND)
    if hospital.verification_status is not OrgVerificationStatus.VERIFIED:
        raise ConflictError(
            "You can only follow verified hospitals", code=ErrorCode.ORGANIZATION_NOT_VERIFIED
        )

    existing = db.execute(
        select(HospitalSubscription).where(
            HospitalSubscription.user_id == principal.user_id,
            HospitalSubscription.hospital_id == hospital.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("You already follow this hospital", code=ErrorCode.CONFLICT)

    profile = db.execute(
        select(DonorProfile).where(DonorProfile.user_id == principal.user_id)
    ).scalar_one_or_none()

    subscription = HospitalSubscription(
        hospital_id=hospital.id,
        user_id=principal.user_id,
        donor_profile_id=profile.id if profile else None,
        blood_groups=",".join(group.value for group in payload.blood_groups) or None,
        max_urgency=payload.max_urgency,
        is_active=True,
    )
    db.add(subscription)
    db.commit()
    return success(
        request,
        {"id": subscription.id, "hospitalId": hospital.id, "hospitalName": hospital.name},
    )


@router.delete("/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Unfollow a hospital")
def delete_subscription(
    subscription_id: str, principal: CurrentPrincipal, db: Session = Depends(get_db)
) -> Response:
    """Remove a hospital subscription.

    OWNER: D4
    PURPOSE: Donor alert management.
    INPUT: path subscriptionId
    OUTPUT: 204 No Content
    AUTHORIZATION: Self only.
    STATE CHANGES: HospitalSubscription deleted
    ERRORS: 404 NOT_FOUND
    """
    subscription = db.execute(
        select(HospitalSubscription).where(
            HospitalSubscription.id == subscription_id,
            HospitalSubscription.user_id == principal.user_id,
        )
    ).scalar_one_or_none()
    if subscription is None:
        raise NotFoundError("Subscription not found")
    db.delete(subscription)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/nearby-hospitals", summary="Verified hospitals near me")
def nearby_hospitals(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    profile: DonorProfile = Depends(require_donor_profile),
) -> dict:
    """List verified hospitals with a coarse distance band for the donor.

    OWNER: D4
    PURPOSE: Subscription discovery.
    INPUT: none
    OUTPUT: { items: [ { id, name, locationLabel, distanceBand } ] }
    AUTHORIZATION: Authenticated donor.
    STATE CHANGES: none
    ERRORS: 403 DONOR_PROFILE_REQUIRED
    MUST NOT: leak hospital exact coordinates (banded only, spec §21)
    """
    hospitals = db.execute(
        select(Organization).where(
            Organization.org_type == "HOSPITAL",
            Organization.verification_status == OrgVerificationStatus.VERIFIED,
        )
    ).scalars()
    items = []
    for hospital in hospitals:
        km = distance_km(
            from_lat=profile.latitude,
            from_lon=profile.longitude,
            to_lat=hospital.latitude,
            to_lon=hospital.longitude,
        )
        items.append(
            {
                "id": hospital.id,
                "name": hospital.name,
                "locationLabel": hospital.location_label,
                "distanceBand": distance_band(km),
                "_km": km if km is not None else float("inf"),
            }
        )
    items.sort(key=lambda item: item.pop("_km"))
    return success(request, {"items": items[:40]})


@router.get("/lookup/donors", summary="Hospital: find donors by group and locality")
def donor_lookup(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """DIRECTORY-OUT-OF-SCOPE STUB.

    OWNER: D4
    PURPOSE: Placeholder documenting a deliberately *rejected* capability: a
             browsable donor directory would break spec §21 (ordinary users must
             never receive donor locations/contact data).
    AUTHORIZATION: none — always 404 by design.
    MUST NOT: ever be implemented as a general donor directory. Matching is
              request-scoped and driven by an open BloodRequest (§11).
    """
    raise NotFoundError(
        "Donor directory is out of scope: matching is request-scoped and privacy-preserving",
        code=ErrorCode.NOT_FOUND,
    )


MODULE = register_module(
    ModuleSpec(
        key="donors",
        owner="D4",
        domain="donor-profile",
        api_prefix="/donor/profile",
        description="Donor profile, availability, hospital subscriptions, nearby hospitals.",
        foundation_status="COMPLETE",
        router=router,
        depends_on=("auth", "notifications"),
    )
)
