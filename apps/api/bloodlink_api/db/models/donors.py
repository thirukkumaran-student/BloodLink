"""Donor-side models (owner: D4, spec §7, §10, §11, §12).

DonorProfile     — donor identity, availability and internal location data
DonorResponse    — explicit acceptance/selection/standby/withdrawal state
HospitalSubscription — hospital -> donor alert subscription
OrganizationResponse — blood-centre response to a request
DonationRecord   — confirmed donation history feeding the cooldown rule
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bloodlink_api.core.clock import utcnow
from bloodlink_api.db.base import Base, JSONType, TimestampMixin, enum_column, pk_column
from bloodlink_contracts.enums import (
    BloodComponent,
    BloodGroup,
    DonorResponseStatus,
    DonorStandbyStatus,
    NotificationType,
    OrganizationResponseOutcome,
    OrganizationResponseStatus,
    Urgency,
)


class DonorProfile(Base, TimestampMixin):
    """A voluntary donor. Medical eligibility is NOT determined by BloodLink."""

    __tablename__ = "donor_profiles"
    __table_args__ = (
        Index("ix_donor_profiles_group_available", "blood_group", "is_available"),
        Index("ix_donor_profiles_geo_bucket", "district", "state"),
    )

    id: Mapped[str] = pk_column()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    blood_group: Mapped[BloodGroup] = enum_column(BloodGroup, nullable=False, index=True)
    date_of_birth: Mapped[datetime | None] = mapped_column(DateTime)
    weight_kg: Mapped[float | None] = mapped_column()
    city: Mapped[str | None] = mapped_column(String(80))
    district: Mapped[str | None] = mapped_column(String(80), index=True)
    state: Mapped[str | None] = mapped_column(String(80))
    pincode: Mapped[str | None] = mapped_column(String(10))

    # ---- INTERNAL location data (spec §21) ------------------------------------
    # Never serialised to another donor or to an ordinary individual user. The
    # hospital-facing view exposes only a rounded distance such as "~4 km away".
    latitude: Mapped[float | None] = mapped_column()
    longitude: Mapped[float | None] = mapped_column()

    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    #: Donor chooses whether to receive outreach (notification preference, §11).
    accepts_notifications: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_emergency_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_donation_at: Mapped[datetime | None] = mapped_column(DateTime)
    total_donations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Donor-declared acknowledgement that screening happens at the facility.
    acknowledged_screening_notice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship()  # noqa: F821
    responses: Mapped[list["DonorResponse"]] = relationship(
        back_populates="donor_profile", cascade="all, delete-orphan"
    )

    @property
    def display_name(self) -> str:
        return self.user.full_name if self.user else "Donor"


class DonorResponse(Base, TimestampMixin):
    """A donor's explicit response to a request (spec §10).

    ``ACCEPTED`` means the donor confirmed they intend to donate. It is *not* a
    successful donation, and it never closes the request on its own.
    """

    __tablename__ = "donor_responses"
    __table_args__ = (
        UniqueConstraint("blood_request_id", "donor_profile_id", name="uq_response_request_donor"),
        Index("ix_donor_responses_request_status", "blood_request_id", "status"),
    )

    id: Mapped[str] = pk_column()
    blood_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("blood_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    donor_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("donor_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[DonorResponseStatus] = enum_column(
        DonorResponseStatus, nullable=False, default=DonorResponseStatus.ACCEPTED, index=True
    )
    standby_status: Mapped[DonorStandbyStatus] = enum_column(
        DonorStandbyStatus, nullable=False, default=DonorStandbyStatus.NONE
    )
    #: Set when the donor explicitly confirms in the confirmation UI (§10).
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    #: Explicit confirmation is mandatory; a cancel must not mutate state.
    confirmation_method: Mapped[str | None] = mapped_column(String(40))

    # ---- internal coordination signal (spec §21) ------------------------------
    #: Donor's own declared travel availability, stored internally and shown to
    #: hospital staff only as a coarse band ("available within ~30 min").
    eta_minutes: Mapped[int | None] = mapped_column(Integer)

    #: Progress of the *donor's own* coordination checklist. BloodLink never
    #: records screening results or medical clearance.
    coordination_status: Mapped[str | None] = mapped_column(String(40))
    selected_at: Mapped[datetime | None] = mapped_column(DateTime)
    selected_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    released_at: Mapped[datetime | None] = mapped_column(DateTime)
    released_reason: Mapped[str | None] = mapped_column(String(240))
    remarks: Mapped[str | None] = mapped_column(Text)

    donor_profile: Mapped[DonorProfile] = relationship(back_populates="responses")
    blood_request: Mapped["BloodRequest"] = relationship()  # noqa: F821

    @property
    def is_active_commitment(self) -> bool:
        return self.status in (
            DonorResponseStatus.ACCEPTED,
            DonorResponseStatus.SELECTED,
            DonorResponseStatus.STANDBY,
        )


class OrganizationResponse(Base, TimestampMixin):
    """Blood-centre (or partner hospital) response to a request (spec §7)."""

    __tablename__ = "organization_responses"
    __table_args__ = (
        UniqueConstraint("blood_request_id", "organization_id", name="uq_orgresponse_request_org"),
    )

    id: Mapped[str] = pk_column()
    blood_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("blood_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    responded_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    status: Mapped[OrganizationResponseStatus] = enum_column(
        OrganizationResponseStatus, nullable=False, default=OrganizationResponseStatus.AVAILABLE
    )
    units_offered: Mapped[int | None] = mapped_column(Integer)
    component: Mapped[BloodComponent | None] = enum_column(BloodComponent)
    blood_group: Mapped[BloodGroup | None] = enum_column(BloodGroup)
    notes: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[OrganizationResponseOutcome] = enum_column(
        OrganizationResponseOutcome, nullable=False, default=OrganizationResponseOutcome.PENDING
    )
    decided_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)

    organization: Mapped["Organization"] = relationship()  # noqa: F821


class HospitalSubscription(Base, TimestampMixin):
    """A donor subscribing to a hospital's future requests (spec §5, §7, §12)."""

    __tablename__ = "hospital_subscriptions"
    __table_args__ = (
        UniqueConstraint("hospital_id", "user_id", name="uq_subscription_hospital_user"),
    )

    id: Mapped[str] = pk_column()
    hospital_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    donor_profile_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("donor_profiles.id"))
    blood_groups: Mapped[str | None] = mapped_column(String(80))  # comma-separated filter codes
    max_urgency: Mapped[Urgency | None] = enum_column(Urgency)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime)

    hospital: Mapped["Organization"] = relationship()  # noqa: F821


