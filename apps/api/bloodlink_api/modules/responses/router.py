"""Donor response endpoints — OWNER: D4 (spec §10, §11).

Implemented in the foundation sprint (the acceptance contract is
cross-domain-critical, so D1 built the rails and D4 owns the surrounding flows):

    GET  /donor/matched-requests          requests compatible with my profile
    GET  /donor/responses                 my responses
    POST /donor/blood-requests/{id}/accept  explicit, confirmed acceptance
    POST /donor/responses/{id}/withdraw     withdraw an acceptance
    POST /blood-centres/responses         blood centre offers availability
    GET  /blood-centres/responses         my organization's offers


The blood-centre router is exported separately (`MODULE_EXTRA_ROUTERS`) so it mounts
at `/blood-centres`, not beneath the donor prefix.
"""

from __future__ import annotations

from fastapi import Depends, Request, status
from sqlalchemy.orm import Session

from bloodlink_api.core.context import BloodCentrePrincipal, CurrentPrincipal
from bloodlink_api.core.envelope import success
from bloodlink_api.core.errors import NotFoundError
from bloodlink_api.core.registry import ModuleSpec, register_module
from bloodlink_api.core.routing import api_router
from bloodlink_api.db.models.blood_requests import BloodRequest
from bloodlink_api.db.models.donors import DonorProfile, DonorResponse, OrganizationResponse
from bloodlink_api.db.session import get_db
from bloodlink_api.modules.responses import service as response_service
from bloodlink_contracts.dto import APIModel
from bloodlink_contracts.enums import BloodGroup, BloodComponent, OrganizationResponseStatus
from bloodlink_contracts.errors import ErrorCode
from bloodlink_api.core.context import require_donor_profile

router = api_router(owner="D4", domain="donor-responses", prefix="/donor")


class AcceptRequest(APIModel):
    """INPUT DTO for POST /donor/blood-requests/{id}/accept.

    ``confirmation`` must be ``EXPLICIT`` — the client sends this only after the
    user confirms in the confirmation UI (spec §10). Cancelling that UI must not
    call this endpoint at all.
    """

    confirmation: str = "NONE"
    eta_minutes: int | None = None
    remarks: str | None = None


class WithdrawRequest(APIModel):
    reason: str | None = None


class OrganizationResponseRequest(APIModel):
    blood_request_id: str
    status: OrganizationResponseStatus
    units_offered: int | None = None
    component: BloodComponent | None = None
    blood_group: BloodGroup | None = None
    notes: str | None = None


@router.get("/matched-requests", summary="Requests my donor profile can help with")
def matched_requests(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    profile: DonorProfile = Depends(require_donor_profile),
) -> dict:
    """List open requests compatible with the donor's blood group, nearest first.

    OWNER: D4
    PURPOSE: Donor discovery surface (web).
    INPUT: none (uses the caller's donor profile)
    OUTPUT: { items: [DonorRequestCard], donor: { bloodGroup, distanceBandNote } }
    AUTHORIZATION: Authenticated user with a donor profile.
    STATE CHANGES: none
    ERRORS: 403 DONOR_PROFILE_REQUIRED
    DEPENDENCIES: matching + geo helpers (D1), compatibility matrix (D1 contract)
    MUST NOT: rank by anything other than distance for MVP; never decide medical
              eligibility; never expose patient identity (§2, §11, §21)
    PRIVACY: hospital name + coarse distance band only; no patient, no coordinates
    """
    eligible, cooldown_days = response_service.mobile_eligible(db, profile)
    items = response_service.matched_requests_for_profile(db, profile)
    return success(
        request,
        {
            "items": items,
            "donor": {
                "bloodGroup": profile.blood_group.value,
                "isAvailable": profile.is_available,
                "acceptsNotifications": profile.accepts_notifications,
                "eligibleForOutreach": eligible,
                "cooldownDaysRemaining": cooldown_days,
                "compatibilityNote": (
                    "Compatibility shown here only targets BloodLink outreach. Screening, "
                    "crossmatching, collection and issue remain with the hospital / blood centre."
                ),
            },
        },
    )


