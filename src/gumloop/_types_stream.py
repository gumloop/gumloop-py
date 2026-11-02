"""Stream event envelope; the only model the transport needs, so it loads without ``gumloop.types``."""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field
from pydantic import SerializerFunctionWrapHandler
from pydantic import model_serializer
from pydantic import model_validator

from gumloop._types_base import _Model


class StreamEvent(_Model):
    type: str | None = None
    data: Any = None
    stream_cursor: str | None = None
    final: bool | None = None
    # Wire format uses camelCase on these two; surface snake_case attributes
    # to callers while still accepting the wire names on deserialize.
    finish_reason: str | None = Field(default=None, validation_alias="finishReason")
    error: str | None = None
    error_details: dict[str, Any] | None = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _structured_error(cls, value: Any) -> Any:
        if isinstance(value, dict) and isinstance(value.get("error"), dict):
            details = value["error"]
            return {**value, "error": details.get("message") or json.dumps(details), "error_details": details}
        return value

    @model_serializer(mode="wrap")
    def _serialize_event(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if self.error_details is not None and "error" in data:
            data["error"] = self.error_details
        return data

    error_message: str | None = Field(default=None, validation_alias="errorMessage")
