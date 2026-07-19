from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import DeviceRecord, HubHeartbeatPayload


class DeviceAuthenticationError(ValueError):
    pass


class DeviceNotFoundError(KeyError):
    pass


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class HubDatabase:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL,
                    hostname TEXT NOT NULL,
                    agent_version TEXT NOT NULL,
                    agent_port INTEGER NOT NULL,
                    ip_addresses_json TEXT NOT NULL,
                    player_service TEXT NOT NULL,
                    player_status TEXT NOT NULL,
                    current_stream_id TEXT,
                    current_stream_url TEXT,
                    config_revision INTEGER NOT NULL,
                    cpu_percent REAL,
                    memory_percent REAL,
                    disk_percent REAL NOT NULL,
                    disk_free_bytes INTEGER NOT NULL,
                    log_usage_bytes INTEGER NOT NULL,
                    uptime_seconds INTEGER,
                    temperature_c REAL,
                    approved INTEGER NOT NULL DEFAULT 0,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    raw_status_json TEXT NOT NULL
                )
                """
            )

    def upsert_heartbeat(self, payload: HubHeartbeatPayload, token: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        supplied_hash = _token_hash(token)
        status = payload.status
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT token_hash, approved FROM devices WHERE device_id = ?",
                (payload.device_id,),
            ).fetchone()
            if existing and not secrets.compare_digest(existing["token_hash"], supplied_hash):
                raise DeviceAuthenticationError("device token mismatch")

            values = (
                payload.device_id,
                supplied_hash,
                payload.hostname,
                payload.agent_version,
                payload.agent_port,
                json.dumps(status.ip_addresses),
                status.player_service,
                status.player.status,
                status.player.stream_id,
                status.player.url,
                status.config_revision,
                status.cpu_percent,
                status.memory_percent,
                status.disk_percent,
                status.disk_free_bytes,
                status.log_usage_bytes,
                status.uptime_seconds,
                status.temperature_c,
                now,
                now,
                status.model_dump_json(),
            )
            connection.execute(
                """
                INSERT INTO devices (
                    device_id, token_hash, hostname, agent_version, agent_port,
                    ip_addresses_json, player_service, player_status,
                    current_stream_id, current_stream_url, config_revision,
                    cpu_percent, memory_percent, disk_percent, disk_free_bytes,
                    log_usage_bytes, uptime_seconds, temperature_c,
                    first_seen, last_seen, raw_status_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    hostname=excluded.hostname,
                    agent_version=excluded.agent_version,
                    agent_port=excluded.agent_port,
                    ip_addresses_json=excluded.ip_addresses_json,
                    player_service=excluded.player_service,
                    player_status=excluded.player_status,
                    current_stream_id=excluded.current_stream_id,
                    current_stream_url=excluded.current_stream_url,
                    config_revision=excluded.config_revision,
                    cpu_percent=excluded.cpu_percent,
                    memory_percent=excluded.memory_percent,
                    disk_percent=excluded.disk_percent,
                    disk_free_bytes=excluded.disk_free_bytes,
                    log_usage_bytes=excluded.log_usage_bytes,
                    uptime_seconds=excluded.uptime_seconds,
                    temperature_c=excluded.temperature_c,
                    last_seen=excluded.last_seen,
                    raw_status_json=excluded.raw_status_json
                """,
                values,
            )
            row = connection.execute(
                "SELECT approved FROM devices WHERE device_id = ?", (payload.device_id,)
            ).fetchone()
            return bool(row["approved"])

    def approve(self, device_id: str) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE devices SET approved = 1 WHERE device_id = ?", (device_id,)
            )
            if cursor.rowcount == 0:
                raise DeviceNotFoundError(device_id)

    def get(self, device_id: str, offline_after_seconds: int) -> DeviceRecord:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM devices WHERE device_id = ?", (device_id,)
            ).fetchone()
        if not row:
            raise DeviceNotFoundError(device_id)
        return self._record(row, offline_after_seconds)

    def list(self, offline_after_seconds: int) -> list[DeviceRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM devices ORDER BY hostname COLLATE NOCASE, device_id"
            ).fetchall()
        return [self._record(row, offline_after_seconds) for row in rows]

    @staticmethod
    def _record(row: sqlite3.Row, offline_after_seconds: int) -> DeviceRecord:
        last_seen = datetime.fromisoformat(row["last_seen"])
        age = (datetime.now(timezone.utc) - last_seen).total_seconds()
        return DeviceRecord(
            device_id=row["device_id"],
            hostname=row["hostname"],
            agent_version=row["agent_version"],
            agent_port=row["agent_port"],
            ip_addresses=json.loads(row["ip_addresses_json"]),
            player_service=row["player_service"],
            player_status=row["player_status"],
            current_stream_id=row["current_stream_id"],
            current_stream_url=row["current_stream_url"],
            config_revision=row["config_revision"],
            cpu_percent=row["cpu_percent"],
            memory_percent=row["memory_percent"],
            disk_percent=row["disk_percent"],
            disk_free_bytes=row["disk_free_bytes"],
            log_usage_bytes=row["log_usage_bytes"],
            uptime_seconds=row["uptime_seconds"],
            temperature_c=row["temperature_c"],
            approved=bool(row["approved"]),
            online=age <= offline_after_seconds,
            first_seen=datetime.fromisoformat(row["first_seen"]),
            last_seen=last_seen,
        )
