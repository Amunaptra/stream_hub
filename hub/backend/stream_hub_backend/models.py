from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


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


class HubHeartbeatResponse(BaseModel):
    ok: bool = True
    approved: bool
    heartbeat_interval_seconds: float


class DeviceRecord(BaseModel):
    device_id: str
    hostname: str
    agent_version: str
    agent_port: int
    ip_addresses: list[str]
    player_service: str
    player_status: str
    current_stream_id: str | None = None
    current_stream_url: str | None = None
    config_revision: int
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
