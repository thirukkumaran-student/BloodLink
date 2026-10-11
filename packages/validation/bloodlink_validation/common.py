"""Field-level validation shared by API DTOs and web forms (owner: D1)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

from bloodlink_contracts.enums import (
    MESSAGE_MAX_LENGTH,
    PUSH_PAYLOAD_FORBIDDEN_KEYS,
    UNITS_MAX,
    UNITS_MIN,
    BloodComponent,
    BloodGroup,
    Urgency,
)

PASSWORD_MIN_LENGTH = 10
NAME_MIN_LENGTH = 2
NAME_MAX_LENGTH = 120
NOTES_MAX_LENGTH = 1000
MIN_REQUIRED_BY_LEAD_MINUTES = 15
MAX_REQUIRED_BY_HORIZON_DAYS = 30
MIN_LATITUDE, MAX_LATITUDE = -90.0, 90.0
MIN_LONGITUDE, MAX_LONGITUDE = -180.0, 180.0

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_PHONE_RE = re.compile(r"^[6-9]\d{9}$")
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,118}$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    message: str

    def as_detail(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #
def normalise_blood_group(raw: object) -> BloodGroup | None:
    return BloodGroup.coerce(raw)


def normalise_component(raw: object) -> BloodComponent | None:
    return BloodComponent.coerce(raw)


def normalise_urgency(raw: object) -> Urgency | None:
    return Urgency.coerce(raw)


def validate_email(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address")
    if len(value) > 254:
        raise ValueError("Email address is too long")
    return value


def validate_person_name(raw: str | None, *, field: str = "name") -> str:
    value = re.sub(r"\s+", " ", (raw or "").strip())
    if len(value) < NAME_MIN_LENGTH:
        raise ValueError(f"{field.replace('_', ' ').capitalize()} is too short")
    if len(value) > NAME_MAX_LENGTH:
        raise ValueError(f"{field.replace('_', ' ').capitalize()} is too long")
    if not _NAME_RE.match(value):
        raise ValueError("Use letters, spaces, hyphens and apostrophes only")
    return value


def validate_phone(raw: str | None) -> str:
    """Return a normalised 10-digit Indian mobile number."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if not _PHONE_RE.match(digits):
        raise ValueError("Enter a valid 10-digit Indian mobile number")
    return digits


def hash_phone(raw: str) -> str:
    """Store a hash, never a raw phone number, for unverified contacts."""
    return hashlib.sha256(validate_phone(raw).encode()).hexdigest()[:32]


def password_issues(raw: str | None) -> list[str]:
    value = raw or ""
    issues: list[str] = []
    if len(value) < PASSWORD_MIN_LENGTH:
        issues.append(f"Use at least {PASSWORD_MIN_LENGTH} characters")
    if not re.search(r"[A-Za-z]", value):
        issues.append("Include at least one letter")
    if not re.search(r"\d", value):
        issues.append("Include at least one number")
    if value and value.lower() in {"password12", "bloodlink12"}:
        issues.append("Choose something less guessable")
    return issues


def validate_coordinates(latitude: float | None, longitude: float | None) -> tuple[float, float]:
    if latitude is None or longitude is None:
        raise ValueError("Location is required")
    if not MIN_LATITUDE <= float(latitude) <= MAX_LATITUDE:
        raise ValueError("Latitude is out of range")
    if not MIN_LONGITUDE <= float(longitude) <= MAX_LONGITUDE:
        raise ValueError("Longitude is out of range")
    return round(float(latitude), 5), round(float(longitude), 5)


def validate_units(raw: object) -> int:
    try:
        units = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("Units must be a whole number") from exc
    if not UNITS_MIN <= units <= UNITS_MAX:
        raise ValueError(f"Units must be between {UNITS_MIN} and {UNITS_MAX}")
    return units


def validate_required_by(raw: datetime | None, *, now: datetime | None = None) -> datetime:
    """``requiredBy`` is an exact timestamp that must be in the near future."""
    reference = now or datetime.utcnow()
    if raw is None:
        raise ValueError("Required-by date and time is required")
    value = raw.replace(tzinfo=None) if raw.tzinfo else raw
    if value < reference + timedelta(minutes=MIN_REQUIRED_BY_LEAD_MINUTES):
        raise ValueError(f"Required by must be at least {MIN_REQUIRED_BY_LEAD_MINUTES} minutes from now")
    if value > reference + timedelta(days=MAX_REQUIRED_BY_HORIZON_DAYS):
        raise ValueError(f"Required by must be within {MAX_REQUIRED_BY_HORIZON_DAYS} days")
    return value


def clean_text(raw: str | None, *, max_length: int, allow_empty: bool = True) -> str | None:
    value = _CONTROL_CHARS_RE.sub("", (raw or "").strip())
    value = re.sub(r"\n{3,}", "\n\n", value)
    if not value:
        return None if allow_empty else ""
    if len(value) > max_length:
        raise ValueError(f"Keep this under {max_length} characters")
    return value


def validate_notes(raw: str | None) -> str | None:
    """``additionalNotes`` is coordination context — not a medical record."""
    return clean_text(raw, max_length=NOTES_MAX_LENGTH)


def validate_message_content(raw: str | None) -> str:
    value = clean_text(raw, max_length=MESSAGE_MAX_LENGTH, allow_empty=False)
    if not value:
        raise ValueError("Message cannot be empty")
    return value


# --------------------------------------------------------------------------- #
# Privacy guard (spec §12, §21)
# --------------------------------------------------------------------------- #
def assert_privacy_safe_payload(payload: Any, *, path: str = "payload") -> None:
    """Raise ``ValueError`` if a notification payload leaks sensitive data.

    Enforced at the notification dispatch boundary so no feature module can
    accidentally push patient identity, medical detail or exact coordinates.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalised = str(key).replace("_", "").lower()
            if normalised in PUSH_PAYLOAD_FORBIDDEN_KEYS:
                raise ValueError(f"Privacy violation: forbidden key '{key}' at {path}")
            assert_privacy_safe_payload(value, path=f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            assert_privacy_safe_payload(item, path=f"{path}[{index}]")


def collect_issues(pairs: Iterable[tuple[str, str | None]]) -> list[ValidationIssue]:
    """Helper for web forms: turn ``(field, error)`` pairs into issues."""
    return [ValidationIssue(field=field, message=message) for field, message in pairs if message]
