from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from stream_hub_backend.api import create_app
from stream_hub_backend.settings import HubSettings


ADMIN_TOKEN = "admin-token-with-at-least-24-characters"
DEVICE_TOKEN = "device-token-with-at-least-thirty-two-characters"


def payload(device_id: str = "odroid-test-001") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "device_id": device_id,
        "hostname": "stream-test-01",
        "agent_version": "0.1.0",
        "agent_port": 8787,
        "status": {
            "device_id": device_id,
            "hostname": "stream-test-01",
            "ip_addresses": ["192.168.1.31"],
            "player_service": "active",
            "player": {
                "status": "playing",
                "stream_id": "salon-1",
                "url": "http://media/salon-1.m3u8",
                "started_at": now,
                "updated_at": now,
            },
            "config_revision": 4,
            "cpu_percent": 12.0,
            "memory_percent": 30.0,
            "disk_percent": 25.0,
            "disk_free_bytes": 6_000_000_000,
            "log_usage_bytes": 100_000_000,
            "uptime_seconds": 7200,
            "temperature_c": 50.0,
            "timestamp": now,
        },
    }


def make_client(tmp_path):
    settings = HubSettings(
        database_file=tmp_path / "hub.sqlite3",
        admin_token=ADMIN_TOKEN,
        advertise_mdns=False,
    )
    app = create_app(settings)
    return TestClient(app), app


def test_unknown_device_is_auto_discovered_as_pending(tmp_path) -> None:
    client, _ = make_client(tmp_path)
    with client:
        heartbeat = client.post(
            "/api/v1/devices/heartbeat",
            headers={"Authorization": f"Bearer {DEVICE_TOKEN}"},
            json=payload(),
        )
        unauthorized = client.get("/api/v1/devices")
        devices = client.get(
            "/api/v1/devices",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )

    assert heartbeat.status_code == 200
    assert heartbeat.json()["approved"] is False
    assert unauthorized.status_code == 401
    assert devices.status_code == 200
    assert devices.json()[0]["device_id"] == "odroid-test-001"
    assert devices.json()[0]["approved"] is False
    assert devices.json()[0]["online"] is True


def test_device_can_be_approved_and_next_heartbeat_reports_approval(tmp_path) -> None:
    client, _ = make_client(tmp_path)
    admin = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    device = {"Authorization": f"Bearer {DEVICE_TOKEN}"}
    with client:
        client.post("/api/v1/devices/heartbeat", headers=device, json=payload())
        approved = client.post("/api/v1/devices/odroid-test-001/approve", headers=admin)
        heartbeat = client.post(
            "/api/v1/devices/heartbeat", headers=device, json=payload()
        )

    assert approved.status_code == 200
    assert heartbeat.json()["approved"] is True


def test_registered_device_rejects_a_different_token(tmp_path) -> None:
    client, _ = make_client(tmp_path)
    with client:
        first = client.post(
            "/api/v1/devices/heartbeat",
            headers={"Authorization": f"Bearer {DEVICE_TOKEN}"},
            json=payload(),
        )
        rejected = client.post(
            "/api/v1/devices/heartbeat",
            headers={"Authorization": "Bearer a-different-device-token-that-is-long-enough"},
            json=payload(),
        )

    assert first.status_code == 200
    assert rejected.status_code == 401


def test_heartbeat_rejects_mismatched_device_identity(tmp_path) -> None:
    client, _ = make_client(tmp_path)
    broken = payload()
    broken["status"]["device_id"] = "another-device"
    with client:
        response = client.post(
            "/api/v1/devices/heartbeat",
            headers={"Authorization": f"Bearer {DEVICE_TOKEN}"},
            json=broken,
        )

    assert response.status_code == 400


def test_missing_device_returns_not_found(tmp_path) -> None:
    client, _ = make_client(tmp_path)
    with client:
        response = client.get(
            "/api/v1/devices/missing",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )
    assert response.status_code == 404


def test_device_becomes_offline_after_heartbeat_deadline(tmp_path) -> None:
    client, app = make_client(tmp_path)
    admin = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    device = {"Authorization": f"Bearer {DEVICE_TOKEN}"}
    with client:
        client.post("/api/v1/devices/heartbeat", headers=device, json=payload())
        old = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        with app.state.database.connect() as connection:
            connection.execute(
                "UPDATE devices SET last_seen = ? WHERE device_id = ?",
                (old, "odroid-test-001"),
            )
        response = client.get("/api/v1/devices", headers=admin)

    assert response.status_code == 200
    assert response.json()[0]["online"] is False


def test_approved_device_receives_config_and_reports_completion(tmp_path) -> None:
    client, _ = make_client(tmp_path)
    admin = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    device = {"Authorization": f"Bearer {DEVICE_TOKEN}"}
    with client:
        client.post("/api/v1/devices/heartbeat", headers=device, json=payload())
        denied = client.put(
            "/api/v1/devices/odroid-test-001/config",
            headers=admin,
            json={"default_seconds": 20, "streams": []},
        )
        client.post("/api/v1/devices/odroid-test-001/approve", headers=admin)
        desired = client.put(
            "/api/v1/devices/odroid-test-001/config",
            headers=admin,
            json={
                "default_seconds": 20,
                "streams": [
                    {
                        "id": "new-stream",
                        "enabled": True,
                        "seconds": 30,
                        "url": "http://media/new.m3u8",
                    }
                ],
            },
        )
        heartbeat = client.post(
            "/api/v1/devices/heartbeat", headers=device, json=payload()
        )
        result = client.post(
            "/api/v1/devices/odroid-test-001/config-result",
            headers=device,
            json={"revision": desired.json()["revision"], "ok": True, "message": "applied"},
        )
        inventory = client.get("/api/v1/devices", headers=admin)

    assert denied.status_code == 403
    assert desired.status_code == 200
    assert desired.json()["revision"] == 5
    assert heartbeat.json()["desired_config"]["revision"] == 5
    assert result.status_code == 204
    assert inventory.json()[0]["desired_revision"] == 5
    assert inventory.json()[0]["config_sync_status"] == "applied"


def test_approved_device_receives_reboot_command_and_reports_result(tmp_path) -> None:
    client, _ = make_client(tmp_path)
    admin = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    device = {"Authorization": f"Bearer {DEVICE_TOKEN}"}
    with client:
        client.post("/api/v1/devices/heartbeat", headers=device, json=payload())
        client.post("/api/v1/devices/odroid-test-001/approve", headers=admin)
        queued = client.post(
            "/api/v1/devices/odroid-test-001/commands",
            headers=admin,
            json={"command": "reboot"},
        )
        heartbeat = client.post(
            "/api/v1/devices/heartbeat", headers=device, json=payload()
        )
        command_id = queued.json()["command_id"]
        result = client.post(
            f"/api/v1/devices/odroid-test-001/commands/{command_id}/result",
            headers=device,
            json={"ok": True, "message": "reboot requested"},
        )
        commands = client.get(
            "/api/v1/devices/odroid-test-001/commands", headers=admin
        )

    assert queued.status_code == 200
    assert heartbeat.json()["commands"][0]["command"] == "reboot"
    assert result.status_code == 204
    assert commands.json()[0]["status"] == "completed"
