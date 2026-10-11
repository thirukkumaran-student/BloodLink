"""PatientNeed model (owner: D2, spec §8).

Ownership note for D2: this table is yours. D1 established the shape and the
``PENDING_HOSPITAL_REVIEW`` initial status; extend it through Lead-reviewed
migrations only.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bloodlink_api.db.base import Base, TimestampMixin, enum_column, pk_column
from bloodlink_contracts.enums import (
    NEED_STATUS_PENDING_REVIEW,
    BloodComponent,
    BloodGroup,
    PatientNeedStatus,
    Urgency,
)

#: Clinical vocabulary lives in the contracts package; these tables never store
#: diagnosis, test results or any other medical record (spec §2, §8).
NEED_STATUSES_REVIEWABLE = {PatientNeedStatus.PENDING_HOSPITAL_REVIEW}


class PatientNeed(Base, TimestampMixin):
    __tablename__ = "patient_needs"
    __table_args__ = (
        Index("ix_patient_needs_hospital_status", "hospital_id", "status"),
        Index("ix_patient_needs_submitter", "submitted_by_user_id", "status"),
    )

    id: Mapped[str] = pk_column()
    #: D2: the individual (or hospital staff on a patient's behalf) who submitted.
    submitted_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    #: D3 reviews these. Hospital must be VERIFIED before it can act.
    hospital_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    blood_group: Mapped[BloodGroup] = enum_column(BloodGroup, nullable=False)
    component: Mapped[BloodComponent] = enum_column(BloodComponent, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    urgency: Mapped[Urgency] = enum_column(Urgency, nullable=False, index=True)
    #: Exact timestamp, not a date (spec §8).
    required_by: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    #: Required coordination context (ward, contact window, instructions).
    #: NOT a medical record and not a place for diagnosis or test results.
    additional_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[PatientNeedStatus] = enum_column(
        PatientNeedStatus, nullable=False, default=NEED_STATUS_PENDING_REVIEW, index=True
    )
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    #: Populated on rejection or cancellation so the submitter sees why.
    review_reason: Mapped[str | None] = mapped_column(String(240))

    blood_request: Mapped["BloodRequest | None"] = relationship(  # noqa: F821
        back_populates="patient_need", uselist=False
    )

    @property
    def is_pending_review(self) -> bool:
        return self.status is PatientNeedStatus.PENDING_HOSPITAL_REVIEW

    @property
    def is_open_for_conversion(self) -> bool:
        """D3 may only mint a BloodRequest from an APPROVED, unconverted need."""
        return self.status is PatientNeedStatus.APPROVED
