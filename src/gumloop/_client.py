from __future__ import annotations

import os
import time
import warnings
from typing import Any

import httpx

from gumloop._auth import EnvToken
from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.oauth import OAuth
from gumloop.resources import MCP
from gumloop.resources import Agents
from gumloop.resources import Artifacts
from gumloop.resources import AsyncAgents
from gumloop.resources import AsyncArtifacts
from gumloop.resources import AsyncBrain
from gumloop.resources import AsyncChat
from gumloop.resources import AsyncMCP
from gumloop.resources import AsyncModels
from gumloop.resources import AsyncSessions
from gumloop.resources import AsyncSkills
from gumloop.resources import AsyncTeams
from gumloop.resources import Brain
from gumloop.resources import Chat
from gumloop.resources import Models
from gumloop.resources import Sessions
from gumloop.resources import Skills
from gumloop.resources import Sync
from gumloop.resources import Teams

DEFAULT_BASE_URL = "https://api.gumloop.com/api/v1"
DEFAULT_TIMEOUT = 90.0
DEFAULT_STREAM_TIMEOUT = 3600.0


def _derive_stream_base_url(base_url: str) -> str:
    # Prod: api.gumloop.com -> ws.gumloop.com. Local dev: :8080 -> :9093.
    # Other backends should pass ``stream_base_url=`` explicitly.
    return base_url.replace("api.gumloop.com", "ws.gumloop.com").replace("localhost:8080", "localhost:9093")


