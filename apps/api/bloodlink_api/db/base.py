"""SQLAlchemy declarative base, shared column types and mixins (owner: D1, spec §23).

Feature developers add *models* inside their own modules, but the declarative
base, ID/timestamp conventions and column types are owned here so every table
looks the same. Migrations are generated and merged by D1 from the single
canonical metadata object.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import JSON, DateTime, Enum as SAEnum, MetaData, String, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from bloodlink_api.core.clock import utcnow

# Explicit naming convention => stable, predictable Alembic autogenerate output.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata_obj = MetaData(naming_convention=NAMING_CONVENTION)

#: JSON on SQLite, JSONB on PostgreSQL.
JSONType = JSON().with_variant(postgresql.JSONB(astext_type=String()), "postgresql")

EnumVar = TypeVar("EnumVar")


class Base(DeclarativeBase):
    metadata = metadata_obj

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - debug helper
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


def new_id() -> str:
    """UUID4 string primary keys — stable across SQLite and PostgreSQL."""
    return str(uuid.uuid4())


def pk_column() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=new_id)


def enum_column(enum_cls: type[EnumVar], **kwargs: Any):
    """Store the enum's *wire value* (e.g. ``A+``), not the member name.

    ``String(N)`` columns rather than native PG enums: adding a new status value
    then never needs a database type migration, and SQLite behaves identically.
    """
    length = int(kwargs.pop("length", 48))
    return mapped_column(
        SAEnum(
            enum_cls,  # type: ignore[arg-type]
            native_enum=False,
            length=length,
            values_callable=lambda cls: [member.value for member in cls],
            validate_strings=True,
        ),
        **kwargs,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, server_default=func.now(), nullable=False
    )
