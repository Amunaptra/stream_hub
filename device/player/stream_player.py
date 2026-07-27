#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from stream_agent.models import PlaylistConfig, StreamItem


CONFIG_FILE = Path(os.environ.get("STREAM_HUB_PLAYLIST", "/etc/stream-hub/playlist.json"))
RUNTIME_DIR = Path(os.environ.get("STREAM_HUB_RUNTIME_DIR", "/run/stream-hub"))
STATE_FILE = RUNTIME_DIR / "player-state.json"
RETRY_SECONDS = 2
STOP_REQUESTED = False

MPV_COMMAND = [
    "mpv",
    "--fullscreen",
    "--no-config",
    "--stop-screensaver",
    "--cache=no",
    "--demuxer-readahead-secs=0",
    "--network-timeout=5",
    "--hls-bitrate=max",
    "--video-sync=display-desync",
    "--no-terminal",
    "--input-terminal=no",
    "--input-ipc-server=/run/stream-hub/mpv.sock",
]

logging.basicConfig(
    level=os.environ.get("STREAM_HUB_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("stream-player")


def atomic_state(payload: dict) -> None:
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


def write_state(status: str, stream: StreamItem | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    atomic_state(
        {
            "status": status,
            "stream_id": stream.id if stream else None,
            "url": stream.url if stream else None,
            "started_at": now if stream and status == "playing" else None,
            "updated_at": now,
        }
    )


def load_playlist() -> PlaylistConfig:
    return PlaylistConfig.model_validate_json(CONFIG_FILE.read_text(encoding="utf-8"))


def terminate_process(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def play(stream: StreamItem) -> None:
    write_state("playing", stream)
    LOGGER.info("playing stream=%s seconds=%s", stream.id, stream.seconds)
    process = subprocess.Popen([*MPV_COMMAND, stream.url])
    try:
        if stream.seconds == 0:
            while not STOP_REQUESTED and process.poll() is None:
                time.sleep(0.5)
        else:
            deadline = time.monotonic() + stream.seconds
            while not STOP_REQUESTED and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.25)
        if process.poll() is None:
            terminate_process(process)
    finally:
        if process.poll() is None:
            terminate_process(process)
        LOGGER.info("stream ended stream=%s returncode=%s", stream.id, process.returncode)


def request_stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def main() -> int:
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    write_state("starting")

    while not STOP_REQUESTED:
        try:
            playlist = load_playlist()
            enabled = [stream for stream in playlist.streams if stream.enabled]
        except Exception as exc:
            LOGGER.error("playlist load failed: %s", type(exc).__name__)
            write_state("config-error")
            time.sleep(3)
            continue

        if not enabled:
            write_state("idle")
            time.sleep(3)
            continue

        for stream in enabled:
            if STOP_REQUESTED:
                break
            try:
                play(stream)
            except FileNotFoundError:
                LOGGER.critical("mpv executable not found")
                write_state("player-missing")
                return 2
            except Exception as exc:
                LOGGER.error("stream failed stream=%s error=%s", stream.id, type(exc).__name__)
            if not STOP_REQUESTED:
                time.sleep(RETRY_SECONDS)

    write_state("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
