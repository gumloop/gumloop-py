from __future__ import annotations

# pyright: reportTypedDictNotRequiredAccess=false
import asyncio

import httpx
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE


@respx.mock
def test_skills_list_forwards_set_filters_and_drops_unset_ones(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/skills").mock(
        return_value=httpx.Response(200, json={"skills": [{"id": "skill_123"}], "next_cursor": "abc"})
    )

    result = client.skills.list(
        team_id="team_123",
        search_query="retrieval",
        page_size=25,
        cursor="prev",
        related_server_id="gmail",
    )

    assert result == {"skills": [{"id": "skill_123"}], "next_cursor": "abc"}
    params = route.calls[0].request.url.params
    assert params["team_id"] == "team_123"
    assert params["search_query"] == "retrieval"
    assert params["page_size"] == "25"
    assert params["cursor"] == "prev"
    assert params["related_server_id"] == "gmail"
    # Unset filters must not appear as ``=None`` in the URL.
    assert "sort_order" not in params
    assert "creator_user_id" not in params
    assert "gummie_id" not in params
    assert "unused" not in params


@respx.mock
def test_skills_create_posts_multipart_with_files_and_team_id(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/skills").mock(
        return_value=httpx.Response(201, json={"skill": {"id": "skill_123", "name": "my-skill"}})
    )

    result = client.skills.create(
        [("my-skill.md", b"# A real skill\nbody text", "text/markdown")],
        team_id="team_123",
    )

    assert result["skill"]["id"] == "skill_123"
    body = route.calls[0].request.content
    assert b"# A real skill" in body
    assert b"my-skill.md" in body
    assert b"team_123" in body
    assert route.calls[0].request.headers["content-type"].startswith("multipart/form-data")


@respx.mock
def test_skills_create_accepts_mapping_form_of_files(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/skills").mock(return_value=httpx.Response(201, json={"skill": {"id": "skill_abc"}}))

    client.skills.create({"a.md": b"alpha", "b.md": b"beta"})

    body = route.calls[0].request.content
    assert b"alpha" in body
    assert b"beta" in body
    assert b"a.md" in body
    assert b"b.md" in body


@respx.mock
def test_skills_update_patches_per_skill_endpoint_with_multipart(client: Gumloop) -> None:
    route = respx.patch(f"{API_BASE}/skills/skill_abc").mock(
        return_value=httpx.Response(200, json={"skill": {"id": "skill_abc"}})
    )

    result = client.skills.update("skill_abc", [("v2.md", b"new content")])

    assert result["skill"]["id"] == "skill_abc"
    body = route.calls[0].request.content
    assert b"new content" in body
    assert b"v2.md" in body
    assert route.calls[0].request.headers["content-type"].startswith("multipart/form-data")


@respx.mock
def test_skills_download_forwards_version_id_query_param(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/skills/skill_abc/download").mock(
        return_value=httpx.Response(
            200,
            json={
                "download_url": "https://signed.example/skill.zip",
                "filename": "skill.zip",
                "media_type": "application/zip",
                "id": "skill_abc",
            },
        )
    )

    result = client.skills.download("skill_abc", version_id="v_42")

    assert result["download_url"] == "https://signed.example/skill.zip"
    assert route.calls[0].request.url.params["version_id"] == "v_42"

    client.skills.download("skill_abc")
    assert "version_id" not in route.calls[1].request.url.params


@respx.mock
def test_async_skills_methods() -> None:
    respx.get(f"{API_BASE}/skills").mock(return_value=httpx.Response(200, json={"skills": [], "next_cursor": None}))
    respx.post(f"{API_BASE}/skills").mock(return_value=httpx.Response(201, json={"skill": {"id": "skill_abc"}}))
    respx.patch(f"{API_BASE}/skills/skill_abc").mock(
        return_value=httpx.Response(200, json={"skill": {"id": "skill_abc"}})
    )
    respx.get(f"{API_BASE}/skills/skill_abc/download").mock(
        return_value=httpx.Response(
            200,
            json={
                "download_url": "https://signed.example/skill.zip",
                "filename": "skill.zip",
                "media_type": "application/zip",
                "id": "skill_abc",
            },
        )
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            assert (await client.skills.list(search_query="foo"))["skills"] == []
            created = await client.skills.create([("s.md", b"body")], team_id="team_123")
            assert created["skill"]["id"] == "skill_abc"
            updated = await client.skills.update("skill_abc", [("s.md", b"body2")])
            assert updated["skill"]["id"] == "skill_abc"
            downloaded = await client.skills.download("skill_abc", version_id="v_1")
            assert downloaded["download_url"] == "https://signed.example/skill.zip"

    asyncio.run(run())
