"""Notification transport layer (owner: D4, spec §12).

Platform: web (Web Push / service worker). The transport is pluggable so the
foundation sprint runs with zero external infrastructure:

* ``log``     — structured log line (default in dev/test)
* ``console`` — writes the payload to ``var/notifications.log`` for inspection
* ``webpush`` — real Web Push over VAPID (requires ``pywebpush``; install with
  ``pip install -e '.[prod]'`` and set the VAPID keys)

Every outbound payload passes ``assert_privacy_safe_payload`` first: patient
identity, medical detail and exact coordinates are rejected before send.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from bloodlink_api.core.settings import get_settings
from bloodlink_config.logging import get_logger
from bloodlink_config.paths import PROJECT_ROOT
from bloodlink_validation.common import assert_privacy_safe_payload

logger = get_logger("bloodlink.notifications.transport")


@dataclass
class PushMessage:
    """A privacy-safe notification ready for delivery."""

    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)
    tag: str | None = None
    urgency: str = "normal"
    endpoint: str | None = None
    p256dh: str | None = None
    auth: str | None = None

    def privacy_checked(self) -> "PushMessage":
        assert_privacy_safe_payload({"title": self.title, "body": self.body, "data": self.data})
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "data": self.data,
            "tag": self.tag,
            "urgency": self.urgency,
        }


@dataclass
class DeliveryResult:
    delivered: bool
    channel: str
    error: str | None = None


class NotificationTransport:
    name = "base"

    def send(self, message: PushMessage) -> DeliveryResult:  # pragma: no cover - interface
        raise NotImplementedError


class LogTransport(NotificationTransport):
    """Default transport — no external service required."""

    name = "log"

    def send(self, message: PushMessage) -> DeliveryResult:
        message.privacy_checked()
        logger.info(
            "push.send channel=log title=%r body=%r data=%s",
            message.title,
            message.body,
            json.dumps(message.data, default=str),
        )
        return DeliveryResult(delivered=True, channel=self.name)


class ConsoleTransport(NotificationTransport):
    """Append JSON lines to ``var/notifications.log`` so the web dev can watch
    notification traffic without a push service."""

    name = "console"

    def __init__(self) -> None:
        self.path = PROJECT_ROOT / "var" / "notifications.log"

    def send(self, message: PushMessage) -> DeliveryResult:
        message.privacy_checked()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(message.as_dict(), default=str) + "\n")
        return DeliveryResult(delivered=True, channel=self.name)


class WebPushTransport(NotificationTransport):
    """Real Web Push delivery. Requires the ``prod`` extra (``pywebpush``)."""

    name = "webpush"

    def __init__(self) -> None:
        try:  # pragma: no cover - optional dependency
            from pywebpush import webpush  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "pywebpush is required for BLOODLINK_PUSH_TRANSPORT=webpush; "
                "install with `pip install -e '.[prod]'`"
            ) from exc
        self._webpush = webpush
        settings = get_settings()
        self._vapid_claims = {
            "sub": getattr(settings, "vapid_subject", "mailto:ops@bloodlink.local"),
        }
        self._vapid_private_key = getattr(settings, "vapid_private_key", "")

    def send(self, message: PushMessage) -> DeliveryResult:  # pragma: no cover - network path
        message.privacy_checked()
        if not message.endpoint:
            return DeliveryResult(False, self.name, "missing endpoint")
        try:
            self._webpush(
                subscription_info={
                    "endpoint": message.endpoint,
                    "keys": {"p256dh": message.p256dh, "auth": message.auth},
                },
                data=json.dumps(message.as_dict()),
                vapid_private_key=self._vapid_private_key,
                vapid_claims=dict(self._vapid_claims),
            )
            return DeliveryResult(True, self.name)
        except Exception as exc:  # noqa: BLE001 - surfaced to the delivery ledger
            logger.warning("push.send failed channel=webpush error=%s", exc)
            return DeliveryResult(False, self.name, str(exc)[:240])


_TRANSPORTS: dict[str, type[NotificationTransport]] = {
    "log": LogTransport,
    "console": ConsoleTransport,
    "webpush": WebPushTransport,
}


def get_transport() -> NotificationTransport:
    settings = get_settings()
    transport_cls = _TRANSPORTS.get(settings.push_transport, LogTransport)
    return transport_cls()
