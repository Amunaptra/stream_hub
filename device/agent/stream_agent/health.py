from __future__ import annotations

import asyncio
import hashlib
import logging
import time

import httpx

from .models import HealthItem, PlaylistConfig, StreamItem
from .storage import DeviceStore


LOGGER = logging.getLogger("stream-agent.health")
FFPROBE_STREAM_SCHEMES = ("rtmp://", "rtmps://", "rtsp://", "rtsps://")
FFPROBE_TIMEOUT_SECONDS = 8.0
STREAM_HEALTH_MAX_CONCURRENCY = 2


def deterministic_initial_delay(phase_key: str, interval_seconds: float) -> float:
    """Spread device probes across the interval without random drift."""
    if not phase_key:
        return 0.0
    digest = hashlib.sha256(phase_key.encode("utf-8")).digest()
    ratio = int.from_bytes(digest[:8], "big") / float(1 << 64)
    return ratio * max(0.0, interval_seconds)


def _safe_probe_error(detail: str, stream_url: str, fallback: str) -> str:
    sanitized = detail.replace(stream_url, "<stream-url>").strip()
    return sanitized[-500:] or fallback


async def _check_ffprobe_stream(stream: StreamItem) -> HealthItem:
    started = time.monotonic()
    process: asyncio.subprocess.Process | None = None
    protocol = stream.url.split(":", 1)[0].upper()
    input_options: list[str] = []
    if stream.url.lower().startswith(("rtsp://", "rtsps://")):
        input_options = ["-rtsp_transport", "tcp"]
    try:
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            *input_options,
            "-rw_timeout",
            str(int(FFPROBE_TIMEOUT_SECONDS * 1_000_000)),
            "-show_entries",
            "stream=codec_type",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            stream.url,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=FFPROBE_TIMEOUT_SECONDS + 1
        )
        ok = process.returncode == 0 and bool(stdout.strip())
        error = None
        if not ok:
            detail = stderr.decode("utf-8", errors="replace").strip()
            error = _safe_probe_error(
                detail,
                stream.url,
                f"{protocol} stream probe failed",
            )
    except asyncio.TimeoutError:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        ok = False
        error = f"{protocol} stream probe timed out"
    except (FileNotFoundError, OSError) as exc:
        ok = False
        error = type(exc).__name__

    return HealthItem(
        id=stream.id,
        url=stream.url,
        enabled=stream.enabled,
        ok=ok,
        status_code=None,
        latency_ms=int((time.monotonic() - started) * 1000),
        error=error,
    )


async def _check_stream(client: httpx.AsyncClient, stream: StreamItem) -> HealthItem:
    if stream.url.lower().startswith(FFPROBE_STREAM_SCHEMES):
        return await _check_ffprobe_stream(stream)

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
    limits = httpx.Limits(
        max_connections=STREAM_HEALTH_MAX_CONCURRENCY,
        max_keepalive_connections=STREAM_HEALTH_MAX_CONCURRENCY,
    )
    timeout = httpx.Timeout(3.0, connect=1.0)
    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
    ) as client:
        semaphore = asyncio.Semaphore(STREAM_HEALTH_MAX_CONCURRENCY)

        async def limited(stream: StreamItem) -> HealthItem:
            async with semaphore:
                return await _check_stream(client, stream)

        return await asyncio.gather(*(limited(stream) for stream in streams))


class StreamHealthMonitor:
    def __init__(
        self,
        store: DeviceStore,
        interval_seconds: float = 300.0,
        phase_key: str = "",
    ):
        self.store = store
        self.interval_seconds = max(15.0, interval_seconds)
        self.initial_delay_seconds = deterministic_initial_delay(
            phase_key, self.interval_seconds
        )
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
        if self.initial_delay_seconds > 0:
            LOGGER.info(
                "stream health initial delay seconds=%.1f interval_seconds=%.1f",
                self.initial_delay_seconds,
                self.interval_seconds,
            )
            await asyncio.sleep(self.initial_delay_seconds)
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
