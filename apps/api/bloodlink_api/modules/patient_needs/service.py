"""PatientNeed service — OWNER: D2 (spec §8, §15).

Everything an individual can do with a need lives here: submit one to a verified
hospital, list their own history, read one, cancel one while it is still pending,
and discover which hospitals can receive a need.

The hospital *review* is D3's (`modules/blood_requests/review.py`) because the
review is what mints a BloodRequest.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from bloodlink_api.core.clock import iso, utcnow
from bloodlink_api.core.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    UnprocessableError,
)
from bloodlink_api.core.geo import distance_band, distance_km
from bloodlink_api.db.models.donors import DonorProfile
from bloodlink_api.db.models.identity import Organization, User
from bloodlink_api.db.models.needs import PatientNeed
from bloodlink_api.modules.notifications import service as notification_service
from bloodlink_contracts.enums import (
    BloodComponent,
    BloodGroup,
    NotificationType,
    OrgVerificationStatus,
    PatientNeedStatus,
    Urgency,
)
from bloodlink_contracts.errors import ErrorCode
from bloodlink_validation.common import validate_notes, validate_required_by, validate_units


def hospital_payload(organization: Organization | None) -> dict | None:
    """Hospital summary safe to show a submitter (no coordinates, spec §21)."""
    if organization is None:
        return None
    return {
        "id": organization.id,
        "name": organization.name,
        "city": organization.city,
        "district": organization.district,
        "locationLabel": organization.location_label,
    }


def serialise_need(
    need: PatientNeed,
    *,
    hospital: Organization | None = None,
    submitter: User | None = None,
) -> dict:
    """PatientNeedResponse.

    PRIVACY: the submitter sees their own coordination notes and the hospital's
    decision reason. No donor, no third party, and no clinical field is included.
    """
    return {
        "id": need.id,
        "hospitalId": need.hospital_id,
        "hospital": hospital_payload(hospital),
        "submittedBy": (
            {"id": submitter.id, "fullName": submitter.full_name} if submitter is not None else None
        ),
        "bloodGroup": need.blood_group.value,
        "component": need.component.value,
        "units": need.units,
        "urgency": need.urgency.value,
        "requiredBy": iso(need.required_by),
        "additionalNotes": need.additional_notes,
        "status": need.status.value,
        "reviewReason": need.review_reason,
        "reviewedAt": iso(need.reviewed_at),
        "bloodRequestId": need.blood_request.id if need.blood_request else None,
        "createdAt": iso(need.created_at),
        "updatedAt": iso(need.updated_at),
    }


def _verified_hospital(db: Session, hospital_id: str) -> Organization:
    hospital = db.get(Organization, hospital_id)
    if hospital is None:
        raise NotFoundError("Hospital not found", code=ErrorCode.ORGANIZATION_NOT_FOUND)
    if hospital.verification_status is not OrgVerificationStatus.VERIFIED:
        raise ConflictError(
            "This hospital cannot receive BloodLink requests yet",
            code=ErrorCode.ORGANIZATION_NOT_VERIFIED,
        )
    if not hospital.is_operational:
        raise ConflictError(
            "This hospital is not currently accepting requests",
            code=ErrorCode.ORGANIZATION_SUSPENDED,
        )
    return hospital


def create_need(
    db: Session,
    *,
    submitter: User,
    hospital_id: str,
    blood_group: BloodGroup,
    component: BloodComponent,
    units: int,
    urgency: Urgency,
    required_by: datetime,
    additional_notes: str | None = None,
) -> tuple[PatientNeed, Organization]:
    """Create a PENDING_HOSPITAL_REVIEW need.

    STATE CHANGES: PatientNeed(created, status=PENDING_HOSPITAL_REVIEW);
                   Notification(NEED_SUBMITTED) to the hospital's active staff
    ERRORS: 404 ORGANIZATION_NOT_FOUND, 409 ORGANIZATION_NOT_VERIFIED,
            422 NEED_REQUIRED_BY_IN_PAST / VALIDATION_ERROR
    MUST NOT: create a BloodRequest or contact donors — that is D3/D4 after review
    """
    hospital = _verified_hospital(db, hospital_id)

    try:
        units_value = validate_units(units)
    except ValueError as exc:
        raise UnprocessableError(str(exc), code=ErrorCode.VALIDATION_ERROR) from exc

    try:
        required_by_value = validate_required_by(required_by)
    except ValueError as exc:
        raise UnprocessableError(str(exc), code=ErrorCode.NEED_REQUIRED_BY_IN_PAST) from exc

    try:
        notes = validate_notes(additional_notes)
    except ValueError as exc:
        raise UnprocessableError(str(exc), code=ErrorCode.VALIDATION_ERROR) from exc

    need = PatientNeed(
        submitted_by_user_id=submitter.id,
        hospital_id=hospital.id,
        blood_group=blood_group,
        component=component,
        units=units_value,
        urgency=urgency,
        required_by=required_by_value,
        additional_notes=notes,
        status=PatientNeedStatus.PENDING_HOSPITAL_REVIEW,
    )
    db.add(need)
    db.flush()

    _notify_hospital_of_need(db, need=need, hospital=hospital)
    return need, hospital


def _notify_hospital_of_need(db: Session, *, need: PatientNeed, hospital: Organization) -> int:
    """Tell the hospital's active staff that a need is waiting for review.

    PRIVACY: the payload carries the need id, group, component, units, urgency and
    a UI url — never the submitter's name, notes, or any clinical detail.
    """
    staff = db.execute(
        select(User).where(User.organization_id == hospital.id, User.is_active.is_(True))
    ).scalars().all()

    sent = 0
    for member in staff:
        created = notification_service.create_notification(
            db,
            user_id=member.id,
            notification_type=NotificationType.NEED_SUBMITTED,
            data={
                "needId": need.id,
                "bloodGroup": need.blood_group.value,
                "component": need.component.value,
                "units": need.units,
                "urgency": need.urgency.value,
                "requiredBy": iso(need.required_by),
                "url": "/hospital/queue",
            },
        )
        if created is not None:
            sent += 1
    return sent


def list_for_submitter(
    db: Session,
    *,
    submitter_id: str,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[Sequence[PatientNeed], int]:
    """The submitter's own history — self only."""
    filters = [PatientNeed.submitted_by_user_id == submitter_id]
    if status:
        status_value = PatientNeedStatus.coerce(status)
        if status_value is None:
            raise UnprocessableError("Unknown need status", code=ErrorCode.VALIDATION_ERROR)
        filters.append(PatientNeed.status == status_value)

    total = db.execute(select(func.count()).select_from(PatientNeed).where(*filters)).scalar_one()
    rows = db.execute(
        select(PatientNeed)
        .options(joinedload(PatientNeed.blood_request))
        .where(*filters)
        .order_by(PatientNeed.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()
    return rows, int(total)


def get_for_submitter(db: Session, *, need_id: str, submitter_id: str, is_admin: bool = False) -> PatientNeed:
    need = db.execute(
        select(PatientNeed).options(joinedload(PatientNeed.blood_request)).where(PatientNeed.id == need_id)
    ).scalar_one_or_none()
    if need is None:
        raise NotFoundError("Need not found", code=ErrorCode.NEED_NOT_FOUND)
    if not is_admin and need.submitted_by_user_id != submitter_id:
        # 404 rather than 403: a submitter must not learn that a need id exists.
        raise NotFoundError("Need not found", code=ErrorCode.NEED_NOT_FOUND)
    return need


def cancel_need(db: Session, *, need: PatientNeed, actor: User, reason: str | None = None) -> PatientNeed:
    """Cancel a need that has not been reviewed yet.

    ERRORS: 409 NEED_NOT_CANCELLABLE once the hospital has reviewed it — from then
            on the BloodRequest lifecycle owns the decision (§9).
    """
    if need.submitted_by_user_id != actor.id:
        raise NotFoundError("Need not found", code=ErrorCode.NEED_NOT_FOUND)
    if need.status is not PatientNeedStatus.PENDING_HOSPITAL_REVIEW:
        raise ConflictError(
            "This need has already been reviewed — contact the hospital instead",
            code=ErrorCode.NEED_NOT_CANCELLABLE,
        )

    need.status = PatientNeedStatus.CANCELLED
    need.review_reason = validate_notes(reason) or "Cancelled by the submitter"
    db.flush()
    return need


def discover_hospitals(
    db: Session,
    *,
    q: str | None = None,
    city: str | None = None,
    district: str | None = None,
    viewer: User | None = None,
    limit: int = 50,
) -> list[dict]:
    """Verified, operational hospitals an individual can send a need to.

    PRIVACY: name + locality + coarse distance band only. A hospital's exact
    coordinates are internal matching data (spec §21).
    """
    # `is_operational` is derived from verification, so the VERIFIED filter is
    # the same gate the request board uses (spec §16).
    filters = [Organization.verification_status == OrgVerificationStatus.VERIFIED]
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                Organization.name.ilike(pattern),
                Organization.city.ilike(pattern),
                Organization.district.ilike(pattern),
            )
        )
    if city:
        filters.append(Organization.city.ilike(f"%{city.strip()}%"))
    if district:
        filters.append(Organization.district.ilike(f"%{district.strip()}%"))

    hospitals = db.execute(
        select(Organization).where(*filters).order_by(Organization.name).limit(limit)
    ).scalars().all()

    viewer_profile = None
    if viewer is not None:
        viewer_profile = db.execute(
            select(DonorProfile).where(DonorProfile.user_id == viewer.id)
        ).scalar_one_or_none()

    payload: list[dict] = []
    for hospital in hospitals:
        band = None
        if (
            viewer_profile is not None
            and viewer_profile.latitude is not None
            and viewer_profile.longitude is not None
            and hospital.latitude is not None
            and hospital.longitude is not None
        ):
            band = distance_band(
                distance_km(
                    from_lat=viewer_profile.latitude,
                    from_lon=viewer_profile.longitude,
                    to_lat=hospital.latitude,
                    to_lon=hospital.longitude,
                )
            )
        payload.append(
            {
                "id": hospital.id,
                "name": hospital.name,
                "orgType": hospital.org_type.value,
                "city": hospital.city,
                "district": hospital.district,
                "state": hospital.state,
                "locationLabel": hospital.location_label,
                "distanceBand": band,
                "verifiedAt": iso(hospital.verified_at),
            }
        )
    return payload


