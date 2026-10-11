"""Notification + subscription endpoints — OWNER: D4 (spec §12)."""

from __future__ import annotations

from fastapi import Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from bloodlink_api.core.context import CurrentPrincipal
from bloodlink_api.core.envelope import success
from bloodlink_api.core.registry import ModuleSpec, register_module
from bloodlink_api.core.routing import api_router
from bloodlink_api.db.session import get_db
from bloodlink_api.modules.notifications import service as notification_service
from bloodlink_contracts.dto import APIModel

router = api_router(owner="D4", domain="notifications", prefix="/notifications")


class PushSubscriptionRequest(APIModel):
    """INPUT DTO for POST /notifications/subscriptions (Web Push subscription)."""

    endpoint: str
    keys: dict[str, str] | None = None
    platform: str = "WEB"


class MarkReadRequest(APIModel):
    notification_ids: list[str] | None = None


@router.get("", summary="In-app notification feed")
def list_notifications(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    unread_only: bool = Query(False, alias="unreadOnly"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """Return the caller's notifications, newest first.

    OWNER: D4
    PURPOSE: Web notification centre.
    INPUT: unreadOnly?, limit?
    OUTPUT: { items: [NotificationView], unreadCount: int }
    AUTHORIZATION: Self only.
    STATE CHANGES: none
    ERRORS: 401 UNAUTHENTICATED
    DEPENDENCIES: Notification ledger
    MUST NOT: return another user's notifications
    PRIVACY: payloads are privacy-safe by construction (§12)
    """
    items = notification_service.list_for_user(
        db, principal.user_id, unread_only=unread_only, limit=limit
    )
    db.commit()
    return success(
        request, {"items": items, "unreadCount": notification_service.unread_count(db, principal.user_id)}
    )


@router.post("/read", summary="Mark notifications as read")
def mark_read(
    payload: MarkReadRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Mark the given notifications (or all) as read.

    OWNER: D4
    PURPOSE: Feed hygiene for the web client.
    INPUT: MarkReadRequest
    OUTPUT: { updated: int }
    AUTHORIZATION: Self only.
    STATE CHANGES: Notification.readAt
    ERRORS: 401 UNAUTHENTICATED
    """
    updated = notification_service.mark_read(db, principal.user_id, payload.notification_ids)
    db.commit()
    return success(request, {"updated": updated})


@router.get("/subscriptions", summary="List push subscriptions")
def list_subscriptions(
    request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)
) -> dict:
    """List the caller's registered devices/browsers.

    OWNER: D4
    PURPOSE: Notification settings screen.
    INPUT: none
    OUTPUT: { items: [PushSubscriptionView] }
    AUTHORIZATION: Self only.
    STATE CHANGES: none
    PRIVACY: endpoints are returned truncated to host so they cannot be replayed
    """
    from sqlalchemy import select

    from bloodlink_api.db.models.coordination import PushSubscription

    rows = db.execute(
        select(PushSubscription).where(PushSubscription.user_id == principal.user_id)
    ).scalars()
    items = [
        {
            "id": row.id,
            "platform": row.platform.value,
            "endpointHost": (row.endpoint_token.split("/")[2] if "//" in row.endpoint_token else "browser"),
            "enabled": row.enabled,
            "userAgent": row.user_agent,
            "lastUsedAt": row.last_used_at.isoformat() + "Z" if row.last_used_at else None,
        }
        for row in rows
    ]
    return success(request, {"items": items})


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED, summary="Register a push subscription")
def create_subscription(
    payload: PushSubscriptionRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Register a browser Web Push subscription (idempotent per endpoint).

    OWNER: D4
    PURPOSE: Enable Web Push / service-worker delivery for this browser.
    INPUT: PushSubscriptionRequest { endpoint, keys.p256dh, keys.auth }
    OUTPUT: 201 PushSubscriptionView
    AUTHORIZATION: Self only.
    STATE CHANGES: PushSubscription(enabled=True, created or re-enabled)
    ERRORS: 422 VALIDATION_ERROR
    DEPENDENCIES: transport (``notifications/transport.py``)
    MUST NOT: accept a subscription for another user
    PRIVACY: endpoint keys are stored for delivery and never returned in full
    """
    keys = payload.keys or {}
    subscription = notification_service.register_subscription(
        db,
        user_id=principal.user_id,
        endpoint=payload.endpoint,
        p256dh=keys.get("p256dh"),
        auth=keys.get("auth"),
        platform=payload.platform,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return success(
        request, {"id": subscription.id, "enabled": subscription.enabled, "platform": subscription.platform.value}
    )


@router.delete("/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a push subscription")
def delete_subscription(
    subscription_id: str, principal: CurrentPrincipal, db: Session = Depends(get_db)
) -> Response:
    """Disable a push subscription (e.g. the user turned notifications off).

    OWNER: D4
    PURPOSE: Notification control, and the browser-unsubscribe path.
    INPUT: path subscriptionId
    OUTPUT: 204 No Content
    AUTHORIZATION: Self only.
    STATE CHANGES: PushSubscription.enabled=False
    ERRORS: 404 NOT_FOUND when the subscription is not the caller's
    """
    updated = notification_service.set_subscription_enabled(
        db, principal.user_id, subscription_id, enabled=False
    )
    db.commit()
    if not updated:
        from bloodlink_api.core.errors import NotFoundError

        raise NotFoundError("Subscription not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


MODULE = register_module(
    ModuleSpec(
        key="notifications",
        owner="D4",
        domain="notifications",
        api_prefix="/notifications",
        description="Operational notification feed, device subscriptions and the push transport.",
        foundation_status="COMPLETE",
        router=router,
        depends_on=("auth",),
    )
)
