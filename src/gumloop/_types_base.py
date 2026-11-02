"""Base model shared by every SDK type; importable without the full ``gumloop.types`` catalog."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict


class _Model(BaseModel):
    """Base for all SDK models. ``extra="allow"`` lets the SDK transparently
    pass through fields the backend adds in future versions without an SDK
    bump — both on parsed responses and on user-supplied request kwargs."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @classmethod
    def build(cls, request: Any = None, /, **kwargs: Any) -> dict[str, Any]:
        """Merge a (model | dict | None) request with caller kwargs and return
        a JSON-ready dict. ``exclude_unset`` is used so unspecified fields
        keep their backend-side defaults instead of being overwritten by the
        SDK's local default values."""
        base = request.model_dump(exclude_unset=True) if isinstance(request, cls) else dict(request or {})
        base.update({k: v for k, v in kwargs.items() if v is not None})
        return cls.model_validate(base).model_dump(exclude_unset=True)
