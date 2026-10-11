"""Hospital PatientNeed review queue — OWNER: D3 (spec §5, §8).

STATUS: IMPLEMENTED. D3 owns the review decision because the review is what mints
a BloodRequest; D2 owns everything before review (submission) and the
individual-facing history.

Endpoint contracts:

    GET  /hospital/patient-needs                 review queue (PENDING first)
    GET  /hospital/patient-needs/{id}            need detail for review
    POST /hospital/patient-needs/{id}/review     APPROVE or REJECT
"""

from __future__ import annotations

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from bloodlink_api.core.audit import record as audit_record
from bloodlink_api.core.context import CurrentPrincipal, require_hospital_context
from bloodlink_api.core.envelope import success
from bloodlink_api.core.errors import NotFoundError
from bloodlink_api.core.pagination import Page, pagination_params
from bloodlink_api.core.routing import api_router
from bloodlink_api.db.models.identity import Organization
from bloodlink_api.db.session import get_db
from bloodlink_api.modules.blood_requests import service as request_service
from bloodlink_api.modules.patient_needs import service as need_service
from bloodlink_contracts.dto import APIModel
from bloodlink_contracts.enums import PatientNeedStatus
from bloodlink_contracts.errors import ErrorCode

#: Role guard runs *before* the handler, so a donor receives 403 (not 404/501):
#: authorization is part of the contract D1 fixed (spec §15, §16).
router = api_router(
    owner="D3",
    domain="hospital-needs",
    prefix="/hospital/patient-needs",
    foundation_status="IMPLEMENTED",
)
router.dependencies.append(Depends(require_hospital_context))


class ReviewDecisionRequest(APIModel):
    """INPUT DTO for POST /hospital/patient-needs/{id}/review (D3)."""

    decision: PatientNeedStatus  # APPROVED | REJECTED
    reason: str | None = None  # shown to the submitter; coordination context only


def _hospital_of(db: Session, principal: CurrentPrincipal) -> Organization:
    hospital = db.get(Organization, principal.organization_id)
    if hospital is None:  # pragma: no cover - the guard already proves context
        raise NotFoundError("Organization not found", code=ErrorCode.ORGANIZATION_NOT_FOUND)
    return hospital


@router.get("", summary="Hospital review queue")
def review_queue(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    need_status: str | None = Query(None, alias="status", description="Filter by PatientNeed status"),
    page_params: tuple[int, int] = Depends(pagination_params),
) -> dict:
    """List PatientNeeds submitted to this hospital, pending review first.

    OWNER: D3
    STATUS: IMPLEMENTED
    PURPOSE: The hospital's inbox of incoming needs (spec §5).
    INPUT: status?, page, pageSize
    OUTPUT: Page<PatientNeedResponse>
    AUTHORIZATION: HOSPITAL users in a verified organization, own hospital only.
    STATE CHANGES: none
    ERRORS: 403 ORGANIZATION_NOT_VERIFIED / FORBIDDEN
    DEPENDENCIES: PatientNeed (D2 model)
    MUST NOT: show pending needs addressed to a different hospital
    PRIVACY: submitter name + contact window only; no diagnosis stored or returned
    """
    page, page_size = page_params
    rows, total, hospitals, submitters = need_service.review_queue(
        db,
        hospital_id=principal.organization_id or "",
        status=need_status,
        page=page,
        page_size=page_size,
    )
    items = [
        need_service.serialise_need(
            need,
            hospital=hospitals.get(need.hospital_id),
            submitter=submitters.get(need.submitted_by_user_id),
        )
        for need in rows
    ]
    return success(
        request,
        {"items": items, "pagination": Page(items=items, total=total, page=page, page_size=page_size).meta()},
    )


@router.get("/{need_id}", summary="Need detail for review")
def review_detail(
    need_id: str,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Return a submitted need with the information needed to decide.

    OWNER: D3
    STATUS: IMPLEMENTED
    PURPOSE: Hospital review screen.
    INPUT: path needId
    OUTPUT: PatientNeedResponse
    AUTHORIZATION: HOSPITAL users of the addressed hospital only.
    STATE CHANGES: none
    ERRORS: 404 NEED_NOT_FOUND, 403 FORBIDDEN
    DEPENDENCIES: PatientNeed
    MUST NOT: expose data to blood centres or other hospitals — a foreign id is 404
    PRIVACY: notes are coordination context; the hospital already owns the clinical relationship
    """
    from bloodlink_api.db.models.needs import PatientNeed

    need = db.get(PatientNeed, need_id)
    if need is None or need.hospital_id != principal.organization_id:
        raise NotFoundError("Need not found", code=ErrorCode.NEED_NOT_FOUND)
    submitter = db.get(type(principal.user), need.submitted_by_user_id)
    return success(
        request,
        need_service.serialise_need(
            need, hospital=_hospital_of(db, principal), submitter=submitter
        ),
    )


@router.post("/{need_id}/review", summary="Approve or reject a submitted need")
def review_need(
    need_id: str,
    payload: ReviewDecisionRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Record the hospital's decision on a PatientNeed.

    OWNER: D3
    STATUS: IMPLEMENTED
    PURPOSE: Gate between a request submitted by an individual and an official
             BloodRequest (spec §8 flow).
    INPUT: ReviewDecisionRequest { decision: APPROVED | REJECTED, reason? }
    OUTPUT: PatientNeedResponse
    AUTHORIZATION: HOSPITAL users of the addressed hospital, verified org.
    STATE CHANGES: PatientNeed(PENDING_HOSPITAL_REVIEW -> APPROVED | REJECTED);
                   reviewedByUserId, reviewedAt, reviewReason;
                   Notification(NEED_REVIEWED) to the submitter
    ERRORS: 404 NEED_NOT_FOUND, 409 NEED_ALREADY_REVIEWED
    DEPENDENCIES: PatientNeed; notification request to D4 for the submitter
    MUST NOT: create the BloodRequest (separate explicit step: POST /blood-requests),
              or contact donors
    PRIVACY: reason is shared with the submitter and must stay non-clinical
    """
    from bloodlink_api.db.models.needs import PatientNeed

    need = db.get(PatientNeed, need_id)
    if need is None or need.hospital_id != principal.organization_id:
        raise NotFoundError("Need not found", code=ErrorCode.NEED_NOT_FOUND)

    need = request_service.review_need(
        db,
        need=need,
        hospital_id=principal.organization_id or "",
        decision=payload.decision,
        reason=payload.reason,
        actor=principal.user,
    )
    audit_record(
        db,
        action="patient_need.reviewed",
        actor=principal,
        entity_type="PatientNeed",
        entity_id=need.id,
        detail={"decision": need.status.value},
    )
    db.commit()
    submitter = db.get(type(principal.user), need.submitted_by_user_id)
    return success(
        request,
        need_service.serialise_need(
            need, hospital=_hospital_of(db, principal), submitter=submitter
        ),
    )
