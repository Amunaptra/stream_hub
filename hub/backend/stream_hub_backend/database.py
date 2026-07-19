from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    DeviceRecord,
    HubCommand,
    HubCommandRecord,
    HubHeartbeatPayload,
    HubPlaylistConfig,
    HubPlaylistDraft,
    HubStreamHealth,
)


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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS desired_configs (
                    device_id TEXT PRIMARY KEY REFERENCES devices(device_id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL,
                    config_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_message TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reported_configs (
                    device_id TEXT PRIMARY KEY REFERENCES devices(device_id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL,
                    config_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS commands (
                    command_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    delivered_at TEXT,
                    completed_at TEXT,
                    result_message TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS stream_health (
                    device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
                    stream_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    ok INTEGER NOT NULL,
                    status_code INTEGER,
                    latency_ms INTEGER NOT NULL,
                    error TEXT,
                    checked_at TEXT NOT NULL,
                    PRIMARY KEY (device_id, stream_id)
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
            connection.execute(
                """
                INSERT INTO reported_configs (device_id, revision, config_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    revision=excluded.revision,
                    config_json=excluded.config_json,
                    updated_at=excluded.updated_at
                """,
                (
                    payload.device_id,
                    payload.reported_config.revision,
                    payload.reported_config.model_dump_json(),
                    now,
                ),
            )
            connection.execute(
                "DELETE FROM stream_health WHERE device_id = ?", (payload.device_id,)
            )
            if payload.stream_health:
                connection.executemany(
                    """
                    INSERT INTO stream_health (
                        device_id, stream_id, url, enabled, ok, status_code,
                        latency_ms, error, checked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            payload.device_id,
                            item.id,
                            item.url,
                            int(item.enabled),
                            int(item.ok),
                            item.status_code,
                            item.latency_ms,
                            item.error,
                            item.checked_at.isoformat(),
                        )
                        for item in payload.stream_health
                    ],
                )
            return bool(row["approved"])

    def stream_health(self, device_id: str) -> list[HubStreamHealth]:
        with self.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM devices WHERE device_id = ?", (device_id,)
            ).fetchone()
            if not exists:
                raise DeviceNotFoundError(device_id)
            rows = connection.execute(
                """
                SELECT stream_id, url, enabled, ok, status_code, latency_ms,
                       error, checked_at
                FROM stream_health
                WHERE device_id = ?
                ORDER BY stream_id COLLATE NOCASE
                """,
                (device_id,),
            ).fetchall()
        return [
            HubStreamHealth(
                id=row["stream_id"],
                url=row["url"],
                enabled=bool(row["enabled"]),
                ok=bool(row["ok"]),
                status_code=row["status_code"],
                latency_ms=row["latency_ms"],
                error=row["error"],
                checked_at=datetime.fromisoformat(row["checked_at"]),
            )
            for row in rows
        ]

    def authenticate_device(self, device_id: str, token: str) -> None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT token_hash FROM devices WHERE device_id = ?", (device_id,)
            ).fetchone()
        if not row or not secrets.compare_digest(row["token_hash"], _token_hash(token)):
            raise DeviceAuthenticationError("device token mismatch")

    def require_approved(self, device_id: str, connection: sqlite3.Connection) -> sqlite3.Row:
        row = connection.execute(
            "SELECT approved, config_revision FROM devices WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        if not row:
            raise DeviceNotFoundError(device_id)
        if not row["approved"]:
            raise PermissionError("device approval required")
        return row

    def set_desired_config(
        self, device_id: str, draft: HubPlaylistDraft
    ) -> HubPlaylistConfig:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            device = self.require_approved(device_id, connection)
            previous = connection.execute(
                "SELECT revision FROM desired_configs WHERE device_id = ?", (device_id,)
            ).fetchone()
            revision = max(
                int(device["config_revision"]),
                int(previous["revision"]) if previous else 0,
            ) + 1
            config = HubPlaylistConfig(revision=revision, **draft.model_dump())
            connection.execute(
                """
                INSERT INTO desired_configs (
                    device_id, revision, config_json, status, result_message, updated_at
                ) VALUES (?, ?, ?, 'pending', NULL, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    revision=excluded.revision,
                    config_json=excluded.config_json,
                    status='pending',
                    result_message=NULL,
                    updated_at=excluded.updated_at
                """,
                (device_id, revision, config.model_dump_json(), now),
            )
        return config

    def desired_config_for(self, device_id: str, reported_revision: int) -> HubPlaylistConfig | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT revision, config_json, status FROM desired_configs WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            if not row or row["status"] in {"applied", "failed"}:
                return None
            if int(row["revision"]) <= reported_revision:
                connection.execute(
                    "UPDATE desired_configs SET status = 'applied' WHERE device_id = ?",
                    (device_id,),
                )
                return None
            connection.execute(
                "UPDATE desired_configs SET status = 'delivered' WHERE device_id = ?",
                (device_id,),
            )
        return HubPlaylistConfig.model_validate_json(row["config_json"])

    def effective_config(self, device_id: str) -> HubPlaylistConfig:
        with self.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM devices WHERE device_id = ?", (device_id,)
            ).fetchone()
            if not exists:
                raise DeviceNotFoundError(device_id)
            desired = connection.execute(
                "SELECT config_json FROM desired_configs WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            if desired:
                return HubPlaylistConfig.model_validate_json(desired["config_json"])
            reported = connection.execute(
                "SELECT config_json FROM reported_configs WHERE device_id = ?",
                (device_id,),
            ).fetchone()
        if not reported:
            return HubPlaylistConfig(revision=0)
        return HubPlaylistConfig.model_validate_json(reported["config_json"])

    def complete_config(self, device_id: str, revision: int, ok: bool, message: str) -> None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT revision FROM desired_configs WHERE device_id = ?", (device_id,)
            ).fetchone()
            if not row or int(row["revision"]) != revision:
                raise DeviceNotFoundError(f"config revision {revision}")
            connection.execute(
                """
                UPDATE desired_configs
                SET status = ?, result_message = ?, updated_at = ?
                WHERE device_id = ?
                """,
                (
                    "applied" if ok else "failed",
                    message[:500],
                    datetime.now(timezone.utc).isoformat(),
                    device_id,
                ),
            )

    def enqueue_command(self, device_id: str, command: str) -> HubCommandRecord:
        now = datetime.now(timezone.utc)
        command_id = uuid.uuid4().hex
        with self.connect() as connection:
            self.require_approved(device_id, connection)
            connection.execute(
                """
                INSERT INTO commands (
                    command_id, device_id, command, status, created_at
                ) VALUES (?, ?, ?, 'queued', ?)
                """,
                (command_id, device_id, command, now.isoformat()),
            )
        return HubCommandRecord(
            command_id=command_id,
            device_id=device_id,
            command=command,
            status="queued",
            created_at=now,
        )

    def deliver_commands(self, device_id: str) -> list[HubCommand]:
        delivered_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT command_id, command, created_at
                FROM commands
                WHERE device_id = ? AND status IN ('queued', 'delivered')
                ORDER BY created_at
                LIMIT 10
                """,
                (device_id,),
            ).fetchall()
            if rows:
                connection.executemany(
                    "UPDATE commands SET status = 'delivered', delivered_at = ? WHERE command_id = ?",
                    [(delivered_at, row["command_id"]) for row in rows],
                )
        return [
            HubCommand(
                command_id=row["command_id"],
                command=row["command"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def complete_command(
        self, device_id: str, command_id: str, ok: bool, message: str
    ) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE commands
                SET status = ?, completed_at = ?, result_message = ?
                WHERE command_id = ? AND device_id = ?
                """,
                (
                    "completed" if ok else "failed",
                    datetime.now(timezone.utc).isoformat(),
                    message[:500],
                    command_id,
                    device_id,
                ),
            )
            if cursor.rowcount == 0:
                raise DeviceNotFoundError(command_id)

    def list_commands(self, device_id: str) -> list[HubCommandRecord]:
        with self.connect() as connection:
            self.require_approved(device_id, connection)
            rows = connection.execute(
                "SELECT * FROM commands WHERE device_id = ? ORDER BY created_at DESC",
                (device_id,),
            ).fetchall()
        return [
            HubCommandRecord(
                command_id=row["command_id"],
                device_id=row["device_id"],
                command=row["command"],
                status=row["status"],
                created_at=datetime.fromisoformat(row["created_at"]),
                delivered_at=datetime.fromisoformat(row["delivered_at"])
                if row["delivered_at"]
                else None,
                completed_at=datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None,
                result_message=row["result_message"],
            )
            for row in rows
        ]

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
                """
                SELECT d.*, c.revision AS desired_revision, c.status AS config_sync_status
                FROM devices d
                LEFT JOIN desired_configs c ON c.device_id = d.device_id
                WHERE d.device_id = ?
                """,
                (device_id,),
            ).fetchone()
        if not row:
            raise DeviceNotFoundError(device_id)
        return self._record(row, offline_after_seconds)

    def list(self, offline_after_seconds: int) -> list[DeviceRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT d.*, c.revision AS desired_revision, c.status AS config_sync_status
                FROM devices d
                LEFT JOIN desired_configs c ON c.device_id = d.device_id
                ORDER BY d.hostname COLLATE NOCASE, d.device_id
                """
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
            desired_revision=row["desired_revision"],
            config_sync_status=row["config_sync_status"],
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
