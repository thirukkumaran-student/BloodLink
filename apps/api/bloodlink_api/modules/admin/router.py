"""Admin endpoints (owner: D1, spec §16)."""

from __future__ import annotations

from fastapi import Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bloodlink_api.core.audit import record
from bloodlink_api.core.clock import iso, utcnow
from bloodlink_api.core.context import AdminPrincipal
from bloodlink_api.core.envelope import success
from bloodlink_api.core.errors import DomainError, NotFoundError
from bloodlink_api.core.pagination import Page, pagination_params
from bloodlink_api.core.registry import ModuleSpec, module_summary, register_module
from bloodlink_api.core.routing import api_router
from bloodlink_api.db.models.blood_requests import BloodRequest
from bloodlink_api.db.models.identity import AuditLog, Organization, User
from bloodlink_api.db.session import get_db
from bloodlink_contracts.enums import BloodRequestStatus, OrgVerificationStatus
from bloodlink_contracts.errors import ErrorCode

router = api_router(owner="D1", domain="admin", prefix="/admin", foundation_status="COMPLETE")


@router.get("/organizations", summary="List organizations awaiting or holding verification")
def list_organizations(
    request: Request,
    principal: AdminPrincipal,
    db: Session = Depends(get_db),
    verification_status: str | None = Query(None, description="PENDING | VERIFIED | SUSPENDED"),
    page_params: tuple[int, int] = Depends(pagination_params),
) -> dict:
    """List organizations with verification state.

    OWNER: D1
    PURPOSE: Administration console for hospital / blood centre onboarding.
    INPUT: verificationStatus?, page, pageSize
    OUTPUT: Page<OrganizationAdminView>
    AUTHORIZATION: ADMIN only.
    STATE CHANGES: none
    ERRORS: 403 FORBIDDEN
    DEPENDENCIES: none
    MUST NOT: mutate verification state (see the verify/suspend endpoints)
    PRIVACY: exact coordinates are withheld; only city/district are returned
    """
    page, page_size = page_params
    query = select(Organization)
    if verification_status:
        status_value = OrgVerificationStatus.coerce(verification_status)
        if status_value is None:
            raise DomainError(
                "Unknown verification status", code=ErrorCode.VALIDATION_ERROR, status_code=422
            )
        query = query.where(Organization.verification_status == status_value)

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(
        query.order_by(Organization.created_at.desc()).limit(page_size).offset((page - 1) * page_size)
    ).scalars()
    items = [
        {
            "id": org.id,
            "name": org.name,
            "orgType": org.org_type.value,
            "verificationStatus": org.verification_status.value,
            "registrationNumber": org.registration_number,
            "contactEmail": org.contact_email,
            "contactPhone": org.contact_phone,
            "locationLabel": org.location_label,
            "city": org.city,
            "district": org.district,
            "createdAt": iso(org.created_at),
            "isOperational": org.is_operational,
        }
        for org in rows
    ]
    return success(
        request,
        {
            "items": items,
            "pagination": Page(items=items, total=total, page=page, page_size=page_size).meta(),
        },
    )


@router.post("/organizations/{organization_id}/verify", summary="Verify an organization")
def verify_organization(
    organization_id: str, request: Request, principal: AdminPrincipal, db: Session = Depends(get_db)
) -> dict:
    """Mark an organization VERIFIED, unlocking operational endpoints.

    OWNER: D1
    PURPOSE: Manual verification of hospitals and blood centres.
    INPUT: path organizationId
    OUTPUT: OrganizationAdminView
    AUTHORIZATION: ADMIN only.
    STATE CHANGES: Organization.verificationStatus=VERIFIED, verifiedAt, verifiedByUserId
    ERRORS: 404 ORGANIZATION_NOT_FOUND, 409 CONFLICT when already suspended/verified
    DEPENDENCIES: none
    MUST NOT: verify an organization without an out-of-band document check
    PRIVACY: audit entry records the acting administrator only
    """
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise NotFoundError("Organization not found", code=ErrorCode.ORGANIZATION_NOT_FOUND)
    if organization.verification_status is OrgVerificationStatus.SUSPENDED:
        raise DomainError(
            "Suspended organizations must be reinstated explicitly",
            code=ErrorCode.CONFLICT,
            status_code=409,
        )

    organization.verification_status = OrgVerificationStatus.VERIFIED
    organization.verified_at = utcnow()
    organization.verified_by_user_id = principal.user_id
    record(
        db,
        action="organization.verified",
        actor=principal,
        entity_type="organization",
        entity_id=organization.id,
    )
    db.commit()
    return success(
        request,
        {"id": organization.id, "name": organization.name, "verificationStatus": "VERIFIED"},
    )


