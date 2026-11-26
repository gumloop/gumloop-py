from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.commands import _confirmation
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

AGENT_URL = f"{API_BASE}/agents/agent_1"
REQUEST_FILE = "<request file>"
REMOVAL_COMMANDS = [
    pytest.param(["agents", "delete", "agent_1"], None, id="delete"),
    pytest.param(["agents", "update", "agent_1", "--inactive"], None, id="inactive-flag"),
    pytest.param(["agents", "update", "agent_1", "--args-json", '{"is_active":false}'], None, id="args-json"),
    pytest.param(["agents", "update", "agent_1", "--args-file", REQUEST_FILE], None, id="args-file"),
    pytest.param(["agents", "update", "agent_1", "--args", "-"], '{"is_active":false}', id="args-stdin"),
    pytest.param(["agents", "update", "agent_1", "--args-json", '{"is_active":"false"}'], None, id="coerced-json"),
    pytest.param(
        ["agents", "update", "agent_1", "--args-json", '{"is_active":true}', "--inactive"], None, id="flag-over-json"
    ),
]


class _Question:
    def __init__(self, answer: bool | None) -> None:
        self._answer = answer

    def ask(self) -> bool | None:
        return self._answer


@pytest.fixture
def answer_in_terminal(monkeypatch: pytest.MonkeyPatch) -> Callable[[bool | None], list[tuple[str, bool]]]:
    """Run the command as if in a terminal where the person gives `answer`; returns the questions asked."""

    def _answer(answer: bool | None) -> list[tuple[str, bool]]:
        asked: list[tuple[str, bool]] = []

        def confirm(message: str, default: bool = True) -> _Question:
            asked.append((message, default))
            return _Question(answer)

        monkeypatch.setattr(_confirmation, "can_ask", lambda: True)
        monkeypatch.setattr(_confirmation.questionary, "confirm", confirm)
        return asked

    return _answer


@pytest.fixture
def agent_api(respx_mock: respx.MockRouter) -> respx.MockRouter:
    """A signed-in CLI and an API that accepts every request these commands can send for agent_1."""
    save_credentials(Credentials(api_key="key"))
    respx_mock.delete(AGENT_URL).respond(200, json={"agent_id": "agent_1", "deleted": True})
    respx_mock.patch(AGENT_URL).respond(200, json={"agent": {"id": "agent_1", "name": "Bot"}})
    respx_mock.patch(f"{AGENT_URL}/incognito").respond(200, json={"agent": {"id": "agent_1", "name": "Bot"}})
    return respx_mock


def _resolve(command: list[str], tmp_path: Path) -> list[str]:
    request_file = tmp_path / "request.json"
    request_file.write_text('{"is_active":false}', encoding="utf-8")
    return [str(request_file) if part == REQUEST_FILE else part for part in command]


def _text(output: str) -> str:
    return " ".join(output.split())


@pytest.mark.parametrize("command,stdin", REMOVAL_COMMANDS)
def test_removal_is_refused_without_a_terminal_unless_yes_is_passed(
    cli_runner: CliRunner, tmp_path: Path, agent_api: respx.MockRouter, command: list[str], stdin: str | None
) -> None:
    result = cli_runner.invoke(app, _resolve(command, tmp_path), input=stdin)

    assert result.exit_code == 1
    assert "Nothing was sent. Pass --yes to confirm." in _text(result.stderr)
    assert not agent_api.calls


@pytest.mark.parametrize("command,stdin", REMOVAL_COMMANDS)
def test_removal_with_json_is_refused_even_in_a_terminal(
    cli_runner: CliRunner,
    tmp_path: Path,
    agent_api: respx.MockRouter,
    answer_in_terminal: Callable[[bool | None], list[tuple[str, bool]]],
    command: list[str],
    stdin: str | None,
) -> None:
    asked = answer_in_terminal(True)

    result = cli_runner.invoke(app, [*_resolve(command, tmp_path), "--json"], input=stdin)

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["message"].endswith("Nothing was sent. Pass --yes to confirm.")
    assert result.stdout == ""
    assert asked == []
    assert not agent_api.calls


@pytest.mark.parametrize("answer", [False, None])
@pytest.mark.parametrize("command,stdin", REMOVAL_COMMANDS)
def test_removal_declined_in_a_terminal_sends_nothing(
    cli_runner: CliRunner,
    tmp_path: Path,
    agent_api: respx.MockRouter,
    answer_in_terminal: Callable[[bool | None], list[tuple[str, bool]]],
    command: list[str],
    stdin: str | None,
    answer: bool | None,
) -> None:
    asked = answer_in_terminal(answer)

    result = cli_runner.invoke(app, _resolve(command, tmp_path), input=stdin)

    assert result.exit_code == 1
    assert "Cancelled; nothing was sent." in result.output
    assert [default for _, default in asked] == [False]
    assert not agent_api.calls


