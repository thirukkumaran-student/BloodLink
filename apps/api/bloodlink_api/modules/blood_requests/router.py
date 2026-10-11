"""BloodRequest endpoints — OWNER: D3 (spec §9, §15).

STATUS: IMPLEMENTED. Contracts were frozen by D1; D3 filled in the bodies in this
file plus ``service.py`` (lifecycle) and ``review.py`` (hospital review gate).

Lifecycle (D1-owned transition table in ``bloodlink_contracts.enums``):

    OPEN -> RESPONSES_RECEIVED -> COVERED -> COORDINATING
         -> FULFILLMENT_PENDING -> FULFILLMENT_CONFIRMED -> FULFILLED
    failure path: coordinating -> BACKUP_REQUIRED -> standby / expanded outreach /
                  reopen coordination

Endpoint contracts:

    GET    /blood-requests                     organization request board
    POST   /blood-requests                     mint a request from an APPROVED need
    GET    /blood-requests/nearby              blood-centre discovery view
    GET    /blood-requests/{id}                request detail (hospital view)
    POST   /blood-requests/{id}/transition     drive the lifecycle
    POST   /blood-requests/{id}/select-donor   select a donor / set standby
    POST   /blood-requests/{id}/confirm-fulfillment  close the loop
    GET    /blood-requests/{id}/outreach       outreach + response summary
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from bloodlink_api.core.audit import record as audit_record
from bloodlink_api.core.clock import iso
from bloodlink_api.core.context import (
    CurrentPrincipal,
    require_blood_centre_context,
    require_hospital_context,
)
from bloodlink_api.core.envelope import success
from bloodlink_api.core.errors import ConflictError, NotFoundError
from bloodlink_api.core.pagination import Page, pagination_params
from bloodlink_api.core.registry import ModuleSpec, register_module
from bloodlink_api.core.routing import api_router
from bloodlink_api.db.models.identity import Organization
from bloodlink_api.db.models.needs import PatientNeed
from bloodlink_api.db.session import get_db
from bloodlink_api.modules.blood_requests import service as request_service
from bloodlink_api.modules.blood_requests.review import router as review_router
from bloodlink_contracts.dto import APIModel
from bloodlink_contracts.enums import BloodRequestStatus, Urgency
from bloodlink_contracts.errors import ErrorCode

#: D3 exposes two surfaces: the request board (``/blood-requests``) and the
#: hospital review queue (``/hospital/patient-needs``). Both belong to D3 (§22).
router = APIRouter()
router.include_router(review_router)
_request_router = api_router(
    owner="D3", domain="blood-requests", prefix="/blood-requests", foundation_status="IMPLEMENTED"
)
#: Verified hospital context is required before any lifecycle endpoint runs — this
#: also blocks a PENDING organization with 403 ORGANIZATION_NOT_VERIFIED, which is
#: the point of the verification gate (`tests/test_auth.py`).
_request_router.dependencies.append(Depends(require_hospital_context))

#: Blood centres see open requests near them, but never the lifecycle endpoints.
_nearby_router = api_router(
    owner="D3", domain="blood-requests", prefix="/blood-requests", foundation_status="IMPLEMENTED"
)
_nearby_router.dependencies.append(Depends(require_blood_centre_context))


class CreateBloodRequestRequest(APIModel):
    """INPUT DTO for POST /blood-requests (D3)."""

    patient_need_id: str
    units_required: int | None = None  # defaults to the need's units
    urgency: Urgency | None = None  # defaults to the need's urgency
    coordination_note: str | None = None


class TransitionRequest(APIModel):
    """INPUT DTO for POST /blood-requests/{id}/transition (D3)."""

    to_status: BloodRequestStatus
    reason: str | None = None


class SelectDonorRequest(APIModel):
    """INPUT DTO for POST /blood-requests/{id}/select-donor (D3, consumes D4 data)."""

    donor_response_id: str
    also_move_to_standby: list[str] = []  # other response ids (suitable, not selected)


class ConfirmFulfillmentRequest(APIModel):
    """INPUT DTO for POST /blood-requests/{id}/confirm-fulfillment (D3)."""

    donor_profile_ids: list[str] = []  # defaults to selected/standby donors
    hospital_reference: str | None = None


def _response_view(db: Session, blood_request) -> list[dict]:
    """Donor response list for the hospital — display name + band + status only."""
    from bloodlink_api.modules.responses import service as response_service

    return response_service.responses_for_request(db, blood_request.id)


@_request_router.get("", summary="Organization request board")
def list_requests(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    request_status: str | None = Query(None, alias="status"),
    urgency: str | None = Query(None),
    page_params: tuple[int, int] = Depends(pagination_params),
) -> dict:
    """List the hospital organization's requests.

    OWNER: D3
    STATUS: IMPLEMENTED
    PURPOSE: Hospital dashboard of open and historical requests.
    INPUT: status?, urgency?, page, pageSize
    OUTPUT: Page<BloodRequestResponse>
    AUTHORIZATION: HOSPITAL users, verified org, own organization only.
    STATE CHANGES: none
    ERRORS: 403 ORGANIZATION_NOT_VERIFIED / FORBIDDEN
    DEPENDENCIES: BloodRequest
    MUST NOT: leak needs from other hospitals
    PRIVACY: response counts only, never patient identity
    """
    page, page_size = page_params
    rows, total = request_service.list_board(
        db,
        hospital_id=principal.organization_id or "",
        status_filter=request_status,
        urgency_filter=urgency,
        page=page,
        page_size=page_size,
    )
    items = [request_service.serialise_request(db, row) for row in rows]
    return success(
        request,
        {"items": items, "pagination": Page(items=items, total=total, page=page, page_size=page_size).meta()},
    )


@_request_router.post("", status_code=status.HTTP_201_CREATED, summary="Create a BloodRequest from an approved need")
def create_request(
    payload: CreateBloodRequestRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Create the official BloodRequest after hospital review of a PatientNeed.

    OWNER: D3
    STATUS: IMPLEMENTED
    PURPOSE: Turn a verified PatientNeed into an actionable request.
    INPUT: CreateBloodRequestRequest
    OUTPUT: 201 BloodRequestResponse (status OPEN)
    AUTHORIZATION: HOSPITAL users only, verified org, need belongs to this hospital.
    STATE CHANGES: PatientNeed(APPROVED -> CONVERTED); BloodRequest(OPEN);
                   BloodRequestEvent(REQUEST_CREATED); tier-1 outreach dispatched via D4
    ERRORS: 403 ORGANIZATION_NOT_VERIFIED, 404 NEED_NOT_FOUND, 409 NEED_ALREADY_REVIEWED
    DEPENDENCIES: Approved PatientNeed, ``bloodlink_validation.validate_units``, D4 outreach
    MUST NOT: perform donor matching inline, send push notifications directly, or manage
              donor acceptance — those are D4 (spec §15 example contract)
    PRIVACY: no patient identity in the request or its events
    """
    hospital = request_service.verified_hospital_of(principal.organization)
    need = db.get(PatientNeed, payload.patient_need_id)
    if need is None or need.hospital_id != hospital.id:
        raise NotFoundError("Need not found", code=ErrorCode.NEED_NOT_FOUND)

    blood_request = request_service.create_from_need(
        db,
        need=need,
        hospital=hospital,
        units_required=payload.units_required,
        urgency=payload.urgency,
        coordination_note=payload.coordination_note,
        actor=principal.user,
    )

    # Tier-1 outreach: ask D4 to match and dispatch. The lifecycle never fails
    # because matching is unavailable — the request simply stays un-notified.
    from bloodlink_api.modules.matching import interfaces as matching_interfaces

    try:
        notified = matching_interfaces.request_outreach(db, blood_request, tier=1)
    except NotImplementedError:  # pragma: no cover - D4 engine is implemented
        notified = 0
    if notified:
        blood_request.outreach_tier = 1

    audit_record(
        db,
        action="blood_request.created",
        actor=principal,
        entity_type="BloodRequest",
        entity_id=blood_request.id,
        detail={"needId": need.id, "units": blood_request.units_required, "notified": notified},
    )
    db.commit()
    return success(request, request_service.serialise_request(db, blood_request, detail=True))


