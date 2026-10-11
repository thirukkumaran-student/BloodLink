"""Shared paths (owner: D1)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # <repo>/bloodlink
WORKSPACE_ROOT = PROJECT_ROOT.parent


def repo_path(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)
