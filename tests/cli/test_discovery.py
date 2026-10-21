from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE


@pytest.mark.parametrize("group", ["teams", "organizations"])
@pytest.mark.parametrize("json_output", [False, True])
@respx.mock
def test_discovery_lists_ids_and_names(cli_runner: CliRunner, group: str, json_output: bool) -> None:
    save_credentials(Credentials(api_key="key"))
    payload = {group: [{"id": "scope-1", "name": "[Ops]"}, {"id": "scope-2", "name": "Support"}]}
    respx.get(f"{API_BASE}/{group}").mock(return_value=httpx.Response(200, json=payload))

    result = cli_runner.invoke(app, [group, "list", *(["--json"] if json_output else [])])

    assert result.exit_code == 0, result.output
    if json_output:
        assert json.loads(result.output) == payload
    else:
        assert "scope-1" in result.output
        assert "[Ops]" in result.output
        assert "scope-2" in result.output


@pytest.mark.parametrize("group", ["teams", "organizations"])
@respx.mock
def test_discovery_empty_membership(cli_runner: CliRunner, group: str) -> None:
    save_credentials(Credentials(api_key="key"))
    respx.get(f"{API_BASE}/{group}").mock(return_value=httpx.Response(200, json={group: []}))
    result = cli_runner.invoke(app, [group, "list"])
    assert result.exit_code == 0, result.output
    assert f"No {group} found." in result.output


@respx.mock
def test_discovery_organization_without_name(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    respx.get(f"{API_BASE}/organizations").mock(
        return_value=httpx.Response(200, json={"organizations": [{"id": "org-1", "name": None}]})
    )
    result = cli_runner.invoke(app, ["organizations", "list"])
    assert result.exit_code == 0, result.output
    assert "org-1" in result.output
    assert "None" not in result.output


@pytest.mark.parametrize("group", ["teams", "organizations"])
@respx.mock
def test_discovery_permission_error(cli_runner: CliRunner, group: str) -> None:
    save_credentials(Credentials(api_key="key"))
    respx.get(f"{API_BASE}/{group}").mock(
        return_value=httpx.Response(403, json={"error": {"code": "forbidden", "message": "Access denied"}})
    )
    result = cli_runner.invoke(app, [group, "list", "--json"])
    assert result.exit_code != 0
    assert "Access denied" in result.output
