from __future__ import annotations

import socket

from .models import DeviceIdentity, DeviceStatus
from .settings import Settings
from .storage import DeviceStore
from .system import SystemController


def collect_status(
    settings: Settings,
    identity: DeviceIdentity,
    store: DeviceStore,
    controller: SystemController,
) -> DeviceStatus:
    playlist = store.load_playlist()
    disk_percent, disk_free = controller.disk_usage(settings.data_dir)
    return DeviceStatus(
        device_id=identity.device_id,
        hostname=socket.gethostname(),
        ip_addresses=controller.ip_addresses(),
        player_service=controller.player_service_status(),
        player=controller.read_player_state(),
        config_revision=playlist.revision,
        cpu_percent=controller.cpu_percent(),
        memory_percent=controller.memory_percent(),
        disk_percent=disk_percent,
        disk_free_bytes=disk_free,
        log_usage_bytes=controller.journal_usage_bytes(),
        uptime_seconds=controller.uptime_seconds(),
        temperature_c=controller.temperature_c(),
    )
