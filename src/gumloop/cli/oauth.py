from __future__ import annotations

import errno
import time
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from typing import Any
from urllib.parse import parse_qs
from urllib.parse import urlparse

from gumloop import GumloopError
from gumloop import OAuth
from gumloop._client import DEFAULT_TIMEOUT

GUMLOOP_CLI_CLIENT_ID = "gumloop_cli"
GUMLOOP_CLI_SCOPES = ("gumloop_api", "userinfo")
REDIRECT_HOST = "127.0.0.1"
DEFAULT_REDIRECT_PORT = 8765
# Hard ceiling so a closed browser tab doesn't hang the CLI forever.
_CALLBACK_DEADLINE_SECONDS = 300
_CALLBACK_TICK_SECONDS = 1


def build_redirect_uri(port: int) -> str:
    return f"http://{REDIRECT_HOST}:{port}/callback"


def _run_callback_server(expected_state: str, *, port: int) -> str:
    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
            parsed_path = urlparse(self.path)

            # Ignore favicon prefetches and other non-callback paths,
            # otherwise they short-circuit the wait loop with a bogus
            # "no code in callback" error before the real redirect arrives.
            if parsed_path.path != "/callback":
                body = b"Not found"
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            query = parse_qs(parsed_path.query)
            state = query.get("state", [""])[0]
            code = query.get("code", [""])[0]
            error = query.get("error", [""])[0]
            error_description = query.get("error_description", [""])[0]

            if error:
                result["error"] = error_description or error
            elif state != expected_state:
                result["error"] = "OAuth state mismatch."
            elif code:
                result["code"] = code
            else:
                result["error"] = "OAuth callback did not include a code."

            body = b"Gumloop login complete. You can close this tab and return to the terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: N802, A002
            return

    try:
        server = HTTPServer((REDIRECT_HOST, port), Handler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise GumloopError(
                f"Port {port} is already in use. Free the port or pass `gumloop login --callback-port <free port>`."
            ) from exc
        raise GumloopError(f"Could not start local OAuth callback server on port {port}: {exc}") from exc

    # Short per-request timeout so the loop can poll the overall deadline.
    server.timeout = _CALLBACK_TICK_SECONDS
    deadline = time.monotonic() + _CALLBACK_DEADLINE_SECONDS
    try:
        while "code" not in result and "error" not in result:
            if time.monotonic() > deadline:
                raise GumloopError(
                    f"OAuth login timed out after {_CALLBACK_DEADLINE_SECONDS // 60} minutes "
                    "waiting for the browser callback."
                )
            server.handle_request()
    finally:
        server.server_close()

    if "error" in result:
        raise GumloopError(f"OAuth callback returned an error: {result['error']}")
    return result["code"]


def perform_oauth_login(
    *,
    base_url: str,
    port: int = DEFAULT_REDIRECT_PORT,
    open_browser: bool = True,
    on_url: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run the PKCE flow against the well-known Gumloop CLI client and return tokens."""
    oauth = OAuth(base_url=base_url, timeout=DEFAULT_TIMEOUT)
    redirect_uri = build_redirect_uri(port)
    # Security invariant: SDK uses secrets.token_urlsafe for state +
    # code_verifier. Swapping to random.* breaks both PKCE and CSRF.
    authorization_url, code_verifier, state = oauth.build_authorization_url(
        client_id=GUMLOOP_CLI_CLIENT_ID,
        redirect_uri=redirect_uri,
        scopes=GUMLOOP_CLI_SCOPES,
    )

    if on_url is not None:
        on_url(authorization_url)
    if open_browser:
        webbrowser.open(authorization_url)

    code = _run_callback_server(state, port=port)
    return oauth.exchange_code(
        client_id=GUMLOOP_CLI_CLIENT_ID,
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
    )


def refresh_oauth_tokens(*, base_url: str, refresh_token: str) -> dict[str, Any]:
    oauth = OAuth(base_url=base_url, timeout=DEFAULT_TIMEOUT)
    return oauth.refresh_token(
        client_id=GUMLOOP_CLI_CLIENT_ID,
        refresh_token=refresh_token,
    )


def revoke_oauth_token(*, base_url: str, token: str) -> None:
    """Server-side revoke. Raises on HTTP failure; the caller decides whether to surface."""
    oauth = OAuth(base_url=base_url, timeout=DEFAULT_TIMEOUT)
    oauth.revoke(client_id=GUMLOOP_CLI_CLIENT_ID, token=token)
