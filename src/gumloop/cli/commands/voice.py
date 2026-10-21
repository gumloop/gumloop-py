from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

voice_app = typer.Typer(help="Exchange SDP and end live agent voice sessions.", no_args_is_help=True)
MAX_OFFER_BYTES = 1024 * 1024


def _read_offer(file_path: str | None, stdin_marker: str | None) -> str:
    if (file_path is None) == (stdin_marker is None):
        raise GumloopError("Pass exactly one of --offer-sdp-file or --offer-sdp-stdin -.")
    if stdin_marker is not None:
        if stdin_marker != "-":
            raise GumloopError("--offer-sdp-stdin only accepts '-'.")
        try:
            raw = sys.stdin.buffer.read(MAX_OFFER_BYTES + 1)
            offer = raw.decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise GumloopError("Could not read the SDP offer from stdin as UTF-8 text.") from error
    else:
        try:
            with Path(file_path or "").expanduser().open("rb") as source:
                raw = source.read(MAX_OFFER_BYTES + 1)
            if len(raw) > MAX_OFFER_BYTES:
                raise GumloopError("The SDP offer exceeds 1 MiB.")
            offer = raw.decode("utf-8")
        except OSError as error:
            raise GumloopError(f"Could not read the SDP offer: {error.strerror or error}.") from error
        except UnicodeError as error:
            raise GumloopError("The SDP offer file must contain UTF-8 text.") from error
    if not offer.strip():
        raise GumloopError("The SDP offer must not be empty.")
    if len(offer.encode("utf-8")) > MAX_OFFER_BYTES:
        raise GumloopError("The SDP offer exceeds 1 MiB.")
    return offer


@voice_app.command("start")
def start_voice(
    ctx: typer.Context,
    agent_id: Annotated[str, typer.Argument(help="Agent whose enabled voice ability should handle the call.")],
    session_id: Annotated[str, typer.Option("--session", help="New or existing session id for this call.")],
    offer_sdp_file: Annotated[
        str | None, typer.Option("--offer-sdp-file", help="UTF-8 SDP offer from your WebRTC client.")
    ] = None,
    offer_sdp_stdin: Annotated[
        str | None, typer.Option("--offer-sdp-stdin", help="Use '-' to read an SDP offer from stdin.")
    ] = None,
    incognito: Annotated[bool, typer.Option("--incognito", help="Use the agent's incognito session policy.")] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print answer SDP, expiry and timing metadata as JSON.")
    ] = False,
) -> None:
    cli: CliContext = ctx.obj
    try:
        offer = _read_offer(offer_sdp_file, offer_sdp_stdin)
        response = cli.call_with_refresh(
            lambda client: client.voice.start(agent_id, session_id=session_id, offer_sdp=offer, incognito=incognito)
        )
    except (GumloopError, ValidationError) as error:
        exit_with_error(error, json_output=json_output)
    if json_output:
        print_json(response)
    else:
        console.print("Voice session:", response.voice_session_id, markup=False, highlight=False)
        console.print("Answer SDP:", markup=False, highlight=False)
        console.print(response.answer_sdp, markup=False, highlight=False)


@voice_app.command("end")
def end_voice(
    ctx: typer.Context,
    agent_id: Annotated[str, typer.Argument(help="Agent that owns the voice session.")],
    voice_session_id: Annotated[str, typer.Argument(help="Voice session id returned by start.")],
    json_output: Annotated[bool, typer.Option("--json", help="Print the end request result as JSON.")] = False,
) -> None:
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.voice.end(agent_id, voice_session_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
    if json_output:
        print_json(response)
    else:
        console.print("Voice session is ending.")
