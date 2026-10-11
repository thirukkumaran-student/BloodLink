"""Request-scoped communication + push subscriptions (owner: D4, spec §12, §13).

There is no generic social chat. A Conversation is always bound to exactly one
BloodRequest and one donor (or one responding blood centre).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bloodlink_api.core.clock import utcnow
from bloodlink_api.db.base import Base, TimestampMixin, enum_column, pk_column
from bloodlink_contracts.enums import ConversationParticipantRole, ConversationStatus, Platform


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"
    __table_args__ = (
        # One coordination thread per (request, organization, donor/user).
        UniqueConstraint(
            "blood_request_id", "organization_id", "donor_id", name="uq_conversation_scope"
        ),
        Index("ix_conversations_request_status", "blood_request_id", "status"),
    )

    id: Mapped[str] = pk_column()
    blood_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("blood_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    #: The counterparty user (donor, or blood-centre coordinator). Always set.
    donor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    donor_response_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("donor_responses.id")
    )
    organization_response_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organization_responses.id")
    )
    counterparty_role: Mapped[ConversationParticipantRole] = enum_column(
        ConversationParticipantRole, nullable=False, default=ConversationParticipantRole.DONOR
    )
    status: Mapped[ConversationStatus] = enum_column(
        ConversationStatus, nullable=False, default=ConversationStatus.OPEN, index=True
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[str] = pk_column()
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class PushSubscription(Base, TimestampMixin):
    """A device/browser endpoint that can receive operational notifications (§12).

    Web-only build: platform is ``WEB`` with a Web Push endpoint. The ``MOBILE``
    value stays in the contract so a native client can be re-added later without
    a schema or API change.
    """

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "endpoint_token", name="uq_push_user_endpoint"),
        Index("ix_push_subscriptions_user_enabled", "user_id", "enabled"),
    )

    id: Mapped[str] = pk_column()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[Platform] = enum_column(Platform, nullable=False, default=Platform.WEB)
    endpoint_token: Mapped[str] = mapped_column(Text, nullable=False)
    #: Base64url P-256 keys required by the Web Push protocol.
    p256dh: Mapped[str | None] = mapped_column(Text)
    auth: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    failure_count: Mapped[int] = mapped_column(nullable=False, default=0)
