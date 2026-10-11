"""Request-id middleware + canonical success wrapping helpers (owner: D1)."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from bloodlink_contracts.envelope import success_envelope


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id, time the request, and echo ``X-Request-Id``."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.started_at = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - request.state.started_at) * 1000:.1f}"
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def success(request: Request, data: Any, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wrap a payload in the canonical success envelope.

    The API returns dict bodies (not enforced response models) so the envelope is
    always exactly what ``success_envelope`` produces; response models stay on
    the DTO layer for internal validation and OpenAPI docs.
    """
    return success_envelope(data, meta=meta, request_id=getattr(request.state, "request_id", None))
