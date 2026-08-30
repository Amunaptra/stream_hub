from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PLAYER_PATH = ROOT / "device" / "player" / "stream_player.py"
SPEC = importlib.util.spec_from_file_location("stream_player_under_test", PLAYER_PATH)
assert SPEC is not None and SPEC.loader is not None
PLAYER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PLAYER
SPEC.loader.exec_module(PLAYER)


def test_playlist_parser_preserves_order_and_filters_enabled_streams() -> None:
    playlist = PLAYER.parse_playlist(
        """
        {
          "revision": 7,
          "default_seconds": 20,
          "streams": [
            {"id": "one", "url": "http://media/one.m3u8", "seconds": 12},
            {"id": "two", "url": "https://media/two.m3u8", "enabled": false}
          ]
        }
        """
    )

    assert playlist.revision == 7
    assert [stream.id for stream in playlist.streams] == ["one", "two"]
    assert [stream.id for stream in playlist.streams if stream.enabled] == ["one"]
    assert playlist.streams[1].seconds == 20


@pytest.mark.parametrize(
    "payload",
    [
        '{"streams":[{"id":"same","url":"http://one/x.m3u8"},'
        '{"id":"same","url":"http://two/x.m3u8"}]}',
        '{"streams":[{"id":"bad","url":"file:///tmp/video.mp4"}]}',
        '{"streams":[{"id":"bad","url":"http://media/x.m3u8","seconds":-1}]}',
    ],
)
def test_playlist_parser_rejects_unsafe_or_ambiguous_entries(payload: str) -> None:
    with pytest.raises(ValueError):
        PLAYER.parse_playlist(payload)


def test_mpv_is_started_once_in_idle_keep_open_mode() -> None:
    assert "--idle=yes" in PLAYER.MPV_COMMAND
    assert "--keep-open=yes" in PLAYER.MPV_COMMAND
    assert "--force-window=yes" in PLAYER.MPV_COMMAND
    assert not any(item.startswith("http") for item in PLAYER.MPV_COMMAND)


def test_rtmp_source_precheck_uses_ffprobe(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    options: list[dict[str, object]] = []

    def fake_run(command: list[str], **kwargs: object) -> object:
        calls.append(command)
        options.append(kwargs)
        return types.SimpleNamespace(returncode=0, stdout="video\n")

    monkeypatch.setattr(PLAYER.subprocess, "run", fake_run)

    assert PLAYER.source_is_reachable("rtmp://192.168.102.6/play/salon1")
    assert calls[0][0] == "ffprobe"
    assert calls[0][calls[0].index("-rw_timeout") + 1] == "8000000"
    assert calls[0][-1] == "rtmp://192.168.102.6/play/salon1"
    assert options[0]["timeout"] == 9.0


def test_rtsp_source_precheck_uses_ffprobe_over_tcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> object:
        calls.append(command)
        return types.SimpleNamespace(returncode=0, stdout="video\n")

    monkeypatch.setattr(PLAYER.subprocess, "run", fake_run)

    url = "rtsp://viewer:secret@192.168.102.50:554/stream1"
    assert PLAYER.source_is_reachable(url)
    assert calls[0][0] == "ffprobe"
    assert calls[0][calls[0].index("-rtsp_transport") + 1] == "tcp"
    assert calls[0][calls[0].index("-rw_timeout") + 1] == "8000000"
    assert calls[0][-1] == url


def test_stream_switch_uses_loadfile_on_existing_mpv(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = PLAYER.StreamItem(
        id="next",
        url="http://media/next.m3u8",
        seconds=20,
        enabled=True,
    )
    player = PLAYER.PersistentMpv()
    commands: list[list[object]] = []
    player.send = types.MethodType(
        lambda _self, command, timeout=3: commands.append(command) or {},
        player,
    )
    monkeypatch.setattr(PLAYER.STOP_REQUESTED, "wait", lambda _timeout: False)

    elapsed = player.load(stream)

    assert commands == [["loadfile", stream.url, "replace"]]
    assert elapsed >= 0


def test_zero_duration_waits_until_mpv_becomes_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = PLAYER.PersistentMpv()
    idle_values = iter([False, False, True])
    positions = iter([1.0, 2.0])
    player.idle = types.MethodType(lambda _self: next(idle_values), player)
    player.get_property = types.MethodType(
        lambda _self, _name, timeout=3: next(positions),
        player,
    )
    monkeypatch.setattr(PLAYER.STOP_REQUESTED, "wait", lambda _timeout: False)

    assert PLAYER.wait_for_stream_duration(player, 0) == "idle"


def test_zero_duration_detects_frozen_playback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = PLAYER.PersistentMpv()
    clock = [0.0]
    player.idle = types.MethodType(lambda _self: False, player)
    player.get_property = types.MethodType(
        lambda _self, _name, timeout=3: 42.0,
        player,
    )
    monkeypatch.setattr(PLAYER, "PLAYBACK_STALL_SECONDS", 3.0)
    monkeypatch.setattr(PLAYER, "PLAYBACK_POLL_SECONDS", 1.0)
    monkeypatch.setattr(PLAYER.time, "monotonic", lambda: clock[0])

    def advance(timeout: float) -> bool:
        clock[0] += timeout
        return False

    monkeypatch.setattr(PLAYER.STOP_REQUESTED, "wait", advance)

    assert PLAYER.wait_for_stream_duration(player, 0) == "stalled"
    assert clock[0] == 3.0


def test_startup_tolerates_time_position_becoming_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = PLAYER.PersistentMpv()
    clock = [0.0]
    results: list[object] = [RuntimeError("not ready"), 1.0, 2.0]
    player.idle = types.MethodType(lambda _self: False, player)

    def delayed_position(_self: object, _name: str, timeout: float = 3) -> float:
        value = results.pop(0)
        if isinstance(value, Exception):
            raise value
        return float(value)

    player.get_property = types.MethodType(delayed_position, player)
    monkeypatch.setattr(PLAYER, "PLAYBACK_STALL_SECONDS", 3.0)
    monkeypatch.setattr(PLAYER, "PLAYBACK_POLL_SECONDS", 1.0)
    monkeypatch.setattr(PLAYER.time, "monotonic", lambda: clock[0])

    def advance(timeout: float) -> bool:
        clock[0] += timeout
        return clock[0] >= 3.0

    monkeypatch.setattr(PLAYER.STOP_REQUESTED, "wait", advance)

    assert PLAYER.wait_for_stream_duration(player, 3) == "duration"
    assert not results


def test_finite_duration_keeps_watchdog_and_returns_on_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = PLAYER.PersistentMpv()
    clock = [0.0]
    position = [0.0]
    player.idle = types.MethodType(lambda _self: False, player)

    def advancing_position(_self: object, _name: str, timeout: float = 3) -> float:
        position[0] += 1.0
        return position[0]

    player.get_property = types.MethodType(advancing_position, player)
    monkeypatch.setattr(PLAYER, "PLAYBACK_POLL_SECONDS", 1.0)
    monkeypatch.setattr(PLAYER.time, "monotonic", lambda: clock[0])

    def advance(timeout: float) -> bool:
        clock[0] += timeout
        return False

    monkeypatch.setattr(PLAYER.STOP_REQUESTED, "wait", advance)

    assert PLAYER.wait_for_stream_duration(player, 3) == "duration"
    assert clock[0] == 3.0
