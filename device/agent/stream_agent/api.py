from __future__ import annotations

import secrets
import socket
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from . import __version__
from .health import check_playlist
from .models import (
    CommandResult,
    ConfigApplyResult,
    DeviceInfo,
    DeviceStatus,
    HealthItem,
    PlaylistConfig,
    RebootRequest,
)
from .settings import Settings
from .storage import DeviceStore, RevisionConflict
from .system import SystemController


def create_app(
    settings: Settings | None = None,
    controller: SystemController | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    store = DeviceStore(settings)
    identity = store.load_or_create_identity()
    controller = controller or SystemController(settings)

    app = FastAPI(title="Stream Hub Device Agent", version=__version__)
    app.state.settings = settings
    app.state.store = store
    app.state.identity = identity
    app.state.controller = controller

    def require_device_token(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        scheme, _, supplied = (authorization or "").partition(" ")
        valid = scheme.lower() == "bearer" and secrets.compare_digest(
            supplied, identity.token
        )
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="valid device token required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    authenticated = [Depends(require_device_token)]

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/info", response_model=DeviceInfo, dependencies=authenticated)
    def info() -> DeviceInfo:
        return DeviceInfo(
            device_id=identity.device_id,
            hostname=socket.gethostname(),
            agent_version=__version__,
            capabilities=[
                "playlist",
                "player-restart",
                "reboot",
                "stream-health",
                "system-health",
            ],
        )

    @app.get(
        "/api/v1/config",
        response_model=PlaylistConfig,
        dependencies=authenticated,
    )
    def get_config() -> PlaylistConfig:
        return store.load_playlist()

    @app.put(
        "/api/v1/config",
        response_model=ConfigApplyResult,
        dependencies=authenticated,
    )
    def put_config(config: PlaylistConfig) -> ConfigApplyResult:
        try:
            applied, changed = store.apply_playlist(config)
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        if not changed:
            return ConfigApplyResult(
                ok=True,
                message="configuration already applied",
                revision=applied.revision,
                changed=False,
                player_restarted=False,
            )

        restarted, message = controller.restart_player()
        if not restarted:
            store.restore_playlist_backup()
            raise HTTPException(
                status_code=503,
                detail=f"player restart failed; previous configuration restored: {message}",
            )
        return ConfigApplyResult(
            ok=True,
            message="configuration applied",
            revision=applied.revision,
            changed=True,
            player_restarted=True,
        )

    @app.get(
        "/api/v1/status",
        response_model=DeviceStatus,
        dependencies=authenticated,
    )
    def get_status() -> DeviceStatus:
        playlist = store.load_playlist()
        disk_percent, disk_free = controller.disk_usage(settings.data_dir)
        return DeviceStatus(
            device_id=identity.device_id,
            hostname=socket.gethostname(),
            ip_addresses=controller.ip_addresses(),
            player_service=controller.player_service_status(),
            player=controller.read_player_state(),
            config_revision=playlist.revision,
            cpu_percent=controller.cpu_percent(),
            memory_percent=controller.memory_percent(),
            disk_percent=disk_percent,
            disk_free_bytes=disk_free,
            log_usage_bytes=controller.journal_usage_bytes(),
            uptime_seconds=controller.uptime_seconds(),
            temperature_c=controller.temperature_c(),
        )

    @app.get(
        "/api/v1/streams/health",
        response_model=list[HealthItem],
        dependencies=authenticated,
    )
    async def stream_health() -> list[HealthItem]:
        return await check_playlist(store.load_playlist())

    @app.post(
        "/api/v1/player/restart",
        response_model=CommandResult,
        dependencies=authenticated,
    )
    def restart_player() -> CommandResult:
        ok, message = controller.restart_player()
        if not ok:
            raise HTTPException(status_code=503, detail=message)
        return CommandResult(ok=True, message=message)

    @app.post(
        "/api/v1/system/reboot",
        response_model=CommandResult,
        dependencies=authenticated,
    )
    def reboot(request: RebootRequest) -> CommandResult:
        if not request.confirm:
            raise HTTPException(status_code=400, detail="explicit confirmation required")
        ok, message = controller.reboot()
        if not ok:
            raise HTTPException(status_code=503, detail=message)
        return CommandResult(ok=True, message=message)

    @app.get(
        "/api/v1/logs",
        response_class=PlainTextResponse,
        dependencies=authenticated,
    )
    def logs(lines: Annotated[int, Query(ge=20, le=2_000)] = 250) -> str:
        return controller.recent_logs(lines)

    return app