def review_queue(
    db: Session,
    *,
    hospital_id: str,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[Sequence[PatientNeed], int, dict[str, Organization], dict[str, User]]:
    """Needs addressed to one hospital, pending review first (D3 reads this)."""
    filters = [PatientNeed.hospital_id == hospital_id]
    if status:
        status_value = PatientNeedStatus.coerce(status)
        if status_value is None:
            raise UnprocessableError("Unknown need status", code=ErrorCode.VALIDATION_ERROR)
        filters.append(PatientNeed.status == status_value)

    total = db.execute(select(func.count()).select_from(PatientNeed).where(*filters)).scalar_one()
    pending_first = PatientNeed.status != PatientNeedStatus.PENDING_HOSPITAL_REVIEW
    rows = db.execute(
        select(PatientNeed)
        .options(joinedload(PatientNeed.blood_request))
        .where(*filters)
        .order_by(pending_first, PatientNeed.required_by.asc(), PatientNeed.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    hospitals: dict[str, Organization] = {}
    submitters: dict[str, User] = {}
    hospital = db.get(Organization, hospital_id)
    if hospital is not None:
        hospitals[hospital.id] = hospital
    for need in rows:
        if need.submitted_by_user_id not in submitters:
            user = db.get(User, need.submitted_by_user_id)
            if user is not None:
                submitters[user.id] = user
    return rows, int(total), hospitals, submitters
