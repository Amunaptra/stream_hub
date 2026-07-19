from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HubSettings:
    database_file: Path
    admin_token: str
    port: int = 8788
    advertise_mdns: bool = True
    offline_after_seconds: int = 30
    heartbeat_interval_seconds: float = 10.0
    ui_dir: Path | None = None
    secure_cookie: bool = False

    @classmethod
    def from_env(cls) -> "HubSettings":
        token = os.environ.get("STREAM_HUB_ADMIN_TOKEN", "").strip()
        if len(token) < 24:
            raise RuntimeError("STREAM_HUB_ADMIN_TOKEN must contain at least 24 characters")
        default_ui = Path(__file__).resolve().parents[2] / "ui"
        return cls(
            database_file=Path(
                os.environ.get("STREAM_HUB_DATABASE", "/var/lib/stream-hub/hub.sqlite3")
            ),
            admin_token=token,
            port=int(os.environ.get("STREAM_HUB_PORT", "8788")),
            advertise_mdns=os.environ.get("STREAM_HUB_MDNS", "1") != "0",
            offline_after_seconds=int(os.environ.get("STREAM_HUB_OFFLINE_AFTER", "30")),
            heartbeat_interval_seconds=float(
                os.environ.get("STREAM_HUB_HEARTBEAT_INTERVAL", "10")
            ),
            ui_dir=Path(os.environ.get("STREAM_HUB_UI_DIR", str(default_ui))),
            secure_cookie=os.environ.get("STREAM_HUB_SECURE_COOKIE", "0") == "1",
        )
