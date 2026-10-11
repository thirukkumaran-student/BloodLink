"""Identity, organization & audit models (owner: D1, spec §5, §16).

These tables are platform infrastructure: authentication, RBAC, organization
context and the audit trail. Feature developers read them freely but must not
change their shape without Lead review (spec §24).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bloodlink_api.core.clock import utcnow
from bloodlink_api.db.base import Base, JSONType, TimestampMixin, enum_column, new_id, pk_column
from bloodlink_contracts.enums import OrgType, OrgVerificationStatus, Role


class Organization(Base, TimestampMixin):
    """A hospital or blood centre. Organization users act *inside* this context."""

    __tablename__ = "organizations"

    id: Mapped[str] = pk_column()
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    org_type: Mapped[OrgType] = enum_column(OrgType, nullable=False, index=True)
    registration_number: Mapped[str | None] = mapped_column(String(80), index=True)
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(String(240))
    city: Mapped[str | None] = mapped_column(String(80), index=True)
    district: Mapped[str | None] = mapped_column(String(80), index=True)
    state: Mapped[str | None] = mapped_column(String(80))
    pincode: Mapped[str | None] = mapped_column(String(10))
    #: Internal matching data. Exact coordinates are never returned to ordinary
    #: users; only approximate distances are exposed (spec §21).
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    verification_status: Mapped[OrgVerificationStatus] = enum_column(
        OrgVerificationStatus, nullable=False, default=OrgVerificationStatus.PENDING, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    #: ``users`` and ``organizations`` reference each other (a user belongs to an
    #: organization, an organization records the admin who verified it). That cycle
    #: cannot be created inline on PostgreSQL, so this one side is deferred with
    #: ``use_alter``: ``create_all`` and Alembic both emit ``ALTER TABLE ... ADD
    #: CONSTRAINT`` once both tables exist. PostgreSQL enforces the real constraint;
    #: SQLite ignores it either way.
    verified_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "users.id",
            use_alter=True,
            name="fk_organizations_verified_by_user_id_users",
        ),
    )

    memberships: Mapped[list["OrganizationMembership"]] = relationship(back_populates="organization")

    @property
    def is_operational(self) -> bool:
        """Verified organizations may issue requests / responses (spec §16)."""
        return self.verification_status is OrgVerificationStatus.VERIFIED

    @property
    def location_label(self) -> str:
        parts = [part for part in (self.city, self.district, self.state) if part]
        return ", ".join(parts) if parts else "Location not provided"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = pk_column()
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[Role] = enum_column(Role, nullable=False, index=True)
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    organization: Mapped[Organization | None] = relationship(foreign_keys=[organization_id])
    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_organization_user(self) -> bool:
        return self.role in (Role.HOSPITAL, Role.BLOOD_CENTRE)

    @property
    def initials(self) -> str:
        return "".join(part[0].upper() for part in self.full_name.split()[:2]) or "?"


class OrganizationMembership(Base, TimestampMixin):
    __tablename__ = "organization_memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),)

    id: Mapped[str] = pk_column()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(80))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")


class RefreshToken(Base):
    """Hashed refresh tokens — rotating, revocable."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = pk_column()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    user_agent: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    @property
    def is_usable(self) -> bool:
        from bloodlink_api.core.clock import utcnow

        return self.revoked_at is None and self.expires_at > utcnow()


class AuditLog(Base):
    """Append-only record of consequential actions (spec §7 audit entity)."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id"),)

    id: Mapped[str] = pk_column()
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    actor_role: Mapped[Role | None] = enum_column(Role)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"))
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    detail: Mapped[dict | None] = mapped_column(JSONType)
    ip_address: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True, default=utcnow)


class IdempotencyRecord(Base):
    """Optional client-supplied ``Idempotency-Key`` support.

    Lets the web client safely retry POSTs without duplicate domain records.
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("key", "user_id", "endpoint", name="uq_idempotency_scope"),)

    id: Mapped[str] = pk_column()
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    endpoint: Mapped[str] = mapped_column(String(160), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(nullable=False)
    response_body: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class VerificationDocument(Base):
    """Organization verification paperwork. Never rendered in ordinary views."""

    __tablename__ = "verification_documents"

    id: Mapped[str] = pk_column()
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(60), nullable=False)
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
