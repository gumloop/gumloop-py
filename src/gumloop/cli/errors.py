from __future__ import annotations

from typing import Any
from typing import NoReturn

import typer
from rich.markup import escape as escape_markup

from gumloop import APIStatusError
from gumloop import AuthenticationError
from gumloop import GumloopError
from gumloop.cli.console import error_console
from gumloop.cli.console import print_json_error

# A set of backend error codes whose raw string tells the user nothing actionable.
# This lookup is used to provide a more helpful hint in the CLI output.
# Keyed on the flat {"error": "<code>"} body the API returns.
_ERROR_HINTS = {
    "tier_required_pro": (
        "This account needs the Pro plan or higher. Commands will keep failing "
        "until it is upgraded at https://www.gumloop.com/pricing -- or ask a "
        "workspace admin to upgrade it."
    ),
}


def api_error_hint(error: APIStatusError) -> str | None:
    """Return a plain-language explanation for a known backend error code.

    Some endpoints refuse a request with a bare code such as
    ``tier_required_pro`` and no actionable message, leaving the CLI
    nothing to show but an HTTP status.

    Args:
        error: The API failure to explain.

    Returns:
        A friendly message telling the user what went wrong and how to
        fix it. Returns nothing if we do not have a message for this
        error, and the caller shows the original error instead.
    """
    code = error.code or (error.error if isinstance(error.error, str) else None)
    return _ERROR_HINTS.get(code or "")


def exit_with_error(error: Exception, *, json_output: bool = False) -> NoReturn:
    if isinstance(error, AuthenticationError):
        message = "Not authenticated. Run `gumloop login` to sign in."
        payload: dict[str, Any] = {"error": {"message": message, "type": "authentication_error"}}
    elif isinstance(error, APIStatusError):
        message = str(error)
        hint = api_error_hint(error)
        payload = {
            "error": {
                "message": message,
                "status_code": error.status_code,
                "code": error.code,
                "type": error.type,
                "param": error.param,
                "details": error.details,
            }
        }
        if hint:
            payload["error"]["hint"] = hint
            message = hint
    elif isinstance(error, GumloopError):
        message = str(error)
        payload = {"error": {"message": message, "type": "gumloop_error"}}
    else:
        message = str(error) or error.__class__.__name__
        payload = {"error": {"message": message, "type": "cli_error"}}

    if json_output:
        print_json_error(payload)
    else:
        # message can include server-supplied text (e.g. APIStatusError body);
        # escape it so a crafted response can't render terminal hyperlinks
        # through the [red]Error:[/red] framing print.
        error_console.print(f"[red]Error:[/red] {escape_markup(message)}")
    raise typer.Exit(1)
