from __future__ import annotations

import asyncio
import json
import os
import time
import webbrowser
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from urllib.parse import urlparse

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.errors import APIStatusError

DEFAULT_BASE_URL = "https://api.gumloop.com/api/v1"
CONFIG_PATH = Path(os.environ.get("GUMLOOP_SDK_EXAMPLE_CONFIG", Path.home() / ".gumloop" / "config.json"))
BASE_URL = os.environ.get("GUMLOOP_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 8765
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}/callback"
SCOPES = ("gumloop_api", "userinfo")
SESSION_WAIT_SECONDS = float(os.environ.get("GUMLOOP_SDK_EXAMPLE_WAIT_SECONDS", "30"))


def log(message: str) -> None:
    print(message, flush=True)


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text())


def save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2, sort_keys=True))
    try:
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass


def resolve_base_url(config: dict[str, Any]) -> str:
    return os.environ.get("GUMLOOP_BASE_URL") or config.get("base_url") or BASE_URL


def run_oauth_callback_server(expected_state: str) -> str:
    result: dict[str, str] = {}

    class OAuthCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            query = parse_qs(urlparse(self.path).query)
            state = query.get("state", [""])[0]
            code = query.get("code", [""])[0]
            error = query.get("error", [""])[0]

            if error:
                result["error"] = error
            elif state != expected_state:
                result["error"] = "state_mismatch"
            elif code:
                result["code"] = code
            else:
                result["error"] = "missing_code"

            body = b"You can close this tab and return to the terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    with HTTPServer((REDIRECT_HOST, REDIRECT_PORT), OAuthCallbackHandler) as server:
        while "code" not in result and "error" not in result:
            server.handle_request()

    if "error" in result:
        raise RuntimeError(f"OAuth failed: {result['error']}")
    return result["code"]


def authenticate(config: dict[str, Any]) -> dict[str, Any]:
    base_url = resolve_base_url(config)
    config["base_url"] = base_url
    oauth_client = Gumloop(access_token=config.get("access_token") or "bootstrap", base_url=base_url).oauth
    registration = config.get("oauth_client") or oauth_client.register_client(
        redirect_uri=REDIRECT_URI,
        client_name="Gumloop Python SDK Example",
        scopes=SCOPES,
    )
    config["oauth_client"] = registration
    save_config(config)

    authorization_url, code_verifier, state = oauth_client.build_authorization_url(
        client_id=registration["client_id"],
        redirect_uri=REDIRECT_URI,
        scopes=SCOPES,
    )

    log(f"Opening browser for OAuth: {authorization_url}")
    webbrowser.open(authorization_url)
    code = run_oauth_callback_server(state)
    tokens = oauth_client.exchange_code(
        client_id=registration["client_id"],
        code=code,
        redirect_uri=REDIRECT_URI,
        code_verifier=code_verifier,
    )
    config["access_token"] = tokens["access_token"]
    if tokens.get("refresh_token"):
        config["refresh_token"] = tokens["refresh_token"]
    save_config(config)
    return config


def refresh_access_token(config: dict[str, Any]) -> dict[str, Any] | None:
    oauth_client_meta = config.get("oauth_client") or {}
    refresh_token = config.get("refresh_token")
    client_id = oauth_client_meta.get("client_id")
    if not client_id or not refresh_token:
        return None

    oauth_client = Gumloop(
        access_token=config.get("access_token") or "bootstrap",
        base_url=resolve_base_url(config),
    ).oauth
    tokens = oauth_client.refresh_token(client_id=client_id, refresh_token=refresh_token)
    config["access_token"] = tokens["access_token"]
    if tokens.get("refresh_token"):
        config["refresh_token"] = tokens["refresh_token"]
    save_config(config)
    return config


def get_authenticated_config() -> dict[str, Any]:
    config = load_config()
    config["base_url"] = resolve_base_url(config)
    if config.get("access_token"):
        client = Gumloop(access_token=config["access_token"], base_url=config["base_url"])
        try:
            client.models.list()
            return config
        except APIStatusError as exc:
            if exc.status_code != 401:
                raise
            refreshed = refresh_access_token(config)
            if refreshed:
                return refreshed
    return authenticate(config)


def pick_model(client: Gumloop) -> str:
    models = client.models.list()
    for group in models.model_groups:
        for option in group.get("options", []):
            value = option.get("value") or option.get("model_name") or option.get("id")
            if value and not option.get("restricted"):
                return value
    return "auto"


def wait_for_session(client: Gumloop, session_id: str, timeout_seconds: float = SESSION_WAIT_SECONDS):
    deadline = time.monotonic() + timeout_seconds
    last_status = None
    while time.monotonic() < deadline:
        session_response = client.sessions.retrieve(session_id)
        if session_response.session.state != last_status:
            last_status = session_response.session.state
            log(f"Session {session_id} state: {last_status}")
        if session_response.session.state in {"completed", "failed"}:
            return session_response
        time.sleep(2)
    return client.sessions.retrieve(session_id)


