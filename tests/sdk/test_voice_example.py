from __future__ import annotations

import argparse
import asyncio
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize("failure", [None, "start", "remote", "end"])
def test_wav_example_records_and_cleans_up_without_network(monkeypatch, failure):
    callbacks = {}
    peer = MagicMock()
    peer.on.side_effect = lambda event: lambda callback: callbacks.setdefault(event, callback)
    peer.createOffer = AsyncMock(return_value="offer")
    peer.setLocalDescription = AsyncMock()
    peer.localDescription = SimpleNamespace(sdp="v=0\r\noffer")
    peer.close = AsyncMock()

    async def set_remote(_description):
        if failure == "remote":
            raise RuntimeError("remote failed")
        callbacks["track"](SimpleNamespace(kind="audio"))

    peer.setRemoteDescription = AsyncMock(side_effect=set_remote)
    player = MagicMock()
    recorder = MagicMock(start=AsyncMock(), stop=AsyncMock())
    start = AsyncMock(return_value=SimpleNamespace(voice_session_id="voice", answer_sdp="answer"))
    end = AsyncMock()
    if failure == "start":
        start.side_effect = RuntimeError("start failed")
    if failure == "end":
        end.side_effect = RuntimeError("end failed")
    client = MagicMock(voice=SimpleNamespace(start=start, end=end))
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=context)
    monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "dummy-oauth")
    monkeypatch.setitem(
        sys.modules,
        "aiortc",
        SimpleNamespace(RTCPeerConnection=MagicMock(return_value=peer), RTCSessionDescription=MagicMock()),
    )
    monkeypatch.setitem(sys.modules, "aiortc.contrib", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "aiortc.contrib.media",
        SimpleNamespace(MediaPlayer=MagicMock(return_value=player), MediaRecorder=MagicMock(return_value=recorder)),
    )
    example = runpy.run_path(str(Path(__file__).resolve().parents[2] / "examples" / "voice_wav.py"))
    exchange = example["exchange"]
    exchange.__globals__["AsyncGumloop"] = factory
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    args = argparse.Namespace(
        input=Path("source.wav"),
        output=Path("received.wav"),
        stream_base_url="https://voice.test/api/v1",
        agent_id="agent",
        session_id="chat",
        seconds=1,
    )
    if failure:
        with pytest.raises(RuntimeError, match=f"{failure} failed"):
            asyncio.run(exchange(args))
    else:
        asyncio.run(exchange(args))
    factory.assert_called_once_with(access_token="dummy-oauth", stream_base_url="https://voice.test/api/v1")
    start.assert_awaited_once_with("agent", session_id="chat", offer_sdp="v=0\r\noffer")
    peer.createDataChannel.assert_called_once_with("oai-events")
    peer.close.assert_awaited_once()
    player.audio.stop.assert_called_once()
    player.video.stop.assert_called_once()
    recorder.stop.assert_awaited_once()
    if failure == "start":
        end.assert_not_awaited()
    else:
        end.assert_awaited_once_with("agent", "voice")
    if failure in (None, "end"):
        recorder.start.assert_awaited_once()
    else:
        recorder.start.assert_not_awaited()
