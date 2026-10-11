"""Donation confirmation service (owner: D4, spec §10).

Only the fulfilment confirmation path (D3) may call this. Acceptance is not a
donation; a DonationRecord means the hospital confirmed that coordination
completed.
"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from bloodlink_api.core.clock import utcnow
from bloodlink_api.core.errors import ConflictError, NotFoundError
from bloodlink_api.core.settings import get_settings
from bloodlink_api.db.models.blood_requests import BloodRequest
from bloodlink_api.db.models.donors import DonationRecord, DonorProfile, DonorResponse
from bloodlink_api.db.models.identity import User
from bloodlink_api.modules.notifications import service as notification_service
from bloodlink_contracts.enums import DonorResponseStatus, NotificationType
from bloodlink_contracts.errors import ErrorCode
from bloodlink_validation.blood import cooldown_remaining_days


def confirm_donations(
    db: Session,
    *,
    blood_request: BloodRequest,
    donor_profile_ids: Sequence[str],
    actor: User | None = None,
    hospital_reference: str | None = None,
) -> list[DonationRecord]:
    """Create DonationRecords for the donors who actually donated.

    OWNER: D4
    PURPOSE: Close the loop after the hospital confirms fulfilment (§10).
    STATE CHANGES: DonationRecord(created per donor); DonorProfile.lastDonationAt
                   and totalDonations updated (the cooldown source of truth);
                   DonorResponse marked CONTRIBUTED; donors notified
    ERRORS: 409 DONATION_CONFIRMATION_INCOMPLETE, 409 DONATION_ALREADY_CONFIRMED
    MUST NOT: record screening results, crossmatch data or medical clearance
    PRIVACY: hospital id, group, component, units and date only
    """
    if not donor_profile_ids:
        raise ConflictError(
            "Select the donors who donated before confirming fulfilment",
            code=ErrorCode.DONATION_CONFIRMATION_INCOMPLETE,
        )

    settings = get_settings()
    records: list[DonationRecord] = []
    now = utcnow()

    for profile_id in donor_profile_ids:
        profile = db.get(DonorProfile, profile_id)
        if profile is None:
            raise NotFoundError("Donor profile not found", code=ErrorCode.NOT_FOUND)

        existing = db.execute(
            select(DonationRecord).where(
                DonationRecord.blood_request_id == blood_request.id,
                DonationRecord.donor_profile_id == profile_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(
                "A donation is already recorded for this donor on this request",
                code=ErrorCode.DONATION_ALREADY_CONFIRMED,
            )

        record = DonationRecord(
            donor_profile_id=profile.id,
            blood_request_id=blood_request.id,
            hospital_id=blood_request.hospital_id,
            blood_group=blood_request.blood_group,
            component=blood_request.component,
            units=1,
            confirmed_at=now,
            confirmed_by_user_id=actor.id if actor else None,
            hospital_reference=hospital_reference,
        )
        db.add(record)
        records.append(record)

        # Cooldown is measured from the donation date, never the acceptance date.
        profile.last_donation_at = now
        profile.total_donations = (profile.total_donations or 0) + 1

        response = db.execute(
            select(DonorResponse).where(
                DonorResponse.blood_request_id == blood_request.id,
                DonorResponse.donor_profile_id == profile_id,
            )
        ).scalar_one_or_none()
        if response is not None:
            response.coordination_status = "CONTRIBUTED"
            if response.status is DonorResponseStatus.SELECTED:
                response.status = DonorResponseStatus.RELEASED
                response.released_at = now
                response.released_reason = "Contribution confirmed"

        notification_service.create_notification(
            db,
            user_id=profile.user_id,
            notification_type=NotificationType.FULFILLMENT_CONFIRMED,
            data={
                "requestId": blood_request.id,
                "reference": blood_request.reference,
                "cooldownDays": settings.donor_cooldown_days,
                "url": "/donor/commitments",
            },
            blood_request_id=blood_request.id,
        )

    blood_request.units_coordinated = min(
        blood_request.units_required, len(records) + (blood_request.units_coordinated or 0)
    )
    db.flush()
    return records


def donor_cooldown_state(db: Session, profile: DonorProfile) -> tuple[bool, int]:
    """Convenience for UIs: whether the donor is clear to be matched again."""
    remaining = cooldown_remaining_days(
        profile.last_donation_at, get_settings().donor_cooldown_days, as_of=utcnow()
    )
    return remaining == 0, remaining
