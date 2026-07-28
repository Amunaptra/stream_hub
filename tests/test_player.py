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
    player.idle = types.MethodType(lambda _self: next(idle_values), player)
    monkeypatch.setattr(PLAYER.STOP_REQUESTED, "wait", lambda _timeout: False)

    PLAYER.wait_for_stream_duration(player, 0)
