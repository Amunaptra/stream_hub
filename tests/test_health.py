from __future__ import annotations

import asyncio

from stream_agent import health
from stream_agent.models import StreamItem


class FakeProbe:
    returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"video\n", b""


def test_rtmp_health_uses_ffprobe(monkeypatch) -> None:
    commands: list[tuple[object, ...]] = []

    async def fake_create_subprocess_exec(*command: object, **_kwargs: object) -> FakeProbe:
        commands.append(command)
        return FakeProbe()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    stream = StreamItem(id="salon1", url="rtmp://192.168.102.6/play/salon1")

    result = asyncio.run(health._check_rtmp_stream(stream))

    assert result.ok is True
    assert result.status_code is None
    assert commands[0][0] == "ffprobe"
    assert commands[0][-1] == stream.url
