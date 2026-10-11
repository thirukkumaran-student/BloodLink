"""Cross-domain interface for matching (owner: D1 contract, D4 implementation).

D3 must call these functions instead of reaching into D4's tables. The signatures
in this file are frozen for the sprint; D4 changes only the implementations.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from bloodlink_api.db.models.blood_requests import BloodRequest


@dataclass(frozen=True)
class CandidateSummary:
    """Privacy-safe candidate view handed to D3 (spec §21).

    Deliberately excludes coordinates, address and contact details.
    """

    donor_profile_id: str
    display_name: str
    blood_group: str
    distance_band: str
    tier: int
    rank: int


def request_outreach(db: Session, blood_request: BloodRequest, *, tier: int = 1) -> int:
    """Ask D4 to run matching and dispatch tier-``tier`` notifications.

    Returns the number of donors notified. Safe to call repeatedly; already
    notified donors are skipped.
    """
    from bloodlink_api.modules.matching import service as matching_service
    from bloodlink_api.modules.notifications import service as notification_service

    result = matching_service.find_candidates(db, blood_request, tier=tier)
    return notification_service.notify_matched_donors(db, blood_request, result.candidates)


def eligible_candidates(db: Session, blood_request: BloodRequest, *, tier: int = 1) -> list[CandidateSummary]:
    """Return privacy-safe summaries of matched donors for a hospital view."""
    from bloodlink_api.core.geo import distance_band
    from bloodlink_api.modules.matching import service as matching_service

    result = matching_service.find_candidates(db, blood_request, tier=tier)
    return [
        CandidateSummary(
            donor_profile_id=candidate.donor_profile_id,
            display_name=candidate.display_name,
            blood_group=candidate.blood_group,
            distance_band=distance_band(candidate.distance_km),
            tier=candidate.tier,
            rank=candidate.rank,
        )
        for candidate in result.candidates
    ]


def expand_request_outreach(db: Session, blood_request: BloodRequest, *, next_tier: int) -> int:
    """Escalation hook used by D3 on the BACKUP_REQUIRED path."""
    from bloodlink_api.modules.matching import service as matching_service
    from bloodlink_api.modules.notifications import service as notification_service

    records = matching_service.expand_outreach(db, blood_request, next_tier=next_tier)
    return notification_service.notify_outreach_records(db, blood_request, records)
