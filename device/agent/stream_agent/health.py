from __future__ import annotations

import asyncio
import time

import httpx

from .models import HealthItem, PlaylistConfig, StreamItem


async def _check_stream(client: httpx.AsyncClient, stream: StreamItem) -> HealthItem:
    started = time.monotonic()
    status_code: int | None = None
    try:
        async with client.stream(
            "GET",
            stream.url,
            headers={"User-Agent": "stream-hub-agent/0.1"},
        ) as response:
            status_code = response.status_code
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) >= 4096:
                    break
        valid_manifest = b"#EXTM3U" in bytes(body[:4096])
        ok = status_code == 200 and valid_manifest
        error = None if ok else "response is not a valid HLS manifest"
    except Exception as exc:
        ok = False
        error = type(exc).__name__

    return HealthItem(
        id=stream.id,
        url=stream.url,
        enabled=stream.enabled,
        ok=ok,
        status_code=status_code,
        latency_ms=int((time.monotonic() - started) * 1000),
        error=error,
    )


async def check_playlist(playlist: PlaylistConfig) -> list[HealthItem]:
    streams = [stream for stream in playlist.streams if stream.enabled]
    limits = httpx.Limits(max_connections=6, max_keepalive_connections=3)
    timeout = httpx.Timeout(3.0, connect=1.0)
    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
    ) as client:
        semaphore = asyncio.Semaphore(6)

        async def limited(stream: StreamItem) -> HealthItem:
            async with semaphore:
                return await _check_stream(client, stream)

        return await asyncio.gather(*(limited(stream) for stream in streams))
