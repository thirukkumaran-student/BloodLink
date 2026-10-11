"""The one canonical API response convention (owner: D1, spec §14).

Success
-------
{
  "data": <payload>,
  "meta": {"requestId": "...", "generatedAt": "..."},
  "error": null
}

Error
-----
{
  "data": null,
  "meta": {"requestId": "...", "generatedAt": "..."},
  "error": {"code": "NOT_FOUND", "message": "...", "details": [...]}
}

Every endpoint in every domain uses this shape. Clients unwrap ``data``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def success_envelope(data: Any, *, meta: dict[str, Any] | None = None, request_id: str | None = None) -> dict:
    payload_meta: dict[str, Any] = {"generatedAt": _now_iso()}
    if request_id:
        payload_meta["requestId"] = request_id
    if meta:
        payload_meta.update(meta)
    return {"data": data, "meta": payload_meta, "error": None}


def error_envelope(
    code: str,
    message: str,
    *,
    details: list[dict[str, Any]] | None = None,
    request_id: str | None = None,
) -> dict:
    return {
        "data": None,
        "meta": {"requestId": request_id, "generatedAt": _now_iso()},
        "error": {"code": code, "message": message, "details": details or []},
    }
