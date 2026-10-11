"""Shared DTO base (owner: D1, spec §14).

Wire convention: **JSON is camelCase**. Python stays snake_case. Every request
and response DTO inherits :class:`APIModel`, which accepts both spellings on
input and emits camelCase on output.

Public serialisers in each module return plain camelCase dicts; the canonical
envelope wraps them, so response models stay declarative while the wire format
remains exactly one shape.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from pydantic.alias_generators import to_camel


class APIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        str_strip_whitespace=True,
        extra="ignore",
    )


class ORMModel(APIModel):
    """Same conventions, but reads straight from SQLAlchemy instances."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="ignore",
    )


ShortText = Annotated[str, StringConstraints(min_length=1, max_length=240)]
LongText = Annotated[str, StringConstraints(max_length=2000)]


def normalise_blank_strings(value: object) -> object:
    """Turn ``""`` into ``None`` so optional fields behave predictably."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


class _BlankCoercer(APIModel):
    _coerce_blanks = field_validator("*", mode="before")(normalise_blank_strings)
