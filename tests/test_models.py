from __future__ import annotations

import pytest
from pydantic import ValidationError

from stream_hub_backend.models import HubPlaylistDraft, HubStreamItem
from stream_agent.models import PlaylistConfig, StreamItem


def test_playlist_accepts_zero_seconds() -> None:
    playlist = PlaylistConfig(
        revision=1,
        streams=[
            StreamItem(
                id="salon-1",
                enabled=True,
                seconds=0,
                url="http://media.local/salon-1/index.m3u8",
            )
        ],
    )

    assert playlist.streams[0].seconds == 0


def test_playlist_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="stream IDs must be unique"):
        PlaylistConfig(
            streams=[
                StreamItem(id="same", url="http://one/index.m3u8"),
                StreamItem(id="same", url="http://two/index.m3u8"),
            ]
        )


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://host/file", "not-a-url"])
def test_stream_rejects_non_http_urls(url: str) -> None:
    with pytest.raises(ValidationError, match="http or https"):
        StreamItem(id="bad", url=url)


def test_device_playlist_accepts_fifty_streams() -> None:
    streams = [
        StreamItem(id=f"stream-{index}", url=f"http://media/{index}.m3u8")
        for index in range(50)
    ]

    assert len(PlaylistConfig(streams=streams).streams) == 50


def test_device_playlist_rejects_more_than_fifty_streams() -> None:
    streams = [
        StreamItem(id=f"stream-{index}", url=f"http://media/{index}.m3u8")
        for index in range(51)
    ]
    with pytest.raises(ValidationError):
        PlaylistConfig(streams=streams)


def test_hub_playlist_accepts_fifty_streams() -> None:
    streams = [
        HubStreamItem(id=f"stream-{index}", url=f"http://media/{index}.m3u8")
        for index in range(50)
    ]

    assert len(HubPlaylistDraft(streams=streams).streams) == 50


def test_hub_playlist_rejects_more_than_fifty_streams() -> None:
    streams = [
        HubStreamItem(id=f"stream-{index}", url=f"http://media/{index}.m3u8")
        for index in range(51)
    ]
    with pytest.raises(ValidationError):
        HubPlaylistDraft(streams=streams)
