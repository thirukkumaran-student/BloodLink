"""ASGI entrypoint.

    uvicorn bloodlink_api.main:app --reload --port 8000
"""

from __future__ import annotations

from bloodlink_api.app import create_app

app = create_app()

__all__ = ["app"]
