from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterator
from itertools import chain

from gumloop import Gumloop
from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.types import StreamEvent


def print_session_stream(
    cli: CliContext, open_stream: Callable[[Gumloop], Iterator[StreamEvent]], *, json_output: bool
) -> None:
    def start(client: Gumloop) -> Iterator[StreamEvent]:
        stream = open_stream(client)
        first = next(stream, None)
        return chain((), stream) if first is None else chain((first,), stream)

    cursor = None
    session_id = None
    try:
        for event in cli.call_with_refresh(start):
            payload = event.model_dump(exclude_unset=True)
            if event.stream_cursor:
                cursor = event.stream_cursor
            if json_output:
                print_json(payload)
            else:
                if payload.get("interaction_id") and payload["interaction_id"] != session_id:
                    session_id = payload["interaction_id"]
                    console.print(f"Session: {session_id}", markup=False, highlight=False)
                if event.type == "text-delta" and isinstance(payload.get("delta"), str):
                    console.print(payload["delta"], end="", markup=False, highlight=False)
                elif event.type == "finish":
                    console.print()
            if event.finish_reason == "not_resumable":
                raise GumloopError("This stream cannot be resumed. Retrieve the session to check its current state.")
            if event.type == "error" or event.error or event.finish_reason == "error":
                raise GumloopError(event.error_message or event.error or "Agent stream failed.")
    finally:
        if not json_output and cursor:
            console.print(f"\nResume cursor: {cursor}", markup=False, highlight=False)
