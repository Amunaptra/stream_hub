from __future__ import annotations

import asyncio
import logging
import socket

import httpx

from . import __version__
from .discovery import discover_hub
from .health import StreamHealthMonitor
from .models import DeviceIdentity, HeartbeatPayload, HeartbeatResponse
from .settings import Settings
from .storage import DeviceStore
from .system import SystemController
from .telemetry import collect_status


LOGGER = logging.getLogger("stream-agent.heartbeat")


class HeartbeatWorker:
    def __init__(
        self,
        settings: Settings,
        identity: DeviceIdentity,
        store: DeviceStore,
        controller: SystemController,
        health_monitor: StreamHealthMonitor | None = None,
    ):
        self.settings = settings
        self.identity = identity
        self.store = store
        self.controller = controller
        self.health_monitor = health_monitor
        self.hub_url = settings.hub_url
        self._last_error: str | None = None

    async def resolve_hub(self) -> str | None:
        if self.hub_url:
            return self.hub_url
        self.hub_url = await asyncio.to_thread(
            discover_hub, self.settings.discovery_timeout_seconds
        )
        if self.hub_url:
            LOGGER.info("discovered Hub at %s", self.hub_url)
        return self.hub_url

    def payload(self) -> HeartbeatPayload:
        status = collect_status(
            self.settings, self.identity, self.store, self.controller
        )
        return HeartbeatPayload(
            device_id=self.identity.device_id,
            hostname=socket.gethostname(),
            agent_version=__version__,
            agent_port=self.settings.agent_port,
            status=status,
            reported_config=self.store.load_playlist(),
            stream_health=(
                self.health_monitor.snapshot() if self.health_monitor else []
            ),
        )

    async def send_once(self, client: httpx.AsyncClient) -> HeartbeatResponse | None:
        hub_url = await self.resolve_hub()
        if not hub_url:
            return None
        response = await client.post(
            f"{hub_url.rstrip('/')}/api/v1/devices/heartbeat",
            headers={"Authorization": f"Bearer {self.identity.token}"},
            json=self.payload().model_dump(mode="json"),
        )
        response.raise_for_status()
        result = HeartbeatResponse.model_validate(response.json())
        if result.approved:
            await self.process_response(client, hub_url, result)
        return result

    async def _report_config(
        self,
        client: httpx.AsyncClient,
        hub_url: str,
        revision: int,
        ok: bool,
        message: str,
    ) -> None:
        response = await client.post(
            f"{hub_url.rstrip('/')}/api/v1/devices/{self.identity.device_id}/config-result",
            headers={"Authorization": f"Bearer {self.identity.token}"},
            json={"revision": revision, "ok": ok, "message": message[:500]},
        )
        response.raise_for_status()

    async def _report_command(
        self,
        client: httpx.AsyncClient,
        hub_url: str,
        command_id: str,
        ok: bool,
        message: str,
    ) -> None:
        response = await client.post(
            f"{hub_url.rstrip('/')}/api/v1/devices/{self.identity.device_id}/commands/{command_id}/result",
            headers={"Authorization": f"Bearer {self.identity.token}"},
            json={"ok": ok, "message": message[:500]},
        )
        response.raise_for_status()

    async def process_response(
        self,
        client: httpx.AsyncClient,
        hub_url: str,
        result: HeartbeatResponse,
    ) -> None:
        if result.desired_config:
            config = result.desired_config
            try:
                _, changed = self.store.apply_playlist(config)
                if changed:
                    restarted, message = self.controller.restart_player()
                    if not restarted:
                        self.store.restore_playlist_backup()
                        raise RuntimeError(message)
                await self._report_config(
                    client, hub_url, config.revision, True, "configuration applied"
                )
            except Exception as exc:
                await self._report_config(
                    client,
                    hub_url,
                    config.revision,
                    False,
                    f"configuration failed: {type(exc).__name__}",
                )

        for command in result.commands:
            cached = self.store.command_result(command.command_id)
            if cached:
                ok, message = cached
            elif command.command == "player_restart":
                ok, message = self.controller.restart_player()
                self.store.save_command_result(command.command_id, ok, message)
            else:
                ok, message = self.controller.reboot()
                self.store.save_command_result(command.command_id, ok, message)
            await self._report_command(
                client, hub_url, command.command_id, ok, message
            )

    async def run(self) -> None:
        timeout = httpx.Timeout(5.0, connect=2.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            while True:
                delay = self.settings.heartbeat_interval_seconds
                try:
                    result = await self.send_once(client)
                    if result:
                        delay = result.heartbeat_interval_seconds
                    if self._last_error is not None:
                        LOGGER.info("Hub heartbeat recovered")
                    self._last_error = None
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    error = type(exc).__name__
                    if error != self._last_error:
                        LOGGER.warning("Hub heartbeat failed: %s", error)
                    self._last_error = error
                    self.hub_url = self.settings.hub_url
                await asyncio.sleep(max(2.0, delay))
