from __future__ import annotations

import asyncio
import logging
import time

import httpx

from .models import HealthItem, PlaylistConfig, StreamItem
from .storage import DeviceStore


LOGGER = logging.getLogger("stream-agent.health")


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


class StreamHealthMonitor:
    def __init__(self, store: DeviceStore, interval_seconds: float = 60.0):
        self.store = store
        self.interval_seconds = max(15.0, interval_seconds)
        self._results: list[HealthItem] = []
        self._lock = asyncio.Lock()

    def snapshot(self) -> list[HealthItem]:
        return list(self._results)

    async def refresh(self) -> list[HealthItem]:
        async with self._lock:
            results = await check_playlist(self.store.load_playlist())
            self._results = results
            return self.snapshot()

    async def run(self) -> None:
        while True:
            started = time.monotonic()
            try:
                await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.warning("stream health check failed: %s", type(exc).__name__)
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(1.0, self.interval_seconds - elapsed))
