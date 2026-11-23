from __future__ import annotations

from urllib.parse import quote

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import CliCustomProxyRegisterRequest
from gumloop.types import CliCustomProxyRegistration
from gumloop.types import CustomProxyGatewayToken


class CustomProxies:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def register_cli(
        self, *, name: str, public_key: str, machine_name: str, cli_version: str
    ) -> CliCustomProxyRegistration:
        """Registering a key the caller already registered returns that personal proxy unchanged."""
        body = CliCustomProxyRegisterRequest(
            name=name, public_key=public_key, machine_name=machine_name, cli_version=cli_version
        ).model_dump()
        return CliCustomProxyRegistration.model_validate(self._client.post("custom-proxies", json=body, scoped=False))

    def create_gateway_token(self, custom_proxy_id: str) -> CustomProxyGatewayToken:
        """The token a CLI personal proxy signs in to the linked proxy gateway with."""
        return CustomProxyGatewayToken.model_validate(
            self._client.post(f"custom-proxies/{quote(custom_proxy_id, safe='')}/gateway-token", scoped=False)
        )

    def delete(self, custom_proxy_id: str) -> None:
        self._client.delete(f"custom-proxies/{quote(custom_proxy_id, safe='')}", scoped=False)


class AsyncCustomProxies:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def register_cli(
        self, *, name: str, public_key: str, machine_name: str, cli_version: str
    ) -> CliCustomProxyRegistration:
        """Registering a key the caller already registered returns that personal proxy unchanged."""
        body = CliCustomProxyRegisterRequest(
            name=name, public_key=public_key, machine_name=machine_name, cli_version=cli_version
        ).model_dump()
        return CliCustomProxyRegistration.model_validate(
            await self._client.post("custom-proxies", json=body, scoped=False)
        )

    async def create_gateway_token(self, custom_proxy_id: str) -> CustomProxyGatewayToken:
        """The token a CLI personal proxy signs in to the linked proxy gateway with."""
        return CustomProxyGatewayToken.model_validate(
            await self._client.post(f"custom-proxies/{quote(custom_proxy_id, safe='')}/gateway-token", scoped=False)
        )

    async def delete(self, custom_proxy_id: str) -> None:
        await self._client.delete(f"custom-proxies/{quote(custom_proxy_id, safe='')}", scoped=False)
