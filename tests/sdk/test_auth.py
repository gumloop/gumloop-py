from __future__ import annotations

from urllib.parse import parse_qs
from urllib.parse import urlparse

import httpx
import pytest
import respx

from gumloop import Gumloop
from gumloop.errors import APIStatusError
from tests.sdk.helpers import OAUTH_BASE
from tests.sdk.helpers import request_json


@respx.mock
def test_register_client_posts_dynamic_client_registration_shape() -> None:
    route = respx.post(f"{OAUTH_BASE}/oauth/register").mock(
        return_value=httpx.Response(201, json={"client_id": "client_123"})
    )

    result = Gumloop(access_token="token").auth.register_client(
        redirect_uri="http://localhost:8765/callback",
        client_name="Test App",
        scopes=("gumloop", "userinfo"),
    )

    assert result == {"client_id": "client_123"}
    assert request_json(route.calls[0].request) == {
        "client_name": "Test App",
        "redirect_uris": ["http://localhost:8765/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "gumloop userinfo",
    }


def test_build_authorization_url_includes_pkce_and_state() -> None:
    authorization_url, code_verifier, state = Gumloop(access_token="token").auth.build_authorization_url(
        client_id="client_123",
        redirect_uri="http://localhost:8765/callback",
        scopes="gumloop",
        resource="https://api.gumloop.com/api/v1",
        state="state_123",
    )

    parsed = urlparse(authorization_url)
    query = parse_qs(parsed.query)
    assert parsed.path == "/oauth/authorize"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client_123"]
    assert query["redirect_uri"] == ["http://localhost:8765/callback"]
    assert query["scope"] == ["gumloop"]
    assert query["state"] == ["state_123"]
    assert query["resource"] == ["https://api.gumloop.com/api/v1"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"][0]
    assert len(code_verifier) > 40
    assert state == "state_123"


@respx.mock
def test_exchange_code_and_refresh_token_form_payloads() -> None:
    token_route = respx.post(f"{OAUTH_BASE}/oauth/token").mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "access", "refresh_token": "refresh"}),
            httpx.Response(200, json={"access_token": "new-access", "refresh_token": "new-refresh"}),
        ]
    )

    auth = Gumloop(access_token="token").auth
    assert (
        auth.exchange_code("client_123", "code_123", "http://localhost/callback", "verifier")["access_token"]
        == "access"
    )
    assert auth.refresh_token("client_123", "refresh")["access_token"] == "new-access"

    first_form = parse_qs(token_route.calls[0].request.content.decode())
    second_form = parse_qs(token_route.calls[1].request.content.decode())
    assert first_form["grant_type"] == ["authorization_code"]
    assert first_form["client_id"] == ["client_123"]
    assert first_form["code"] == ["code_123"]
    assert first_form["redirect_uri"] == ["http://localhost/callback"]
    assert first_form["code_verifier"] == ["verifier"]
    assert second_form["grant_type"] == ["refresh_token"]
    assert second_form["client_id"] == ["client_123"]
    assert second_form["refresh_token"] == ["refresh"]


@respx.mock
def test_auth_non_success_response_raises_gumloop_status_error() -> None:
    error = {
        "error": {
            "code": "invalid_request",
            "message": "Invalid request.",
            "type": "invalid_request_error",
            "details": {},
        }
    }
    respx.post(f"{OAUTH_BASE}/oauth/register").mock(return_value=httpx.Response(400, json=error))

    with pytest.raises(APIStatusError) as exc_info:
        Gumloop(access_token="token").auth.register_client("http://localhost/callback")

    assert exc_info.value.status_code == 400
    assert exc_info.value.body == error
    assert exc_info.value.code == "invalid_request"
    assert exc_info.value.type == "invalid_request_error"
    assert str(exc_info.value) == "Invalid request."


@respx.mock
def test_static_oauth_helpers_delegate_to_auth_resource() -> None:
    respx.post(f"{OAUTH_BASE}/oauth/register").mock(return_value=httpx.Response(201, json={"client_id": "client_123"}))

    assert Gumloop.register_oauth_client("http://localhost/callback") == {"client_id": "client_123"}

    authorization_url, code_verifier, state = Gumloop.build_authorization_url(
        "client_123",
        "http://localhost/callback",
        state="state_123",
    )
    assert "/oauth/authorize?" in authorization_url
    assert code_verifier
    assert state == "state_123"
