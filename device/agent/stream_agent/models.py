from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class StreamItem(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    enabled: bool = True
    seconds: int = Field(default=20, ge=0, le=86_400)
    url: str = Field(min_length=8, max_length=2_048)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if not value.lower().startswith(
            ("http://", "https://", "rtmp://", "rtmps://", "rtsp://", "rtsps://")
        ):
            raise ValueError(
                "stream URL must use http, https, rtmp, rtmps, rtsp or rtsps"
            )
        return value


class PlaylistConfig(BaseModel):
    revision: int = Field(default=0, ge=0)
    default_seconds: int = Field(default=20, ge=0, le=86_400)
    streams: list[StreamItem] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_stream_ids(self) -> "PlaylistConfig":
        ids = [stream.id for stream in self.streams]
        if len(ids) != len(set(ids)):
            raise ValueError("stream IDs must be unique")
        return self


class DeviceIdentity(BaseModel):
    device_id: str
    token: str
    created_at: datetime


class DeviceInfo(BaseModel):
    device_id: str
    hostname: str
    agent_version: str
    api_version: Literal["v1"] = "v1"
    capabilities: list[str]


class PlayerState(BaseModel):
    status: str = "unknown"
    stream_id: str | None = None
    url: str | None = None
    started_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeviceStatus(BaseModel):
    device_id: str
    hostname: str
    ip_addresses: list[str]
    player_service: str
    player: PlayerState
    config_revision: int
    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_percent: float
    disk_free_bytes: int
    log_usage_bytes: int
    uptime_seconds: int | None = None
    temperature_c: float | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CommandResult(BaseModel):
    ok: bool
    message: str


class ConfigApplyResult(CommandResult):
    revision: int
    changed: bool
    player_restarted: bool


class RebootRequest(BaseModel):
    confirm: bool = False


class HealthItem(BaseModel):
    id: str
    url: str
    enabled: bool
    ok: bool
    status_code: int | None = None
    latency_ms: int
    error: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HeartbeatPayload(BaseModel):
    device_id: str
    hostname: str
    agent_version: str
    agent_port: int
    status: DeviceStatus
    reported_config: PlaylistConfig
    stream_health: list[HealthItem] = Field(default_factory=list, max_length=50)


class HeartbeatResponse(BaseModel):
    ok: bool
    approved: bool
    heartbeat_interval_seconds: float = 10.0
    desired_config: PlaylistConfig | None = None
    commands: list["DeviceCommand"] = Field(default_factory=list)


class DeviceCommand(BaseModel):
    command_id: str
    command: Literal["player_restart", "reboot"]
    created_at: datetime
