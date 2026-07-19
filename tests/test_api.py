from __future__ import annotations

from fastapi.testclient import TestClient

from stream_agent.api import create_app
from stream_agent.models import PlayerState
from stream_agent.settings import Settings


class FakeController:
    def __init__(self, restart_ok: bool = True):
        self.restart_ok = restart_ok
        self.restart_calls = 0
        self.reboot_calls = 0

    def restart_player(self):
        self.restart_calls += 1
        return self.restart_ok, "player restarted" if self.restart_ok else "simulated failure"

    def reboot(self):
        self.reboot_calls += 1
        return True, "reboot requested"

    def player_service_status(self):
        return "active"

    def read_player_state(self):
        return PlayerState(status="idle")

    def ip_addresses(self):
        return ["192.168.1.20"]

    def disk_usage(self, _path):
        return 12.5, 8_000_000_000

    def uptime_seconds(self):
        return 3600

    def memory_percent(self):
        return 20.0

    def cpu_percent(self):
        return 10.0

    def journal_usage_bytes(self):
        return 64_000_000

    def temperature_c(self):
        return 48.5

    def recent_logs(self, lines):
        return f"requested={lines}"


def make_client(tmp_path, restart_ok: bool = True):
    settings = Settings(data_dir=tmp_path / "data", runtime_dir=tmp_path / "run")
    controller = FakeController(restart_ok=restart_ok)
    app = create_app(settings=settings, controller=controller)
    token = app.state.identity.token
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    return client, headers, controller


def test_healthz_is_available_without_device_token(tmp_path) -> None:
    client, _, _ = make_client(tmp_path)
    assert client.get("/healthz").json() == {"ok": True}


def test_device_api_requires_token(tmp_path) -> None:
    client, _, _ = make_client(tmp_path)
    assert client.get("/api/v1/info").status_code == 401


def test_info_and_status_report_stable_device_id(tmp_path) -> None:
    client, headers, _ = make_client(tmp_path)

    info = client.get("/api/v1/info", headers=headers)
    status = client.get("/api/v1/status", headers=headers)

    assert info.status_code == 200
    assert status.status_code == 200
    assert info.json()["device_id"] == status.json()["device_id"]
    assert status.json()["disk_free_bytes"] == 8_000_000_000
    assert status.json()["log_usage_bytes"] == 64_000_000



def test_config_apply_restarts_player_and_is_idempotent(tmp_path) -> None:
    client, headers, controller = make_client(tmp_path)
    payload = {
        "revision": 1,
        "default_seconds": 20,
        "streams": [
            {
                "id": "salon-1",
                "enabled": True,
                "seconds": 60,
                "url": "http://media/salon-1.m3u8",
            }
        ],
    }

    first = client.put("/api/v1/config", headers=headers, json=payload)
    second = client.put("/api/v1/config", headers=headers, json=payload)

    assert first.status_code == 200
    assert first.json()["player_restarted"] is True
    assert second.status_code == 200
    assert second.json()["changed"] is False
    assert controller.restart_calls == 1


def test_config_is_rolled_back_when_player_restart_fails(tmp_path) -> None:
    client, headers, _ = make_client(tmp_path, restart_ok=False)
    payload = {"revision": 1, "streams": []}

    response = client.put("/api/v1/config", headers=headers, json=payload)

    assert response.status_code == 503
    assert client.get("/api/v1/config", headers=headers).json()["revision"] == 0


def test_reboot_requires_explicit_confirmation(tmp_path) -> None:
    client, headers, controller = make_client(tmp_path)

    denied = client.post("/api/v1/system/reboot", headers=headers, json={"confirm": False})
    accepted = client.post("/api/v1/system/reboot", headers=headers, json={"confirm": True})

    assert denied.status_code == 400
    assert accepted.status_code == 200
    assert controller.reboot_calls == 1
