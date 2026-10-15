from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any


def item_access_body(
    *,
    share: Sequence[Mapping[str, Any]] | None,
    remove: Sequence[Mapping[str, Any]] | None,
    link: Mapping[str, Any] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if share is not None:
        body["share"] = list(share)
    if remove is not None:
        body["remove"] = list(remove)
    if link is not None:
        body["link"] = dict(link)
    return body