@router.post("/organizations/{organization_id}/suspend", summary="Suspend an organization")
def suspend_organization(
    organization_id: str, request: Request, principal: AdminPrincipal, db: Session = Depends(get_db)
) -> dict:
    """Suspend an organization, immediately blocking its operational endpoints.

    OWNER: D1
    PURPOSE: Safety valve for misuse or expired credentials.
    INPUT: path organizationId
    OUTPUT: OrganizationAdminView
    AUTHORIZATION: ADMIN only.
    STATE CHANGES: Organization.verificationStatus=SUSPENDED
    ERRORS: 404 ORGANIZATION_NOT_FOUND
    DEPENDENCIES: none
    MUST NOT: delete data — suspension is reversible and audited
    """
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise NotFoundError("Organization not found", code=ErrorCode.ORGANIZATION_NOT_FOUND)
    organization.verification_status = OrgVerificationStatus.SUSPENDED
    record(
        db,
        action="organization.suspended",
        actor=principal,
        entity_type="organization",
        entity_id=organization.id,
    )
    db.commit()
    return success(
        request,
        {"id": organization.id, "name": organization.name, "verificationStatus": "SUSPENDED"},
    )


@router.get("/users", summary="List platform accounts")
def list_users(
    request: Request,
    principal: AdminPrincipal,
    db: Session = Depends(get_db),
    role: str | None = Query(None),
    page_params: tuple[int, int] = Depends(pagination_params),
) -> dict:
    """List accounts for administration.

    OWNER: D1
    PURPOSE: Account oversight and support.
    INPUT: role?, page, pageSize
    OUTPUT: Page<UserAdminView>
    AUTHORIZATION: ADMIN only.
    STATE CHANGES: none
    ERRORS: 403 FORBIDDEN
    DEPENDENCIES: none
    MUST NOT: expose password hashes or refresh tokens
    PRIVACY: email + role only; no donor location data
    """
    from bloodlink_contracts.enums import Role

    page, page_size = page_params
    query = select(User)
    if role:
        role_value = Role.coerce(role)
        if role_value is None:
            raise DomainError("Unknown role", code=ErrorCode.VALIDATION_ERROR, status_code=422)
        query = query.where(User.role == role_value)

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(
        query.order_by(User.created_at.desc()).limit(page_size).offset((page - 1) * page_size)
    ).scalars()
    items = [
        {
            "id": user.id,
            "fullName": user.full_name,
            "email": user.email,
            "role": user.role.value,
            "organizationId": user.organization_id,
            "isActive": user.is_active,
            "createdAt": iso(user.created_at),
            "lastLoginAt": iso(user.last_login_at),
        }
        for user in rows
    ]
    return success(
        request,
        {
            "items": items,
            "pagination": Page(items=items, total=total, page=page, page_size=page_size).meta(),
        },
    )


@router.post("/users/{user_id}/deactivate", summary="Deactivate an account")
def deactivate_user(
    user_id: str, request: Request, principal: AdminPrincipal, db: Session = Depends(get_db)
) -> dict:
    """Deactivate an account (reversible), revoking its sessions.

    OWNER: D1
    PURPOSE: Abuse handling / offboarding.
    INPUT: path userId
    OUTPUT: UserAdminView
    AUTHORIZATION: ADMIN only; an admin cannot deactivate themselves.
    STATE CHANGES: User.isActive=false
    ERRORS: 404 NOT_FOUND, 409 CONFLICT on self-deactivation
    DEPENDENCIES: none
    """
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("Account not found")
    if user.id == principal.user_id:
        raise DomainError("You cannot deactivate your own account", code=ErrorCode.CONFLICT, status_code=409)
    user.is_active = False
    record(db, action="user.deactivated", actor=principal, entity_type="user", entity_id=user.id)
    db.commit()
    return success(request, {"id": user.id, "isActive": False})