@router.get("/responses", summary="My donor responses")
def my_responses(
    request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db), profile: DonorProfile = Depends(require_donor_profile)
) -> dict:
    """List the donor's own responses and their coordination status.

    OWNER: D4
    PURPOSE: Donor "my commitments" screen.
    INPUT: none
    OUTPUT: { items: [DonorResponseView] }
    AUTHORIZATION: Self only.
    STATE CHANGES: none
    ERRORS: 403 DONOR_PROFILE_REQUIRED
    PRIVACY: no hospital-internal notes
    """
    return success(request, {"items": response_service.list_responses_for_donor(db, profile)})


@router.post("/blood-requests/{request_id}/accept", status_code=status.HTTP_201_CREATED, summary="Accept a request (explicit confirmation required)")
def accept(
    request_id: str,
    payload: AcceptRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    profile: DonorProfile = Depends(require_donor_profile),
) -> dict:
    """Record an explicit donor acceptance against a blood request.

    OWNER: D4
    PURPOSE: The donor-side acceptance contract (spec §10).
    INPUT: AcceptRequest { confirmation: "EXPLICIT", etaMinutes?, remarks? }
    OUTPUT: 201 DonorResponseView (status ACCEPTED)
    AUTHORIZATION: Authenticated donor (profile required).
    STATE CHANGES: DonorResponse(ACCEPTED, confirmedAt);
                   BloodRequest OPEN -> RESPONSES_RECEIVED (never closed);
                   hospital coordinators notified
    ERRORS: 422 CONFIRMATION_REQUIRED (confirmation step skipped),
            409 REQUEST_NOT_OPEN_FOR_RESPONSES, 409 DONOR_IN_COOLDOWN,
            409 RESPONSE_ALREADY_EXISTS, 409 DONOR_NOT_ELIGIBLE_FOR_OUTREACH,
            404 REQUEST_NOT_FOUND
    DEPENDENCIES: notifications module
    MUST NOT: mark the request covered/fulfilled, mutate state when the
              confirmation step is cancelled, or treat acceptance as a donation
    PRIVACY: hospital sees the donor's name and distance band only
    """
    blood_request = db.get(BloodRequest, request_id)
    if blood_request is None:
        raise NotFoundError("Blood request not found", code=ErrorCode.REQUEST_NOT_FOUND)

    response = response_service.accept_request(
        db,
        user=principal.user,
        profile=profile,
        blood_request=blood_request,
        confirmed=payload.confirmation.upper() == "EXPLICIT",
        eta_minutes=payload.eta_minutes,
        remarks=payload.remarks,
    )
    from bloodlink_api.core.audit import record

    record(
        db,
        action="donor.response.accepted",
        actor=principal,
        entity_type="donor_response",
        entity_id=response.id,
        detail={"requestId": blood_request.id},
    )
    db.commit()
    return success(
        request,
        {
            "id": response.id,
            "requestId": blood_request.id,
            "status": response.status.value,
            "confirmedAt": response.confirmed_at.isoformat() + "Z" if response.confirmed_at else None,
        },
    )


@router.post("/responses/{response_id}/withdraw", summary="Withdraw an acceptance")
def withdraw(
    response_id: str,
    payload: WithdrawRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    profile: DonorProfile = Depends(require_donor_profile),
) -> dict:
    """Withdraw a previously accepted response.

    OWNER: D4
    PURPOSE: Donors must be able to step back; the hospital then needs backup.
    INPUT: path responseId, { reason? }
    OUTPUT: DonorResponseView (status WITHDRAWN)
    AUTHORIZATION: The donor who owns the response.
    STATE CHANGES: DonorResponse(WITHDRAWN); if the donor was SELECTED, the request
                   moves to BACKUP_REQUIRED and the hospital is notified
    ERRORS: 403 FORBIDDEN, 404 RESPONSE_NOT_FOUND, 409 CONFLICT
    DEPENDENCIES: notifications module
    MUST NOT: silently reopen a request without telling the hospital
    """
    response = db.get(DonorResponse, response_id)
    if response is None:
        raise NotFoundError("Response not found", code=ErrorCode.RESPONSE_NOT_FOUND)
    response_service.withdraw_response(db, profile=profile, response=response, reason=payload.reason)
    db.commit()
    return success(request, {"id": response.id, "status": response.status.value})


