"""Ask before a command does something the user cannot undo."""

from __future__ import annotations

import sys

import questionary
import typer

from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.errors import exit_with_error


def can_ask() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def confirm_or_exit(*, warning: str, question: str, yes: bool, json_output: bool) -> None:
    """Return once --yes or a yes answer confirms the action; refuse it when nobody can answer."""
    if yes:
        return

    if json_output or not can_ask():
        exit_with_error(
            GumloopError(f"{warning} Nothing was sent. Pass --yes to confirm."),
            json_output=json_output,
        )

    console.print(warning, markup=False, highlight=False)
    if not questionary.confirm(question, default=False).ask():
        console.print("Cancelled; nothing was sent.")
        raise typer.Exit(1)
