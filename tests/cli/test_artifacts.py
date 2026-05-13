from __future__ import annotations

from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

_FAKE_DOWNLOAD_URL = "https://signed.example.com/artifacts/artifact_abc/payload"


@respx.mock
def test_artifacts_list_calls_per_agent_endpoint_with_pagination(cli_runner: CliRunner) -> None:
    route = respx.get(f"{API_BASE}/agents/agent_xyz/artifacts").mock(
        return_value=httpx.Response(200, json={"artifacts": [], "next_cursor": None})
    )
    save_credentials(Credentials(api_key="key"))

    cli_runner.invoke(
        app,
        ["artifacts", "list", "agent_xyz", "--limit", "10", "--cursor", "abc", "--json"],
    )

    params = route.calls[0].request.url.params
    assert params["page_size"] == "10"
    assert params["cursor"] == "abc"


@respx.mock
def test_artifacts_list_requires_agent_id_positional(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["artifacts", "list", "--json"])

    assert result.exit_code != 0


@respx.mock
def test_artifacts_download_streams_bytes_to_output_path(cli_runner: CliRunner, tmp_path: Path) -> None:
    body = b"artifact-binary-content"
    respx.get(f"{API_BASE}/artifacts/artifact_abc/download").mock(
        return_value=httpx.Response(
            200,
            json={"download_url": _FAKE_DOWNLOAD_URL, "filename": "report.pdf", "media_type": "application/pdf"},
        )
    )
    respx.get(_FAKE_DOWNLOAD_URL).mock(return_value=httpx.Response(200, content=body))
    save_credentials(Credentials(api_key="key"))

    target = tmp_path / "out.pdf"
    result = cli_runner.invoke(app, ["artifacts", "download", "artifact_abc", "-o", str(target), "--json"])

    assert result.exit_code == 0, result.output
    assert target.read_bytes() == body


@respx.mock
def test_artifacts_download_with_directory_output_uses_server_filename(cli_runner: CliRunner, tmp_path: Path) -> None:
    body = b"hello"
    respx.get(f"{API_BASE}/artifacts/artifact_abc/download").mock(
        return_value=httpx.Response(200, json={"download_url": _FAKE_DOWNLOAD_URL, "filename": "from-server.bin"})
    )
    respx.get(_FAKE_DOWNLOAD_URL).mock(return_value=httpx.Response(200, content=body))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["artifacts", "download", "artifact_abc", "-o", str(tmp_path) + "/", "--json"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "from-server.bin").read_bytes() == body
