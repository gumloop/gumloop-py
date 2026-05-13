from __future__ import annotations

from typing import Any
from typing import NoReturn

import typer

from gumloop import APIStatusError
from gumloop import AuthenticationError
from gumloop import GumloopError
from gumloop.cli.console import error_console
from gumloop.cli.console import print_json_error


def exit_with_error(error: Exception, *, json_output: bool = False) -> NoReturn:
    if isinstance(error, AuthenticationError):
        message = "Not authenticated. Run `gumloop login` to sign in."
        payload: dict[str, Any] = {"error": {"message": message, "type": "authentication_error"}}
    elif isinstance(error, APIStatusError):
        message = str(error)
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
    elif isinstance(error, GumloopError):
        message = str(error)
        payload = {"error": {"message": message, "type": "gumloop_error"}}
    else:
        message = str(error) or error.__class__.__name__
        payload = {"error": {"message": message, "type": "cli_error"}}

    if json_output:
        print_json_error(payload)
    else:
        error_console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(1)
