from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE


@dataclass(frozen=True)
class DeleteCommand:
    argv: list[str]
    path: str
    response: dict | None
    warning: str
    question: str


DELETE_COMMANDS = [
    pytest.param(
        DeleteCommand(
            ["agents", "triggers", "delete", "agent_1", "trigger_1"],
            "agents/agent_1/triggers/trigger_1",
            {"agent_id": "agent_1", "trigger_id": "trigger_1", "deleted": True},
            "This deletes trigger trigger_1 from agent agent_1. You cannot undo it.",
            "Delete trigger trigger_1?",
        ),
        id="agent-trigger",
    ),
    pytest.param(
        DeleteCommand(
            ["artifacts", "delete", "artifact_1"],
            "artifacts/artifact_1",
            {"deleted": True},
            "This deletes artifact artifact_1. You cannot undo it.",
            "Delete artifact artifact_1?",
        ),
        id="artifact",
    ),
    pytest.param(
        DeleteCommand(
            ["brain", "sources", "delete", "src_1"],
            "brain/sources/src_1",
            {"deleted": True},
            "This deletes Brain source src_1 and every file in it. You cannot undo it.",
            "Delete Brain source src_1?",
        ),
        id="brain-source",
    ),
    pytest.param(
        DeleteCommand(
            ["brain", "files", "delete", "src_1", "file_1"],
            "brain/sources/src_1/files/file_1",
            {"deleted": True},
            "This deletes file file_1 from Brain source src_1 and from search. You cannot undo it.",
            "Delete file file_1?",
        ),
        id="brain-file",
    ),
    pytest.param(
        DeleteCommand(
            ["browser", "profiles", "delete", "profile_1"],
            "browser-profiles/profile_1",
            {"status": "success"},
            "This deletes browser profile profile_1 and its saved sign-ins. You cannot undo it.",
            "Delete browser profile profile_1?",
        ),
        id="browser-profile",
    ),
    pytest.param(
        DeleteCommand(
            ["evaluations", "delete", "eval_1"],
            "evaluations/eval_1",
            None,
            "This deletes evaluation eval_1. You cannot undo it.",
            "Delete evaluation eval_1?",
        ),
        id="evaluation",
    ),
    pytest.param(
        DeleteCommand(
            ["sessions", "queue", "delete", "session_1", "queued_1"],
            "sessions/session_1/queue/queued_1",
            {"queue": []},
            "This deletes queued message queued_1 from session session_1. You cannot undo it.",
            "Delete queued message queued_1?",
        ),
        id="queued-message",
    ),
    pytest.param(
        DeleteCommand(
            ["skills", "delete", "skill_1"],
            "skills/skill_1",
            {"deleted": True},
            "This deletes skill skill_1. You cannot undo it.",
            "Delete skill skill_1?",
        ),
        id="skill",
    ),
]


@pytest.fixture
def delete_route(respx_mock: respx.MockRouter, command: DeleteCommand) -> respx.Route:
    """A signed-in CLI and an API that accepts the DELETE this command sends."""
    save_credentials(Credentials(api_key="key"))
    route = respx_mock.delete(f"{API_BASE}/{command.path}")
    if command.response is None:
        return route.respond(204)
    return route.respond(200, json=command.response)


def _text(output: str) -> str:
    return " ".join(output.split())


@pytest.mark.parametrize("command", DELETE_COMMANDS)
def test_delete_is_refused_without_a_terminal_unless_yes_is_passed(
    cli_runner: CliRunner, delete_route: respx.Route, command: DeleteCommand
) -> None:
    result = cli_runner.invoke(app, command.argv)

    assert result.exit_code == 1
    assert f"{command.warning} Nothing was sent. Pass --yes to confirm." in _text(result.stderr)
    assert not delete_route.calls


@pytest.mark.parametrize("command", DELETE_COMMANDS)
def test_delete_with_json_is_refused_even_in_a_terminal(
    cli_runner: CliRunner,
    delete_route: respx.Route,
    answer_in_terminal: Callable[[bool | None], list[tuple[str, bool]]],
    command: DeleteCommand,
) -> None:
    asked = answer_in_terminal(True)

    result = cli_runner.invoke(app, [*command.argv, "--json"])

    assert result.exit_code == 1
    message = json.loads(result.stderr)["error"]["message"]
    assert message == f"{command.warning} Nothing was sent. Pass --yes to confirm."
    assert result.stdout == ""
    assert asked == []
    assert not delete_route.calls


@pytest.mark.parametrize("answer", [False, None])
@pytest.mark.parametrize("command", DELETE_COMMANDS)
def test_delete_declined_in_a_terminal_sends_nothing(
    cli_runner: CliRunner,
    delete_route: respx.Route,
    answer_in_terminal: Callable[[bool | None], list[tuple[str, bool]]],
    command: DeleteCommand,
    answer: bool | None,
) -> None:
    asked = answer_in_terminal(answer)

    result = cli_runner.invoke(app, command.argv)

    assert result.exit_code == 1
    assert command.warning in _text(result.output)
    assert "Cancelled; nothing was sent." in result.output
    assert asked == [(command.question, False)]
    assert not delete_route.calls


@pytest.mark.parametrize("command", DELETE_COMMANDS)
def test_delete_confirmed_in_a_terminal_is_sent(
    cli_runner: CliRunner,
    delete_route: respx.Route,
    answer_in_terminal: Callable[[bool | None], list[tuple[str, bool]]],
    command: DeleteCommand,
) -> None:
    asked = answer_in_terminal(True)

    result = cli_runner.invoke(app, command.argv)

    assert result.exit_code == 0, result.output
    assert asked == [(command.question, False)]
    assert len(delete_route.calls) == 1


@pytest.mark.parametrize("yes", ["--yes", "-y"])
@pytest.mark.parametrize("output", [[], ["--json"]])
@pytest.mark.parametrize("command", DELETE_COMMANDS)
def test_yes_deletes_without_asking(
    cli_runner: CliRunner, delete_route: respx.Route, command: DeleteCommand, output: list[str], yes: str
) -> None:
    result = cli_runner.invoke(app, [*command.argv, yes, *output])

    assert result.exit_code == 0, result.output
    assert len(delete_route.calls) == 1


@pytest.mark.parametrize("command", DELETE_COMMANDS)
def test_delete_help_names_the_confirmation_flag(cli_runner: CliRunner, command: DeleteCommand) -> None:
    subcommand = command.argv[: command.argv.index("delete") + 1]

    result = cli_runner.invoke(app, [*subcommand, "--help"])

    assert "--yes" in result.output
