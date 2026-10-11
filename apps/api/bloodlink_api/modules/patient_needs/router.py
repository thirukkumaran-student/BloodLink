"""PatientNeed endpoints — OWNER: D2 (spec §8, §15).

STATUS: IMPLEMENTED. The contracts were frozen by D1 during the foundation
sprint; D2 filled in the bodies in this file plus ``service.py``. Paths, DTOs and
error codes are unchanged from the scaffold.

Endpoint contracts:

    POST   /patient-needs                     individual submits a need
    GET    /patient-needs                     own submissions (submitter view)
    GET    /patient-needs/{id}                own submission detail
    POST   /patient-needs/{id}/cancel         withdraw a pending need
    GET    /patient-needs/reference/hospitals hospitals that can receive a need

The hospital review queue lives in D3 (``modules/blood_requests/review.py``):
reviewing a need is what mints a BloodRequest, so the decision belongs with the
request lifecycle owner.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Depends, Query, Request, status
from sqlalchemy.orm import Session

from bloodlink_api.core.audit import record as audit_record
from bloodlink_api.core.context import CurrentPrincipal, require_authenticated
from bloodlink_api.core.envelope import success
from bloodlink_api.core.pagination import Page, pagination_params
from bloodlink_api.core.registry import ModuleSpec, register_module
from bloodlink_api.core.routing import api_router
from bloodlink_api.db.models.identity import Organization
from bloodlink_api.db.session import get_db
from bloodlink_api.modules.patient_needs import service as need_service
from bloodlink_contracts.dto import APIModel
from bloodlink_contracts.enums import BloodComponent, BloodGroup, Urgency
from bloodlink_contracts.errors import ErrorCode

router = api_router(
    owner="D2", domain="patient-needs", prefix="/patient-needs", foundation_status="IMPLEMENTED"
)
#: Authentication is the only precondition for the individual surface.
router.dependencies.append(Depends(require_authenticated))


class CreatePatientNeedRequest(APIModel):
    """INPUT DTO for POST /patient-needs.

    Field rules are owned by ``bloodlink_validation`` (D1); the service layer
    applies them again so the API never trusts a client-side check.
    """

    hospital_id: str
    blood_group: BloodGroup
    component: BloodComponent
    units: int
    urgency: Urgency
    required_by: datetime  # ISO-8601 timestamp; exact time, not a date (spec §8)
    additional_notes: str | None = None


class CancelNeedRequest(APIModel):
    reason: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED, summary="Submit a PatientNeed")
def create_need(
    payload: CreatePatientNeedRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Create a PatientNeed for a specific hospital to review.

    OWNER: D2
    STATUS: IMPLEMENTED
    PURPOSE: Let an individual (or hospital staff on a patient's behalf) request
             blood from a chosen hospital.
    INPUT: CreatePatientNeedRequest
    OUTPUT: 201 PatientNeedResponse { id, status: PENDING_HOSPITAL_REVIEW, ... }
    AUTHORIZATION: Any authenticated user; hospitalId must reference a VERIFIED hospital.
    STATE CHANGES: PatientNeed(status=PENDING_HOSPITAL_REVIEW);
                   Notification(NEED_SUBMITTED) to the hospital's active staff
    ERRORS: 404 ORGANIZATION_NOT_FOUND, 409 ORGANIZATION_NOT_VERIFIED / ORGANIZATION_SUSPENDED,
            422 NEED_REQUIRED_BY_IN_PAST / VALIDATION_ERROR
    DEPENDENCIES: Organization (D1), bloodlink_validation, notifications (D4)
    MUST NOT: create a BloodRequest, contact donors, or notify donors
    PRIVACY: additionalNotes is coordination context — reject anything that looks
             like a diagnosis, test result or medical record
    """
    need, hospital = need_service.create_need(
        db,
        submitter=principal.user,
        hospital_id=payload.hospital_id,
        blood_group=payload.blood_group,
        component=payload.component,
        units=payload.units,
        urgency=payload.urgency,
        required_by=payload.required_by,
        additional_notes=payload.additional_notes,
    )
    audit_record(
        db,
        action="patient_need.created",
        actor=principal,
        entity_type="PatientNeed",
        entity_id=need.id,
        detail={"hospitalId": hospital.id, "urgency": need.urgency.value, "units": need.units},
    )
    db.commit()
    return success(request, need_service.serialise_need(need, hospital=hospital, submitter=principal.user))


