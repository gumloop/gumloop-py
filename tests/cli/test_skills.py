from __future__ import annotations

from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

_FAKE_DOWNLOAD_URL = "https://signed.example.com/skills/skill_abc/payload"


@respx.mock
def test_skills_list_uses_filters_and_pagination(cli_runner: CliRunner) -> None:
    route = respx.get(f"{API_BASE}/skills").mock(
        return_value=httpx.Response(200, json={"skills": [], "next_cursor": None})
    )
    save_credentials(Credentials(api_key="key"))

    cli_runner.invoke(app, ["skills", "list", "--search", "retrieval", "--limit", "25", "--json"])

    params = route.calls[0].request.url.params
    assert params["search_query"] == "retrieval"
    assert params["page_size"] == "25"


@respx.mock
def test_skills_create_uploads_real_file_contents(cli_runner: CliRunner, tmp_path: Path) -> None:
    skill = tmp_path / "my-skill.md"
    skill.write_text("# A real skill\n\nbody text")
    route = respx.post(f"{API_BASE}/skills").mock(
        return_value=httpx.Response(
            201, json={"skill": {"id": "skill_abc", "name": "my-skill", "description": "", "team_id": "team_abc"}}
        )
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["skills", "create", str(skill), "--json"])

    assert result.exit_code == 0, result.output
    body = route.calls[0].request.content
    assert b"# A real skill" in body
    assert b"my-skill.md" in body


@respx.mock
def test_skills_create_rejects_missing_file(cli_runner: CliRunner, tmp_path: Path) -> None:
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["skills", "create", str(tmp_path / "missing.md"), "--json"])

    assert result.exit_code != 0


@respx.mock
def test_skills_update_posts_to_per_skill_endpoint(cli_runner: CliRunner, tmp_path: Path) -> None:
    skill = tmp_path / "skill.md"
    skill.write_text("new")
    route = respx.patch(f"{API_BASE}/skills/skill_abc").mock(
        return_value=httpx.Response(
            200, json={"skill": {"id": "skill_abc", "name": "my-skill", "description": "", "team_id": "team_abc"}}
        )
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["skills", "update", "skill_abc", str(skill), "--json"])

    assert result.exit_code == 0, result.output
    assert route.called


@respx.mock
def test_skills_delete_calls_per_skill_endpoint(cli_runner: CliRunner) -> None:
    route = respx.delete(f"{API_BASE}/skills/skill_abc").mock(return_value=httpx.Response(200, json={"deleted": True}))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["skills", "delete", "skill_abc", "--json"])

    assert result.exit_code == 0, result.output
    assert route.called
    assert '"deleted": true' in result.output


@respx.mock
def test_skills_download_streams_signed_url_bytes_to_output_path(cli_runner: CliRunner, tmp_path: Path) -> None:
    download_body = b"streamed-skill-bytes"
    respx.get(f"{API_BASE}/skills/skill_abc/download").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "skill_abc",
                "download_url": _FAKE_DOWNLOAD_URL,
                "filename": "skill.zip",
                "media_type": "application/zip",
            },
        )
    )
    respx.get(_FAKE_DOWNLOAD_URL).mock(return_value=httpx.Response(200, content=download_body))
    save_credentials(Credentials(api_key="key"))

    out = tmp_path / "saved.md"
    result = cli_runner.invoke(app, ["skills", "download", "skill_abc", "-o", str(out), "--json"])

    assert result.exit_code == 0, result.output
    assert out.read_bytes() == download_body


@respx.mock
def test_skills_download_streams_to_stdout_when_output_is_dash(cli_runner: CliRunner) -> None:
    download_body = b"stdout-bytes"
    respx.get(f"{API_BASE}/skills/skill_abc/download").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "skill_abc",
                "download_url": _FAKE_DOWNLOAD_URL,
                "filename": "skill.zip",
                "media_type": "application/zip",
            },
        )
    )
    respx.get(_FAKE_DOWNLOAD_URL).mock(return_value=httpx.Response(200, content=download_body))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["skills", "download", "skill_abc", "-o", "-"])

    assert result.exit_code == 0, result.output
    assert "stdout-bytes" in result.output


@respx.mock
def test_skills_download_with_directory_output_uses_server_filename(cli_runner: CliRunner, tmp_path: Path) -> None:
    body = b"named-by-server"
    respx.get(f"{API_BASE}/skills/skill_abc/download").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "skill_abc",
                "download_url": _FAKE_DOWNLOAD_URL,
                "filename": "actual-name.zip",
                "media_type": "application/zip",
            },
        )
    )
    respx.get(_FAKE_DOWNLOAD_URL).mock(return_value=httpx.Response(200, content=body))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["skills", "download", "skill_abc", "-o", str(tmp_path) + "/", "--json"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "actual-name.zip").read_bytes() == body