class Gumloop:
    """Sync Gumloop SDK client. Composes an :class:`HttpClient` with the
    resource classes (``agents``, ``sessions``, ``mcp``, ``teams``,
    ``skills``, ``artifacts``, ``brain``, ``models``). The :attr:`oauth`
    attribute holds OAuth helpers — kept off the transport because it
    bootstraps the bearer token rather than consuming one."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        access_token: str | None = None,
        user_id: str | None = None,
        team_id: str | None = None,
        base_url: str | None = None,
        stream_base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        stream_timeout: float | None = DEFAULT_STREAM_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.access_token = access_token or api_key or EnvToken.from_env()
        # Personal Gumloop API keys are user-scoped; the backend uses the
        # x-auth-key header to look up the owner's stored secret. OAuth
        # callers omit it because the bearer token already identifies them.
        self.user_id = user_id or os.environ.get("GUMLOOP_USER_ID")
        # Team API keys are validated against ``team_id``; ``user_id`` stays the acting member.
        self.team_id = team_id or os.environ.get("GUMLOOP_TEAM_ID")
        # Defaults to production; GUMLOOP_BASE_URL is an optional override.
        self.base_url = (base_url or os.environ.get("GUMLOOP_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.stream_base_url = (stream_base_url or _derive_stream_base_url(self.base_url)).rstrip("/")
        self.timeout = timeout
        self.stream_timeout = stream_timeout

        self._http = HttpClient(
            base_url=self.base_url,
            stream_base_url=self.stream_base_url,
            access_token=self.access_token,
            user_id=self.user_id,
            team_id=self.team_id,
            timeout=self.timeout,
            stream_timeout=self.stream_timeout,
        )

        self.agents = Agents(self._http)
        self.sessions = Sessions(self._http)
        self.chat = Chat(self._http)
        self.models = Models(self._http)
        self.mcp = MCP(self._http)
        self.teams = Teams(self._http)
        self.skills = Skills(self._http)
        self.sync = Sync(self._http)
        self.artifacts = Artifacts(self._http)
        self.brain = Brain(self._http)
        self.oauth = OAuth(base_url=self.base_url, timeout=self.timeout)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Gumloop:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class AsyncGumloop:
    """Async mirror of :class:`Gumloop`."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        access_token: str | None = None,
        user_id: str | None = None,
        team_id: str | None = None,
        base_url: str | None = None,
        stream_base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        stream_timeout: float | None = DEFAULT_STREAM_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.access_token = access_token or api_key or EnvToken.from_env()
        self.user_id = user_id or os.environ.get("GUMLOOP_USER_ID")
        # Team API keys are validated against ``team_id``; ``user_id`` stays the acting member.
        self.team_id = team_id or os.environ.get("GUMLOOP_TEAM_ID")
        # Defaults to production; GUMLOOP_BASE_URL is an optional override.
        self.base_url = (base_url or os.environ.get("GUMLOOP_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.stream_base_url = (stream_base_url or _derive_stream_base_url(self.base_url)).rstrip("/")
        self.timeout = timeout
        self.stream_timeout = stream_timeout

        self._http = AsyncHttpClient(
            base_url=self.base_url,
            stream_base_url=self.stream_base_url,
            access_token=self.access_token,
            user_id=self.user_id,
            team_id=self.team_id,
            timeout=self.timeout,
            stream_timeout=self.stream_timeout,
        )

        self.agents = AsyncAgents(self._http)
        self.sessions = AsyncSessions(self._http)
        self.chat = AsyncChat(self._http)
        self.models = AsyncModels(self._http)
        self.mcp = AsyncMCP(self._http)
        self.teams = AsyncTeams(self._http)
        self.skills = AsyncSkills(self._http)
        self.artifacts = AsyncArtifacts(self._http)
        self.brain = AsyncBrain(self._http)
        self.oauth = OAuth(base_url=self.base_url, timeout=self.timeout)

    async def __aenter__(self) -> AsyncGumloop:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()


class GumloopClient:
    """Flows/pipelines client. Predates :class:`Gumloop` (the agents/sessions
    client) and is kept working for existing integrations that call
    :meth:`run_flow` / :meth:`get_run_status`. New code should use
    :class:`Gumloop` instead."""

    def __init__(self, api_key: str, user_id: str, project_id: str | None = None):
        warnings.warn(
            "GumloopClient is the flows client. For agents and sessions, use gumloop.Gumloop.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.api_key = api_key
        self.user_id = user_id
        self.project_id = project_id
        self.base_url = DEFAULT_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # Persistent client so the polling loop reuses one TCP connection
        # across start_pipeline + get_pl_run instead of handshaking per call.
        self._client = httpx.Client(headers=self.headers)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GumloopClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def run_flow(
        self,
        flow_id: str,
        inputs: dict[str, Any],
        poll_interval: float = 1.0,
        timeout: float | None = None,
    ) -> dict:
        """Run a Gumloop flow and block until it reaches a terminal state.

        Raises ``TimeoutError`` if the run doesn't finish within ``timeout``
        seconds, and ``RuntimeError`` for ``FAILED`` / ``TERMINATING`` /
        ``TERMINATED`` states.
        """
        pipeline_inputs = [{"input_name": k, "value": v} for k, v in inputs.items()]

        request_body: dict[str, Any] = {
            "user_id": self.user_id,
            "saved_item_id": flow_id,
            "pipeline_inputs": pipeline_inputs,
        }
        if self.project_id:
            request_body["project_id"] = self.project_id

        response = self._client.post(f"{self.base_url}/start_pipeline", json=request_body)
        response.raise_for_status()
        run_id = response.json()["run_id"]

        start_time = time.time()
        while True:
            # ``is not None`` so timeout=0 raises immediately rather than
            # being treated as "no deadline" by truthiness.
            if timeout is not None and (time.time() - start_time) > timeout:
                raise TimeoutError("Flow execution timed out")

            status = self.get_run_status(run_id)
            if status["state"] == "DONE":
                return status["outputs"]
            if status["state"] == "FAILED":
                raise RuntimeError(f"Flow execution failed: {status.get('log', [])}")
            if status["state"] in ("TERMINATING", "TERMINATED"):
                raise RuntimeError(f"Flow execution was terminated: {status.get('log', [])}")

            time.sleep(poll_interval)

    def get_run_status(self, run_id: str) -> dict:
        """Fetch the current state, outputs, and log for a flow run."""
        params: dict[str, Any] = {"run_id": run_id, "user_id": self.user_id}
        if self.project_id:
            params["project_id"] = self.project_id

        response = self._client.get(f"{self.base_url}/get_pl_run", params=params)
        response.raise_for_status()
        return response.json()
