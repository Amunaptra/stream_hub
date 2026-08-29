#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import signal
import socket
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from stream_agent.models import PlaylistConfig, StreamItem


CONFIG_FILE = Path(
    os.environ.get("STREAM_HUB_PLAYLIST", "/etc/stream-hub/playlist.json")
)
RUNTIME_DIR = Path(os.environ.get("STREAM_HUB_RUNTIME_DIR", "/run/stream-hub"))
STATE_FILE = RUNTIME_DIR / "player-state.json"
MPV_SOCKET = RUNTIME_DIR / "mpv.sock"
SOURCE_CHECK_TIMEOUT = max(
    0.5,
    float(os.environ.get("STREAM_HUB_SOURCE_CHECK_TIMEOUT", "2")),
)
FFPROBE_STREAM_SCHEMES = ("rtmp://", "rtmps://", "rtsp://", "rtsps://")
FFPROBE_SOURCE_CHECK_TIMEOUT = max(
    SOURCE_CHECK_TIMEOUT,
    float(
        os.environ.get(
            "STREAM_HUB_FFPROBE_SOURCE_CHECK_TIMEOUT",
            os.environ.get("STREAM_HUB_RTMP_SOURCE_CHECK_TIMEOUT", "8"),
        )
    ),
)
STOP_REQUESTED = threading.Event()

MPV_COMMAND = [
    "mpv",
    "--vo=sdl",
    "--fullscreen",
    "--fs",
    "--autofit-larger=1920x1080",
    "--keepaspect=yes",
    "--geometry=0:0",
    "--no-config",
    "--no-audio",
    "--stop-screensaver",
    "--cache=yes",
    "--cache-secs=2",
    "--demuxer-readahead-secs=2",
    "--network-timeout=5",
    "--hls-bitrate=max",
    "--demuxer-lavf-o=fflags=+genpts+igndts",
    "--video-sync=display-desync",
    "--no-terminal",
    "--input-terminal=no",
    "--idle=yes",
    "--keep-open=yes",
    "--force-window=yes",
    f"--input-ipc-server={MPV_SOCKET}",
]

logging.basicConfig(
    level=os.environ.get("STREAM_HUB_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("stream-player")


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
    stream: StreamItem | None = None,
    *,
    message: str | None = None,
    load_ms: int = 0,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "status": status,
        "stream_id": stream.id if stream else None,
        "url": stream.url if stream else None,
        "started_at": now if stream and status == "playing" else None,
        "updated_at": now,
    }
    if message is not None:
        payload["transition"] = {
            "success": status == "playing",
            "message": message,
            "load_ms": load_ms,
        }
    atomic_state(payload)


def parse_playlist(raw: str) -> PlaylistConfig:
    return PlaylistConfig.model_validate_json(raw)


def load_playlist() -> PlaylistConfig:
    return parse_playlist(CONFIG_FILE.read_text(encoding="utf-8"))


def source_is_reachable(url: str, timeout: float = SOURCE_CHECK_TIMEOUT) -> bool:
    lowered_url = url.lower()
    if lowered_url.startswith(FFPROBE_STREAM_SCHEMES):
        probe_timeout = max(timeout, FFPROBE_SOURCE_CHECK_TIMEOUT)
        input_options: list[str] = []
        if lowered_url.startswith(("rtsp://", "rtsps://")):
            input_options = ["-rtsp_transport", "tcp"]
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    *input_options,
                    "-rw_timeout",
                    str(int(probe_timeout * 1_000_000)),
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    url,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=probe_timeout + 1,
                check=False,
                text=True,
            )
            return result.returncode == 0 and bool(result.stdout.strip())
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired, ValueError):
            return False

    try:
        request = Request(url, headers={"User-Agent": "stream-hub-player/0.1"})
        with urlopen(request, timeout=timeout) as response:
            response.read(1)
        return True
    except (OSError, URLError, ValueError):
        return False


class PersistentMpv:
    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        MPV_SOCKET.unlink(missing_ok=True)
        self.process = subprocess.Popen(
            MPV_COMMAND,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 8
        while not STOP_REQUESTED.is_set() and time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"mpv exited during startup: {self.process.returncode}")
            if MPV_SOCKET.is_socket():
                LOGGER.info("persistent mpv started pid=%s", self.process.pid)
                return
            STOP_REQUESTED.wait(0.1)
        raise RuntimeError("mpv IPC socket was not created")

    def stop(self) -> None:
        process = self.process
        self.process = None
        if process is None or process.poll() is not None:
            MPV_SOCKET.unlink(missing_ok=True)
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
        MPV_SOCKET.unlink(missing_ok=True)

    def send(self, command: list[Any], timeout: float = 3) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            raise RuntimeError("mpv is not running")
        payload = json.dumps(
            {"command": command},
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(MPV_SOCKET))
            client.sendall(payload)

    def get_property(self, name: str, timeout: float = 3) -> Any:
        process = self.process
        if process is None or process.poll() is not None:
            raise RuntimeError("mpv is not running")
        payload = json.dumps(
            {"command": ["get_property", name]},
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(MPV_SOCKET))
            client.sendall(payload)
            buffered = b""
            while b"\n" not in buffered:
                chunk = client.recv(4096)
                if not chunk:
                    raise RuntimeError("mpv IPC closed without a response")
                buffered += chunk
        line = buffered.split(b"\n", 1)[0]
        response = json.loads(line.decode("utf-8"))
        if response.get("error") != "success":
            raise RuntimeError(f"mpv property failed: {response.get('error')}")
        return response.get("data")

    def load(self, stream: StreamItem) -> int:
        started = time.monotonic()
        self.send(["loadfile", stream.url, "replace"])
        STOP_REQUESTED.wait(0.3)
        return int((time.monotonic() - started) * 1000)

    def idle(self) -> bool:
        return bool(self.get_property("idle-active"))


def wait_for_stream_duration(player: PersistentMpv, seconds: int) -> None:
    if seconds == 0:
        while not STOP_REQUESTED.wait(1):
            try:
                if player.idle():
                    return
            except Exception as exc:
                LOGGER.warning("mpv idle check failed error=%s", type(exc).__name__)
                return
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

    player = PersistentMpv()
    try:
        player.start()
    except FileNotFoundError:
        LOGGER.critical("mpv executable not found")
        write_state("player-missing")
        return 2
    except Exception as exc:
        LOGGER.critical("persistent mpv startup failed error=%s", type(exc).__name__)
        write_state("player-missing")
        return 2

    playlist_index = 0
    try:
        while not STOP_REQUESTED.is_set():
            try:
                playlist = load_playlist()
                enabled = [stream for stream in playlist.streams if stream.enabled]
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

            if not source_is_reachable(stream.url):
                LOGGER.warning("stream skipped offline stream=%s", stream.id)
                STOP_REQUESTED.wait(1)
                continue

            try:
                load_ms = player.load(stream)
            except Exception as exc:
                LOGGER.error(
                    "mpv load failed stream=%s error=%s",
                    stream.id,
                    type(exc).__name__,
                )
                STOP_REQUESTED.wait(1)
                continue

            write_state(
                "playing",
                stream,
                message="persistent mpv loadfile",
                load_ms=load_ms,
            )
            LOGGER.info(
                "playing stream=%s seconds=%s load_ms=%s",
                stream.id,
                stream.seconds,
                load_ms,
            )
            wait_for_stream_duration(player, stream.seconds)
    finally:
        player.stop()
        write_state("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
