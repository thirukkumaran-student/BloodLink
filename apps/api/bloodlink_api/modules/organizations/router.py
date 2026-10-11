"""Organization endpoints (owner: D1, spec §5, §16).

Read-only organization directory used by every role, plus self-service
maintenance of the caller's own organization profile.
"""

from __future__ import annotations

from fastapi import Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from bloodlink_api.core.clock import iso
from bloodlink_api.core.context import CurrentPrincipal
from bloodlink_api.core.envelope import success
from bloodlink_api.core.errors import ForbiddenError, NotFoundError
from bloodlink_api.core.geo import distance_band, distance_km
from bloodlink_api.core.pagination import Page, pagination_params
from bloodlink_api.core.registry import ModuleSpec, register_module
from bloodlink_api.core.routing import api_router
from bloodlink_api.db.models.donors import DonorProfile
from bloodlink_api.db.models.identity import Organization, OrganizationMembership
from bloodlink_api.db.session import get_db
from bloodlink_contracts.dto import APIModel
from bloodlink_contracts.enums import OrgType, OrgVerificationStatus
from bloodlink_contracts.errors import ErrorCode
from bloodlink_validation.common import clean_text

router = api_router(owner="D1", domain="organizations", prefix="/organizations")


class OrganizationUpdateRequest(APIModel):
    name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    pincode: str | None = None
    latitude: float | None = None
    longitude: float | None = None


def _serialise(organization: Organization) -> dict:
    """Public projection — never includes coordinates (spec §21)."""
    return {
        "id": organization.id,
        "name": organization.name,
        "orgType": organization.org_type.value,
        "verificationStatus": organization.verification_status.value,
        "isOperational": organization.is_operational,
        "city": organization.city,
        "district": organization.district,
        "state": organization.state,
        "locationLabel": organization.location_label,
        "createdAt": iso(organization.created_at),
    }


@router.get("", summary="Organization directory")
def list_organizations(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    org_type: str | None = Query(None, alias="orgType"),
    q: str | None = Query(None, description="Name or city fragment"),
    page_params: tuple[int, int] = Depends(pagination_params),
) -> dict:
    """List verified organizations, optionally filtered by type or name.

    OWNER: D1
    PURPOSE: Shared directory used by hospital discovery (D2) and donor subscriptions (D4).
    INPUT: orgType?, q?, page, pageSize
    OUTPUT: Page<OrganizationView>
    AUTHORIZATION: Any authenticated user; suspended organizations are hidden.
    STATE CHANGES: none
    ERRORS: 401 UNAUTHENTICATED
    DEPENDENCIES: none
    MUST NOT: return coordinates, contact phone numbers or registration numbers
    PRIVACY: name + locality only (spec §21)
    """
    page, page_size = page_params
    query = select(Organization).where(
        Organization.verification_status == OrgVerificationStatus.VERIFIED
    )
    if org_type:
        value = OrgType.coerce(org_type)
        if value is None:
            raise NotFoundError("Unknown organization type", code=ErrorCode.VALIDATION_ERROR)
        query = query.where(Organization.org_type == value)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Organization.name.ilike(like), Organization.city.ilike(like)))

    from sqlalchemy import func

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(
        query.order_by(Organization.name.asc()).limit(page_size).offset((page - 1) * page_size)
    ).scalars()
    items = [_serialise(organization) for organization in rows]
    return success(
        request,
        {"items": items, "pagination": Page(items=items, total=total, page=page, page_size=page_size).meta()},
    )


