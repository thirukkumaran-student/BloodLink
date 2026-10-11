"""Auth endpoints (owner: D1, spec §16).

    POST /auth/register

    OWNER: D1
    PURPOSE: Create an account (individual, hospital or blood centre).
    INPUT: RegisterRequest
    OUTPUT: 201 SessionResponse (tokens + current user)
    AUTHORIZATION: Public.
    STATE CHANGES: User(created[, organization PENDING])
    ERRORS: 409 EMAIL_ALREADY_REGISTERED, 422 VALIDATION_ERROR
    DEPENDENCIES: none
    MUST NOT: verify organizations, grant ADMIN, or expose password material
    PRIVACY: password stored only as a bcrypt hash
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from bloodlink_api.core.context import CurrentPrincipal
from bloodlink_api.core.envelope import success
from bloodlink_api.core.registry import ModuleSpec, register_module
from bloodlink_api.core.routing import api_router
from bloodlink_api.db.session import get_db
from bloodlink_api.modules.auth import service
from bloodlink_api.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
)

router = api_router(owner="D1", domain="auth", prefix="/auth", foundation_status="COMPLETE")


@router.post("/register", status_code=status.HTTP_201_CREATED, summary="Register an account")
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    """Register a new account.

    OWNER: D1
    PURPOSE: Create an individual, hospital or blood centre account and open a session.
    INPUT: RegisterRequest
    OUTPUT: SessionResponse
    AUTHORIZATION: Public.
    STATE CHANGES: User(ACTIVE); for hospital/blood centre: Organization(PENDING)
    ERRORS: 409 EMAIL_ALREADY_REGISTERED, 422 VALIDATION_ERROR
    DEPENDENCIES: none
    MUST NOT: verify the organization, issue ADMIN accounts, leak password hashes
    PRIVACY: organization coordinates are stored for matching and never returned exactly
    """
    result = service.register(db, payload, user_agent=request.headers.get("user-agent"))
    return success(request, result)


@router.post("/login", summary="Sign in with email and password")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    """Sign in and receive an access + refresh token pair.

    OWNER: D1
    PURPOSE: Exchange credentials for a session.
    INPUT: LoginRequest
    OUTPUT: SessionResponse
    AUTHORIZATION: Public.
    STATE CHANGES: User.last_login_at; RefreshToken(created)
    ERRORS: 401 INVALID_CREDENTIALS
    DEPENDENCIES: none
    MUST NOT: reveal whether the email exists
    PRIVACY: identical error for unknown email and wrong password
    """
    result = service.login(
        db, str(payload.email), payload.password, user_agent=request.headers.get("user-agent")
    )
    return success(request, result)


@router.post("/refresh", summary="Rotate a refresh token")
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    """Exchange a refresh token for a new session (the old token is revoked).

    OWNER: D1
    PURPOSE: Silent session renewal for the web client.
    INPUT: RefreshRequest
    OUTPUT: SessionResponse
    AUTHORIZATION: Valid refresh token.
    STATE CHANGES: old RefreshToken(revoked), new RefreshToken(created)
    ERRORS: 401 TOKEN_EXPIRED / TOKEN_INVALID
    DEPENDENCIES: none
    MUST NOT: extend a revoked or expired session
    PRIVACY: refresh tokens are stored only as SHA-256 digests
    """
    result = service.refresh_session(
        db, payload.refresh_token, user_agent=request.headers.get("user-agent")
    )
    return success(request, result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke the refresh token")
def logout(payload: RefreshRequest, db: Session = Depends(get_db)) -> Response:
    """Revoke the presented refresh token.

    OWNER: D1
    PURPOSE: End a session server-side.
    INPUT: RefreshRequest
    OUTPUT: 204 No Content
    AUTHORIZATION: Valid refresh token.
    STATE CHANGES: RefreshToken(revoked)
    ERRORS: 204 even when the token is already gone (idempotent)
    DEPENDENCIES: none
    MUST NOT: require an access token (it may already be expired)
    """
    service.logout(db, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", summary="Current account, organization context and capabilities")
def me(request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)) -> dict:
    """Return the caller's identity, organization context and capability list.

    OWNER: D1
    PURPOSE: Drive role-aware navigation and route guards in the web client.
    INPUT: none
    OUTPUT: CurrentUserResponse
    AUTHORIZATION: Any authenticated user.
    STATE CHANGES: none
    ERRORS: 401 UNAUTHENTICATED
    DEPENDENCIES: none
    MUST NOT: return capabilities the role does not actually hold
    PRIVACY: no donor location or contact detail is included
    """
    return success(request, service.current_user_payload(db, principal.user))


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT, summary="Change password")
def change_password(
    payload: ChangePasswordRequest, principal: CurrentPrincipal, db: Session = Depends(get_db)
) -> Response:
    """Change the current account password and revoke other sessions.

    OWNER: D1
    PURPOSE: Credential rotation by the account owner.
    INPUT: ChangePasswordRequest
    OUTPUT: 204 No Content
    AUTHORIZATION: Any authenticated user.
    STATE CHANGES: User.password_hash; all RefreshToken(revoked)
    ERRORS: 401 INVALID_CREDENTIALS
    DEPENDENCIES: none
    MUST NOT: accept the change without the current password
    """
    service.change_password(db, principal.user, payload.current_password, payload.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


MODULE = register_module(
    ModuleSpec(
        key="auth",
        owner="D1",
        domain="auth",
        api_prefix="/auth",
        description="Registration, sign-in, token rotation, account context.",
        foundation_status="COMPLETE",
        router=router,
    )
)