@pytest.mark.parametrize("command,stdin", REMOVAL_COMMANDS)
def test_removal_confirmed_in_a_terminal_is_sent(
    cli_runner: CliRunner,
    tmp_path: Path,
    agent_api: respx.MockRouter,
    answer_in_terminal: Callable[[bool | None], list[tuple[str, bool]]],
    command: list[str],
    stdin: str | None,
) -> None:
    asked = answer_in_terminal(True)

    result = cli_runner.invoke(app, _resolve(command, tmp_path), input=stdin)

    assert result.exit_code == 0, result.output
    assert len(asked) == 1
    assert len(agent_api.calls) == 1


@pytest.mark.parametrize("yes", ["--yes", "-y"])
@pytest.mark.parametrize("output", [[], ["--json"]])
@pytest.mark.parametrize("command,stdin", REMOVAL_COMMANDS)
def test_yes_removes_the_agent_without_asking(
    cli_runner: CliRunner,
    tmp_path: Path,
    agent_api: respx.MockRouter,
    command: list[str],
    stdin: str | None,
    output: list[str],
    yes: str,
) -> None:
    result = cli_runner.invoke(app, [*_resolve(command, tmp_path), yes, *output], input=stdin)

    assert result.exit_code == 0, result.output
    assert len(agent_api.calls) == 1
    request = agent_api.calls[0].request
    assert request.method == "DELETE" or json.loads(request.content) == {"is_active": False}


def test_delete_question_says_it_cannot_be_undone(
    cli_runner: CliRunner,
    agent_api: respx.MockRouter,
    answer_in_terminal: Callable[[bool | None], list[tuple[str, bool]]],
) -> None:
    asked = answer_in_terminal(False)

    result = cli_runner.invoke(app, ["agents", "delete", "agent_1"])

    assert "This deletes agent agent_1. You cannot undo it" in _text(result.output)
    assert asked == [("Delete agent agent_1?", False)]


def test_inactive_question_says_it_is_not_a_pause_and_points_to_triggers(
    cli_runner: CliRunner,
    agent_api: respx.MockRouter,
    answer_in_terminal: Callable[[bool | None], list[tuple[str, bool]]],
) -> None:
    asked = answer_in_terminal(False)

    result = cli_runner.invoke(app, ["agents", "update", "agent_1", "--inactive"])

    warning = _text(result.output)
    assert "Marking agent agent_1 inactive removes it." in warning
    assert "This is not a pause, and --is-active cannot bring the agent back" in warning
    assert "turn off its triggers instead with `gumloop agents triggers update`" in warning
    assert asked == [("Remove agent agent_1?", False)]


def test_declined_inactive_does_not_change_incognito_either(
    cli_runner: CliRunner,
    agent_api: respx.MockRouter,
    answer_in_terminal: Callable[[bool | None], list[tuple[str, bool]]],
) -> None:
    answer_in_terminal(False)

    result = cli_runner.invoke(app, ["agents", "update", "agent_1", "--inactive", "--incognito"])

    assert result.exit_code == 1
    assert not agent_api.calls


@pytest.mark.parametrize(
    "options,sent",
    [
        (["--name", "Renamed"], {"name": "Renamed"}),
        (["--is-active"], {"is_active": True}),
        (["--args-json", '{"is_active":true}'], {"is_active": True}),
        (["--args-json", '{"is_active":false}', "--is-active"], {"is_active": True}),
    ],
)
def test_update_that_keeps_the_agent_is_sent_without_asking(
    cli_runner: CliRunner, agent_api: respx.MockRouter, options: list[str], sent: dict
) -> None:
    result = cli_runner.invoke(app, ["agents", "update", "agent_1", *options])

    assert result.exit_code == 0, result.output
    assert [json.loads(call.request.content) for call in agent_api.calls] == [sent]


def test_update_sends_the_team_id_option_in_place_of_a_request_json_team_id(
    cli_runner: CliRunner, agent_api: respx.MockRouter
) -> None:
    result = cli_runner.invoke(
        app,
        ["--team-id", "team_123", "agents", "update", "agent_1", "--args-json", '{"team_id":123,"name":"Renamed"}'],
    )

    assert result.exit_code == 0, result.output
    assert [json.loads(call.request.content) for call in agent_api.calls] == [
        {"team_id": "team_123", "name": "Renamed"}
    ]


@pytest.mark.parametrize("command", [["agents", "delete"], ["agents", "update"]])
def test_help_names_the_confirmation_flag(cli_runner: CliRunner, command: list[str]) -> None:
    result = cli_runner.invoke(app, [*command, "--help"])

    assert "--yes" in result.output
