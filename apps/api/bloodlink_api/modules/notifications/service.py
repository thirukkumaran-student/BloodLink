"""Notification service (owner: D4, spec §12).

Responsibilities
----------------
* turn domain events into **privacy-safe** notification payloads
* persist the in-app notification feed (``Notification``) and per-device
  delivery state (``NotificationDelivery``)
* respect ``PushSubscription.enabled`` and a per-user hourly rate limit
* never include patient identity, medical detail or exact coordinates

D1 provides: the model, the transport abstraction, the privacy assertion and the
rate-limit setting. D4 extends the catalogue of notification types.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bloodlink_api.core.clock import iso, utcnow
from bloodlink_api.core.geo import distance_band
from bloodlink_api.core.settings import get_settings
from bloodlink_api.db.models.coordination import PushSubscription
from bloodlink_api.db.models.donors import (
    DonationRecord,
    DonorProfile,
    Notification,
    NotificationDelivery,
)
from bloodlink_api.db.models.identity import Organization, User
from bloodlink_api.modules.notifications.transport import PushMessage, get_transport
from bloodlink_contracts.enums import BloodGroup, NotificationType
from bloodlink_config.logging import get_logger

logger = get_logger("bloodlink.notifications")

#: Human copy per notification type. Bodies are written to be safe by
#: construction: no patient identity, no clinical detail, no coordinates.
COPY: dict[NotificationType, tuple[str, str]] = {
    NotificationType.NEED_SUBMITTED: (
        "New blood requirement submitted",
        "A patient requirement needs your hospital's review.",
    ),
    NotificationType.NEED_REVIEWED: (
        "Your blood requirement was reviewed",
        "A hospital reviewed your requirement. Open BloodLink to see the outcome.",
    ),
    NotificationType.REQUEST_OPENED: (
        "Blood required near you",
        "A hospital has opened a requirement. Open BloodLink to see if you can help.",
    ),
    NotificationType.REQUEST_OUTREACH_EXPANDED: (
        "Wider search for a requirement",
        "A hospital has widened its search. Your group may be able to help.",
    ),
    NotificationType.DONOR_ACCEPTED: (
        "A donor accepted",
        "A donor accepted your requirement. Review and select in BloodLink.",
    ),
    NotificationType.DONOR_SELECTED: (
        "You were selected",
        "A hospital selected you for a requirement. Open BloodLink for coordination details.",
    ),
    NotificationType.DONOR_STANDBY: (
        "You are on standby",
        "You were placed on standby for a requirement. We will update you if needed.",
    ),
    NotificationType.ORGANIZATION_RESPONDED: (
        "A blood centre responded",
        "A blood centre responded to your requirement. Review the offer in BloodLink.",
    ),
    NotificationType.MESSAGE_RECEIVED: (
        "New coordination message",
        "You have a new message on a BloodLink requirement thread.",
    ),
    NotificationType.FULFILLMENT_PENDING: (
        "Confirm your contribution",
        "Coordination details for a requirement you accepted are ready.",
    ),
    NotificationType.FULFILLMENT_CONFIRMED: (
        "Contribution confirmed",
        "Thank you — your contribution was confirmed by the hospital.",
    ),
    NotificationType.REQUEST_FULFILLED: (
        "Requirement fulfilled",
        "A requirement you were involved with has been fulfilled.",
    ),
    NotificationType.REQUEST_BACKUP_REQUIRED: (
        "Backup needed",
        "A requirement needs backup coordination. Open BloodLink to review options.",
    ),
    NotificationType.SUBSCRIPTION_ALERT: (
        "Alert from a hospital you follow",
        "A hospital you follow opened a requirement matching your alert preference.",
    ),
    NotificationType.ACCOUNT: ("BloodLink account", "There is an update to your BloodLink account."),
}


def _claim(title: str, body: str, notification_type: NotificationType) -> tuple[str, str]:
    fallback = COPY.get(notification_type, ("BloodLink", "You have a BloodLink update."))
    return (title or fallback[0])[:120], (body or fallback[1])[:240]


def _rate_limited(db: Session, user_id: str) -> bool:
    limit = get_settings().rate_limit_notifications_per_hour
    if limit <= 0:
        return False
    since = utcnow() - timedelta(hours=1)
    recent = db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.created_at >= since)
    ).scalar_one()
    return recent >= limit


def create_notification(
    db: Session,
    *,
    user_id: str,
    notification_type: NotificationType,
    title: str | None = None,
    body: str | None = None,
    data: dict[str, Any] | None = None,
    blood_request_id: str | None = None,
    deliver: bool = True,
) -> Notification | None:
    """Persist a notification and (optionally) push it to every active device.

    ``data`` must be privacy-safe: use ids, blood group, component, urgency and
    ``distance_band`` values — never coordinates or patient information.
    """
    if _rate_limited(db, user_id):
        logger.info("notification.suppressed user_id=%s reason=rate_limit", user_id)
        return None

    safe_title, safe_body = _claim(title or "", body or "", notification_type)
    notification = Notification(
        user_id=user_id,
        type=notification_type,
        title=safe_title,
        body=safe_body,
        data=data or {},
        blood_request_id=blood_request_id,
    )
    db.add(notification)
    db.flush()

    if deliver:
        _deliver(db, notification)
    return notification


def _deliver(db: Session, notification: Notification) -> int:
    subscriptions = db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == notification.user_id,
            PushSubscription.enabled.is_(True),
        )
    ).scalars().all()

    if not subscriptions:
        db.add(
            NotificationDelivery(
                notification_id=notification.id,
                channel="in_app",
                status="STORED",
                sent_at=utcnow(),
            )
        )
        return 0

    transport = get_transport()
    sent = 0
    for subscription in subscriptions:
        message = PushMessage(
            title=notification.title,
            body=notification.body,
            data=notification.data or {},
            tag=notification.blood_request_id,
            endpoint=subscription.endpoint_token,
            p256dh=subscription.p256dh,
            auth=subscription.auth,
        )
        result = transport.send(message)
        db.add(
            NotificationDelivery(
                notification_id=notification.id,
                push_subscription_id=subscription.id,
                channel=transport.name,
                status="SENT" if result.delivered else "FAILED",
                error=result.error,
                sent_at=utcnow() if result.delivered else None,
            )
        )
        if result.delivered:
            sent += 1
            subscription.last_used_at = utcnow()
            subscription.failure_count = 0
        else:
            subscription.failure_count = (subscription.failure_count or 0) + 1
            if subscription.failure_count >= 5:
                # Stop hammering an endpoint that keeps failing (browser unsubscribed).
                subscription.enabled = False
    return sent


def notify_matched_donors(db: Session, blood_request, candidates: Sequence) -> int:
    """Dispatch tier outreach to matched donors (§11, §12).

    Notification body deliberately contains only the blood group, component,
    urgency and a coarse distance band.
    """
    notified = 0
    for candidate in candidates:
        if not getattr(candidate, "notifications_enabled", True):
            continue
        user = db.get(User, candidate.user_id)
        if user is None or not user.is_active:
            continue
        from bloodlink_api.db.models.blood_requests import DonorOutreach

        record = db.execute(
            select(DonorOutreach).where(
                DonorOutreach.blood_request_id == blood_request.id,
                DonorOutreach.donor_profile_id == candidate.donor_profile_id,
                DonorOutreach.tier == candidate.tier,
            )
        ).scalar_one_or_none()
        if record is not None and record.notified_at is not None:
            continue

        create_notification(
            db,
            user_id=user.id,
            notification_type=NotificationType.REQUEST_OPENED
            if candidate.tier == 1
            else NotificationType.REQUEST_OUTREACH_EXPANDED,
            data={
                "requestId": blood_request.id,
                "reference": blood_request.reference,
                "bloodGroup": blood_request.blood_group.value,
                "component": blood_request.component.value,
                "urgency": blood_request.urgency.value,
                "distanceBand": distance_band(candidate.distance_km),
                "url": f"/donor/requests/{blood_request.id}",
            },
            blood_request_id=blood_request.id,
        )
        if record is None:
            record = candidate.as_outreach_record(blood_request_id=blood_request.id)
            db.add(record)
        record.notified_at = utcnow()
        notified += 1
    db.flush()
    return notified


def notify_outreach_records(db: Session, blood_request, records: Iterable) -> int:
    """Notify donors covered by already-created outreach rows (expansion path)."""
    from bloodlink_api.modules.matching.service import Candidate

    wrapped = []
    for record in records:
        profile = db.get(DonorProfile, record.donor_profile_id)
        if profile is None:
            continue
        wrapped.append(
            Candidate(
                donor_profile_id=record.donor_profile_id,
                user_id=profile.user_id,
                display_name=profile.display_name,
                blood_group=profile.blood_group.value,
                distance_km=record.distance_km,
                tier=record.tier,
                rank=record.compatibility_rank or 0,
                exact_group_match=True,
                notifications_enabled=profile.accepts_notifications,
            )
        )
    return notify_matched_donors(db, blood_request, wrapped)


# --------------------------------------------------------------------------- #
# User-facing helpers (used by the notification endpoints)
# --------------------------------------------------------------------------- #
def list_for_user(db: Session, user_id: str, *, unread_only: bool = False, limit: int = 50) -> list[dict]:
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    rows = db.execute(query.order_by(Notification.created_at.desc()).limit(limit)).scalars()
    return [
        {
            "id": row.id,
            "type": row.type.value,
            "title": row.title,
            "body": row.body,
            "data": row.data or {},
            "readAt": iso(row.read_at),
            "createdAt": iso(row.created_at),
        }
        for row in rows
    ]


def unread_count(db: Session, user_id: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    ).scalar_one()


def mark_read(db: Session, user_id: str, notification_ids: Sequence[str] | None = None) -> int:
    query = select(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    if notification_ids:
        query = query.where(Notification.id.in_(list(notification_ids)))
    rows = db.execute(query).scalars().all()
    now = utcnow()
    for row in rows:
        row.read_at = now
    db.flush()
    return len(rows)


def register_subscription(
    db: Session,
    *,
    user_id: str,
    endpoint: str,
    p256dh: str | None,
    auth: str | None,
    platform: str = "WEB",
    user_agent: str | None = None,
) -> PushSubscription:
    """Register (or re-enable) a browser push subscription for this user."""
    from bloodlink_contracts.enums import Platform

    existing = db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user_id, PushSubscription.endpoint_token == endpoint
        )
    ).scalar_one_or_none()
    if existing:
        existing.enabled = True
        existing.p256dh = p256dh or existing.p256dh
        existing.auth = auth or existing.auth
        existing.last_used_at = utcnow()
        existing.failure_count = 0
        db.flush()
        return existing

    subscription = PushSubscription(
        user_id=user_id,
        platform=Platform.coerce(platform) or Platform.WEB,
        endpoint_token=endpoint,
        p256dh=p256dh,
        auth=auth,
        user_agent=(user_agent or "")[:200] or None,
        enabled=True,
    )
    db.add(subscription)
    db.flush()
    return subscription


def set_subscription_enabled(db: Session, user_id: str, subscription_id: str, *, enabled: bool) -> bool:
    subscription = db.execute(
        select(PushSubscription).where(
            PushSubscription.id == subscription_id, PushSubscription.user_id == user_id
        )
    ).scalar_one_or_none()
    if subscription is None:
        return False
    subscription.enabled = enabled
    db.flush()
    return True


def recent_donations(db: Session, donor_profile_id: str) -> DonationRecord | None:
    return db.execute(
        select(DonationRecord)
        .where(DonationRecord.donor_profile_id == donor_profile_id)
        .order_by(DonationRecord.confirmed_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def hospital_display(organization: Organization | None) -> str:
    return organization.name if organization else "BloodLink partner hospital"


def blood_group_label(group: BloodGroup) -> str:
    return group.value
