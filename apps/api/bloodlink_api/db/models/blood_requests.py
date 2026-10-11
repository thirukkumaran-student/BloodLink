"""BloodRequest, lifecycle events and outreach ledger (owner: D3, spec §9).

D3 owns the request lifecycle. D4 generates candidate responses *for* a request
and must never mutate ``status`` directly — it reports response state back
through the response service so the Lead-owned transition table stays in one
place (``bloodlink_contracts.enums.BLOOD_REQUEST_TRANSITIONS``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bloodlink_api.core.clock import utcnow
from bloodlink_api.db.base import Base, JSONType, TimestampMixin, enum_column, pk_column
from bloodlink_contracts.enums import (
    BloodComponent,
    BloodGroup,
    BloodRequestStatus,
    DonorStandbyStatus,
    Urgency,
)


class BloodRequest(Base, TimestampMixin):
    __tablename__ = "blood_requests"
    __table_args__ = (
        Index("ix_blood_requests_hospital_status", "hospital_id", "status"),
        Index("ix_blood_requests_status_required_by", "status", "required_by"),
    )

    id: Mapped[str] = pk_column()
    #: Short human-facing reference used in notification bodies (no PHI).
    reference: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    hospital_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    #: Every request traces back to a hospital-verified PatientNeed (spec §8 flow).
    patient_need_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patient_needs.id"), nullable=False, unique=True, index=True
    )
    blood_group: Mapped[BloodGroup] = enum_column(BloodGroup, nullable=False, index=True)
    component: Mapped[BloodComponent] = enum_column(BloodComponent, nullable=False)
    units_required: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    units_coordinated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urgency: Mapped[Urgency] = enum_column(Urgency, nullable=False, index=True)
    status: Mapped[BloodRequestStatus] = enum_column(
        BloodRequestStatus, nullable=False, default=BloodRequestStatus.OPEN, index=True
    )
    required_by: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    #: Coordination note visible to responders. Never contains patient identity.
    coordination_note: Mapped[str | None] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    #: Set when the request is escalated because a coordinated donor fell through.
    backup_reason: Mapped[str | None] = mapped_column(String(240))
    outreach_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    hospital: Mapped["Organization"] = relationship(foreign_keys=[hospital_id])  # noqa: F821
    patient_need: Mapped["PatientNeed"] = relationship(back_populates="blood_request")  # noqa: F821
    events: Mapped[list["BloodRequestEvent"]] = relationship(
        back_populates="blood_request", cascade="all, delete-orphan", order_by="BloodRequestEvent.created_at"
    )
    outreach: Mapped[list["DonorOutreach"]] = relationship(
        back_populates="blood_request", cascade="all, delete-orphan"
    )

    @property
    def units_outstanding(self) -> int:
        return max(0, self.units_required - self.units_coordinated)


class BloodRequestEvent(Base):
    """Immutable lifecycle journal — who changed what, when, and why."""

    __tablename__ = "blood_request_events"

    id: Mapped[str] = pk_column()
    blood_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("blood_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    from_status: Mapped[BloodRequestStatus | None] = enum_column(BloodRequestStatus)
    to_status: Mapped[BloodRequestStatus | None] = enum_column(BloodRequestStatus)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    #: Privacy rule: never store patient identity or clinical detail here.
    detail: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)

    blood_request: Mapped[BloodRequest] = relationship(back_populates="events")


class DonorOutreach(Base):
    """D4-owned ledger of who was told about a request.

    Records tiered outreach (§11, §12) so tier 2/3 expansion can be audited and
    so a donor is never notified twice for the same tier.
    """

    __tablename__ = "donor_outreach"
    __table_args__ = (
        UniqueConstraint("blood_request_id", "donor_profile_id", "tier", name="uq_outreach_request_donor_tier"),
    )

    id: Mapped[str] = pk_column()
    blood_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("blood_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    donor_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("donor_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tier: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    distance_km: Mapped[float | None] = mapped_column()
    compatibility_rank: Mapped[int | None] = mapped_column(Integer)
    standby_status: Mapped[DonorStandbyStatus] = enum_column(
        DonorStandbyStatus, nullable=False, default=DonorStandbyStatus.NONE
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    blood_request: Mapped[BloodRequest] = relationship(back_populates="outreach")
    donor_profile: Mapped["DonorProfile"] = relationship()  # noqa: F821
