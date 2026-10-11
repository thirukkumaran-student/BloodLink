"""Auth DTOs (owner: D1)."""

from __future__ import annotations

from typing import Any

from pydantic import EmailStr, Field, field_validator

from bloodlink_api.core.settings import get_settings
from bloodlink_contracts.dto import APIModel
from bloodlink_contracts.enums import OrgType, OrgVerificationStatus, Role
from bloodlink_validation.common import (
    validate_coordinates,
    validate_person_name,
    validate_phone,
    password_issues,
)


class OrganizationSeed(APIModel):
    """Organization details captured when a hospital / blood centre signs up.

    The organization is created ``PENDING`` and cannot run operations until an
    administrator verifies it (spec §16).
    """

    name: str
    org_type: OrgType
    registration_number: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    address: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    pincode: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return validate_person_name(value, field="Organization name")

    @field_validator("contact_phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return validate_phone(value) if value else None

    @field_validator("longitude")
    @classmethod
    def _coords(cls, value: float | None, info) -> float | None:
        latitude = info.data.get("latitude")
        if value is None and latitude is None:
            return None
        validate_coordinates(latitude, value)
        return float(value)


class RegisterRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str
    phone: str | None = None
    role: Role
    organization: OrganizationSeed | None = None

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        issues = password_issues(value)
        if issues:
            raise ValueError("; ".join(issues))
        return value

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, value: str) -> str:
        return validate_person_name(value, field="Full name")

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return validate_phone(value) if value else None

    @field_validator("role")
    @classmethod
    def _role(cls, value: Role) -> Role:
        if value is Role.ADMIN:
            raise ValueError("Administrator accounts are provisioned by BloodLink operations")
        try:
            return Role(value)
        except ValueError as exc:  # pragma: no cover - pydantic handles this
            raise ValueError("Unsupported role") from exc


class LoginRequest(APIModel):
    email: EmailStr
    password: str


class RefreshRequest(APIModel):
    refresh_token: str | None = None


class ChangePasswordRequest(APIModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _password(cls, value: str) -> str:
        issues = password_issues(value)
        if issues:
            raise ValueError("; ".join(issues))
        return value


class OrganizationSummary(APIModel):
    id: str
    name: str
    org_type: OrgType
    verification_status: OrgVerificationStatus
    city: str | None = None
    district: str | None = None
    location_label: str | None = None
    is_operational: bool = False


class CurrentUserResponse(APIModel):
    id: str
    email: str
    full_name: str
    phone: str | None = None
    role: Role
    initials: str
    organization: OrganizationSummary | None = None
    capabilities: list[str] = []
    has_donor_profile: bool = False


class TokenResponse(APIModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: CurrentUserResponse


def token_ttl_seconds() -> int:
    return get_settings().access_token_ttl_minutes * 60


def serialize_organization(organization) -> dict[str, Any] | None:
    if organization is None:
        return None
    return {
        "id": organization.id,
        "name": organization.name,
        "orgType": organization.org_type.value,
        "verificationStatus": organization.verification_status.value,
        "city": organization.city,
        "district": organization.district,
        "locationLabel": organization.location_label,
        "isOperational": organization.is_operational,
    }
