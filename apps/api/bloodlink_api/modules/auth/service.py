"""Authentication service (owner: D1, spec §16).

Fully implemented in the foundation sprint: registration, credential
verification, token issue/rotate/revoke and the current-account payload used by
the web client to build role-aware navigation.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bloodlink_api.core.clock import utcnow
from bloodlink_api.core.audit import record
from bloodlink_api.core.errors import ConflictError, UnauthenticatedError
from bloodlink_api.core.security import (
    hash_password,
    hash_token,
    issue_access_token,
    issue_refresh_token,
    new_opaque_token,
    tokens_match,
    verify_password,
)
from bloodlink_api.core.settings import get_settings
from bloodlink_api.db.models.donors import DonorProfile
from bloodlink_api.db.models.identity import (
    Organization,
    OrganizationMembership,
    RefreshToken,
    User,
)
from bloodlink_contracts.enums import OrgType, OrgVerificationStatus, Role
from bloodlink_contracts.errors import ErrorCode
from bloodlink_contracts.permissions import capabilities_for
from bloodlink_api.modules.auth.schemas import (
    RegisterRequest,
    serialize_organization,
    token_ttl_seconds,
)


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def user_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == _normalise_email(email))).scalar_one_or_none()


def has_donor_profile(db: Session, user_id: str) -> bool:
    return (
        db.execute(select(DonorProfile.id).where(DonorProfile.user_id == user_id)).scalar_one_or_none()
        is not None
    )


def current_user_payload(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "fullName": user.full_name,
        "phone": user.phone,
        "role": user.role.value,
        "initials": user.initials,
        "organization": serialize_organization(user.organization),
        "capabilities": capabilities_for(user.role),
        "hasDonorProfile": has_donor_profile(db, user.id),
        "lastLoginAt": user.last_login_at.isoformat() + "Z" if user.last_login_at else None,
    }


def _create_organization(db: Session, payload: RegisterRequest) -> tuple[Organization, OrganizationMembership]:
    seed = payload.organization
    assert seed is not None  # validated by the router

    expected_type = {
        Role.HOSPITAL: OrgType.HOSPITAL,
        Role.BLOOD_CENTRE: OrgType.BLOOD_CENTRE,
    }[payload.role]
    if seed.org_type is not expected_type:
        raise ConflictError("Organization type does not match the requested account role")

    organization = Organization(
        name=seed.name,
        org_type=seed.org_type,
        registration_number=seed.registration_number,
        contact_email=str(seed.contact_email) if seed.contact_email else payload.email,
        contact_phone=seed.contact_phone or payload.phone,
        address=seed.address,
        city=seed.city,
        district=seed.district,
        state=seed.state,
        pincode=seed.pincode,
        latitude=seed.latitude,
        longitude=seed.longitude,
        # New organizations always start unverified: operations unlock only after
        # BloodLink administration verifies the facility (spec §16).
        verification_status=OrgVerificationStatus.PENDING,
    )
    db.add(organization)
    db.flush()

    user = db.execute(select(User).where(User.email == _normalise_email(payload.email))).scalar_one()
    membership = OrganizationMembership(
        user_id=user.id, organization_id=organization.id, title="Coordinator", is_primary=True
    )
    db.add(membership)
    user.organization_id = organization.id
    return organization, membership


def register(db: Session, payload: RegisterRequest, *, user_agent: str | None = None) -> dict:
    if user_by_email(db, payload.email):
        raise ConflictError(
            "An account with this email already exists", code=ErrorCode.EMAIL_ALREADY_REGISTERED
        )

    if payload.role in (Role.HOSPITAL, Role.BLOOD_CENTRE) and payload.organization is None:
        raise ConflictError(
            "Organization details are required for hospital and blood centre accounts",
            code=ErrorCode.VALIDATION_ERROR,
        )

    user = User(
        email=_normalise_email(payload.email),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        role=payload.role,
        is_active=True,
        email_verified=False,
    )
    db.add(user)
    db.flush()

    organization = None
    if payload.role in (Role.HOSPITAL, Role.BLOOD_CENTRE):
        organization, _membership = _create_organization(db, payload)

    record(
        db,
        action="user.registered",
        entity_type="user",
        entity_id=user.id,
        detail={"role": payload.role.value, "organizationId": organization.id if organization else None},
    )
    db.commit()
    db.refresh(user)

    return {"user": current_user_payload(db, user), **_issue_session(db, user, user_agent)}


def login(db: Session, email: str, password: str, *, user_agent: str | None = None) -> dict:
    user = user_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthenticatedError("Email or password is incorrect", code=ErrorCode.INVALID_CREDENTIALS)
    if not user.is_active:
        raise UnauthenticatedError(
            "This account has been deactivated. Contact BloodLink support.",
            code=ErrorCode.INVALID_CREDENTIALS,
        )

    user.last_login_at = utcnow()
    record(db, action="user.signed_in", entity_type="user", entity_id=user.id)
    db.commit()
    db.refresh(user)

    return {"user": current_user_payload(db, user), **_issue_session(db, user, user_agent)}


def _issue_session(db: Session, user: User, user_agent: str | None) -> dict:
    access_token, _claims = issue_access_token(
        user_id=user.id, role=user.role, organization_id=user.organization_id
    )
    raw_refresh, token_hash, expires_at = issue_refresh_token(user_id=user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=(user_agent or "")[:200] or None,
            created_at=utcnow(),
        )
    )
    db.commit()
    return {
        "accessToken": access_token,
        "refreshToken": raw_refresh,
        "tokenType": "Bearer",
        "expiresIn": token_ttl_seconds(),
    }


def refresh_session(db: Session, raw_refresh: str | None, *, user_agent: str | None = None) -> dict:
    if not raw_refresh:
        raise UnauthenticatedError("Refresh token missing", code=ErrorCode.TOKEN_INVALID)

    token = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh))
    ).scalar_one_or_none()

    if token is None or not token.is_usable:
        raise UnauthenticatedError("Session expired, please sign in again", code=ErrorCode.TOKEN_EXPIRED)

    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise UnauthenticatedError("Session expired, please sign in again", code=ErrorCode.TOKEN_EXPIRED)

    # Rotate: the presented refresh token is revoked on use.
    token.revoked_at = utcnow()
    db.commit()
    return {"user": current_user_payload(db, user), **_issue_session(db, user, user_agent)}


def logout(db: Session, raw_refresh: str | None) -> None:
    if not raw_refresh:
        return
    token = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh))
    ).scalar_one_or_none()
    if token and token.revoked_at is None:
        token.revoked_at = utcnow()
        db.commit()


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise UnauthenticatedError("Current password is incorrect", code=ErrorCode.INVALID_CREDENTIALS)
    user.password_hash = hash_password(new_password)
    # Invalidate every existing refresh token.
    for token in db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id)).scalars():
        token.revoked_at = token.revoked_at or utcnow()
    record(db, action="user.password_changed", entity_type="user", entity_id=user.id)
    db.commit()


def bootstrap_admin(db: Session, *, email: str, password: str, full_name: str) -> User:
    """Idempotently ensure an administrator exists (used by the seeder)."""
    existing = user_by_email(db, email)
    if existing:
        return existing
    user = User(
        email=_normalise_email(email),
        password_hash=hash_password(password),
        full_name=full_name,
        role=Role.ADMIN,
        is_active=True,
        email_verified=True,
    )
    db.add(user)
    db.commit()
    return user


def opaque_token() -> str:
    return new_opaque_token()


def settings_snapshot() -> dict:
    settings = get_settings()
    return {"env": settings.env, "issuer": settings.jwt_issuer}


# ``tokens_match`` is re-exported for feature modules that verify one-off tokens.
__all__ = [
    "bootstrap_admin",
    "change_password",
    "current_user_payload",
    "has_donor_profile",
    "login",
    "logout",
    "refresh_session",
    "register",
    "tokens_match",
    "user_by_email",
]
