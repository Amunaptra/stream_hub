from __future__ import annotations

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class HubPlayerState(BaseModel):
    status: str = "unknown"
    stream_id: str | None = None
    url: str | None = None
    started_at: datetime | None = None
    updated_at: datetime


class HubDeviceStatus(BaseModel):
    device_id: str
    hostname: str
    ip_addresses: list[str]
    player_service: str
    player: HubPlayerState
    config_revision: int = Field(ge=0)
    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_percent: float
    disk_free_bytes: int
    log_usage_bytes: int
    uptime_seconds: int | None = None
    temperature_c: float | None = None
    timestamp: datetime


class HubHeartbeatPayload(BaseModel):
    device_id: str = Field(min_length=3, max_length=128)
    hostname: str = Field(min_length=1, max_length=255)
    agent_version: str = Field(min_length=1, max_length=40)
    agent_port: int = Field(ge=1, le=65535)
    status: HubDeviceStatus
    reported_config: "HubPlaylistConfig"
    stream_health: list["HubStreamHealth"] = Field(default_factory=list, max_length=50)


class HubHeartbeatResponse(BaseModel):
    ok: bool = True
    approved: bool
    heartbeat_interval_seconds: float
    desired_config: "HubPlaylistConfig | None" = None
    commands: list["HubCommand"] = Field(default_factory=list)


class HubStreamItem(BaseModel):
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


class HubPlaylistDraft(BaseModel):
    default_seconds: int = Field(default=20, ge=0, le=86_400)
    streams: list[HubStreamItem] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_stream_ids(self) -> "HubPlaylistDraft":
        ids = [stream.id for stream in self.streams]
        if len(ids) != len(set(ids)):
            raise ValueError("stream IDs must be unique")
        return self


class HubPlaylistConfig(HubPlaylistDraft):
    revision: int = Field(ge=0)


class HubStreamHealth(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=8, max_length=2_048)
    enabled: bool
    ok: bool
    status_code: int | None = None
    latency_ms: int = Field(ge=0)
    error: str | None = Field(default=None, max_length=500)
    checked_at: datetime


class HubCommand(BaseModel):
    command_id: str
    command: Literal["player_restart", "reboot"]
    created_at: datetime


class HubCommandRequest(BaseModel):
    command: Literal["player_restart", "reboot"]


class HubCommandResult(BaseModel):
    ok: bool
    message: str = Field(max_length=500)


class HubConfigResult(HubCommandResult):
    revision: int = Field(ge=1)


class DeviceRecord(BaseModel):
    device_id: str
    hostname: str
    display_name: str | None = None
    agent_version: str
    agent_port: int
    ip_addresses: list[str]
    player_service: str
    player_status: str
    current_stream_id: str | None = None
    current_stream_url: str | None = None
    config_revision: int
    desired_revision: int | None = None
    config_sync_status: str | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_percent: float
    disk_free_bytes: int
    log_usage_bytes: int
    uptime_seconds: int | None = None
    temperature_c: float | None = None
    approved: bool
    online: bool
    first_seen: datetime
    last_seen: datetime


class ApprovalResult(BaseModel):
    ok: bool
    device_id: str
    approved: bool


class DeviceNameUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class HubCommandRecord(HubCommand):
    device_id: str
    status: str
    delivered_at: datetime | None = None
    completed_at: datetime | None = None
    result_message: str | None = None


class AdminSessionRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class AdminSessionResponse(BaseModel):
    ok: bool = True


class AdminProfile(BaseModel):
    username: str


class AdminCredentialsUpdate(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    new_password: str = Field(min_length=8, max_length=128)