class DonationRecord(Base, TimestampMixin):
    """Confirmed donation history (spec §7, §12).

    Written only after the hospital confirms fulfilment, and used for the donor
    cooldown rule. It contains no clinical outcome data.
    """

    __tablename__ = "donation_records"

    id: Mapped[str] = pk_column()
    donor_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("donor_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    blood_request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("blood_requests.id"), index=True
    )
    hospital_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    blood_group: Mapped[BloodGroup] = enum_column(BloodGroup, nullable=False)
    component: Mapped[BloodComponent] = enum_column(BloodComponent, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)
    confirmed_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    #: BloodLink does not record screening results or medical clearance (spec §2).
    hospital_reference: Mapped[str | None] = mapped_column(String(60))


class Notification(Base):
    """Notification ledger (D4) — delivery state per subscription, plus the
    in-app notification feed."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)

    id: Mapped[str] = pk_column()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[NotificationType] = enum_column(NotificationType, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(String(240), nullable=False)
    #: Privacy-safe deep-link payload: ids, group, component, urgency, distance band.
    data: Mapped[dict | None] = mapped_column(JSONType)
    blood_request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("blood_requests.id"), index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)


class NotificationDelivery(Base):
    """Per-subscription delivery attempt + result."""

    __tablename__ = "notification_deliveries"

    id: Mapped[str] = pk_column()
    notification_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    push_subscription_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("push_subscriptions.id")
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="push")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    error: Mapped[str | None] = mapped_column(String(240))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
