from __future__ import annotations

from urllib.parse import quote

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import VoiceSessionCreateRequest
from gumloop.types import VoiceSessionEndResponse
from gumloop.types import VoiceSessionStarted


class Voice:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def start(self, agent_id: str, *, session_id: str, offer_sdp: str, incognito: bool = False) -> VoiceSessionStarted:
        body = VoiceSessionCreateRequest(session_id=session_id, offer_sdp=offer_sdp, incognito=incognito)
        return VoiceSessionStarted.model_validate(
            self._client.post_to_stream_origin(
                f"gummies/{quote(agent_id, safe='')}/voice/sessions",
                json=body.model_dump(by_alias=True),
            )
        )

    def end(self, agent_id: str, voice_session_id: str) -> VoiceSessionEndResponse:
        return VoiceSessionEndResponse.model_validate(
            self._client.post_to_stream_origin(
                f"gummies/{quote(agent_id, safe='')}/voice/sessions/{quote(voice_session_id, safe='')}/end",
            )
        )


class AsyncVoice:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def start(
        self, agent_id: str, *, session_id: str, offer_sdp: str, incognito: bool = False
    ) -> VoiceSessionStarted:
        body = VoiceSessionCreateRequest(session_id=session_id, offer_sdp=offer_sdp, incognito=incognito)
        return VoiceSessionStarted.model_validate(
            await self._client.post_to_stream_origin(
                f"gummies/{quote(agent_id, safe='')}/voice/sessions",
                json=body.model_dump(by_alias=True),
            )
        )

    async def end(self, agent_id: str, voice_session_id: str) -> VoiceSessionEndResponse:
        return VoiceSessionEndResponse.model_validate(
            await self._client.post_to_stream_origin(
                f"gummies/{quote(agent_id, safe='')}/voice/sessions/{quote(voice_session_id, safe='')}/end",
            )
        )