def run_stream_smoke(client: Gumloop, agent_id: str) -> dict[str, Any]:
    log("\n== Sync streaming smoke ==")
    session_id = f"sdk_example_stream_{int(time.time() * 1000)}"
    last_cursor = None
    event_count = 0
    for event in client.sessions.stream(
        agent_id,
        session_id=session_id,
        input="Stream one short sentence confirming HTTP streaming works.",
        metadata={"example": "sync_stream"},
    ):
        event_count += 1
        last_cursor = event.stream_cursor or last_cursor
        log(f"Stream event {event_count}: {event.type}")
        if event.final:
            break

    log(f"Stream session id: {session_id}")
    if last_cursor:
        log(f"Last stream cursor: {last_cursor}")
    return {"session_id": session_id, "last_cursor": last_cursor, "event_count": event_count}


def run_sync_smoke(access_token: str, base_url: str) -> dict[str, Any]:
    client = Gumloop(access_token=access_token, base_url=base_url)

    log("\n== Sync SDK smoke ==")
    log(f"Base URL: {base_url}")
    models = client.models.list()
    agents = client.agents.list(page_size=10)
    log(f"Model groups returned: {len(models.model_groups)}")
    log(f"Agents returned: {len(agents.agents)}")

    model = pick_model(client)
    agent_response = client.agents.create(
        name=f"SDK Example Agent {int(time.time())}",
        model_name=model,
        system_prompt="You are a concise assistant used to test the Gumloop Python SDK.",
    )
    agent_id = agent_response.agent.id
    log(f"Created agent: {agent_id}")

    first_response = client.sessions.create(
        agent_id,
        input="Reply with one short sentence confirming the Gumloop Python SDK works.",
        metadata={"example": "sync"},
    )
    # Streaming branch returns an iterator; without ``stream=True`` we get
    # a SessionResponse back.
    assert not hasattr(first_response, "__iter__")
    session_id = first_response.session.id
    initial_state = first_response.session.state
    log(f"Created session: {session_id}")
    log(f"Initial session state: {initial_state}")

    final_session = wait_for_session(client, session_id)
    final_state = final_session.session.state
    log(f"Final/last observed session state: {final_state}")

    second_response = None
    if final_state in {"completed", "failed"}:
        second_response = client.sessions.send(session_id, input="Send one more short confirmation.")
        log(f"Second response state: {second_response.session.state}")
    else:
        log("Skipping follow-up send because the first response did not reach a terminal state.")

    stream_result = run_stream_smoke(client, agent_id)
    return {"agent_id": agent_id, "session_id": session_id, "response": second_response, "stream": stream_result}


async def run_async_smoke(access_token: str, base_url: str, agent_id: str) -> dict[str, Any]:
    log("\n== Async SDK smoke ==")
    async with AsyncGumloop(access_token=access_token, base_url=base_url) as client:
        models, agents = await asyncio.gather(
            client.models.list(),
            client.agents.list(page_size=10),
        )
        log(f"Async model groups returned: {len(models.model_groups)}")
        log(f"Async agents returned: {len(agents.agents)}")

        created = await client.sessions.create(
            agent_id,
            input="Reply with one short sentence confirming async SDK calls work.",
            metadata={"example": "async"},
        )
        session_id = created.session.id
        latest = await client.sessions.retrieve(session_id)
        follow_up = None
        if latest.session.state in {"completed", "failed"}:
            follow_up = await client.sessions.send(session_id, input="Send an async follow-up confirmation.")

        stream_session_id = f"sdk_example_async_stream_{int(time.time() * 1000)}"
        stream_event_count = 0
        async for event in client.sessions.stream(
            agent_id,
            session_id=stream_session_id,
            input="Stream one short sentence confirming async HTTP streaming works.",
            metadata={"example": "async_stream"},
        ):
            stream_event_count += 1
            log(f"Async stream event {stream_event_count}: {event.type}")
            if event.final:
                break

    log(f"Async session id: {session_id}")
    log(f"Async latest state: {latest.session.state}")
    if follow_up:
        log(f"Async follow-up state: {follow_up.session.state}")
    else:
        log("Skipping async follow-up send because the response is not terminal yet.")
    return {"session_id": session_id, "response": follow_up, "stream_session_id": stream_session_id}


def main() -> None:
    config = get_authenticated_config()
    access_token = config["access_token"]
    base_url = config["base_url"]
    sync_result = run_sync_smoke(access_token, base_url)
    asyncio.run(run_async_smoke(access_token, base_url, sync_result["agent_id"]))
    log(f"\nConfig saved at: {CONFIG_PATH}")


if __name__ == "__main__":
    main()