@router.get("/audit", summary="Read the audit trail")
def list_audit(
    request: Request,
    principal: AdminPrincipal,
    db: Session = Depends(get_db),
    action: str | None = Query(None),
    page_params: tuple[int, int] = Depends(pagination_params),
) -> dict:
    """Return recent audit entries.

    OWNER: D1
    PURPOSE: Accountability for consequential actions.
    INPUT: action?, page, pageSize
    OUTPUT: Page<AuditEntry>
    AUTHORIZATION: ADMIN only.
    STATE CHANGES: none
    ERRORS: 403 FORBIDDEN
    DEPENDENCIES: none
    MUST NOT: allow edits to audit history
    PRIVACY: audit detail is constrained to ids and status codes, no patient data
    """
    page, page_size = page_params
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(
        query.order_by(AuditLog.created_at.desc()).limit(page_size).offset((page - 1) * page_size)
    ).scalars()
    items = [
        {
            "id": entry.id,
            "action": entry.action,
            "actorUserId": entry.actor_user_id,
            "actorRole": entry.actor_role.value if entry.actor_role else None,
            "entityType": entry.entity_type,
            "entityId": entry.entity_id,
            "detail": entry.detail,
            "createdAt": iso(entry.created_at),
        }
        for entry in rows
    ]
    return success(
        request,
        {
            "items": items,
            "pagination": Page(items=items, total=total, page=page, page_size=page_size).meta(),
        },
    )


@router.get("/requests/alerts", summary="Requests needing coordination attention")
def coordination_alerts(
    request: Request, principal: AdminPrincipal, db: Session = Depends(get_db)
) -> dict:
    """Surface requests that are past their required-by time or need backup.

    OWNER: D1 (platform observability only)
    PURPOSE: Help operations spot requests stuck in the failure path.
    INPUT: none
    OUTPUT: { items: [RequestAlert] }
    AUTHORIZATION: ADMIN only.
    STATE CHANGES: none
    ERRORS: 403 FORBIDDEN
    DEPENDENCIES: BloodRequest (D3)
    MUST NOT: mutate request state — this is read-only oversight
    PRIVACY: request ids, group, component, status only; no patient identity
    """
    now = utcnow()
    rows = db.execute(
        select(BloodRequest)
        .where(
            BloodRequest.status.in_(
                [
                    BloodRequestStatus.OPEN,
                    BloodRequestStatus.RESPONSES_RECEIVED,
                    BloodRequestStatus.BACKUP_REQUIRED,
                    BloodRequestStatus.COORDINATING,
                ]
            )
        )
        .order_by(BloodRequest.required_by.asc())
        .limit(50)
    ).scalars()

    items = []
    for blood_request in rows:
        overdue = blood_request.required_by < now
        if not overdue and blood_request.status is not BloodRequestStatus.BACKUP_REQUIRED:
            continue
        items.append(
            {
                "id": blood_request.id,
                "reference": blood_request.reference,
                "status": blood_request.status.value,
                "bloodGroup": blood_request.blood_group.value,
                "component": blood_request.component.value,
                "unitsOutstanding": blood_request.units_outstanding,
                "requiredBy": iso(blood_request.required_by),
                "overdue": overdue,
                "backupReason": blood_request.backup_reason,
            }
        )
    return success(request, {"items": items})


@router.get("/platform/modules", summary="Registered domain modules, owners and status")
def list_modules(request: Request, principal: AdminPrincipal) -> dict:
    """Introspect the modular monolith: module, owner, prefix, foundation status.

    OWNER: D1
    PURPOSE: Single source of truth for the ownership / status map in the docs.
    INPUT: none
    OUTPUT: { modules: [ModuleSummary] }
    AUTHORIZATION: ADMIN only.
    STATE CHANGES: none
    ERRORS: 403 FORBIDDEN
    DEPENDENCIES: module registry
    MUST NOT: reveal secrets or connection strings
    PRIVACY: metadata only
    """
    return success(request, {"modules": module_summary()})


MODULE = register_module(
    ModuleSpec(
        key="admin",
        owner="D1",
        domain="admin",
        api_prefix="/admin",
        description="Organization verification, user administration, audit, platform introspection.",
        foundation_status="COMPLETE",
        router=router,
        depends_on=("auth",),
    )
)
