from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
import asyncio
from typing import Any

from gumloop import AsyncGumloop
from gumloop import AsyncGumloopClient
from gumloop import Gumloop


class _SyncResource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(self, method_name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((method_name, args, kwargs))
        return {"method": method_name}

    def me(self) -> dict[str, Any]:
        return self._record("me")

    def list(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._record("list", *args, **kwargs)

    def create(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._record("create", *args, **kwargs)

    def retrieve(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._record("retrieve", *args, **kwargs)

    def update(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._record("update", *args, **kwargs)

    def send(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._record("send", *args, **kwargs)

    def cancel(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._record("cancel", *args, **kwargs)


class _AsyncResource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def _record(self, method_name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((method_name, args, kwargs))
        return {"method": method_name}

    async def me(self) -> dict[str, Any]:
        return await self._record("me")

    async def list(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self._record("list", *args, **kwargs)

    async def create(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self._record("create", *args, **kwargs)

    async def retrieve(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self._record("retrieve", *args, **kwargs)

    async def update(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self._record("update", *args, **kwargs)

    async def send(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self._record("send", *args, **kwargs)

    async def cancel(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self._record("cancel", *args, **kwargs)


def test_sync_convenience_methods_delegate_to_resources() -> None:
    client = Gumloop(access_token="token")
    client.models = _SyncResource()
    client.agents = _SyncResource()
    client.sessions = _SyncResource()

    assert client.list_models() == {"method": "list"}
    assert client.list_agents(search="support") == {"method": "list"}
    assert client.create_agent(name="Support", model_name="auto") == {"method": "create"}
    assert client.get_agent("agent_123") == {"method": "retrieve"}
    assert client.update_agent("agent_123", model_name="auto") == {"method": "update"}
    assert client.create_session("agent_123", input="Hello") == {"method": "create"}
    assert client.get_session("session_123") == {"method": "retrieve"}
    assert client.send_message("session_123", "Hello") == {"method": "send"}
    assert client.cancel_session("session_123") == {"method": "cancel"}

    assert client.agents.calls[0] == ("list", (), {"search": "support"})
    assert client.sessions.calls[-2] == ("send", ("session_123", "Hello"), {})


def test_async_convenience_methods_delegate_to_resources() -> None:
    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            client.models = _AsyncResource()
            client.agents = _AsyncResource()
            client.sessions = _AsyncResource()

            assert await client.list_models() == {"method": "list"}
            assert await client.list_agents(search="support") == {"method": "list"}
            assert await client.create_agent(name="Support", model_name="auto") == {"method": "create"}
            assert await client.get_agent("agent_123") == {"method": "retrieve"}
            assert await client.update_agent("agent_123", model_name="auto") == {"method": "update"}
            assert await client.create_session("agent_123", input="Hello") == {"method": "create"}
            assert await client.get_session("session_123") == {"method": "retrieve"}
            assert await client.send_message("session_123", "Hello") == {"method": "send"}
            assert await client.cancel_session("session_123") == {"method": "cancel"}

            assert client.agents.calls[0] == ("list", (), {"search": "support"})
            assert client.sessions.calls[-2] == ("send", ("session_123", "Hello"), {})

    asyncio.run(run())


def test_async_alias_is_new_sdk_client() -> None:
    assert AsyncGumloopClient is AsyncGumloop
