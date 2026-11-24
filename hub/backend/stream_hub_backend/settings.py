from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HubSettings:
    database_file: Path
    admin_username: str
    admin_password: str
    port: int = 8788
    advertise_mdns: bool = True
    offline_after_seconds: int = 30
    heartbeat_interval_seconds: float = 10.0
    ui_dir: Path | None = None
    secure_cookie: bool = False

    @classmethod
    def from_env(cls) -> "HubSettings":
        username = os.environ.get("STREAM_HUB_ADMIN_USERNAME", "admin").strip()
        password = os.environ.get("STREAM_HUB_ADMIN_PASSWORD", "")
        if len(username) < 3:
            raise RuntimeError("STREAM_HUB_ADMIN_USERNAME must contain at least 3 characters")
        if len(password) < 8:
            raise RuntimeError("STREAM_HUB_ADMIN_PASSWORD must contain at least 8 characters")
        default_ui = Path(__file__).resolve().parents[2] / "ui"
        return cls(
            database_file=Path(
                os.environ.get("STREAM_HUB_DATABASE", "/var/lib/stream-hub/hub.sqlite3")
            ),
            admin_username=username,
            admin_password=password,
            port=int(os.environ.get("STREAM_HUB_PORT", "8788")),
            advertise_mdns=os.environ.get("STREAM_HUB_MDNS", "1") != "0",
            offline_after_seconds=int(os.environ.get("STREAM_HUB_OFFLINE_AFTER", "30")),
            heartbeat_interval_seconds=float(
                os.environ.get("STREAM_HUB_HEARTBEAT_INTERVAL", "10")
            ),
            ui_dir=Path(os.environ.get("STREAM_HUB_UI_DIR", str(default_ui))),
            secure_cookie=os.environ.get("STREAM_HUB_SECURE_COOKIE", "0") == "1",
        )
