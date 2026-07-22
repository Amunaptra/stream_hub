from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from .models import DeviceIdentity, PlaylistConfig
from .settings import Settings


class RevisionConflict(ValueError):
    pass


def _atomic_json_write(path: Path, payload: dict, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class DeviceStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._config_lock = Lock()

    def ensure_layout(self) -> None:
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.runtime_dir.mkdir(parents=True, exist_ok=True)

    def load_or_create_identity(self) -> DeviceIdentity:
        self.ensure_layout()
        path = self.settings.identity_file
        if path.exists():
            return DeviceIdentity.model_validate_json(path.read_text(encoding="utf-8"))

        hostname = socket.gethostname().split(".", 1)[0].lower()
        identity = DeviceIdentity(
            device_id=f"{hostname}-{uuid.uuid4().hex[:12]}",
            token=secrets.token_urlsafe(32),
            created_at=datetime.now(timezone.utc),
        )
        _atomic_json_write(path, identity.model_dump(mode="json"), mode=0o640)
        return identity

    def load_playlist(self) -> PlaylistConfig:
        path = self.settings.playlist_file
        if not path.exists():
            playlist = PlaylistConfig()
            _atomic_json_write(path, playlist.model_dump(mode="json"))
            return playlist
        return PlaylistConfig.model_validate_json(path.read_text(encoding="utf-8"))

    def apply_playlist(self, incoming: PlaylistConfig) -> tuple[PlaylistConfig, bool]:
        with self._config_lock:
            current = self.load_playlist()
            if incoming.revision < current.revision:
                raise RevisionConflict(
                    f"incoming revision {incoming.revision} is older than {current.revision}"
                )
            if incoming.revision == current.revision:
                if incoming == current:
                    return current, False
                raise RevisionConflict(
                    f"revision {incoming.revision} already exists with different content"
                )

            path = self.settings.playlist_file
            backup = path.with_suffix(".json.bak")
            if path.exists():
                shutil.copy2(path, backup)
            _atomic_json_write(path, incoming.model_dump(mode="json"))
            return incoming, True

    def restore_playlist_backup(self) -> PlaylistConfig:
        path = self.settings.playlist_file
        backup = path.with_suffix(".json.bak")
        if not backup.exists():
            raise FileNotFoundError("playlist backup does not exist")
        restored = PlaylistConfig.model_validate_json(backup.read_text(encoding="utf-8"))
        _atomic_json_write(path, restored.model_dump(mode="json"))
        return restored

    def command_result(self, command_id: str) -> tuple[bool, str] | None:
        path = self.settings.command_results_file
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            result = data.get(command_id)
            if not result:
                return None
            return bool(result["ok"]), str(result["message"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save_command_result(self, command_id: str, ok: bool, message: str) -> None:
        path = self.settings.command_results_file
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            data = {}
        data[command_id] = {"ok": ok, "message": message[:500]}
        if len(data) > 100:
            data = dict(list(data.items())[-100:])
        _atomic_json_write(path, data)
