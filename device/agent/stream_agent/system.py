from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

from .models import PlayerState
from .settings import Settings


class SystemController:
    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def _run(command: list[str], timeout: float = 10) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def player_service_status(self) -> str:
        result = self._run(
            ["sudo", "-n", "systemctl", "is-active", self.settings.player_service]
        )
        return result.stdout.strip() or "unknown"

    def restart_player(self) -> tuple[bool, str]:
        result = self._run(
            ["sudo", "-n", "systemctl", "restart", self.settings.player_service],
            timeout=20,
        )
        if result.returncode:
            return False, (result.stderr or result.stdout or "restart failed").strip()
        return True, "player restarted"

    def reboot(self) -> tuple[bool, str]:
        result = self._run(["sudo", "-n", "systemctl", "reboot"], timeout=5)
        if result.returncode:
            return False, (result.stderr or result.stdout or "reboot failed").strip()
        return True, "reboot requested"

    def recent_logs(self, lines: int) -> str:
        lines = max(20, min(lines, 2_000))
        result = self._run(
            [
                "journalctl",
                "--no-pager",
                "--output=short-iso",
                "-n",
                str(lines),
                "-u",
                self.settings.player_service,
            ],
            timeout=10,
        )
        return result.stdout[-512_000:]

    def read_player_state(self) -> PlayerState:
        try:
            raw = self.settings.player_state_file.read_text(encoding="utf-8")
            return PlayerState.model_validate_json(raw)
        except (OSError, ValueError, json.JSONDecodeError):
            return PlayerState()

    @staticmethod
    def ip_addresses() -> list[str]:
        addresses: set[str] = set()
        try:
            for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                address = item[4][0]
                if not address.startswith("127."):
                    addresses.add(address)
        except OSError:
            pass
        return sorted(addresses)

    @staticmethod
    def disk_usage(path: Path) -> tuple[float, int]:
        usage = shutil.disk_usage(path)
        percent = round((usage.used / usage.total) * 100, 2) if usage.total else 0.0
        return percent, usage.free

    @staticmethod
    def uptime_seconds() -> int | None:
        try:
            return int(float(Path("/proc/uptime").read_text().split()[0]))
        except (OSError, ValueError, IndexError):
            return None

    @staticmethod
    def memory_percent() -> float | None:
        try:
            values: dict[str, int] = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, value = line.split(":", 1)
                values[key] = int(value.strip().split()[0])
            total = values["MemTotal"]
            available = values["MemAvailable"]
            return round(((total - available) / total) * 100, 2)
        except (OSError, ValueError, KeyError, IndexError):
            return None

    @staticmethod
    def cpu_percent() -> float | None:
        def snapshot() -> tuple[int, int]:
            values = [int(value) for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            return sum(values), idle

        try:
            total_one, idle_one = snapshot()
            time.sleep(0.1)
            total_two, idle_two = snapshot()
            total_delta = total_two - total_one
            idle_delta = idle_two - idle_one
            if total_delta <= 0:
                return None
            return round(((total_delta - idle_delta) / total_delta) * 100, 2)
        except (OSError, ValueError, IndexError):
            return None

    @staticmethod
    def journal_usage_bytes() -> int:
        total = 0
        for root in (Path("/var/log/journal"), Path("/run/log/journal")):
            if not root.exists():
                continue
            try:
                for path in root.rglob("*"):
                    if path.is_file():
                        total += path.stat().st_size
            except OSError:
                continue
        return total

    @staticmethod
    def temperature_c() -> float | None:
        candidates = sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
        for candidate in candidates:
            try:
                value = float(candidate.read_text().strip())
                return round(value / 1000 if value > 200 else value, 1)
            except (OSError, ValueError):
                continue
        return None