# --------------------------------------------------------------------------- #
# Blood centre side (D4 owns §5 blood-centre flows)
# --------------------------------------------------------------------------- #
blood_centre_router = api_router(owner="D4", domain="blood-centre-responses", prefix="/blood-centres")


@blood_centre_router.post("/responses", status_code=status.HTTP_201_CREATED, summary="Offer availability for a request")
def submit_organization_response(
    payload: OrganizationResponseRequest,
    request: Request,
    principal: BloodCentrePrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Blood centre reports availability against an open request.

    OWNER: D4
    PURPOSE: OrganizationResponse flow (spec §7).
    INPUT: OrganizationResponseRequest
    OUTPUT: 201 OrganizationResponseView
    AUTHORIZATION: BLOOD_CENTRE users in a VERIFIED organization.
    STATE CHANGES: OrganizationResponse(AVAILABLE|PARTIAL|UNAVAILABLE);
                   hospital coordinators notified
    ERRORS: 403 ORGANIZATION_NOT_VERIFIED, 404 REQUEST_NOT_FOUND,
            409 ORGANIZATION_RESPONSE_EXISTS
    DEPENDENCIES: notifications module
    MUST NOT: modify the request lifecycle (D3 owns transitions), claim stock that
              BloodLink does not track, or expose donor data
    PRIVACY: notes are coordination text; no patient information
    """
    blood_request = db.get(BloodRequest, payload.blood_request_id)
    if blood_request is None:
        raise NotFoundError("Blood request not found", code=ErrorCode.REQUEST_NOT_FOUND)

    response = response_service.submit_organization_response(
        db,
        blood_request=blood_request,
        organization=principal.organization,
        actor=principal.user,
        status=payload.status,
        units_offered=payload.units_offered,
        component=payload.component,
        blood_group=payload.blood_group,
        notes=payload.notes,
    )
    db.commit()
    return success(
        request,
        {"id": response.id, "status": response.status.value, "unitsOffered": response.units_offered},
    )


@blood_centre_router.get("/responses", summary="My organization's responses")
def list_organization_responses(
    request: Request, principal: BloodCentrePrincipal, db: Session = Depends(get_db)
) -> dict:
    """List the blood centre's own responses and their outcome.

    OWNER: D4
    PURPOSE: Blood centre dashboard.
    INPUT: none
    OUTPUT: { items: [OrganizationResponseView] }
    AUTHORIZATION: BLOOD_CENTRE users in their own organization.
    STATE CHANGES: none
    ERRORS: 403 FORBIDDEN
    PRIVACY: hospital name + request status only, no patient data
    """
    items = response_service.list_organization_responses(db, principal.organization_id)
    return success(request, {"items": items})


# D4 owns §5 blood-centre flows too, but a blood centre is not a donor: the
# blood-centre router mounts on its own top-level prefix so RBAC and the client's
# endpoint map line up (spec §22 — one prefix per surface).


MODULE = register_module(
    ModuleSpec(
        key="responses",
        owner="D4",
        domain="responses",
        api_prefix="/donor",
        description="Donor acceptance/withdrawal, blood-centre availability responses, standby handling.",
        foundation_status="COMPLETE",
        router=router,
        extra_routers=(blood_centre_router,),
        depends_on=("auth", "matching", "notifications"),
    )
)
