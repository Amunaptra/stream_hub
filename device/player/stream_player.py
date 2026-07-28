#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import signal
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


CONFIG_FILE = Path(
    os.environ.get("STREAM_HUB_PLAYLIST", "/etc/stream-hub/playlist.json")
)
RUNTIME_DIR = Path(os.environ.get("STREAM_HUB_RUNTIME_DIR", "/run/stream-hub"))
STATE_FILE = RUNTIME_DIR / "player-state.json"
FRAMEBUFFER = os.environ.get("STREAM_HUB_FRAMEBUFFER", "/dev/fb0")
CROSSFADE_MS = max(0, int(os.environ.get("STREAM_HUB_CROSSFADE_MS", "400")))
PREROLL_TIMEOUT_SECONDS = max(
    1.0, float(os.environ.get("STREAM_HUB_PREROLL_TIMEOUT", "8"))
)
OUTPUT_WIDTH = max(320, int(os.environ.get("STREAM_HUB_OUTPUT_WIDTH", "1920")))
OUTPUT_HEIGHT = max(240, int(os.environ.get("STREAM_HUB_OUTPUT_HEIGHT", "1080")))
OUTPUT_FPS = max(1, int(os.environ.get("STREAM_HUB_OUTPUT_FPS", "30")))
STOP_REQUESTED = threading.Event()

logging.basicConfig(
    level=os.environ.get("STREAM_HUB_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("stream-player")


@dataclass(frozen=True, slots=True)
class PlayerStream:
    id: str
    url: str
    seconds: int
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class PlayerPlaylist:
    revision: int
    streams: tuple[PlayerStream, ...]

    @property
    def enabled_streams(self) -> tuple[PlayerStream, ...]:
        return tuple(stream for stream in self.streams if stream.enabled)


@dataclass(frozen=True, slots=True)
class TransitionResult:
    success: bool
    message: str
    preroll_ms: int = 0
    fade_ms: int = 0


@dataclass(slots=True)
class GstBranch:
    token: str
    url: str
    elements: tuple[Any, ...]
    mixer_pad: Any
    ready: threading.Event
    error: str | None = None


def atomic_state(payload: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".player-state.", dir=RUNTIME_DIR)
    temporary = Path(name)
    try:
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, STATE_FILE)
    finally:
        temporary.unlink(missing_ok=True)


def write_state(
    status: str,
    stream: PlayerStream | None = None,
    transition: TransitionResult | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "status": status,
        "stream_id": stream.id if stream else None,
        "url": stream.url if stream else None,
        "started_at": now if stream and status == "playing" else None,
        "updated_at": now,
    }
    if transition is not None:
        payload["transition"] = {
            "success": transition.success,
            "message": transition.message,
            "preroll_ms": transition.preroll_ms,
            "fade_ms": transition.fade_ms,
        }
    atomic_state(payload)


def parse_playlist(raw: str) -> PlayerPlaylist:
    payload = json.loads(raw)
    revision = int(payload.get("revision", 0))
    default_seconds = int(payload.get("default_seconds", 20))
    streams: list[PlayerStream] = []
    seen: set[str] = set()
    for index, item in enumerate(payload.get("streams", [])):
        stream_id = str(item.get("id") or f"stream-{index + 1}").strip()
        url = str(item.get("url") or "").strip()
        seconds = int(item.get("seconds", default_seconds))
        enabled = bool(item.get("enabled", True))
        if not stream_id or stream_id in seen:
            raise ValueError("stream IDs must be non-empty and unique")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"stream {stream_id} has an invalid URL")
        if seconds < 0:
            raise ValueError(f"stream {stream_id} has a negative duration")
        seen.add(stream_id)
        streams.append(
            PlayerStream(
                id=stream_id,
                url=url,
                seconds=seconds,
                enabled=enabled,
            )
        )
    return PlayerPlaylist(revision=revision, streams=tuple(streams))


def load_playlist() -> PlayerPlaylist:
    return parse_playlist(CONFIG_FILE.read_text(encoding="utf-8"))


