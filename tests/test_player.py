from __future__ import annotations

import importlib.util
import sys
import threading
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
    assert [stream.id for stream in playlist.enabled_streams] == ["one"]
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


class FakePad:
    def __init__(self) -> None:
        self.properties: dict[str, float | int] = {}

    def set_property(self, name: str, value: float | int) -> None:
        self.properties[name] = value


def branch(token: str, url: str) -> object:
    return PLAYER.GstBranch(
        token=token,
        url=url,
        elements=(),
        mixer_pad=FakePad(),
        ready=threading.Event(),
    )


def backend_for_transition(
    current: object | None,
    pending: object,
    wait_result: tuple[bool, str, int],
) -> tuple[object, list[object]]:
    backend = PLAYER.GstCrossfadeBackend.__new__(PLAYER.GstCrossfadeBackend)
    backend._lock = threading.RLock()
    backend.current = current
    backend.crossfade_ms = 0
    removed: list[object] = []
    backend._new_branch = types.MethodType(lambda _self, _url: pending, backend)
    backend._wait_until_ready = types.MethodType(
        lambda _self, _branch, _timeout: wait_result, backend
    )
    backend._retire_branch = types.MethodType(
        lambda _self, item: removed.append(item), backend
    )
    return backend, removed


def test_failed_preroll_keeps_old_stream_visible() -> None:
    old = branch("old", "http://media/old.m3u8")
    pending = branch("new", "http://media/new.m3u8")
    backend, removed = backend_for_transition(
        old, pending, (False, "preroll timeout", 8000)
    )

    result = backend.transition(pending.url, timeout_seconds=8)

    assert result.success is False
    assert backend.current is old
    assert removed == [pending]
    assert old.mixer_pad.properties == {}


def test_ready_stream_replaces_old_only_after_preroll() -> None:
    old = branch("old", "http://media/old.m3u8")
    pending = branch("new", "http://media/new.m3u8")
    backend, removed = backend_for_transition(
        old, pending, (True, "first frame ready", 640)
    )

    result = backend.transition(pending.url, timeout_seconds=8)

    assert result.success is True
    assert result.preroll_ms == 640
    assert backend.current is pending
    assert pending.mixer_pad.properties["alpha"] == 1.0
    assert removed == [old]
