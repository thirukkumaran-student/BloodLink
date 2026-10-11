"""Tiny .env loader (owner: D1) — avoids an extra dependency for the MVP."""

from __future__ import annotations

import os
from pathlib import Path

from bloodlink_config.paths import PROJECT_ROOT


def load_env_file(path: str | Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Load ``KEY=VALUE`` pairs into ``os.environ``. Returns what was loaded."""
    target = Path(path) if path else PROJECT_ROOT / ".env"
    loaded: dict[str, str] = {}
    if not target.exists():
        return loaded
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (override or key not in os.environ):
            os.environ[key] = value
            loaded[key] = value
    return loaded


def read_env(key: str, default: str | None = None) -> str | None:
    load_env_file()
    return os.environ.get(key, default)
