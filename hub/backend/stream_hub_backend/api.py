from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status

from . import __version__
from .database import (
    DeviceAuthenticationError,
    DeviceNotFoundError,
    HubDatabase,
)
from .discovery import HubAdvertiser
from .models import (
    ApprovalResult,
    DeviceRecord,
    HubHeartbeatPayload,
    HubHeartbeatResponse,
)
from .settings import HubSettings


LOGGER = logging.getLogger("stream-hub")


def create_app(settings: HubSettings) -> FastAPI:
    database = HubDatabase(settings.database_file)
    advertiser: HubAdvertiser | None = None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        nonlocal advertiser
        database.initialize()
        if settings.advertise_mdns:
            try:
                advertiser = HubAdvertiser(settings.port)
                advertiser.start()
            except Exception as exc:
                LOGGER.warning("mDNS advertisement unavailable: %s", type(exc).__name__)
                if advertiser:
                    advertiser.close()
                advertiser = None
        try:
            yield
        finally:
            if advertiser:
                advertiser.close()

    app = FastAPI(title="Stream Hub", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.database = database

    def require_admin_token(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        scheme, _, token = (authorization or "").partition(" ")
        valid = scheme.lower() == "bearer" and secrets.compare_digest(
            token, settings.admin_token
        )
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="valid Hub administrator token required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    admin = [Depends(require_admin_token)]

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.post(
        "/api/v1/devices/heartbeat",
        response_model=HubHeartbeatResponse,
    )
    def heartbeat(
        payload: HubHeartbeatPayload,
        authorization: Annotated[str | None, Header()] = None,
    ) -> HubHeartbeatResponse:
        if payload.device_id != payload.status.device_id:
            raise HTTPException(status_code=400, detail="device ID mismatch")
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or len(token) < 32:
            raise HTTPException(status_code=401, detail="valid device token required")
        try:
            approved = database.upsert_heartbeat(payload, token)
        except DeviceAuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return HubHeartbeatResponse(
            approved=approved,
            heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
        )

    @app.get(
        "/api/v1/devices",
        response_model=list[DeviceRecord],
        dependencies=admin,
    )
    def devices() -> list[DeviceRecord]:
        return database.list(settings.offline_after_seconds)

    @app.get(
        "/api/v1/devices/{device_id}",
        response_model=DeviceRecord,
        dependencies=admin,
    )
    def device(device_id: str) -> DeviceRecord:
        try:
            return database.get(device_id, settings.offline_after_seconds)
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="device not found") from exc

    @app.post(
        "/api/v1/devices/{device_id}/approve",
        response_model=ApprovalResult,
        dependencies=admin,
    )
    def approve(device_id: str) -> ApprovalResult:
        try:
            database.approve(device_id)
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="device not found") from exc
        return ApprovalResult(ok=True, device_id=device_id, approved=True)

    return app