@router.get("", summary="List own submitted needs")
def list_own_needs(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    need_status: str | None = Query(None, alias="status", description="Filter by PatientNeed status"),
    page_params: tuple[int, int] = Depends(pagination_params),
) -> dict:
    """List the caller's own PatientNeed submissions.

    OWNER: D2
    STATUS: IMPLEMENTED
    PURPOSE: Individual request/history UI (spec §5).
    INPUT: status?, page, pageSize
    OUTPUT: Page<PatientNeedResponse>
    AUTHORIZATION: Self only — never another user's submissions.
    STATE CHANGES: none
    ERRORS: 401 UNAUTHENTICATED, 422 VALIDATION_ERROR
    DEPENDENCIES: PatientNeed
    MUST NOT: expose hospital-internal review notes
    PRIVACY: no donor or third-party data
    """
    page, page_size = page_params
    rows, total = need_service.list_for_submitter(
        db, submitter_id=principal.user_id, status=need_status, page=page, page_size=page_size
    )
    hospitals = {
        hospital.id: hospital
        for hospital in db.query(Organization).filter(
            Organization.id.in_({row.hospital_id for row in rows})
        )
    }
    items = [
        need_service.serialise_need(row, hospital=hospitals.get(row.hospital_id), submitter=principal.user)
        for row in rows
    ]
    return success(
        request,
        {"items": items, "pagination": Page(items=items, total=total, page=page, page_size=page_size).meta()},
    )


@router.get("/reference/hospitals", summary="Hospitals available to receive a need")
def discover_hospitals(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    q: str | None = Query(None, description="Match on name, city or district"),
    city: str | None = Query(None),
    district: str | None = Query(None),
) -> dict:
    """Search verified hospitals for the individual 'where should this go' step.

    OWNER: D2
    STATUS: IMPLEMENTED
    PURPOSE: Hospital discovery for individuals (spec §5).
    INPUT: q?, city?, district?
    OUTPUT: { items: [HospitalDiscoveryView] } { id, name, city, district, distanceBand? }
    AUTHORIZATION: Any authenticated user.
    STATE CHANGES: none
    ERRORS: 401 UNAUTHENTICATED, 422 VALIDATION_ERROR
    DEPENDENCIES: Organization (D1, VERIFIED hospitals only), geo distance bands
    MUST NOT: return exact coordinates — only coarse distance bands (spec §21)
    PRIVACY: expose name + locality + distance band only
    """
    items = need_service.discover_hospitals(
        db, q=q, city=city, district=district, viewer=principal.user
    )
    return success(request, {"items": items})


@router.get("/{need_id}", summary="Read one of my needs")
def get_need(
    need_id: str,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Return a single submitted need with its review outcome.

    OWNER: D2
    STATUS: IMPLEMENTED
    PURPOSE: Submission detail screen, including the hospital's decision.
    INPUT: path needId
    OUTPUT: PatientNeedResponse
    AUTHORIZATION: Submitter only (org users see needs for their hospital through
                   the D3 review endpoints). ADMIN for oversight.
    STATE CHANGES: none
    ERRORS: 404 NEED_NOT_FOUND
    DEPENDENCIES: PatientNeed
    MUST NOT: return another submitter's need — a foreign id answers 404, not 403
    PRIVACY: rejection reason is submitter-visible; internal memos are not stored here
    """
    need = need_service.get_for_submitter(
        db, need_id=need_id, submitter_id=principal.user_id, is_admin=principal.is_admin
    )
    hospital = db.get(Organization, need.hospital_id)
    return success(request, need_service.serialise_need(need, hospital=hospital, submitter=principal.user))


@router.post("/{need_id}/cancel", summary="Cancel a pending need")
def cancel_need(
    need_id: str,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    payload: CancelNeedRequest | None = None,
) -> dict:
    """Withdraw a need that is still pending hospital review.

    OWNER: D2
    STATUS: IMPLEMENTED
    PURPOSE: Submitter-controlled cancellation before review.
    INPUT: path needId, optional { reason }
    OUTPUT: PatientNeedResponse (status CANCELLED)
    AUTHORIZATION: Submitter only.
    STATE CHANGES: PatientNeed.status=PENDING_HOSPITAL_REVIEW -> CANCELLED
    ERRORS: 404 NEED_NOT_FOUND, 409 NEED_NOT_CANCELLABLE (already reviewed/converted)
    DEPENDENCIES: PatientNeed
    MUST NOT: cancel a need that already produced a BloodRequest — that request must
               be cancelled through the D3 lifecycle so backup coordination can run
    PRIVACY: none
    """
    need = need_service.get_for_submitter(db, need_id=need_id, submitter_id=principal.user_id)
    need = need_service.cancel_need(
        db, need=need, actor=principal.user, reason=payload.reason if payload else None
    )
    audit_record(
        db,
        action="patient_need.cancelled",
        actor=principal,
        entity_type="PatientNeed",
        entity_id=need.id,
        detail={"reason": need.review_reason},
    )
    db.commit()
    hospital = db.get(Organization, need.hospital_id)
    return success(request, need_service.serialise_need(need, hospital=hospital, submitter=principal.user))


MODULE = register_module(
    ModuleSpec(
        key="patient_needs",
        owner="D2",
        domain="patient-needs",
        api_prefix="/patient-needs",
        description="Individual hospital discovery + PatientNeed submission and history.",
        foundation_status="IMPLEMENTED",
        router=router,
        depends_on=("auth", "organizations"),
    )
)
