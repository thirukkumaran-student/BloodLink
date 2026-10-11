"""Authentication primitives: password hashing + JWT issue/verify (owner: D1, spec §16)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from bloodlink_contracts.enums import Role
from bloodlink_contracts.errors import ErrorCode
from bloodlink_api.core.errors import UnauthenticatedError
from bloodlink_api.core.settings import get_settings

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# bcrypt truncates at 72 bytes; pre-hash so long passwords behave predictably.
_BCRYPT_MAX_BYTES = 72


def _prepared(password: str) -> bytes:
    raw = password.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        return hashlib.sha256(raw).hexdigest().encode("utf-8")
    return raw


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepared(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepared(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def hash_token(raw_token: str) -> str:
    """Refresh tokens are stored hashed, never in plaintext."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def tokens_match(raw_token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_token(raw_token), stored_hash)


@dataclass(frozen=True)
class TokenClaims:
    subject: str
    role: Role | None
    organization_id: str | None
    jti: str
    expires_at: datetime
    token_type: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "sub": self.subject,
            "role": self.role.value if self.role else None,
            "org_id": self.organization_id,
            "jti": self.jti,
            "exp": int(self.expires_at.replace(tzinfo=timezone.utc).timestamp()),
            "type": self.token_type,
            "iss": get_settings().jwt_issuer,
        }


def _encode(claims: TokenClaims) -> str:
    settings = get_settings()
    return jwt.encode(claims.as_dict(), settings.secret_key, algorithm=settings.jwt_algorithm)


def issue_access_token(
    *,
    user_id: str,
    role: Role | None,
    organization_id: str | None,
    now: datetime | None = None,
) -> tuple[str, TokenClaims]:
    settings = get_settings()
    issued = now or datetime.now(timezone.utc)
    claims = TokenClaims(
        subject=str(user_id),
        role=Role.coerce(role.value) if role else None,
        organization_id=str(organization_id) if organization_id else None,
        jti=uuid_like(),
        expires_at=issued + timedelta(minutes=settings.access_token_ttl_minutes),
        token_type=TOKEN_TYPE_ACCESS,
    )
    return _encode(claims), claims


def issue_refresh_token(
    *, user_id: str, now: datetime | None = None
) -> tuple[str, str, datetime]:
    """Return ``(raw_token, token_hash, expires_at)``."""
    settings = get_settings()
    issued = now or datetime.now(timezone.utc)
    raw = new_opaque_token()
    expires_at = issued + timedelta(minutes=settings.refresh_token_ttl_minutes)
    return raw, hash_token(raw), expires_at


def uuid_like() -> str:
    return secrets.token_hex(16)


def decode_token(raw_token: str, *, expected_type: str = TOKEN_TYPE_ACCESS) -> TokenClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            raw_token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthenticatedError(
            "Session expired, please sign in again", code=ErrorCode.TOKEN_EXPIRED
        ) from exc
    except jwt.PyJWTError as exc:
        raise UnauthenticatedError("Invalid credentials token", code=ErrorCode.TOKEN_INVALID) from exc

    if payload.get("type") != expected_type:
        raise UnauthenticatedError("Invalid credentials token", code=ErrorCode.TOKEN_INVALID)

    return TokenClaims(
        subject=str(payload.get("sub")),
        role=Role.coerce(payload.get("role")),
        organization_id=payload.get("org_id"),
        jti=str(payload.get("jti", "")),
        expires_at=datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc),
        token_type=str(payload.get("type")),
    )
