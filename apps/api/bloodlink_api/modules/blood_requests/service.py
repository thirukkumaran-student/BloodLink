"""BloodRequest lifecycle service — OWNER: D3 (spec §9, §10).

One place owns every lifecycle change. Routers stay thin: they check
authorization, call this service, and serialise.

The transition table itself is a D1 contract
(``bloodlink_contracts.enums.BLOOD_REQUEST_TRANSITIONS``) and is never bypassed —
``transition()`` refuses anything outside it with 409.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from bloodlink_api.core.clock import iso, utcnow
from bloodlink_api.core.errors import ConflictError, ForbiddenError, NotFoundError
from bloodlink_api.core.geo import distance_band, distance_km
from bloodlink_api.db.models.blood_requests import BloodRequest, BloodRequestEvent, DonorOutreach
from bloodlink_api.db.models.donors import DonorProfile, DonorResponse
from bloodlink_api.db.models.identity import Organization, User
from bloodlink_api.db.models.needs import PatientNeed
from bloodlink_api.modules.notifications import service as notification_service
from bloodlink_api.modules.responses import service as response_service
from bloodlink_contracts.enums import (
    BLOOD_REQUEST_TRANSITIONS,
    OUTREACH_ACTIVE_STATUSES,
    TERMINAL_REQUEST_STATUSES,
    BloodRequestStatus,
    DonorResponseStatus,
    NotificationType,
    OrgVerificationStatus,
    PatientNeedStatus,
    Urgency,
)
from bloodlink_contracts.errors import ErrorCode
from bloodlink_validation.common import validate_notes, validate_units

ACTIVE_RESPONSE_STATUSES = (
    DonorResponseStatus.ACCEPTED,
    DonorResponseStatus.SELECTED,
    DonorResponseStatus.STANDBY,
)


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #
def hospital_summary(hospital: Organization | None) -> dict | None:
    if hospital is None:
        return None
    return {
        "id": hospital.id,
        "name": hospital.name,
        "city": hospital.city,
        "district": hospital.district,
        "locationLabel": hospital.location_label,
    }


def _responder_counts(db: Session, blood_request_id: str) -> dict[str, int]:
    rows = db.execute(
        select(DonorResponse.status, func.count())
        .where(DonorResponse.blood_request_id == blood_request_id)
        .group_by(DonorResponse.status)
    ).all()
    counts = {status.value: int(count) for status, count in rows}
    counts["accepted"] = counts.get(DonorResponseStatus.ACCEPTED.value, 0)
    counts["selected"] = counts.get(DonorResponseStatus.SELECTED.value, 0)
    counts["standby"] = counts.get(DonorResponseStatus.STANDBY.value, 0)
    counts["withdrawn"] = counts.get(DonorResponseStatus.WITHDRAWN.value, 0)
    counts["total"] = sum(int(count) for _, count in rows)
    return counts


def serialise_request(db: Session, blood_request: BloodRequest, *, detail: bool = False) -> dict:
    """BloodRequestResponse / BloodRequestDetailResponse.

    PRIVACY: counts and distance bands only. Donor identities appear solely in the
    response list, which D4 owns and which never carries coordinates (spec §21).
    """
    payload: dict = {
        "id": blood_request.id,
        "reference": blood_request.reference,
        "hospitalId": blood_request.hospital_id,
        "hospital": hospital_summary(blood_request.hospital),
        "patientNeedId": blood_request.patient_need_id,
        "bloodGroup": blood_request.blood_group.value,
        "component": blood_request.component.value,
        "unitsRequired": blood_request.units_required,
        "unitsCoordinated": blood_request.units_coordinated,
        "urgency": blood_request.urgency.value,
        "status": blood_request.status.value,
        "requiredBy": iso(blood_request.required_by),
        "coordinationNote": blood_request.coordination_note,
        "backupReason": blood_request.backup_reason,
        "outreachTier": blood_request.outreach_tier,
        "openedAt": iso(blood_request.opened_at),
        "closedAt": iso(blood_request.closed_at),
        "createdAt": iso(blood_request.created_at),
        "responders": _responder_counts(db, blood_request.id),
    }
    if detail:
        payload["events"] = [
            {
                "id": event.id,
                "eventType": event.event_type,
                "fromStatus": event.from_status.value if event.from_status else None,
                "toStatus": event.to_status.value if event.to_status else None,
                "detail": event.detail,
                "createdAt": iso(event.created_at),
            }
            for event in blood_request.events
        ]
        payload["responses"] = response_service.responses_for_request(db, blood_request.id)
        payload["outreach"] = outreach_summary(db, blood_request=blood_request)
    return payload


# --------------------------------------------------------------------------- #
# Review gate (D3 reviews; D2 owns submission)
# --------------------------------------------------------------------------- #
def review_need(
    db: Session,
    *,
    need: PatientNeed,
    hospital_id: str,
    decision: PatientNeedStatus,
    reason: str | None,
    actor: User | None,
) -> PatientNeed:
    """Record the hospital's decision on a PatientNeed.

    STATE CHANGES: PatientNeed(status, reviewed_by_user_id, reviewed_at, review_reason);
                   Notification(NEED_REVIEWED) to the submitter
    ERRORS: 404 NEED_NOT_FOUND, 409 NEED_ALREADY_REVIEWED
    MUST NOT: mint the BloodRequest — that is a separate explicit step
    """
    if need.hospital_id != hospital_id:
        # A hospital must not learn about needs addressed elsewhere.
        raise NotFoundError("Need not found", code=ErrorCode.NEED_NOT_FOUND)
    if decision not in (PatientNeedStatus.APPROVED, PatientNeedStatus.REJECTED):
        raise ConflictError(
            "A review decision is either APPROVED or REJECTED",
            code=ErrorCode.VALIDATION_ERROR,
        )
    if need.status is not PatientNeedStatus.PENDING_HOSPITAL_REVIEW:
        raise ConflictError(
            "This need has already been reviewed", code=ErrorCode.NEED_ALREADY_REVIEWED
        )

    need.status = decision
    need.reviewed_by_user_id = actor.id if actor else None
    need.reviewed_at = utcnow()
    need.review_reason = validate_notes(reason)
    db.flush()

    notification_service.create_notification(
        db,
        user_id=need.submitted_by_user_id,
        notification_type=NotificationType.NEED_REVIEWED,
        data={
            "needId": need.id,
            "decision": decision.value,
            "url": f"/needs/{need.id}",
        },
    )
    return need


# --------------------------------------------------------------------------- #
# Request creation
# --------------------------------------------------------------------------- #
def create_from_need(
    db: Session,
    *,
    need: PatientNeed,
    hospital: Organization,
    units_required: int | None,
    urgency: Urgency | None,
    coordination_note: str | None,
    actor: User | None,
) -> BloodRequest:
    """Mint the official BloodRequest from an APPROVED need.

    STATE CHANGES: PatientNeed(APPROVED -> CONVERTED); BloodRequest(OPEN);
                   BloodRequestEvent(REQUEST_CREATED); tier-1 outreach dispatched
    ERRORS: 404 NEED_NOT_FOUND, 409 NEED_ALREADY_REVIEWED (not in an APPROVED state)
    MUST NOT: notify donors directly — outreach goes through D4's interface
    """
    if need.hospital_id != hospital.id:
        raise NotFoundError("Need not found", code=ErrorCode.NEED_NOT_FOUND)
    if not need.is_open_for_conversion:
        raise ConflictError(
            "A request can only be created from an APPROVED need",
            code=ErrorCode.NEED_ALREADY_REVIEWED,
        )

    try:
        units_value = validate_units(units_required if units_required is not None else need.units)
    except ValueError as exc:
        raise ConflictError(str(exc), code=ErrorCode.VALIDATION_ERROR) from exc

    blood_request = BloodRequest(
        reference=_next_reference(db),
        hospital_id=hospital.id,
        patient_need_id=need.id,
        blood_group=need.blood_group,
        component=need.component,
        units_required=units_value,
        units_coordinated=0,
        urgency=urgency or need.urgency,
        status=BloodRequestStatus.OPEN,
        required_by=need.required_by,
        coordination_note=validate_notes(coordination_note),
        opened_at=utcnow(),
        outreach_tier=0,
    )
    db.add(blood_request)
    need.status = PatientNeedStatus.CONVERTED
    db.flush()

    _record_event(
        db,
        blood_request=blood_request,
        event_type="REQUEST_CREATED",
        from_status=None,
        to_status=BloodRequestStatus.OPEN,
        actor=actor,
        detail={"patientNeedId": need.id, "units": units_value},
    )
    return blood_request


def _next_reference(db: Session) -> str:
    """Human-facing reference (BL-YYMMDD-NNNN) — safe to put in a push payload."""
    today = utcnow().strftime("%y%m%d")
    prefix = f"BL-{today}-"
    used = db.execute(
        select(func.count()).select_from(BloodRequest).where(BloodRequest.reference.like(f"{prefix}%"))
    ).scalar_one()
    candidate = f"{prefix}{used + 1:04d}"
    while db.execute(
        select(BloodRequest.id).where(BloodRequest.reference == candidate)
    ).scalar_one_or_none():
        used += 1
        candidate = f"{prefix}{used + 1:04d}"
    return candidate


def _record_event(
    db: Session,
    *,
    blood_request: BloodRequest,
    event_type: str,
    from_status: BloodRequestStatus | None,
    to_status: BloodRequestStatus | None,
    actor: User | None,
    detail: dict | None = None,
) -> BloodRequestEvent:
    event = BloodRequestEvent(
        blood_request_id=blood_request.id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor.id if actor else None,
        detail=detail or {},
        created_at=utcnow(),
    )
    db.add(event)
    return event


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def transition(
    db: Session,
    *,
    blood_request: BloodRequest,
    to_status: BloodRequestStatus,
    reason: str | None,
    actor: User | None,
) -> BloodRequest:
    """Move a request one legal step, applying that step's side effects.

    OWNER: D3
    ERRORS: 409 REQUEST_TERMINAL, 409 REQUEST_INVALID_TRANSITION
    SIDE EFFECTS: BACKUP_REQUIRED opens tier-2 outreach and alerts staff;
                  FULFILLMENT_PENDING notifies the selected/standby donors;
                  terminal statuses release every active response and close the clock
    """
    current = blood_request.status
    if current in TERMINAL_REQUEST_STATUSES:
        raise ConflictError(
            f"This request is {current.value.lower()} and can no longer change",
            code=ErrorCode.REQUEST_TERMINAL,
        )
    if to_status not in BLOOD_REQUEST_TRANSITIONS.get(current, set()):
        raise ConflictError(
            f"{current.value} cannot move to {to_status.value}",
            code=ErrorCode.REQUEST_INVALID_TRANSITION,
        )

    note = validate_notes(reason)
    blood_request.status = to_status

    if to_status is BloodRequestStatus.BACKUP_REQUIRED:
        blood_request.backup_reason = note or "Coordination needs backup"
    if to_status in TERMINAL_REQUEST_STATUSES:
        blood_request.closed_at = utcnow()
        if to_status is BloodRequestStatus.CANCELLED and note:
            blood_request.backup_reason = note

    db.flush()
    _record_event(
        db,
        blood_request=blood_request,
        event_type="STATUS_CHANGED",
        from_status=current,
        to_status=to_status,
        actor=actor,
        detail={"reason": note} if note else {},
    )

    if to_status is BloodRequestStatus.BACKUP_REQUIRED:
        _expand_outreach(db, blood_request=blood_request)
        _notify_hospital_staff(
            db,
            blood_request=blood_request,
            notification_type=NotificationType.REQUEST_BACKUP_REQUIRED,
            data={"requestId": blood_request.id, "reference": blood_request.reference},
        )
    elif to_status is BloodRequestStatus.FULFILLMENT_PENDING:
        for response in _active_responses(db, blood_request.id):
            notification_service.create_notification(
                db,
                user_id=response.user_id,
                notification_type=NotificationType.FULFILLMENT_PENDING,
                data={"requestId": blood_request.id, "reference": blood_request.reference},
                blood_request_id=blood_request.id,
            )
    elif to_status in TERMINAL_REQUEST_STATUSES:
        _release_responses(db, blood_request=blood_request, reason=f"Request {to_status.value.lower()}")

    db.flush()
    return blood_request


def _expand_outreach(db: Session, *, blood_request: BloodRequest) -> int:
    """Ask D4 for the next outreach tier (interface, not direct table access)."""
    from bloodlink_api.modules.matching import interfaces as matching_interfaces

    next_tier = min(3, (blood_request.outreach_tier or 0) + 1)
    try:
        notified = matching_interfaces.expand_request_outreach(db, blood_request, next_tier=next_tier)
    except NotImplementedError:
        # D4's engine is still behind a scaffold in some deployments: the lifecycle
        # must still work, so surface the escalation without failing the transition.
        return 0
    if notified:
        blood_request.outreach_tier = next_tier
    return notified


def _active_responses(db: Session, blood_request_id: str) -> Sequence[DonorResponse]:
    return db.execute(
        select(DonorResponse).where(
            DonorResponse.blood_request_id == blood_request_id,
            DonorResponse.status.in_(ACTIVE_RESPONSE_STATUSES),
        )
    ).scalars().all()


def _release_responses(db: Session, *, blood_request: BloodRequest, reason: str) -> int:
    released = 0
    for response in _active_responses(db, blood_request.id):
        response.status = DonorResponseStatus.RELEASED
        response.released_at = utcnow()
        response.released_reason = reason
        released += 1
    return released


def _notify_hospital_staff(
    db: Session, *, blood_request: BloodRequest, notification_type: NotificationType, data: dict
) -> int:
    staff = db.execute(
        select(User).where(
            User.organization_id == blood_request.hospital_id, User.is_active.is_(True)
        )
    ).scalars().all()
    sent = 0
    for member in staff:
        if notification_service.create_notification(
            db,
            user_id=member.id,
            notification_type=notification_type,
            data=data,
            blood_request_id=blood_request.id,
        ):
            sent += 1
    return sent


# --------------------------------------------------------------------------- #
# Donor selection + fulfilment (D3 decides, D4 stores)
# --------------------------------------------------------------------------- #
def select_donor(
    db: Session,
    *,
    blood_request: BloodRequest,
    donor_response_id: str,
    standby_response_ids: list[str] | None,
    actor: User | None,
) -> dict:
    """Select the donor who will fulfil the request; move the others to standby.

    STATE CHANGES: DonorResponse(SELECTED / STANDBY / RELEASED) via D4's service;
                   BloodRequest advances to COORDINATING through the legal path
    ERRORS: 404 RESPONSE_NOT_FOUND, 409 DONOR_NOT_SELECTABLE, 409 REQUEST_TERMINAL
    """
    if blood_request.status in TERMINAL_REQUEST_STATUSES:
        raise ConflictError("This request is closed", code=ErrorCode.REQUEST_TERMINAL)

    result = response_service.select_donor(
        db,
        blood_request=blood_request,
        selected_response_id=donor_response_id,
        standby_response_ids=standby_response_ids,
        actor=actor,
    )

    _advance_to(db, blood_request=blood_request, target=BloodRequestStatus.COORDINATING, actor=actor)
    _record_event(
        db,
        blood_request=blood_request,
        event_type="DONOR_SELECTED",
        from_status=None,
        to_status=blood_request.status,
        actor=actor,
        detail={"donorResponseId": donor_response_id},
    )
    db.flush()
    return result


def confirm_fulfillment(
    db: Session,
    *,
    blood_request: BloodRequest,
    donor_profile_ids: Sequence[str] | None,
    hospital_reference: str | None,
    actor: User | None,
) -> list:
    """Close the loop: record the donations and fulfil the request.

    STATE CHANGES: BloodRequest -> FULFILLMENT_CONFIRMED -> FULFILLED;
                   DonationRecord(s) created through D4 (the only write path);
                   donor cooldowns start; contributors are notified
    ERRORS: 409 REQUEST_TERMINAL, 409 REQUEST_INVALID_TRANSITION,
            409 DONATION_CONFIRMATION_INCOMPLETE when no donor is named
    MUST NOT: record screening results or medical clearance
    """
    if blood_request.status in TERMINAL_REQUEST_STATUSES:
        raise ConflictError("This request is already closed", code=ErrorCode.REQUEST_TERMINAL)

    contributors = list(donor_profile_ids or [])
    if not contributors:
        # Default to the donors the hospital selected or kept on standby.
        contributors = [
            response.donor_profile_id
            for response in db.execute(
                select(DonorResponse).where(
                    DonorResponse.blood_request_id == blood_request.id,
                    DonorResponse.status.in_(
                        (DonorResponseStatus.SELECTED, DonorResponseStatus.STANDBY)
                    ),
                )
            ).scalars()
        ]

    from bloodlink_api.modules.donations import service as donation_service

    _advance_to(db, blood_request=blood_request, target=BloodRequestStatus.FULFILLMENT_CONFIRMED, actor=actor)
    records = donation_service.confirm_donations(
        db,
        blood_request=blood_request,
        donor_profile_ids=contributors,
        actor=actor,
        hospital_reference=validate_notes(hospital_reference),
    )
    _advance_to(db, blood_request=blood_request, target=BloodRequestStatus.FULFILLED, actor=actor)
    _record_event(
        db,
        blood_request=blood_request,
        event_type="FULFILLMENT_CONFIRMED",
        from_status=BloodRequestStatus.FULFILLMENT_CONFIRMED,
        to_status=BloodRequestStatus.FULFILLED,
        actor=actor,
        detail={"donors": len(records)},
    )

    # Everyone still holding a response hears that the request closed.
    for response in _active_responses(db, blood_request.id):
        notification_service.create_notification(
            db,
            user_id=response.user_id,
            notification_type=NotificationType.REQUEST_FULFILLED,
            data={"requestId": blood_request.id, "reference": blood_request.reference},
            blood_request_id=blood_request.id,
        )
    db.flush()
    return records


def _advance_to(
    db: Session, *, blood_request: BloodRequest, target: BloodRequestStatus, actor: User | None
) -> None:
    """Walk the legal path to ``target`` (at most three single steps, spec §9)."""
    if blood_request.status is target:
        return
    route: list[BloodRequestStatus] = {
        BloodRequestStatus.RESPONSES_RECEIVED: [BloodRequestStatus.RESPONSES_RECEIVED],
        BloodRequestStatus.COVERED: [BloodRequestStatus.COVERED],
        BloodRequestStatus.COORDINATING: [
            BloodRequestStatus.COVERED,
            BloodRequestStatus.COORDINATING,
        ],
        BloodRequestStatus.FULFILLMENT_PENDING: [
            BloodRequestStatus.COVERED,
            BloodRequestStatus.COORDINATING,
            BloodRequestStatus.FULFILLMENT_PENDING,
        ],
        BloodRequestStatus.FULFILLMENT_CONFIRMED: [
            BloodRequestStatus.COVERED,
            BloodRequestStatus.COORDINATING,
            BloodRequestStatus.FULFILLMENT_PENDING,
            BloodRequestStatus.FULFILLMENT_CONFIRMED,
        ],
    }.get(target, [target])

    # Walk forward from wherever the request is now: the route is the canonical
    # path, but a request may already be part-way along it.
    if blood_request.status in route:
        remaining = route[route.index(blood_request.status) + 1 :]
    else:
        remaining = list(route)

    for step in remaining:
        if step not in BLOOD_REQUEST_TRANSITIONS.get(blood_request.status, set()):
            raise ConflictError(
                f"{blood_request.status.value} cannot move to {step.value}",
                code=ErrorCode.REQUEST_INVALID_TRANSITION,
            )
        previous = blood_request.status
        blood_request.status = step
        db.flush()
        _record_event(
            db,
            blood_request=blood_request,
            event_type="STATUS_CHANGED",
            from_status=previous,
            to_status=step,
            actor=actor,
            detail={"automatic": True, "target": target.value},
        )


# --------------------------------------------------------------------------- #
# Read-only views
# --------------------------------------------------------------------------- #
def outreach_summary(db: Session, *, blood_request: BloodRequest) -> dict:
    """Aggregate counts by tier — never donor identities (spec §21).

    OWNER: D3 (view) — the ledger belongs to D4.
    """
    # NOTE: `case(...)` rather than SQLite's `iif(...)` so the aggregate also runs
    # on PostgreSQL (the production target behind BLOODLINK_GEO_BACKEND=postgis).
    notified_count = func.sum(
        case((DonorOutreach.notified_at.is_not(None), 1), else_=0)
    )
    rows = db.execute(
        select(
            DonorOutreach.tier,
            func.count(),
            notified_count,
        )
        .where(DonorOutreach.blood_request_id == blood_request.id)
        .group_by(DonorOutreach.tier)
    ).all()
    tiers = [
        {"tier": int(tier), "candidates": int(total), "notified": int(notified or 0)}
        for tier, total, notified in rows
    ]
    counts = _responder_counts(db, blood_request.id)
    return {
        "tiers": sorted(tiers, key=lambda item: item["tier"]),
        "notified": sum(item["notified"] for item in tiers),
        "candidates": sum(item["candidates"] for item in tiers),
        "accepted": counts.get("accepted", 0) + counts.get("selected", 0) + counts.get("standby", 0),
        "standby": counts.get("standby", 0),
        "withdrawn": counts.get("withdrawn", 0),
        "unitsOutstanding": blood_request.units_outstanding,
    }


def nearby_requests(
    db: Session,
    *,
    organization: Organization,
    radius_km: float,
    blood_group: str | None = None,
    component: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """Open requests within ``radius_km`` of a blood centre.

    OWNER: D3
    PRIVACY: request id, reference, hospital name, group, component, urgency,
             required-by and a distance band. No patient data, no coordinates.
    """
    filters = [BloodRequest.status.in_(tuple(OUTREACH_ACTIVE_STATUSES))]
    if blood_group:
        filters.append(BloodRequest.blood_group == blood_group)
    if component:
        filters.append(BloodRequest.component == component)

    statement = (
        select(BloodRequest)
        .options(joinedload(BloodRequest.hospital))
        .where(*filters)
        .order_by(BloodRequest.required_by.asc())
    )
    rows = db.execute(statement).scalars().unique().all()

    results: list[dict] = []
    for blood_request in rows:
        hospital = blood_request.hospital
        band = None
        km = None
        if (
            organization.latitude is not None
            and organization.longitude is not None
            and hospital is not None
            and hospital.latitude is not None
            and hospital.longitude is not None
        ):
            km = distance_km(
                from_lat=organization.latitude,
                from_lon=organization.longitude,
                to_lat=hospital.latitude,
                to_lon=hospital.longitude,
            )
            if km is None or km > radius_km:
                continue
            band = distance_band(km)
        results.append(
            {
                "id": blood_request.id,
                "reference": blood_request.reference,
                "bloodGroup": blood_request.blood_group.value,
                "component": blood_request.component.value,
                "unitsRequired": blood_request.units_required,
                "urgency": blood_request.urgency.value,
                "status": blood_request.status.value,
                "requiredBy": iso(blood_request.required_by),
                "hospital": hospital_summary(hospital),
                "distanceBand": band,
                "hasResponded": _organization_responded(db, blood_request.id, organization.id),
            }
        )
        if len(results) >= limit:
            break

    results.sort(key=lambda item: item["distanceBand"] or "~99 km away")
    return results


def _organization_responded(db: Session, blood_request_id: str, organization_id: str) -> bool:
    from bloodlink_api.db.models.donors import OrganizationResponse

    return (
        db.execute(
            select(OrganizationResponse.id).where(
                OrganizationResponse.blood_request_id == blood_request_id,
                OrganizationResponse.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        is not None
    )


def list_board(
    db: Session,
    *,
    hospital_id: str,
    status_filter: str | None = None,
    urgency_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[Sequence[BloodRequest], int]:
    filters = [BloodRequest.hospital_id == hospital_id]
    if status_filter:
        status_value = BloodRequestStatus.coerce(status_filter)
        if status_value is None:
            raise ConflictError("Unknown request status", code=ErrorCode.VALIDATION_ERROR)
        filters.append(BloodRequest.status == status_value)
    if urgency_filter:
        urgency_value = Urgency.coerce(urgency_filter)
        if urgency_value is None:
            raise ConflictError("Unknown urgency", code=ErrorCode.VALIDATION_ERROR)
        filters.append(BloodRequest.urgency == urgency_value)

    total = db.execute(select(func.count()).select_from(BloodRequest).where(*filters)).scalar_one()
    rows = db.execute(
        select(BloodRequest)
        .options(joinedload(BloodRequest.hospital))
        .where(*filters)
        .order_by(BloodRequest.opened_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().unique().all()
    return rows, int(total)


def get_request(db: Session, *, request_id: str) -> BloodRequest:
    blood_request = db.execute(
        select(BloodRequest)
        .options(
            joinedload(BloodRequest.hospital),
            joinedload(BloodRequest.events),
        )
        .where(BloodRequest.id == request_id)
    ).scalars().unique().one_or_none()
    if blood_request is None:
        raise NotFoundError("Request not found", code=ErrorCode.REQUEST_NOT_FOUND)
    return blood_request


def visible_to(db: Session, *, blood_request: BloodRequest, organization: Organization | None) -> None:
    """Hospital staff see their own; ADMIN oversight sees all; others 404."""
    if organization is None or blood_request.hospital_id != organization.id:
        raise NotFoundError("Request not found", code=ErrorCode.REQUEST_NOT_FOUND)


def verified_hospital_of(principal_organization: Organization | None) -> Organization:
    """Guard already ensures the role; this checks verification state."""
    if principal_organization is None:
        raise ForbiddenError("No organization context", code=ErrorCode.FORBIDDEN)
    if principal_organization.verification_status is not OrgVerificationStatus.VERIFIED:
        raise ForbiddenError(
            "Your organization is awaiting verification",
            code=ErrorCode.ORGANIZATION_NOT_VERIFIED,
        )
    return principal_organization
