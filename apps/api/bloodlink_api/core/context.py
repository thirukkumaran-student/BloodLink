"""Authentication resolution + RBAC foundation (owner: D1, spec §16).

Everything authorization-related lives here:

* ``get_current_principal``  — verifies the bearer JWT and loads the user.
* ``require_roles``          — role guard (router or endpoint level).
* ``require_hospital_context`` / ``require_blood_centre_context``
  — organization context guards; the org must be VERIFIED and not SUSPENDED.
* ``require_donor_profile``  — donor capability guard (D4 flows).

Authorization is enforced **server-side only**. Web route protection is UX
(spec §16); the API never trusts a client-supplied role or organization id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from bloodlink_api.db.models.identity import Organization, User
from bloodlink_api.db.session import get_db
from bloodlink_contracts.errors import ErrorCode
from bloodlink_api.core.errors import ForbiddenError, UnauthenticatedError
from bloodlink_api.core.security import decode_token
from bloodlink_contracts.enums import ROLE_TO_ORG_TYPE, OrgType, OrgVerificationStatus, Role

bearer_scheme = HTTPBearer(auto_error=False, description="Bearer <access token>")


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, resolved from the database (never from claims alone)."""

    user: User
    organization: Organization | None

    @property
    def user_id(self) -> str:
        return self.user.id

    @property
    def role(self) -> Role:
        return self.user.role

    @property
    def organization_id(self) -> str | None:
        return self.user.organization_id

    @property
    def role_value(self) -> str:
        return self.role.value

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN

    @property
    def org_type(self) -> OrgType | None:
        return ROLE_TO_ORG_TYPE.get(self.role)

    @property
    def org_name(self) -> str:
        return self.organization.name if self.organization else ""

    def has_role(self, *roles: Role) -> bool:
        return self.role in roles

    def require_own_organization(self, organization_id: str | None) -> None:
        """Guard for organization-scoped records (spec §16)."""
        if self.is_admin:
            return
        if not organization_id or self.organization_id != organization_id:
            raise ForbiddenError("This record belongs to another organization")


def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    db: Session = Depends(get_db),
) -> Principal:
    if credentials is None or not credentials.credentials:
        raise UnauthenticatedError("Sign in to continue")

    claims = decode_token(credentials.credentials)
    user = db.execute(
        select(User).options(joinedload(User.organization)).where(User.id == claims.subject)
    ).scalar_one_or_none()

    if user is None or not user.is_active:
        raise UnauthenticatedError("This account is not active", code=ErrorCode.TOKEN_INVALID)

    # Suspended organizations lose access to operational endpoints immediately.
    if user.organization and user.organization.verification_status is OrgVerificationStatus.SUSPENDED:
        raise ForbiddenError(
            f"{user.organization.name} is suspended. Contact BloodLink administration.",
            code=ErrorCode.ORGANIZATION_SUSPENDED,
        )

    request.state.principal_user_id = user.id
    return Principal(user=user, organization=user.organization)


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_roles(*roles: Role) -> Callable[..., Principal]:
    """Role guard. Use on a router (``dependencies=[...]``) or an endpoint."""

    def dependency(principal: CurrentPrincipal) -> Principal:
        if principal.role not in roles:
            raise ForbiddenError(
                "Your account role cannot access this resource",
                details=[{"field": "role", "message": f"Required: {', '.join(r.value for r in roles)}"}],
            )
        return principal

    return dependency


def _require_org_context(principal: Principal, expected: OrgType) -> Principal:
    if principal.org_type is not expected:
        raise ForbiddenError(
            f"Only {expected.value.replace('_', ' ').title()} accounts can perform this action"
        )
    if principal.organization is None:
        raise ForbiddenError(
            "Your account is not linked to an organization", code=ErrorCode.ORGANIZATION_NOT_FOUND
        )
    if principal.organization.verification_status is OrgVerificationStatus.PENDING:
        raise ForbiddenError(
            "Your organization is awaiting verification. Operations unlock once BloodLink "
            "administration verifies it.",
            code=ErrorCode.ORGANIZATION_NOT_VERIFIED,
        )
    if principal.organization.verification_status is OrgVerificationStatus.SUSPENDED:
        raise ForbiddenError(
            "Your organization is suspended", code=ErrorCode.ORGANIZATION_SUSPENDED
        )
    return principal


def require_hospital_context(principal: CurrentPrincipal) -> Principal:
    """Hospital users acting inside a verified hospital organization."""
    return _require_org_context(principal, OrgType.HOSPITAL)


def require_blood_centre_context(principal: CurrentPrincipal) -> Principal:
    """Blood-centre users acting inside a verified blood centre."""
    return _require_org_context(principal, OrgType.BLOOD_CENTRE)


def require_authenticated(principal: CurrentPrincipal) -> Principal:
    """Any signed-in, active account (the default for user-scoped endpoints)."""
    return principal


def require_individual(principal: CurrentPrincipal) -> Principal:
    if principal.role is not Role.INDIVIDUAL:
        raise ForbiddenError("This action is only available to individual accounts")
    return principal


def require_admin(principal: CurrentPrincipal) -> Principal:
    if not principal.is_admin:
        raise ForbiddenError("Administrator access required")
    return principal


def require_donor_profile(
    principal: CurrentPrincipal, db: Session = Depends(get_db)
):
    """Capability guard: any authenticated user who has a donor profile.

    Donors are individual accounts that opted into donation; a donor profile is
    the capability, not a separate role (spec §16 role list).
    """
    from bloodlink_api.db.models.donors import DonorProfile

    profile = db.execute(
        select(DonorProfile).where(DonorProfile.user_id == principal.user_id)
    ).scalar_one_or_none()
    if profile is None:
        raise ForbiddenError(
            "Create a donor profile to use donor features", code=ErrorCode.DONOR_PROFILE_REQUIRED
        )
    return profile


# Convenience annotations for feature modules — keeps endpoint signatures clean.
HospitalPrincipal = Annotated[Principal, Depends(require_hospital_context)]
BloodCentrePrincipal = Annotated[Principal, Depends(require_blood_centre_context)]
IndividualPrincipal = Annotated[Principal, Depends(require_individual)]
AdminPrincipal = Annotated[Principal, Depends(require_admin)]
