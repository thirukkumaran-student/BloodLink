"""Pagination + list conventions (owner: D1, spec §14).

Every list endpoint accepts ``?page=&page_size=&sort=&order=`` and returns the
canonical envelope with a ``meta.pagination`` block.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Sequence, TypeVar

from fastapi import Query

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20

T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: Sequence[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    def meta(self, **extra: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "total": self.total,
            "page": self.page,
            "pageSize": self.page_size,
            "pages": self.pages,
            "hasNext": self.has_next,
        }
        payload.update(extra)
        return payload


def pagination_params(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(
        DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, alias="pageSize", description="Items per page"
    ),
) -> tuple[int, int]:
    """FastAPI dependency returning ``(page, page_size)``."""
    return page, page_size


def apply_sort(query, model, *, sort: str | None, order: str | None, allowed: dict[str, Any], default):
    """Apply a whitelisted sort column. Unknown columns fall back to the default."""
    column = allowed.get((sort or "").strip().lower())
    descending = (order or "desc").lower() == "desc"
    if column is None:
        return query.order_by(default)
    return query.order_by(column.desc() if descending else column.asc())
