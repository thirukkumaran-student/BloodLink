"""Clock helpers (owner: D1). All timestamps are naive UTC by convention."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    """Naive UTC now — the single time source for the API."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Normalise an incoming datetime to naive UTC."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def iso(value: datetime | None) -> str | None:
    """Serialise a stored timestamp as an ISO-8601 UTC string (``...Z``)."""
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def minutes_from_now(minutes: int) -> datetime:
    return utcnow() + timedelta(minutes=minutes)
