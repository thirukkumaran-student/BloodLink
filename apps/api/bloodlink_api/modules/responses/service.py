"""Donor response + organization response service (owner: D4, spec §10).

The acceptance contract is the important part of this file:

    Donor sees request -> Accept Donation -> confirmation UI -> Confirm
      -> POST /blood-requests/:id/accept -> DonorResponse = ACCEPTED

Cancelling the confirmation UI must not mutate acceptance state, so the service
requires an explicit ``confirmed=True`` from a *confirmed* submit (the DTO
carries ``confirmation: "EXPLICIT"``). Acceptance is not a successful donation,
and it never closes the request on its own.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bloodlink_api.core.clock import iso, utcnow
from bloodlink_api.core.errors import ConflictError, ForbiddenError, NotFoundError
from bloodlink_api.core.geo import distance_band, distance_km
from bloodlink_api.core.settings import get_settings
from bloodlink_api.db.models.blood_requests import BloodRequest
from bloodlink_api.db.models.donors import DonorProfile, DonorResponse, OrganizationResponse
from bloodlink_api.db.models.identity import Organization, User
from bloodlink_api.db.models.donors import Notification
from bloodlink_api.modules.notifications import service as notification_service
from bloodlink_contracts.enums import (
    OUTREACH_ACTIVE_STATUSES,
    BloodRequestStatus,
    DonorResponseStatus,
    DonorStandbyStatus,
    NotificationType,
    OrganizationResponseOutcome,
    OrganizationResponseStatus,
)
from bloodlink_contracts.errors import ErrorCode
from bloodlink_validation.blood import cooldown_remaining_days, is_compatible
from bloodlink_validation.common import clean_text

ACCEPTABLE_REQUEST_STATUSES = tuple(OUTREACH_ACTIVE_STATUSES)


# --------------------------------------------------------------------------- #
# Donor-facing reads
# --------------------------------------------------------------------------- #
def _profile(db: Session, user_id: str) -> DonorProfile | None:
    return db.execute(
        select(DonorProfile).where(DonorProfile.user_id == user_id)
    ).scalar_one_or_none()


def serialise_request_for_donor(db: Session, blood_request: BloodRequest, profile: DonorProfile) -> dict:
    """Privacy-safe request card for a donor (spec §21).

    Deliberately omits: patient identity, requesting individual, exact hospital
    coordinates, hospital internal notes.
    """
    hospital = blood_request.hospital
    km = distance_km(
        from_lat=profile.latitude,
        from_lon=profile.longitude,
        to_lat=hospital.latitude if hospital else None,
        to_lon=hospital.longitude if hospital else None,
    )
    return {
        "id": blood_request.id,
        "reference": blood_request.reference,
        "bloodGroup": blood_request.blood_group.value,
        "component": blood_request.component.value,
        "unitsRequired": blood_request.units_required,
        "unitsCoordinated": blood_request.units_coordinated,
        "urgency": blood_request.urgency.value,
        "status": blood_request.status.value,
        "requiredBy": iso(blood_request.required_by),
        "hospital": {
            "id": hospital.id,
            "name": hospital.name,
            "locationLabel": hospital.location_label,
        }
        if hospital
        else None,
        "distanceBand": distance_band(km),
        "compatibleForDonor": is_compatible(
            blood_request.blood_group, profile.blood_group, blood_request.component
        ),
        "acceptingResponses": blood_request.status in ACCEPTABLE_REQUEST_STATUSES,
    }


def matched_requests_for_profile(db: Session, profile: DonorProfile, *, limit: int = 25) -> list[dict]:
    """Open requests compatible with the donor's group, nearest first (§11).

    Uses the D1 geo helpers with a bounding-box pre-filter, so it works on
    SQLite during development and can be swapped for PostGIS in production.
    """
    from bloodlink_api.core.geo import bounding_box

    query = select(BloodRequest).where(BloodRequest.status.in_(ACCEPTABLE_REQUEST_STATUSES))
    if profile.latitude is not None and profile.longitude is not None:
        # Wide pre-filter; final distance ordering happens in Python.
        box = bounding_box(profile.latitude, profile.longitude, radius_km=250)
        query = query.where(
            BloodRequest.hospital.has(
                (Organization.latitude >= box["min_lat"])
                & (Organization.latitude <= box["max_lat"])
                & (Organization.longitude >= box["min_lon"])
                & (Organization.longitude <= box["max_lon"])
            )
        )

    rows = db.execute(query.order_by(BloodRequest.required_by.asc())).scalars().all()
    cards: list[tuple[float, dict]] = []
    for blood_request in rows:
        if not is_compatible(blood_request.blood_group, profile.blood_group, blood_request.component):
            continue
        if profile.notify_emergency_only and blood_request.urgency.value == "ROUTINE":
            continue
        hospital = blood_request.hospital
        km = distance_km(
            from_lat=profile.latitude,
            from_lon=profile.longitude,
            to_lat=hospital.latitude if hospital else None,
            to_lon=hospital.longitude if hospital else None,
        )
        cards.append((km if km is not None else float("inf"), serialise_request_for_donor(db, blood_request, profile)))

    cards.sort(key=lambda item: item[0])
    return [card for _km, card in cards[:limit]]


def mobile_eligible(db: Session, profile: DonorProfile) -> tuple[bool, int]:
    """Return ``(eligible_for_outreach, cooldown_days_remaining)``.

    BloodLink does not decide medical eligibility — this only applies the
    platform's post-donation cooldown window (§11) plus the donor's own
    availability switch.
    """
    remaining = cooldown_remaining_days(
        profile.last_donation_at, get_settings().donor_cooldown_days, as_of=utcnow()
    )
    return (profile.is_available and profile.accepts_notifications and remaining == 0), remaining


# --------------------------------------------------------------------------- #
# Donor acceptance (§10)
# --------------------------------------------------------------------------- #
def accept_request(
    db: Session,
    *,
    user: User,
    profile: DonorProfile,
    blood_request: BloodRequest,
    confirmed: bool,
    eta_minutes: int | None = None,
    remarks: str | None = None,
) -> DonorResponse:
    """Record an explicit donor acceptance.

    Raises
    ------
    ConflictError(CONFIRMATION_REQUIRED)  — the confirmation step was skipped.
    ConflictError(DONOR_IN_COOLDOWN)      — post-donation cooldown still running.
    ConflictError(REQUEST_NOT_OPEN_FOR_RESPONSES) — request is past acceptance.
    ConflictError(RESPONSE_ALREADY_EXISTS) — the donor already responded.
    """
    if not confirmed:
        raise ConflictError(
            "Acceptance requires an explicit confirmation step — cancelling the "
            "confirmation must not change any state.",
            code=ErrorCode.CONFIRMATION_REQUIRED,
        )

    if blood_request.status not in ACCEPTABLE_REQUEST_STATUSES:
        raise ConflictError(
            "This request is no longer accepting donor responses",
            code=ErrorCode.REQUEST_NOT_OPEN_FOR_RESPONSES,
        )

    if not is_compatible(blood_request.blood_group, profile.blood_group, blood_request.component):
        raise ConflictError(
            "Your blood group is not compatible with this request",
            code=ErrorCode.DONOR_NOT_ELIGIBLE_FOR_OUTREACH,
        )

    existing = db.execute(
        select(DonorResponse).where(
            DonorResponse.blood_request_id == blood_request.id,
            DonorResponse.donor_profile_id == profile.id,
        )
    ).scalar_one_or_none()
    if existing is not None and existing.status in (
        DonorResponseStatus.ACCEPTED,
        DonorResponseStatus.SELECTED,
        DonorResponseStatus.STANDBY,
    ):
        raise ConflictError(
            "You have already responded to this request", code=ErrorCode.RESPONSE_ALREADY_EXISTS
        )

    cooldown = cooldown_remaining_days(
        profile.last_donation_at, get_settings().donor_cooldown_days, as_of=utcnow()
    )
    if cooldown:
        raise ConflictError(
            f"Your post-donation recovery window has {cooldown} day(s) left. "
            "Please contact the hospital if this is urgent.",
            code=ErrorCode.DONOR_IN_COOLDOWN,
            details=[{"field": "cooldownDaysRemaining", "message": str(cooldown)}],
        )

    response = existing or DonorResponse(
        blood_request_id=blood_request.id,
        donor_profile_id=profile.id,
        user_id=user.id,
    )
    response.status = DonorResponseStatus.ACCEPTED
    response.confirmed_at = utcnow()
    response.confirmation_method = "EXPLICIT_UI_CONFIRMATION"
    response.remarks = clean_text(remarks, max_length=500)
    if eta_minutes is not None:
        response.eta_minutes = max(0, min(24 * 60, int(eta_minutes)))
    if existing is None:
        db.add(response)

    # The first acceptance moves the request out of a bare OPEN state but must
    # NOT close it (§9). D3 owns the full lifecycle; this is the minimum signal.
    if blood_request.status is BloodRequestStatus.OPEN:
        blood_request.status = BloodRequestStatus.RESPONSES_RECEIVED

    # Notify the hospital's coordinators (privacy-safe payload).
    hospital = blood_request.hospital
    if hospital:
        for coordinator in db.execute(
            select(User).where(User.organization_id == hospital.id, User.is_active.is_(True))
        ).scalars():
            notification_service.create_notification(
                db,
                user_id=coordinator.id,
                notification_type=NotificationType.DONOR_ACCEPTED,
                data={
                    "requestId": blood_request.id,
                    "reference": blood_request.reference,
                    "bloodGroup": blood_request.blood_group.value,
                    "url": f"/hospital/requests/{blood_request.id}",
                },
                blood_request_id=blood_request.id,
            )

    db.flush()
    return response


def withdraw_response(
    db: Session, *, profile: DonorProfile, response: DonorResponse, reason: str | None = None
) -> DonorResponse:
    """Donor withdraws an acceptance. The request needs backup if they were selected."""
    if response.donor_profile_id != profile.id:
        raise ForbiddenError("This response belongs to another donor")
    if response.status in (DonorResponseStatus.WITHDRAWN, DonorResponseStatus.RELEASED):
        raise ConflictError("This response is already closed", code=ErrorCode.CONFLICT)

    was_selected = response.status is DonorResponseStatus.SELECTED
    response.status = DonorResponseStatus.WITHDRAWN
    response.released_at = utcnow()
    response.released_reason = clean_text(reason, max_length=240) or "Withdrawn by donor"
    response.standby_status = DonorStandbyStatus.NONE

    blood_request = db.get(BloodRequest, response.blood_request_id)
    if blood_request is not None and was_selected and blood_request.status is not BloodRequestStatus.FULFILLED:
        # Failure path: coordination restarts and backup may be requested (§9).
        if blood_request.status is BloodRequestStatus.COORDINATING:
            blood_request.status = BloodRequestStatus.BACKUP_REQUIRED
            blood_request.backup_reason = "Selected donor withdrew"
        elif blood_request.status is BloodRequestStatus.COVERED:
            blood_request.status = BloodRequestStatus.BACKUP_REQUIRED
            blood_request.backup_reason = "Selected donor withdrew"
        hospital = blood_request.hospital
        if hospital:
            for coordinator in db.execute(
                select(User).where(User.organization_id == hospital.id, User.is_active.is_(True))
            ).scalars():
                notification_service.create_notification(
                    db,
                    user_id=coordinator.id,
                    notification_type=NotificationType.REQUEST_BACKUP_REQUIRED,
                    data={"requestId": blood_request.id, "reference": blood_request.reference, "url": f"/hospital/requests/{blood_request.id}"},
                    blood_request_id=blood_request.id,
                )
    db.flush()
    return response


def list_responses_for_donor(db: Session, profile: DonorProfile) -> list[dict]:
    rows = db.execute(
        select(DonorResponse)
        .where(DonorResponse.donor_profile_id == profile.id)
        .order_by(DonorResponse.created_at.desc())
    ).scalars()
    return [
        {
            "id": row.id,
            "requestId": row.blood_request_id,
            "requestReference": db.get(BloodRequest, row.blood_request_id).reference
            if db.get(BloodRequest, row.blood_request_id)
            else None,
            "status": row.status.value,
            "standbyStatus": row.standby_status.value,
            "confirmedAt": iso(row.confirmed_at),
            "selectedAt": iso(row.selected_at),
            "createdAt": iso(row.created_at),
        }
        for row in rows
    ]


def responses_for_request(db: Session, blood_request_id: str) -> list[dict]:
    """Hospital-facing response list (privacy-safe: distance band, never coords)."""
    rows = db.execute(
        select(DonorResponse)
        .where(DonorResponse.blood_request_id == blood_request_id)
        .order_by(DonorResponse.status.asc(), DonorResponse.created_at.asc())
    ).scalars()
    blood_request = db.get(BloodRequest, blood_request_id)
    hospital = blood_request.hospital if blood_request else None
    items = []
    for row in rows:
        profile = db.get(DonorProfile, row.donor_profile_id)
        user = db.get(User, row.user_id)
        km = distance_km(
            from_lat=hospital.latitude if hospital else None,
            from_lon=hospital.longitude if hospital else None,
            to_lat=profile.latitude if profile else None,
            to_lon=profile.longitude if profile else None,
        )
        items.append(
            {
                "id": row.id,
                "donorProfileId": row.donor_profile_id,
                "donorName": user.full_name if user else "Donor",
                "donorInitials": user.initials if user else "D",
                "bloodGroup": profile.blood_group.value if profile else None,
                "status": row.status.value,
                "standbyStatus": row.standby_status.value,
                "distanceBand": distance_band(km),
                "confirmedAt": iso(row.confirmed_at),
                "selectedAt": iso(row.selected_at),
                "coordinationStatus": row.coordination_status,
                "remarks": row.remarks,
            }
        )
    return items


# --------------------------------------------------------------------------- #
# Hospital selection (D3 decides, D4 owns the stored response state) — §10
# --------------------------------------------------------------------------- #
def select_donor(
    db: Session,
    *,
    blood_request: BloodRequest,
    selected_response_id: str,
    standby_response_ids: list[str] | None = None,
    actor: User | None = None,
) -> dict:
    """Select one donor; other suitable donors become STANDBY."""
    selected = db.get(DonorResponse, selected_response_id)
    if selected is None or selected.blood_request_id != blood_request.id:
        raise NotFoundError("Donor response not found", code=ErrorCode.RESPONSE_NOT_FOUND)
    if selected.status not in (DonorResponseStatus.ACCEPTED, DonorResponseStatus.STANDBY):
        raise ConflictError(
            "Only accepted donors can be selected", code=ErrorCode.DONOR_NOT_SELECTABLE
        )

    selected.status = DonorResponseStatus.SELECTED
    selected.standby_status = DonorStandbyStatus.NONE
    selected.selected_at = utcnow()
    selected.selected_by_user_id = actor.id if actor else None

    others = db.execute(
        select(DonorResponse).where(
            DonorResponse.blood_request_id == blood_request.id,
            DonorResponse.id != selected.id,
            DonorResponse.status.in_([DonorResponseStatus.ACCEPTED, DonorResponseStatus.STANDBY]),
        )
    ).scalars().all()

    for response in others:
        if standby_response_ids is None or response.id in standby_response_ids:
            response.status = DonorResponseStatus.STANDBY
            response.standby_status = DonorStandbyStatus.STANDBY
            notification_service.create_notification(
                db,
                user_id=response.user_id,
                notification_type=NotificationType.DONOR_STANDBY,
                data={"requestId": blood_request.id, "reference": blood_request.reference},
                blood_request_id=blood_request.id,
            )
        else:
            response.status = DonorResponseStatus.RELEASED
            response.released_at = utcnow()
            response.released_reason = "Another donor was selected"
            response.standby_status = DonorStandbyStatus.NONE

    notification_service.create_notification(
        db,
        user_id=selected.user_id,
        notification_type=NotificationType.DONOR_SELECTED,
        data={"requestId": blood_request.id, "reference": blood_request.reference},
        blood_request_id=blood_request.id,
    )

    blood_request.units_coordinated = 1
    db.flush()
    return {
        "selected": selected,
        "standby": [response for response in others if response.status is DonorResponseStatus.STANDBY],
    }


def activate_standby(db: Session, *, blood_request: BloodRequest, response_id: str, actor: User | None = None) -> DonorResponse:
    """Promote a standby donor when the selected donor falls through (§9 backup)."""
    response = db.get(DonorResponse, response_id)
    if response is None or response.blood_request_id != blood_request.id:
        raise NotFoundError("Standby response not found", code=ErrorCode.RESPONSE_NOT_FOUND)
    if response.status is not DonorResponseStatus.STANDBY:
        raise ConflictError("Only standby donors can be activated", code=ErrorCode.CONFLICT)

    response.status = DonorResponseStatus.SELECTED
    response.standby_status = DonorStandbyStatus.ACTIVATED
    response.selected_at = utcnow()
    response.selected_by_user_id = actor.id if actor else None

    for other in db.execute(
        select(DonorResponse).where(
            DonorResponse.blood_request_id == blood_request.id,
            DonorResponse.status == DonorResponseStatus.SELECTED,
            DonorResponse.id != response.id,
        )
    ).scalars():
        other.status = DonorResponseStatus.RELEASED
        other.released_at = utcnow()
        other.released_reason = "Superseded by activated standby donor"

    notification_service.create_notification(
        db,
        user_id=response.user_id,
        notification_type=NotificationType.DONOR_SELECTED,
        data={"requestId": blood_request.id, "reference": blood_request.reference},
        blood_request_id=blood_request.id,
    )
    if blood_request.status is BloodRequestStatus.BACKUP_REQUIRED:
        blood_request.status = BloodRequestStatus.COORDINATING
    db.flush()
    return response


# --------------------------------------------------------------------------- #
# Organization (blood centre) responses
# --------------------------------------------------------------------------- #
def submit_organization_response(
    db: Session,
    *,
    blood_request: BloodRequest,
    organization: Organization,
    actor: User,
    status: OrganizationResponseStatus,
    units_offered: int | None,
    component=None,
    blood_group=None,
    notes: str | None = None,
) -> OrganizationResponse:
    existing = db.execute(
        select(OrganizationResponse).where(
            OrganizationResponse.blood_request_id == blood_request.id,
            OrganizationResponse.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            "Your organization has already responded to this request",
            code=ErrorCode.ORGANIZATION_RESPONSE_EXISTS,
        )

    response = OrganizationResponse(
        blood_request_id=blood_request.id,
        organization_id=organization.id,
        responded_by_user_id=actor.id,
        status=status,
        units_offered=units_offered,
        component=component or blood_request.component,
        blood_group=blood_group or blood_request.blood_group,
        notes=clean_text(notes, max_length=500),
        outcome=OrganizationResponseOutcome.PENDING,
    )
    db.add(response)

    hospital = blood_request.hospital
    if hospital:
        for coordinator in db.execute(
            select(User).where(User.organization_id == hospital.id, User.is_active.is_(True))
        ).scalars():
            notification_service.create_notification(
                db,
                user_id=coordinator.id,
                notification_type=NotificationType.ORGANIZATION_RESPONDED,
                data={
                    "requestId": blood_request.id,
                    "reference": blood_request.reference,
                    "organizationName": organization.name,
                    "url": f"/hospital/requests/{blood_request.id}",
                },
                blood_request_id=blood_request.id,
            )
    db.flush()
    return response


def list_organization_responses(db: Session, organization_id: str) -> list[dict]:
    rows = db.execute(
        select(OrganizationResponse)
        .where(OrganizationResponse.organization_id == organization_id)
        .order_by(OrganizationResponse.created_at.desc())
    ).scalars()
    items = []
    for row in rows:
        blood_request = db.get(BloodRequest, row.blood_request_id)
        items.append(
            {
                "id": row.id,
                "requestId": row.blood_request_id,
                "requestReference": blood_request.reference if blood_request else None,
                "requestBloodGroup": blood_request.blood_group.value if blood_request else None,
                "requestStatus": blood_request.status.value if blood_request else None,
                "status": row.status.value,
                "outcome": row.outcome.value,
                "unitsOffered": row.units_offered,
                "hospitalName": blood_request.hospital.name
                if blood_request and blood_request.hospital
                else None,
                "createdAt": iso(row.created_at),
            }
        )
    return items