@router.get("/mine", summary="My organization")
def my_organization(
    request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)
) -> dict:
    """Return the caller's organization context, including verification state.

    OWNER: D1
    PURPOSE: Drives the organization workspace header and the pending-verification banner.
    INPUT: none
    OUTPUT: OrganizationView + verification detail
    AUTHORIZATION: Organization users only.
    STATE CHANGES: none
    ERRORS: 403 FORBIDDEN, 404 ORGANIZATION_NOT_FOUND
    PRIVACY: includes the organization's own contact details (self-view)
    """
    if principal.organization is None:
        raise NotFoundError(
            "Your account is not linked to an organization", code=ErrorCode.ORGANIZATION_NOT_FOUND
        )
    organization = principal.organization
    memberships = db.execute(
        select(OrganizationMembership).where(OrganizationMembership.organization_id == organization.id)
    ).scalars()
    payload = _serialise(organization)
    payload.update(
        {
            "registrationNumber": organization.registration_number,
            "contactEmail": organization.contact_email,
            "contactPhone": organization.contact_phone,
            "address": organization.address,
            "verifiedAt": iso(organization.verified_at),
            "memberCount": len(list(memberships)),
            "membership": {
                "role": principal.role.value,
                "title": next(
                    (
                        membership.title
                        for membership in memberships
                        if membership.user_id == principal.user_id
                    ),
                    None,
                ),
            },
        }
    )
    return success(request, payload)


@router.patch("/mine", summary="Update my organization profile")
def update_my_organization(
    payload: OrganizationUpdateRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Update the caller's own organization profile.

    OWNER: D1
    PURPOSE: Keep facility details and coordinates current for matching and routing.
    INPUT: OrganizationUpdateRequest
    OUTPUT: OrganizationView
    AUTHORIZATION: Organization users; coordinates are organization-internal data.
    STATE CHANGES: Organization fields updated
    ERRORS: 403 FORBIDDEN, 422 VALIDATION_ERROR
    DEPENDENCIES: ``bloodlink_validation.validate_coordinates``
    MUST NOT: change verificationStatus (admin-only) or orgType
    PRIVACY: coordinates are stored internally and never returned by the public directory
    """
    if principal.organization is None:
        raise ForbiddenError("Your account is not linked to an organization")
    organization = principal.organization

    if payload.name:
        organization.name = clean_text(payload.name, max_length=160, allow_empty=False)
    organization.contact_email = clean_text(payload.contact_email, max_length=254)
    organization.contact_phone = clean_text(payload.contact_phone, max_length=20)
    organization.address = clean_text(payload.address, max_length=240)
    organization.city = clean_text(payload.city, max_length=80)
    organization.district = clean_text(payload.district, max_length=80)
    organization.state = clean_text(payload.state, max_length=80)
    organization.pincode = clean_text(payload.pincode, max_length=10)
    if payload.latitude is not None or payload.longitude is not None:
        from bloodlink_validation.common import validate_coordinates

        latitude, longitude = validate_coordinates(payload.latitude, payload.longitude)
        organization.latitude = latitude
        organization.longitude = longitude

    db.commit()
    return success(request, _serialise(organization))


@router.get("/{organization_id}", summary="Organization detail")
def get_organization(
    organization_id: str, request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)
) -> dict:
    """Return one organization's public profile, with a coarse distance band.

    OWNER: D1
    PURPOSE: Detail view from directory/search results.
    INPUT: path organizationId
    OUTPUT: OrganizationView (+ distanceBand for donors)
    AUTHORIZATION: Any authenticated user.
    STATE CHANGES: none
    ERRORS: 404 ORGANIZATION_NOT_FOUND
    MUST NOT: expose exact coordinates — only a rounded distance band (spec §21)
    """
    organization = db.get(Organization, organization_id)
    if organization is None or organization.verification_status is OrgVerificationStatus.SUSPENDED:
        raise NotFoundError("Organization not found", code=ErrorCode.ORGANIZATION_NOT_FOUND)

    payload = _serialise(organization)
    profile = db.execute(
        select(DonorProfile).where(DonorProfile.user_id == principal.user_id)
    ).scalar_one_or_none()
    if profile is not None:
        km = distance_km(
            from_lat=profile.latitude,
            from_lon=profile.longitude,
            to_lat=organization.latitude,
            to_lon=organization.longitude,
        )
        payload["distanceBand"] = distance_band(km)
    return success(request, payload)


MODULE = register_module(
    ModuleSpec(
        key="organizations",
        owner="D1",
        domain="organizations",
        api_prefix="/organizations",
        description="Organization directory, own-organization context and profile maintenance.",
        foundation_status="COMPLETE",
        router=router,
        depends_on=("auth",),
    )
)
