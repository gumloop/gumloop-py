from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated
from typing import Any

import typer

from gumloop import GumloopError
from gumloop.cli.commands._args_input import resolve_json_args
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.spec import ChatStreamChunk

chat_app = typer.Typer(
    help="Chat completions.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
completions_app = typer.Typer(
    help="Create chat completions.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
chat_app.add_typer(completions_app, name="completions")


_EPILOG = (
    "Examples:\n"
    '  gumloop chat completions create "ping" -m claude-sonnet-4-5\n'
    '  echo "summarize" | gumloop chat completions create -m gpt-4o-mini --message-stdin -\n'
    '  gumloop chat completions create "x" -m claude-haiku-4-5 --json\n'
    '  gumloop chat completions create "stream me" -m claude-sonnet-4-5 --stream --json    # ndjson\n'
    '  gumloop chat completions create "image please" -m gemini-2.5-flash-image \\\n'
    "      --modality image --modality text --json\n"
    "\n"
    "This command mirrors the Python SDK call `client.chat.completions.create(...)`\n"
    "using --args-file/--args-json/--args - for full structured requests.\n"
    "Every flag maps to the matching SDK kwarg (e.g. --modality -> modalities,\n"
    "--max-completion-tokens -> max_completion_tokens). Output streams when stdout\n"
    "is a TTY and the request supports it; pass --stream or --no-stream to be\n"
    "explicit."
)


@completions_app.command("create", epilog=_EPILOG)
def create_completion(
    ctx: typer.Context,
    prompt: Annotated[
        str | None,
        typer.Argument(help="User message. Pass --message-stdin - to read from stdin instead."),
    ] = None,
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="Model slug, e.g. claude-sonnet-4-5."),
    ] = "",
    system: Annotated[
        list[str] | None,
        typer.Option("--system", "-s", help="System message prepended to the conversation. Repeatable."),
    ] = None,
    message_stdin: Annotated[
        str | None,
        typer.Option("--message-stdin", help="Use '-' to read the user message from stdin.", metavar="-"),
    ] = None,
    args_json: Annotated[str | None, typer.Option("--args-json", help="Full chat request as a JSON object.")] = None,
    args_file: Annotated[
        str | None, typer.Option("--args-file", help="File containing the full chat request JSON.")
    ] = None,
    args: Annotated[str | None, typer.Option("--args", help="Use '-' to read request JSON from stdin.")] = None,
    max_completion_tokens: Annotated[
        int | None,
        typer.Option(
            "--max-completion-tokens",
            help="Cap on completion tokens. SDK-aligned name; maps to max_completion_tokens.",
        ),
    ] = None,
    max_tokens: Annotated[
        int | None,
        typer.Option(
            "--max-tokens",
            help="Legacy alias for --max-completion-tokens. Same wire field.",
            hidden=True,
        ),
    ] = None,
    temperature: Annotated[
        float | None,
        typer.Option("--temperature", help="Sampling temperature."),
    ] = None,
    modality: Annotated[
        list[str] | None,
        typer.Option(
            "--modality",
            help="Modality to request. Repeatable (e.g. --modality image --modality text). Maps to `modalities`.",
        ),
    ] = None,
    schema_file: Annotated[
        Path | None,
        typer.Option(
            "--schema-file",
            help="Path to a JSON Schema file. Sent as response_format={type:json_schema,...}.",
        ),
    ] = None,
    schema_name: Annotated[
        str,
        typer.Option("--schema-name", help="json_schema.name field (paired with --schema-file)."),
    ] = "schema",
    stream: Annotated[
        bool,
        typer.Option("--stream", help="Force streaming output (always wins over TTY auto-detect)."),
    ] = False,
    no_stream: Annotated[
        bool,
        typer.Option("--no-stream", help="Wait for the full response then print. Always wins over TTY auto-detect."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json", help="Print the response as JSON. Streaming + --json emits ndjson (one chunk per line)."
        ),
    ] = False,
) -> None:
    """Create a chat completion."""
    cli: CliContext = ctx.obj

    try:
        if prompt is not None and message_stdin is not None:
            raise GumloopError("Pass at most one of PROMPT or --message-stdin.")
        if message_stdin is not None and message_stdin != "-":
            raise GumloopError("--message-stdin only accepts '-' (reads from stdin).")
        if stream and no_stream:
            raise GumloopError("Pass at most one of --stream and --no-stream.")
        if max_tokens is not None and max_completion_tokens is not None:
            raise GumloopError("Pass at most one of --max-tokens and --max-completion-tokens.")

        structured = any(value is not None for value in (args_json, args_file, args))
        if structured and (prompt is not None or message_stdin is not None or system is not None):
            raise GumloopError("Pass structured request JSON or PROMPT/--message-stdin/--system, not both.")
        kwargs = resolve_json_args(inline=args_json, file_path=args_file, stdin_marker=args)
        if not structured:
            user_message = sys.stdin.read() if message_stdin == "-" else prompt
            if not user_message:
                raise GumloopError("Pass a PROMPT, --message-stdin -, or structured request JSON with messages.")
            messages: list[dict[str, Any]] = [{"role": "system", "content": s} for s in (system or [])]
            messages.append({"role": "user", "content": user_message})
            kwargs["messages"] = messages
        if model:
            kwargs["model"] = model
        if not kwargs.get("model"):
            raise GumloopError("Pass --model / -m or a model in the request JSON.")
        if "stream" in kwargs and not isinstance(kwargs["stream"], bool):
            raise GumloopError("The request's stream field must be true or false.")

        # Stream resolution: explicit flags always win; --json without --stream
        # implies unary so machine output is byte-stable; otherwise stream-when-TTY.
        if stream:
            should_stream = True
        elif no_stream:
            should_stream = False
        elif "stream" in kwargs:
            should_stream = kwargs["stream"]
        elif json_output:
            should_stream = False
        else:
            should_stream = _stdout_is_tty()

        token_cap = max_completion_tokens if max_completion_tokens is not None else max_tokens
        if token_cap is not None:
            kwargs["max_completion_tokens"] = token_cap
        if temperature is not None:
            kwargs["temperature"] = temperature
        if modality:
            kwargs["modalities"] = modality
        if schema_file is not None:
            schema = resolve_json_args(inline=None, file_path=str(schema_file), stdin_marker=None, allow_empty=False)
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            }

        if should_stream:
            kwargs["stream"] = True
            stream_iter: Iterator[ChatStreamChunk] = cli.call_with_refresh(
                lambda client: client.chat.completions.create(**kwargs)
            )
            image_notice_emitted = False
            for chunk in stream_iter:
                image_notice_emitted = _emit_stream_chunk(
                    chunk, json_mode=json_output, image_notice_emitted=image_notice_emitted
                )
            if not json_output:
                console.print()  # trailing newline to separate the prompt that follows
            return

        kwargs.pop("stream", None)
        result = cli.call_with_refresh(lambda client: client.chat.completions.create(**kwargs))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(result)
        return

    for choice in result.choices:
        content = choice.message.content
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        if content:
            console.print(content, markup=False, highlight=False)
        if isinstance(choice.message.images, list) and choice.message.images:
            console.print(
                "Generated image available. Use --json to retrieve the image data.", markup=False, highlight=False
            )


def _stdout_is_tty() -> bool:
    # Wrapped so tests can monkeypatch; CliRunner replaces ``sys.stdout`` with
    # a buffer whose ``isatty()`` always returns False, which would always
    # collapse the streaming branch.
    return sys.stdout.isatty()


def _emit_stream_chunk(
    chunk: ChatStreamChunk, *, json_mode: bool = False, image_notice_emitted: bool = False
) -> bool:
    if json_mode:
        # ndjson: one chunk per line, by_alias so wire field names match the SDK.
        sys.stdout.write(chunk.model_dump_json(by_alias=True) + "\n")
        sys.stdout.flush()
        return image_notice_emitted
    for choice in chunk.choices:
        piece = getattr(choice.delta, "content", None)
        if piece:
            # markup=False so output containing [brackets] doesn't trip Rich.
            console.print(piece, end="", markup=False, highlight=False)
        if not image_notice_emitted and isinstance(choice.delta.images, list) and choice.delta.images:
            console.print(
                "\nGenerated image available. Use --json to retrieve the image data.", markup=False, highlight=False
            )
            image_notice_emitted = True
    return image_notice_emitted
