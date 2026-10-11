"""Matching engine (owner: D4) — deterministic, distance-first.

This file is D4's implementation surface. The *shell* below is deliberately
complete on the parts that are contract-critical (ranking inputs, tiering
defaults from ``Settings``, the outreach ledger record) so D4 can focus on the
candidate pipeline without re-deriving agreement points.

STATUS: IMPLEMENTED. ``_load_candidates`` is the real query; the ranking, tiering
and outreach ledger below it were contract-frozen during the foundation sprint.
Do not change the function signatures — D3 and the notification module call
through ``interfaces.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, joinedload

from bloodlink_api.core.clock import utcnow
from bloodlink_api.core.geo import bounding_box, distance_km
from bloodlink_api.core.settings import get_settings
from bloodlink_api.db.models.blood_requests import BloodRequest, DonorOutreach
from bloodlink_api.db.models.donors import DonorProfile
from bloodlink_api.db.models.identity import Organization
from bloodlink_contracts.enums import (
    BloodRequestStatus,
    DonorResponseStatus,
    DonorStandbyStatus,
    Urgency,
)
from bloodlink_validation.blood import cooldown_remaining_days, is_compatible

OUTREACH_TIER_LABELS = {1: "WIDER_GROUP", 2: "EXPANDED_RADIUS", 3: "VERIFIED_ALTERNATIVES"}


@dataclass
class Candidate:
    """A donor matched to a request. Internal shape — never serialised directly.

    ``distance_km`` and coordinates are matching data only (spec §21). Only
    ``bloodlink_api.core.geo.distance_band`` output may reach a client.
    """

    donor_profile_id: str
    user_id: str
    display_name: str
    blood_group: str
    distance_km: float | None
    tier: int
    rank: int
    exact_group_match: bool
    cooldown_days_remaining: int = 0
    notifications_enabled: bool = True
    reasons: list[str] = field(default_factory=list)

    def as_outreach_record(self, *, blood_request_id: str) -> DonorOutreach:
        return DonorOutreach(
            blood_request_id=blood_request_id,
            donor_profile_id=self.donor_profile_id,
            tier=self.tier,
            distance_km=self.distance_km,
            compatibility_rank=self.rank,
            standby_status=DonorStandbyStatus.NONE,
        )


@dataclass
class MatchResult:
    request_id: str
    tier: int
    candidates: list[Candidate]
    total_scanned: int
    generated_at: datetime

    @property
    def count(self) -> int:
        return len(self.candidates)


def is_distance_first_ranked(candidates: list[Candidate]) -> bool:
    """Invariant used by tests: distance dominates ranking (§11)."""
    distances = [c.distance_km if c.distance_km is not None else float("inf") for c in candidates]
    return distances == sorted(distances)


def tier_limits(urgency: Urgency) -> list[tuple[int, float, int]]:
    """Return ``[(tier, radius_km, limit)]`` — emergency escalates immediately.

    Tier 1 is the tightest ring around the hospital; tier 2 and 3 widen it. The
    radius values come from ``Settings`` so operations can tune them without a
    code change.
    """
    settings = get_settings()
    if urgency is Urgency.EMERGENCY:
        return [
            (1, settings.match_tier1_radius_km, settings.match_tier1_limit),
            (2, settings.match_tier2_radius_km, settings.match_tier2_limit),
        ]
    if urgency is Urgency.URGENT:
        return [
            (1, settings.match_tier1_radius_km, settings.match_tier1_limit),
        ]
    return [
        (1, settings.match_tier1_radius_km, settings.match_tier1_limit),
    ]


def _load_candidates(db: Session, blood_request: BloodRequest, *, radius_km: float, limit: int) -> list[Candidate]:
    """Load, filter and rank the donors a request may be offered to.

    OWNER: D4
    PURPOSE: The single candidate query for the deterministic matching engine.
    FILTERS: compatibility (red-cell rule, plasma inverse rule), availability,
             notification preference, post-donation cooldown, radius.
    ORDERING: distance first, then exact-group match, then cooldown remaining —
              geography dominates; district is only a hint (spec §11).
    PRIVACY: coordinates stay inside this function; only ``distance_km`` travels.
    """
    hospital = blood_request.hospital
    if hospital is None:
        hospital = db.get(Organization, blood_request.hospital_id)

    settings = get_settings()
    now = utcnow()

    statement = (
        select(DonorProfile)
        .options(joinedload(DonorProfile.user))
        .where(DonorProfile.is_available.is_(True))
    )
    # Bounding-box pre-filter keeps the scan small; the exact radius check below
    # still decides, because a box is a superset of a circle.
    if hospital is not None and hospital.latitude is not None and hospital.longitude is not None:
        box = bounding_box(hospital.latitude, hospital.longitude, radius_km)
        statement = statement.where(
            and_(
                DonorProfile.latitude.is_not(None),
                DonorProfile.longitude.is_not(None),
                DonorProfile.latitude >= box["min_lat"],
                DonorProfile.latitude <= box["max_lat"],
                DonorProfile.longitude >= box["min_lon"],
                DonorProfile.longitude <= box["max_lon"],
            )
        )

    candidates: list[Candidate] = []
    for profile in db.execute(statement).scalars().unique():
        user = profile.user
        if user is None or not user.is_active:
            continue
        if not is_compatible(blood_request.blood_group, profile.blood_group, blood_request.component):
            continue

        distance = None
        if (
            hospital is not None
            and hospital.latitude is not None
            and hospital.longitude is not None
            and profile.latitude is not None
            and profile.longitude is not None
        ):
            distance = distance_km(
                from_lat=hospital.latitude,
                from_lon=hospital.longitude,
                to_lat=profile.latitude,
                to_lon=profile.longitude,
            )
            if distance is not None and distance > radius_km:
                continue

        remaining = cooldown_remaining_days(
            profile.last_donation_at, settings.donor_cooldown_days, as_of=now
        )
        emergency_only_blocked = (
            profile.notify_emergency_only and blood_request.urgency is not Urgency.EMERGENCY
        )

        reasons: list[str] = []
        if profile.blood_group is blood_request.blood_group:
            reasons.append("EXACT_GROUP")
        if remaining:
            reasons.append(f"COOLDOWN_{remaining}_DAYS")
        if emergency_only_blocked:
            reasons.append("EMERGENCY_ONLY")

        candidates.append(
            Candidate(
                donor_profile_id=profile.id,
                user_id=profile.user_id,
                display_name=user.full_name,
                blood_group=profile.blood_group.value,
                distance_km=distance,
                tier=1,
                rank=0,
                exact_group_match=profile.blood_group is blood_request.blood_group,
                cooldown_days_remaining=remaining,
                notifications_enabled=profile.accepts_notifications,
                reasons=reasons,
            )
        )

    # Outreach eligibility: D4 must never notify a donor who opted out, is inside
    # their recovery window, or asked for emergencies only on a routine request.
    eligible = [
        candidate
        for candidate in candidates
        if candidate.notifications_enabled
        and candidate.cooldown_days_remaining == 0
        and "EMERGENCY_ONLY" not in candidate.reasons
    ]

    eligible.sort(
        key=lambda candidate: (
            candidate.distance_km if candidate.distance_km is not None else float("inf"),
            0 if candidate.exact_group_match else 1,
            candidate.donor_profile_id,
        )
    )
    return eligible[: max(limit * 4, limit)]


def find_candidates(db: Session, blood_request: BloodRequest, *, tier: int = 1) -> MatchResult:
    """Return ranked, tiered candidates for a request (D4).

    OWNER: D4
    STATUS: IMPLEMENTED
    """
    settings = get_settings()
    tiers = {tier_key: (radius, limit) for tier_key, radius, limit in tier_limits(blood_request.urgency)}
    radius_km, limit = tiers.get(tier, tiers[max(tiers)])

    candidates = _load_candidates(db, blood_request, radius_km=radius_km, limit=limit)
    candidates.sort(
        key=lambda candidate: (
            candidate.distance_km if candidate.distance_km is not None else float("inf"),
            0 if candidate.exact_group_match else 1,
            candidate.cooldown_days_remaining,
        )
    )
    for index, candidate in enumerate(candidates, start=1):
        candidate.rank = index
        candidate.tier = tier

    return MatchResult(
        request_id=blood_request.id,
        tier=tier,
        candidates=candidates[:limit],
        total_scanned=len(candidates),
        generated_at=utcnow(),
    )


def expand_outreach(db: Session, blood_request: BloodRequest, *, next_tier: int) -> list[DonorOutreach]:
    """Widen outreach to the next tier, skipping donors already notified (§9, §12).

    OWNER: D4
    STATUS: IMPLEMENTED
    """
    result = find_candidates(db, blood_request, tier=next_tier)
    existing = {
        row.donor_profile_id
        for row in db.execute(
            select(DonorOutreach).where(DonorOutreach.blood_request_id == blood_request.id)
        ).scalars()
    }
    fresh = [candidate for candidate in result.candidates if candidate.donor_profile_id not in existing]
    records = [candidate.as_outreach_record(blood_request_id=blood_request.id) for candidate in fresh]
    for record in records:
        db.add(record)
    return records


def eligible_donor_count(db: Session, blood_request: BloodRequest, *, radius_km: float) -> int:
    """Count compatible, available donors inside a radius — for the hospital's
    "should I widen the net?" signal. Aggregate only; no identities (spec §21).

    OWNER: D4
    STATUS: IMPLEMENTED
    """
    if blood_request.hospital is None or blood_request.hospital.latitude is None:
        return 0
    box = bounding_box(blood_request.hospital.latitude, blood_request.hospital.longitude, radius_km)
    rows = db.execute(
        select(DonorProfile)
        .options(joinedload(DonorProfile.user))
        .where(
            and_(
                DonorProfile.is_available.is_(True),
                DonorProfile.latitude.is_not(None),
                DonorProfile.latitude >= box["min_lat"],
                DonorProfile.latitude <= box["max_lat"],
                DonorProfile.longitude >= box["min_lon"],
                DonorProfile.longitude <= box["max_lon"],
            )
        )
    ).scalars()
    count = 0
    for profile in rows:
        if not is_compatible(blood_request.blood_group, profile.blood_group, blood_request.component):
            continue
        remaining = cooldown_remaining_days(
            profile.last_donation_at, get_settings().donor_cooldown_days, as_of=utcnow()
        )
        if remaining:
            continue
        if (
            distance_km(
                from_lat=blood_request.hospital.latitude,
                from_lon=blood_request.hospital.longitude,
                to_lat=profile.latitude,
                to_lon=profile.longitude,
            )
            or 0
        ) <= radius_km:
            count += 1
    return count


def active_acceptance_statuses() -> tuple[DonorResponseStatus, ...]:
    """Responses that count as an active commitment (used by D3 when deciding
    whether a request is COVERED)."""
    return (
        DonorResponseStatus.ACCEPTED,
        DonorResponseStatus.SELECTED,
        DonorResponseStatus.STANDBY,
    )


def outreach_active_statuses() -> tuple[BloodRequestStatus, ...]:
    from bloodlink_contracts.enums import OUTREACH_ACTIVE_STATUSES

    return tuple(OUTREACH_ACTIVE_STATUSES)
