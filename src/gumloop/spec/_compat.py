"""Wire-safe serialization for Speakeasy-generated models.

Both flags are load-bearing:
- ``exclude_unset=True`` — suppresses the Speakeasy UNSET sentinel string.
- ``by_alias=True`` — emits ``schema`` not ``schema_`` (and any other Python
  reserved-word aliases Speakeasy uses).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def to_wire_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(exclude_unset=True, by_alias=True)


def to_wire_json(model: BaseModel) -> str:
    return model.model_dump_json(exclude_unset=True, by_alias=True)
