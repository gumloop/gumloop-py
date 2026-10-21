from __future__ import annotations

import json

import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE
from tests.sdk.test_organization_admin import ROLE


@pytest.mark.parametrize("flags,expected", [(["--clear"], None), (["--monthly-credit-limit", "0"], 0)])
@respx.mock
def test_cli_credit_limit_clear_and_zero(cli_runner: CliRunner, flags: list[str], expected: int | None) -> None:
    save_credentials(Credentials(api_key="key"))
    route = respx.put(f"{API_BASE}/organizations/org/roles/role/credit-limit").respond(200, json=ROLE)
    result = cli_runner.invoke(app, ["organizations", "roles", "set", "org", "role", *flags, "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content)["monthly_credit_limit"] == expected


@pytest.mark.parametrize("flags", [[], ["--clear", "--monthly-credit-limit", "10"]])
def test_cli_credit_limit_requires_explicit_choice(cli_runner: CliRunner, flags: list[str]) -> None:
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["organizations", "roles", "set", "org", "role", *flags, "--json"])
    assert result.exit_code != 0
    assert "exactly one" in result.output


@respx.mock
def test_cli_audit_filters_and_permission_error(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    route = respx.get(f"{API_BASE}/get_audit_logs").respond(
        403, json={"error": "insufficient_organization_permissions"}
    )
    result = cli_runner.invoke(
        app,
        [
            "organizations",
            "audit-logs",
            "org",
            "start",
            "end",
            "--filter-user-id",
            "a",
            "--filter-user-id",
            "b",
            "--json",
        ],
    )
    assert result.exit_code != 0
    assert "insufficient_organization_permissions" in result.output
    assert route.calls[0].request.url.params["user_ids"] == "a,b"


@respx.mock
def test_cli_export_json_stdin(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    route = respx.post(f"{API_BASE}/export_data").respond(200, json={"data_export_id": "temporary", "state": "PENDING"})
    request = {
        "start_date": "start",
        "end_date": "end",
        "export_fields": ["name"],
        "data_type": "agents",
        "export_scope": "personal",
        "entity_ids": ["temporary-agent"],
    }
    result = cli_runner.invoke(
        app, ["organizations", "exports", "create", "--args", "-", "--json"], input=json.dumps(request)
    )
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content)["export_scope"] == "personal"
