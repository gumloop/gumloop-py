from __future__ import annotations

from urllib.parse import quote

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import CliLinkedProxyRegisterRequest
from gumloop.types import CliLinkedProxyRegistration
from gumloop.types import LinkedProxyGatewayToken


class LinkedProxies:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def register_cli(
        self, *, name: str, public_key: str, machine_name: str, cli_version: str
    ) -> CliLinkedProxyRegistration:
        """Registering a key the caller already registered returns that linked proxy unchanged."""
        body = CliLinkedProxyRegisterRequest(
            name=name, public_key=public_key, machine_name=machine_name, cli_version=cli_version
        ).model_dump()
        return CliLinkedProxyRegistration.model_validate(
            self._client.post("linked-proxies/cli", json=body, scoped=False)
        )

    def create_gateway_token(self, linked_proxy_id: str) -> LinkedProxyGatewayToken:
        """The token a CLI linked proxy signs in to the linked proxy gateway with."""
        return LinkedProxyGatewayToken.model_validate(
            self._client.post(f"linked-proxies/{quote(linked_proxy_id, safe='')}/gateway-token", scoped=False)
        )

    def delete(self, linked_proxy_id: str) -> None:
        self._client.delete(f"linked-proxies/{quote(linked_proxy_id, safe='')}", scoped=False)


class AsyncLinkedProxies:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def register_cli(
        self, *, name: str, public_key: str, machine_name: str, cli_version: str
    ) -> CliLinkedProxyRegistration:
        """Registering a key the caller already registered returns that linked proxy unchanged."""
        body = CliLinkedProxyRegisterRequest(
            name=name, public_key=public_key, machine_name=machine_name, cli_version=cli_version
        ).model_dump()
        return CliLinkedProxyRegistration.model_validate(
            await self._client.post("linked-proxies/cli", json=body, scoped=False)
        )

    async def create_gateway_token(self, linked_proxy_id: str) -> LinkedProxyGatewayToken:
        """The token a CLI linked proxy signs in to the linked proxy gateway with."""
        return LinkedProxyGatewayToken.model_validate(
            await self._client.post(f"linked-proxies/{quote(linked_proxy_id, safe='')}/gateway-token", scoped=False)
        )

    async def delete(self, linked_proxy_id: str) -> None:
        await self._client.delete(f"linked-proxies/{quote(linked_proxy_id, safe='')}", scoped=False)
