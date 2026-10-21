from __future__ import annotations

import asyncio
import json

import pytest
import respx
from pydantic import ValidationError

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.types import DataExportDownload
from gumloop.types import DataExportRequest
from tests.sdk.helpers import API_BASE

ROLE = {"role_id": "role", "role_name": "Test", "is_default": False, "member_count": 0, "monthly_credit_limit": None}


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_empty_audit_filters_are_omitted(asynchronous: bool) -> None:
    route = respx.get(f"{API_BASE}/get_audit_logs").respond(
        200, json={"audit_logs": [], "total_count": 0, "page": 1, "page_size": 50, "total_pages": 0}
    )

    async def run() -> None:
        async with AsyncGumloop(api_key="key", user_id="actor") as client:
            await client.organizations.audit_logs(
                "org",
                start_time="start",
                end_time="end",
                event_types=[],
                user_ids=[],
                ip_addresses=[],
                workspace_ids=[],
                entity_ids=[],
            )

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor") as client:
            client.organizations.audit_logs(
                "org",
                start_time="start",
                end_time="end",
                event_types=[],
                user_ids=[],
                ip_addresses=[],
                workspace_ids=[],
                entity_ids=[],
            )
    params = dict(route.calls[0].request.url.params)
    assert params == {
        "organization_id": "org",
        "start_time": "start",
        "end_time": "end",
        "page": "1",
        "page_size": "50",
    }


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_role_limits_pagination_and_clear(asynchronous: bool) -> None:
    listing = respx.get(f"{API_BASE}/organizations/org/roles/credit-limits").respond(
        200, json={"roles": [ROLE], "next_cursor": "next"}
    )
    detail = respx.get(f"{API_BASE}/organizations/org/roles/role/credit-limit").respond(200, json=ROLE)
    update = respx.put(f"{API_BASE}/organizations/org/roles/role/credit-limit").respond(200, json=ROLE)

    async def run() -> None:
        async with AsyncGumloop(api_key="key", user_id="actor") as client:
            assert (await client.organizations.list_role_credit_limits("org", cursor="previous")).next_cursor == "next"
            assert (await client.organizations.get_role_credit_limit("org", "role")).role_name == "Test"
            assert (await client.organizations.set_role_credit_limit("org", "role", None)).monthly_credit_limit is None

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor") as client:
            assert client.organizations.list_role_credit_limits("org", cursor="previous").next_cursor == "next"
            assert client.organizations.get_role_credit_limit("org", "role").role_name == "Test"
            assert client.organizations.set_role_credit_limit("org", "role", None).monthly_credit_limit is None
    assert listing.calls[0].request.url.params["cursor"] == "previous"
    assert detail.called
    assert json.loads(update.calls[0].request.content) == {"monthly_credit_limit": None}
    assert update.calls[0].request.headers["x-auth-key"] == "actor"


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_admin_scoped_wire_contract(asynchronous: bool) -> None:
    audit = respx.get(f"{API_BASE}/get_audit_logs").respond(
        200,
        json={
            "audit_logs": [{"event_type": "test", "metadata": {"new_field": True}}],
            "total_count": 1,
            "page": 2,
            "page_size": 3,
            "total_pages": 4,
        },
    )
    workspace = respx.post(f"{API_BASE}/manage_workspace_users").respond(200, json={"success": True, "message": "ok"})
    role = respx.post(f"{API_BASE}/manage_permission_group_users").respond(200, json={"success": True, "message": "ok"})
    export = respx.post(f"{API_BASE}/export_data").respond(200, json={"data_export_id": "export", "state": "PENDING"})
    status = respx.get(f"{API_BASE}/export_status").respond(
        200, json={"download_url": "https://storage.example/export.csv", "file_name": "export.csv"}
    )
    request = DataExportRequest(
        start_date="2026-01-01",
        end_date="2026-01-02",
        export_fields=["name"],
        export_scope="personal",
        data_type="agents",
        entity_ids=["temporary-agent"],
    )

    async def run() -> None:
        async with AsyncGumloop(api_key="key", user_id="actor") as client:
            result = await client.organizations.audit_logs(
                "org",
                start_time="start",
                end_time="end",
                page=2,
                page_size=3,
                user_ids=["a", "b"],
                event_types=["test"],
            )
            assert result.audit_logs[0]["metadata"]["new_field"] is True
            await client.organizations.manage_workspace_user("org", "workspace", "test@example.com", action="add")
            await client.organizations.manage_role_user("org", "role", "test@example.com", action="remove")
            assert (await client.organizations.export_data(request)).state == "PENDING"
            assert isinstance(await client.organizations.export_status("export", download_url=True), DataExportDownload)

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor") as client:
            result = client.organizations.audit_logs(
                "org",
                start_time="start",
                end_time="end",
                page=2,
                page_size=3,
                user_ids=["a", "b"],
                event_types=["test"],
            )
            assert result.audit_logs[0]["metadata"]["new_field"] is True
            client.organizations.manage_workspace_user("org", "workspace", "test@example.com", action="add")
            client.organizations.manage_role_user("org", "role", "test@example.com", action="remove")
            assert client.organizations.export_data(request).state == "PENDING"
            assert isinstance(client.organizations.export_status("export", download_url=True), DataExportDownload)
    assert audit.calls[0].request.url.params["user_ids"] == "a,b"
    assert "user_id" not in audit.calls[0].request.url.params
    assert json.loads(workspace.calls[0].request.content)["workspace_id"] == "workspace"
    assert json.loads(role.calls[0].request.content)["group_id"] == "role"
    assert json.loads(export.calls[0].request.content)["entity_ids"] == ["temporary-agent"]
    assert status.calls[0].request.url.params["download_url"] == "true"


def test_export_requires_explicit_scope() -> None:
    with pytest.raises(ValidationError):
        DataExportRequest.model_validate({"start_date": "start", "end_date": "end", "export_fields": ["name"]})


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("explicit_defaults", [False, True])
@respx.mock
def test_export_preserves_unset_and_explicit_defaults(asynchronous: bool, explicit_defaults: bool) -> None:
    route = respx.post(f"{API_BASE}/export_data").respond(200, json={"data_export_id": "export", "state": "PENDING"})
    required = {
        "start_date": "2026-01-01",
        "end_date": "2026-01-02",
        "export_fields": ["name"],
        "export_scope": "personal",
        "data_type": "agents",
    }
    defaults = {"export_level": "organization", "workspace_ids": [], "include_all_workspaces": False}
    payload = {**required, **(defaults if explicit_defaults else {})}
    request = DataExportRequest.model_validate(payload)

    async def run() -> None:
        async with AsyncGumloop(api_key="key", user_id="actor") as client:
            await client.organizations.export_data(request)

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor") as client:
            client.organizations.export_data(request)
    assert json.loads(route.calls[0].request.content) == payload