@_nearby_router.get("/nearby", summary="Open requests near a blood centre")
def nearby_requests(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    radius_km: float = Query(25.0, alias="radiusKm", ge=1.0, le=250.0),
    blood_group: str | None = Query(None, alias="bloodGroup"),
    component: str | None = Query(None),
) -> dict:
    """Open requests within a radius of the caller's blood centre.

    OWNER: D3 (route) — distance helpers from D1 core.
    STATUS: IMPLEMENTED
    PURPOSE: Blood-centre discovery of requests it can support.
    INPUT: radiusKm?, bloodGroup?, component?
    OUTPUT: Page<NearbyRequestView> (distance is returned as a coarse band)
    AUTHORIZATION: BLOOD_CENTRE users in a verified organization.
    STATE CHANGES: none
    ERRORS: 403 ORGANIZATION_NOT_VERIFIED
    DEPENDENCIES: bloodlink_api.core.geo distance helpers
    MUST NOT: expose the requesting hospital's patient details
    PRIVACY: request id, group, component, urgency, distance band, hospital name
    """
    organization = principal.organization
    if organization is None:  # pragma: no cover - guard proves context
        raise NotFoundError("Organization not found", code=ErrorCode.ORGANIZATION_NOT_FOUND)

    items = request_service.nearby_requests(
        db,
        organization=organization,
        radius_km=radius_km,
        blood_group=blood_group,
        component=component,
    )
    return success(
        request,
        {
            "items": items,
            "radiusKm": radius_km,
            "centre": {"id": organization.id, "name": organization.name},
            "pagination": Page(items=items, total=len(items), page=1, page_size=len(items) or 1).meta(),
        },
    )


