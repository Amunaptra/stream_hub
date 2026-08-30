from __future__ import annotations

import asyncio

from stream_agent import health
from stream_agent.models import StreamItem


class FakeProbe:
    returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"video\n", b""


class FakeFailedProbe:
    returncode = 1

    def __init__(self, url: str):
        self.url = url

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", f"Unable to open {self.url}: unauthorized".encode()


def test_rtmp_health_uses_ffprobe(monkeypatch) -> None:
    commands: list[tuple[object, ...]] = []

    async def fake_create_subprocess_exec(*command: object, **_kwargs: object) -> FakeProbe:
        commands.append(command)
        return FakeProbe()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    stream = StreamItem(id="salon1", url="rtmp://192.168.102.6/play/salon1")

    result = asyncio.run(health._check_ffprobe_stream(stream))

    assert result.ok is True
    assert result.status_code is None
    assert commands[0][0] == "ffprobe"
    assert commands[0][-1] == stream.url


def test_rtsp_health_uses_ffprobe_over_tcp(monkeypatch) -> None:
    commands: list[tuple[object, ...]] = []

    async def fake_create_subprocess_exec(*command: object, **_kwargs: object) -> FakeProbe:
        commands.append(command)
        return FakeProbe()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    stream = StreamItem(id="camera1", url="rtsp://camera.local:554/live/main")

    result = asyncio.run(health._check_ffprobe_stream(stream))

    assert result.ok is True
    assert result.status_code is None
    assert commands[0][0] == "ffprobe"
    assert commands[0][commands[0].index("-rtsp_transport") + 1] == "tcp"
    assert commands[0][-1] == stream.url


def test_rtsp_health_error_does_not_expose_url_credentials(monkeypatch) -> None:
    url = "rtsp://viewer:secret@192.168.102.50:554/stream1"

    async def fake_create_subprocess_exec(*_command: object, **_kwargs: object) -> FakeFailedProbe:
        return FakeFailedProbe(url)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    result = asyncio.run(
        health._check_ffprobe_stream(StreamItem(id="camera1", url=url))
    )

    assert result.ok is False
    assert result.error == "Unable to open <stream-url>: unauthorized"
    assert "secret" not in result.error


def test_health_initial_delay_is_stable_and_bounded() -> None:
    first = health.deterministic_initial_delay("odroid-test-1", 300.0)
    second = health.deterministic_initial_delay("odroid-test-1", 300.0)

    assert first == second
    assert 0.0 <= first < 300.0
    assert health.deterministic_initial_delay("", 300.0) == 0.0


def test_health_monitor_waits_for_device_phase_before_first_probe(monkeypatch) -> None:
    events: list[tuple[str, float | None]] = []

    class FakeStore:
        pass

    monitor = health.StreamHealthMonitor(
        FakeStore(), interval_seconds=300.0, phase_key="odroid-test-2"
    )

    async def fake_refresh() -> list[object]:
        events.append(("refresh", None))
        raise asyncio.CancelledError

    async def fake_sleep(seconds: float) -> None:
        events.append(("sleep", seconds))

    monkeypatch.setattr(monitor, "refresh", fake_refresh)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    try:
        asyncio.run(monitor.run())
    except asyncio.CancelledError:
        pass

    assert events[0] == ("sleep", monitor.initial_delay_seconds)
    assert events[1] == ("refresh", None)
