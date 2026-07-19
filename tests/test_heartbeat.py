from __future__ import annotations

import asyncio
import json

import httpx

from stream_agent.heartbeat import HeartbeatWorker
from stream_agent.models import PlayerState
from stream_agent.settings import Settings
from stream_agent.storage import DeviceStore


class HeartbeatController:
    def player_service_status(self):
        return "active"

    def read_player_state(self):
        return PlayerState(status="playing", stream_id="salon-1")

    def ip_addresses(self):
        return ["192.168.1.31"]

    def disk_usage(self, _path):
        return 25.0, 6_000_000_000

    def uptime_seconds(self):
        return 7200

    def memory_percent(self):
        return 30.0

    def cpu_percent(self):
        return 12.0

    def journal_usage_bytes(self):
        return 100_000_000

    def temperature_c(self):
        return 50.0


def test_heartbeat_uses_unique_device_token_and_reports_status(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        runtime_dir=tmp_path / "run",
        hub_url="http://hub.local:8788",
    )
    store = DeviceStore(settings)
    identity = store.load_or_create_identity()
    worker = HeartbeatWorker(settings, identity, store, HeartbeatController())
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"ok": True, "approved": False, "heartbeat_interval_seconds": 10},
        )

    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await worker.send_once(client)

    response = asyncio.run(execute())

    assert response is not None
    assert response.approved is False
    assert captured["url"].endswith("/api/v1/devices/heartbeat")
    assert captured["authorization"] == f"Bearer {identity.token}"
    assert captured["payload"]["device_id"] == identity.device_id
    assert captured["payload"]["status"]["disk_free_bytes"] == 6_000_000_000
