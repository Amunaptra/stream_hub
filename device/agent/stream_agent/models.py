from __future__ import annotations

from datetime import datetime, timezone
from ipaddress import IPv4Address, ip_address
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator


STREAM_URL_SCHEMES = {
    "http",
    "https",
    "rtmp",
    "rtmps",
    "rtsp",
    "rtsps",
    "udp",
    "rtp",
}
MULTICAST_STREAM_SCHEMES = {"udp", "rtp"}


def validate_stream_url(value: str) -> str:
    cleaned = value.strip()
    parts = urlsplit(cleaned)
    scheme = parts.scheme.lower()
    if scheme not in STREAM_URL_SCHEMES:
        raise ValueError(
            "stream URL must use http, https, rtmp, rtmps, rtsp, rtsps, udp or rtp"
        )
    if scheme not in MULTICAST_STREAM_SCHEMES:
        return cleaned

    if parts.password is not None or parts.username not in {None, ""}:
        raise ValueError("UDP/RTP multicast URL must not contain credentials")
    try:
        destination = ip_address(parts.hostname or "")
        port = parts.port
    except ValueError as exc:
        raise ValueError("UDP/RTP multicast URL must contain a valid address and port") from exc
    if not isinstance(destination, IPv4Address) or not destination.is_multicast:
        raise ValueError("UDP/RTP destination must be an IPv4 multicast address")
    if port is None:
        raise ValueError("UDP/RTP multicast URL must contain a port")
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise ValueError("UDP/RTP multicast URL must not contain a path, query or fragment")

    # VLC-style udp://@239.x.x.x:port input is accepted, but MPV/FFmpeg receive
    # a single canonical URL that works for both MPEG-TS/UDP and RTP multicast.
    return f"{scheme}://{destination}:{port}"


class StreamItem(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    enabled: bool = True
    seconds: int = Field(default=20, ge=0, le=86_400)
    url: str = Field(min_length=8, max_length=2_048)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_stream_url(value)


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
    command: Literal["player_restart", "reboot", "hub_url_change"]
    hub_url: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_hub_url_change(self) -> "DeviceCommand":
        if self.command == "hub_url_change":
            if not self.hub_url:
                raise ValueError("hub_url is required for hub_url_change")
            parts = urlsplit(self.hub_url)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.hostname
                or parts.username
                or parts.password
                or parts.path not in {"", "/"}
                or parts.query
                or parts.fragment
            ):
                raise ValueError("hub_url must be an HTTP(S) origin without credentials or path")
            self.hub_url = self.hub_url.rstrip("/")
        elif self.hub_url is not None:
            raise ValueError("hub_url is only valid for hub_url_change")
        return self