@_request_router.get("/{request_id}", summary="Request detail")
def get_request(
    request_id: str,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Return a request with its lifecycle journal and response summary.

    OWNER: D3
    STATUS: IMPLEMENTED
    PURPOSE: Coordination workspace for hospital staff.
    INPUT: path requestId
    OUTPUT: BloodRequestDetailResponse
    AUTHORIZATION: Owning hospital users (ADMIN oversight reads via /admin).
    STATE CHANGES: none
    ERRORS: 403 FORBIDDEN, 404 REQUEST_NOT_FOUND
    DEPENDENCIES: BloodRequest, BloodRequestEvent, DonorResponse (read-only, D4)
    MUST NOT: expose donor exact location or contact data (spec §21)
    PRIVACY: donors appear as display name + distance band + status only
    """
    blood_request = request_service.get_request(db, request_id=request_id)
    request_service.visible_to(db, blood_request=blood_request, organization=principal.organization)
    return success(request, request_service.serialise_request(db, blood_request, detail=True))


@_request_router.post("/{request_id}/transition", summary="Drive the request lifecycle")
def transition(
    request_id: str,
    payload: TransitionRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Move a request to a new lifecycle status.

    OWNER: D3
    STATUS: IMPLEMENTED
    PURPOSE: Single controlled entry point for every lifecycle change.
    INPUT: TransitionRequest { toStatus, reason? }
    OUTPUT: BloodRequestResponse
    AUTHORIZATION: Owning hospital users; ADMIN oversight is read-only elsewhere.
    STATE CHANGES: BloodRequest.status; BloodRequestEvent(from,to,reason);
                   on BACKUP_REQUIRED: backup_reason set, tier-2 outreach requested;
                   on FULFILLMENT_PENDING: donors notified;
                   on terminal status: active responses released and closedAt set
    ERRORS: 404 REQUEST_NOT_FOUND, 409 REQUEST_INVALID_TRANSITION / REQUEST_TERMINAL
    DEPENDENCIES: ``BLOOD_REQUEST_TRANSITIONS`` (D1 contract), D4 matching + notifications
    MUST NOT: bypass the transition table; a first donor acceptance must not
              auto-close the request (spec §9)
    PRIVACY: reasons are coordination notes, not clinical notes
    """
    blood_request = request_service.get_request(db, request_id=request_id)
    request_service.visible_to(db, blood_request=blood_request, organization=principal.organization)

    blood_request = request_service.transition(
        db,
        blood_request=blood_request,
        to_status=payload.to_status,
        reason=payload.reason,
        actor=principal.user,
    )
    audit_record(
        db,
        action="blood_request.transitioned",
        actor=principal,
        entity_type="BloodRequest",
        entity_id=blood_request.id,
        detail={"toStatus": blood_request.status.value, "reason": payload.reason},
    )
    db.commit()
    return success(request, request_service.serialise_request(db, blood_request, detail=True))


@_request_router.post("/{request_id}/select-donor", summary="Select a donor and hold standby donors")
def select_donor(
    request_id: str,
    payload: SelectDonorRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Select one accepted donor; other suitable donors become STANDBY.

    OWNER: D3 (decision) — D4 owns how responses are generated and stored.
    STATUS: IMPLEMENTED
    PURPOSE: Fulfilment coordination (spec §10).
    INPUT: SelectDonorRequest
    OUTPUT: { selected: DonorResponseView, standby: [DonorResponseView] }
    AUTHORIZATION: Owning hospital users, verified org.
    STATE CHANGES: DonorResponse(SELECTED) for the chosen donor;
                   DonorResponse(STANDBY, standbyStatus=STANDBY) for the others;
                   BloodRequest advances to COORDINATING through the legal path
    ERRORS: 404 RESPONSE_NOT_FOUND, 409 DONOR_NOT_SELECTABLE / REQUEST_TERMINAL
    DEPENDENCIES: D4 response module (``bloodlink_api.modules.responses.service``)
    MUST NOT: notify donors directly — notifications go through D4's service
    PRIVACY: only display name, distance band and response status leave this endpoint
    """
    blood_request = request_service.get_request(db, request_id=request_id)
    request_service.visible_to(db, blood_request=blood_request, organization=principal.organization)

    result = request_service.select_donor(
        db,
        blood_request=blood_request,
        donor_response_id=payload.donor_response_id,
        standby_response_ids=payload.also_move_to_standby or None,
        actor=principal.user,
    )
    audit_record(
        db,
        action="blood_request.donor_selected",
        actor=principal,
        entity_type="BloodRequest",
        entity_id=blood_request.id,
        detail={"donorResponseId": payload.donor_response_id},
    )
    db.commit()

    views = {item["id"]: item for item in _response_view(db, blood_request)}
    return success(
        request,
        {
            "request": request_service.serialise_request(db, blood_request),
            "selected": views.get(result["selected"].id),
            "standby": [views.get(row.id) for row in result["standby"] if views.get(row.id)],
        },
    )


@_request_router.post("/{request_id}/confirm-fulfillment", summary="Confirm fulfilment")
def confirm_fulfillment(
    request_id: str,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    payload: ConfirmFulfillmentRequest | None = None,
) -> dict:
    """Confirm that blood was received, closing the request.

    OWNER: D3
    STATUS: IMPLEMENTED
    PURPOSE: Terminal confirmation; BloodLink does not issue blood (spec §2).
    INPUT: path requestId, optional { donorProfileIds, hospitalReference }
    OUTPUT: BloodRequestResponse (status FULFILLED)
    AUTHORIZATION: Owning hospital users, verified org.
    STATE CHANGES: BloodRequest(FULFILLMENT_CONFIRMED -> FULFILLED);
                   DonationRecord(s) created through D4's donations module for the
                   donors who actually donated; their cooldown starts
    ERRORS: 404 REQUEST_NOT_FOUND, 409 REQUEST_INVALID_TRANSITION,
            409 DONATION_CONFIRMATION_INCOMPLETE
    DEPENDENCIES: D4 donations module (this is the ONLY path that creates a
                  DonationRecord — acceptance alone never does, spec §10)
    MUST NOT: record screening results or medical clearance
    PRIVACY: fulfilment records hold no patient data
    """
    blood_request = request_service.get_request(db, request_id=request_id)
    request_service.visible_to(db, blood_request=blood_request, organization=principal.organization)

    records = request_service.confirm_fulfillment(
        db,
        blood_request=blood_request,
        donor_profile_ids=payload.donor_profile_ids if payload else None,
        hospital_reference=payload.hospital_reference if payload else None,
        actor=principal.user,
    )
    audit_record(
        db,
        action="blood_request.fulfilled",
        actor=principal,
        entity_type="BloodRequest",
        entity_id=blood_request.id,
        detail={"donations": len(records)},
    )
    db.commit()
    return success(request, request_service.serialise_request(db, blood_request, detail=True))


@_request_router.get("/{request_id}/outreach", summary="Outreach and response summary")
def outreach_summary(
    request_id: str,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Summarise outreach tiers, notifications sent and responses received.

    OWNER: D3 (read-only view) — D4 owns the underlying ledger.
    STATUS: IMPLEMENTED
    PURPOSE: Let hospital staff judge whether to expand outreach or go to backup.
    INPUT: path requestId
    OUTPUT: { tiers: [...], notified: n, accepted: n, standby: n, withdrawn: n }
    AUTHORIZATION: Owning hospital users, verified org.
    STATE CHANGES: none
    ERRORS: 404 REQUEST_NOT_FOUND
    DEPENDENCIES: DonorOutreach, DonorResponse (D4, read-only)
    MUST NOT: expose donor identities beyond what the hospital already sees in
              the response list
    PRIVACY: aggregate counts by distance tier
    """
    blood_request = request_service.get_request(db, request_id=request_id)
    request_service.visible_to(db, blood_request=blood_request, organization=principal.organization)
    return success(
        request,
        {
            "requestId": blood_request.id,
            "reference": blood_request.reference,
            "status": blood_request.status.value,
            "requiredBy": iso(blood_request.required_by),
            **request_service.outreach_summary(db, blood_request=blood_request),
        },
    )


router.include_router(_nearby_router)
router.include_router(_request_router)

MODULE = register_module(
    ModuleSpec(
        key="blood_requests",
        owner="D3",
        domain="blood-requests",
        api_prefix="/blood-requests",
        description="BloodRequest lifecycle, responder management, donor selection, fulfilment.",
        foundation_status="IMPLEMENTED",
        router=router,
        depends_on=("auth", "patient_needs", "responses", "notifications", "matching"),
    )
)
