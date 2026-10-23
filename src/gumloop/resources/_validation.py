from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from pydantic import ValidationError

from gumloop.errors import GumloopError


@contextmanager
def request_validation(name: str) -> Iterator[None]:
    """Expose validation failures as SDK errors at opt-in request boundaries."""
    try:
        yield
    except ValidationError as error:
        raise GumloopError(f"invalid {name}: {error}") from error
