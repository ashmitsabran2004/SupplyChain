from __future__ import annotations

import pytest

from app.main import stream
import app.stream as stream_module


class RecordingSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


@pytest.mark.anyio
async def test_websocket_stream_emits_scored_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_wait(_delay: float) -> None:
        return None

    monkeypatch.setattr(stream_module.asyncio, "sleep", no_wait)
    engine = stream()
    socket = RecordingSocket()
    await engine.run(socket, speed=200)
    meta, first_tick = socket.messages[:2]
    assert meta["type"] == "meta"
    assert meta["backend"] in {"neo4j", "local"}
    assert meta["centrality_backend"] in {"neo4j_gds", "local"}
    assert len(meta["timestamps"]) >= 30
    assert first_tick["type"] == "tick"
    assert first_tick["timestamp"]
    assert first_tick["nodes"]
    assert "delay_probability" in first_tick["nodes"][0]
    assert socket.messages[-1]["type"] == "done"
