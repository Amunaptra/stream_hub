from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    runtime_dir: Path
    player_service: str = "stream-player.service"
    agent_port: int = 8787
    hub_url: str | None = None
    heartbeat_interval_seconds: float = 10.0
    discovery_timeout_seconds: float = 3.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(os.environ.get("STREAM_HUB_DATA_DIR", "/etc/stream-hub")),
            runtime_dir=Path(os.environ.get("STREAM_HUB_RUNTIME_DIR", "/run/stream-hub")),
            player_service=os.environ.get("STREAM_HUB_PLAYER_SERVICE", "stream-player.service"),
            agent_port=int(os.environ.get("STREAM_HUB_AGENT_PORT", "8787")),
            hub_url=os.environ.get("STREAM_HUB_URL") or None,
            heartbeat_interval_seconds=float(
                os.environ.get("STREAM_HUB_HEARTBEAT_INTERVAL", "10")
            ),
            discovery_timeout_seconds=float(
                os.environ.get("STREAM_HUB_DISCOVERY_TIMEOUT", "3")
            ),
        )

    @property
    def identity_file(self) -> Path:
        return self.data_dir / "device.json"

    @property
    def playlist_file(self) -> Path:
        return self.data_dir / "playlist.json"

    @property
    def player_state_file(self) -> Path:
        return self.runtime_dir / "player-state.json"