class GstCrossfadeBackend:
    def __init__(
        self,
        *,
        framebuffer: str = FRAMEBUFFER,
        width: int = OUTPUT_WIDTH,
        height: int = OUTPUT_HEIGHT,
        fps: int = OUTPUT_FPS,
        crossfade_ms: int = CROSSFADE_MS,
    ) -> None:
        try:
            import gi

            gi.require_version("Gst", "1.0")
            from gi.repository import Gst
        except (ImportError, ValueError) as exc:
            raise RuntimeError("GStreamer Python bindings are unavailable") from exc

        self.Gst = Gst
        self.framebuffer = framebuffer
        self.width = width
        self.height = height
        self.fps = fps
        self.crossfade_ms = crossfade_ms
        self.current: GstBranch | None = None
        self._branch_counter = 0
        self._lock = threading.RLock()
        self._cleanup_guard = threading.Lock()
        self._cleanup_threads: set[threading.Thread] = set()

        Gst.init(None)
        registry = Gst.Registry.get()
        v4l2_decoder = registry.find_feature("v4l2h264dec", Gst.ElementFactory)
        if v4l2_decoder is not None:
            v4l2_decoder.set_rank(Gst.Rank.NONE)

        self.pipeline = Gst.Pipeline.new("stream-hub-crossfade")
        self.mixer = self._make("compositor", "stream-mixer")
        self.mixer.set_property("background", 1)
        output_convert = self._make("videoconvert", "output-convert")
        output_scale = self._make("videoscale", "output-scale")
        output_caps = self._make("capsfilter", "output-caps")
        output_caps.set_property(
            "caps",
            Gst.Caps.from_string(
                f"video/x-raw,format=BGRx,width={width},height={height},"
                f"framerate={fps}/1,pixel-aspect-ratio=1/1"
            ),
        )
        sink = self._make("fbdevsink", "framebuffer-output")
        sink.set_property("device", framebuffer)
        sink.set_property("sync", False)

        self.pipeline.add(self.mixer)
        self.pipeline.add(output_convert)
        self.pipeline.add(output_scale)
        self.pipeline.add(output_caps)
        self.pipeline.add(sink)
        if not self.mixer.link(output_convert):
            raise RuntimeError("could not link compositor to output converter")
        if not output_convert.link(output_scale):
            raise RuntimeError("could not link output converter to scaler")
        if not output_scale.link(output_caps):
            raise RuntimeError("could not link output scaler to caps")
        if not output_caps.link(sink):
            raise RuntimeError("could not link output caps to framebuffer")
        self.bus = self.pipeline.get_bus()

    def _make(self, factory: str, name: str) -> Any:
        element = self.Gst.ElementFactory.make(factory, name)
        if element is None:
            raise RuntimeError(f"required GStreamer element is missing: {factory}")
        return element

    def start(self) -> None:
        result = self.pipeline.set_state(self.Gst.State.PLAYING)
        if result == self.Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("GStreamer output pipeline failed to start")
        LOGGER.info(
            "crossfade backend started framebuffer=%s output=%sx%s@%s fade_ms=%s",
            self.framebuffer,
            self.width,
            self.height,
            self.fps,
            self.crossfade_ms,
        )

    def stop(self) -> None:
        with self._lock:
            self.current = None
            shutdown = threading.Thread(
                target=self.pipeline.set_state,
                args=(self.Gst.State.NULL,),
                name="gstreamer-shutdown",
                daemon=True,
            )
            shutdown.start()
            shutdown.join(timeout=1)
            if shutdown.is_alive():
                LOGGER.warning("GStreamer shutdown continues in background")
        with self._cleanup_guard:
            cleanup_threads = tuple(self._cleanup_threads)
        for thread in cleanup_threads:
            thread.join(timeout=0.1)

    def _request_mixer_pad(self) -> Any:
        pad = self.mixer.request_pad_simple("sink_%u")
        if pad is None:
            raise RuntimeError("could not allocate a compositor input")
        return pad

    def _new_branch(self, url: str) -> GstBranch:
        self._branch_counter += 1
        token = f"branch-{self._branch_counter}"
        source = self._make("uridecodebin", f"{token}-source")
        source.set_property("uri", url)
        source.set_property("caps", self.Gst.Caps.from_string("video/x-raw"))
        queue = self._make("queue", f"{token}-queue")
        queue.set_property("max-size-buffers", 3)
        queue.set_property("max-size-bytes", 0)
        queue.set_property("max-size-time", 0)
        convert = self._make("videoconvert", f"{token}-convert")
        scale = self._make("videoscale", f"{token}-scale")
        capsfilter = self._make("capsfilter", f"{token}-caps")
        capsfilter.set_property(
            "caps",
            self.Gst.Caps.from_string(
                f"video/x-raw,width={self.width},height={self.height},"
                f"pixel-aspect-ratio=1/1"
            ),
        )
        identity = self._make("identity", f"{token}-ready")
        mixer_pad = self._request_mixer_pad()
        mixer_pad.set_property("alpha", 0.0)
        mixer_pad.set_property("zorder", 2)
        ready = threading.Event()
        branch = GstBranch(
            token=token,
            url=url,
            elements=(source, queue, convert, scale, capsfilter, identity),
            mixer_pad=mixer_pad,
            ready=ready,
        )

        for element in branch.elements:
            self.pipeline.add(element)
        if not queue.link(convert):
            raise RuntimeError("could not link branch queue")
        if not convert.link(scale):
            raise RuntimeError("could not link branch converter")
        if not scale.link(capsfilter):
            raise RuntimeError("could not link branch scaler")
        if not capsfilter.link(identity):
            raise RuntimeError("could not link branch caps")
        identity_pad = identity.get_static_pad("src")
        if identity_pad.link(mixer_pad) != self.Gst.PadLinkReturn.OK:
            raise RuntimeError("could not link branch to compositor")

        def pad_added(_source: Any, pad: Any) -> None:
            sink_pad = queue.get_static_pad("sink")
            if sink_pad.is_linked():
                return
            caps = pad.get_current_caps() or pad.query_caps(None)
            structure = caps.get_structure(0) if caps and caps.get_size() else None
            if structure is None or not structure.get_name().startswith("video/"):
                return
            if pad.link(sink_pad) != self.Gst.PadLinkReturn.OK:
                branch.error = "could not link decoded video"

        def source_setup(_decodebin: Any, network_source: Any) -> None:
            if network_source.find_property("timeout") is not None:
                network_source.set_property("timeout", 3)

        def first_buffer(_pad: Any, _info: Any) -> Any:
            ready.set()
            return self.Gst.PadProbeReturn.REMOVE

        source.connect("pad-added", pad_added)
        source.connect("source-setup", source_setup)
        identity_pad.add_probe(self.Gst.PadProbeType.BUFFER, first_buffer)
        for element in branch.elements:
            if not element.sync_state_with_parent():
                branch.error = f"could not start {element.get_name()}"
                break
        return branch

    def _remove_branch(self, branch: GstBranch) -> None:
        identity = branch.elements[-1]
        identity_pad = identity.get_static_pad("src")
        if identity_pad.is_linked():
            identity_pad.unlink(branch.mixer_pad)
        self.mixer.release_request_pad(branch.mixer_pad)
        for element in reversed(branch.elements):
            started = time.monotonic()
            element.set_state(self.Gst.State.NULL)
            LOGGER.info(
                "stopped branch element=%s elapsed_ms=%s",
                element.get_name(),
                int((time.monotonic() - started) * 1000),
            )
        for element in reversed(branch.elements):
            self.pipeline.remove(element)

    def _retire_branch(self, branch: GstBranch) -> None:
        def cleanup() -> None:
            started = time.monotonic()
            try:
                self._remove_branch(branch)
            finally:
                elapsed_ms = int((time.monotonic() - started) * 1000)
                LOGGER.info(
                    "retired stream branch=%s cleanup_ms=%s",
                    branch.token,
                    elapsed_ms,
                )
                with self._cleanup_guard:
                    self._cleanup_threads.discard(thread)

        thread = threading.Thread(
            target=cleanup,
            name=f"stream-cleanup-{branch.token}",
            daemon=True,
        )
        with self._cleanup_guard:
            self._cleanup_threads.add(thread)
        thread.start()

    def _read_branch_error(self, branch: GstBranch) -> str | None:
        message = self.bus.pop_filtered(self.Gst.MessageType.ERROR)
        while message is not None:
            error, debug = message.parse_error()
            source_path = message.src.get_path_string()
            text = f"{error.message} ({debug or source_path})"
            if branch.token in source_path:
                return text
            LOGGER.warning("GStreamer background error source=%s error=%s", source_path, text)
            message = self.bus.pop_filtered(self.Gst.MessageType.ERROR)
        return branch.error

    def _wait_until_ready(
        self, branch: GstBranch, timeout_seconds: float
    ) -> tuple[bool, str, int]:
        started = time.monotonic()
        deadline = started + timeout_seconds
        while not STOP_REQUESTED.is_set() and time.monotonic() < deadline:
            if branch.ready.wait(timeout=0.05):
                elapsed = int((time.monotonic() - started) * 1000)
                return True, "first frame ready", elapsed
            error = self._read_branch_error(branch)
            if error:
                elapsed = int((time.monotonic() - started) * 1000)
                return False, error, elapsed
        elapsed = int((time.monotonic() - started) * 1000)
        return False, "preroll timeout", elapsed

    def transition(
        self, url: str, *, timeout_seconds: float = PREROLL_TIMEOUT_SECONDS
    ) -> TransitionResult:
        with self._lock:
            pending = self._new_branch(url)
            ready, message, preroll_ms = self._wait_until_ready(
                pending, timeout_seconds
            )
            if not ready:
                self._retire_branch(pending)
                return TransitionResult(
                    success=False,
                    message=message,
                    preroll_ms=preroll_ms,
                )

            previous = self.current
            if previous is None or self.crossfade_ms == 0:
                pending.mixer_pad.set_property("alpha", 1.0)
                if previous is not None:
                    self._retire_branch(previous)
                self.current = pending
                return TransitionResult(
                    success=True,
                    message="stream activated",
                    preroll_ms=preroll_ms,
                )

            previous.mixer_pad.set_property("zorder", 1)
            steps = max(2, min(30, self.crossfade_ms // 20))
            fade_started = time.monotonic()
            for step in range(1, steps + 1):
                if STOP_REQUESTED.is_set():
                    break
                progress = step / steps
                pending.mixer_pad.set_property("alpha", progress)
                previous.mixer_pad.set_property("alpha", 1.0 - progress)
                time.sleep(self.crossfade_ms / steps / 1000)
            pending.mixer_pad.set_property("alpha", 1.0)
            previous.mixer_pad.set_property("alpha", 0.0)
            fade_ms = int((time.monotonic() - fade_started) * 1000)
            self.current = pending
            self._retire_branch(previous)
            return TransitionResult(
                success=True,
                message="crossfade completed",
                preroll_ms=preroll_ms,
                fade_ms=fade_ms,
            )


def wait_for_duration(seconds: int) -> None:
    if seconds == 0:
        while not STOP_REQUESTED.wait(0.5):
            pass
        return
    deadline = time.monotonic() + seconds
    while not STOP_REQUESTED.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        STOP_REQUESTED.wait(min(0.25, remaining))


def request_stop(_signum: int, _frame: object) -> None:
    STOP_REQUESTED.set()


def main() -> int:
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    write_state("starting")

    try:
        backend = GstCrossfadeBackend()
        backend.start()
    except Exception as exc:
        LOGGER.critical("crossfade backend startup failed: %s", exc)
        write_state("player-missing")
        return 2

    try:
        playlist_index = 0
        while not STOP_REQUESTED.is_set():
            try:
                playlist = load_playlist()
                enabled = playlist.enabled_streams
            except Exception as exc:
                LOGGER.error("playlist load failed: %s", type(exc).__name__)
                write_state("config-error")
                STOP_REQUESTED.wait(3)
                continue

            if not enabled:
                write_state("idle")
                STOP_REQUESTED.wait(3)
                continue

            if playlist_index >= len(enabled):
                playlist_index = 0
            stream = enabled[playlist_index]
            playlist_index = (playlist_index + 1) % len(enabled)

            LOGGER.info("preparing stream=%s seconds=%s", stream.id, stream.seconds)
            transition = backend.transition(stream.url)
            if not transition.success:
                LOGGER.error(
                    "transition rejected stream=%s preroll_ms=%s error=%s",
                    stream.id,
                    transition.preroll_ms,
                    transition.message,
                )
                STOP_REQUESTED.wait(2)
                continue

            write_state("playing", stream, transition)
            LOGGER.info(
                "playing stream=%s seconds=%s preroll_ms=%s fade_ms=%s",
                stream.id,
                stream.seconds,
                transition.preroll_ms,
                transition.fade_ms,
            )
            wait_for_duration(stream.seconds)
    finally:
        backend.stop()
        write_state("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
