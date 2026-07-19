from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .database import (
    DeviceAuthenticationError,
    DeviceNotFoundError,
    HubDatabase,
)
from .discovery import HubAdvertiser
from .models import (
    ApprovalResult,
    AdminSessionRequest,
    AdminSessionResponse,
    DeviceRecord,
    HubCommandRecord,
    HubCommandRequest,
    HubCommandResult,
    HubConfigResult,
    HubHeartbeatPayload,
    HubHeartbeatResponse,
    HubPlaylistConfig,
    HubPlaylistDraft,
    HubStreamHealth,
)
from .settings import HubSettings


LOGGER = logging.getLogger("stream-hub")
SESSION_COOKIE = "stream_hub_session"
SESSION_SECONDS = 12 * 60 * 60


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

    def make_session() -> str:
        payload = f"admin|{int(time.time()) + SESSION_SECONDS}".encode("ascii")
        encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        signature = hmac.new(
            settings.admin_token.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return f"{encoded}.{signature}"

    def verify_session(value: str) -> bool:
        try:
            encoded, signature = value.split(".", 1)
            expected = hmac.new(
                settings.admin_token.encode("utf-8"),
                encoded.encode("ascii"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return False
            padding = "=" * ((4 - len(encoded) % 4) % 4)
            role, expires = base64.urlsafe_b64decode(encoded + padding).decode("ascii").split("|", 1)
            return role == "admin" and int(expires) > int(time.time())
        except (ValueError, TypeError):
            return False

    def require_admin_token(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        scheme, _, token = (authorization or "").partition(" ")
        bearer_valid = scheme.lower() == "bearer" and secrets.compare_digest(
            token, settings.admin_token
        )
        cookie_valid = verify_session(request.cookies.get(SESSION_COOKIE, ""))
        if not (bearer_valid or cookie_valid):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="valid Hub administrator token required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    admin = [Depends(require_admin_token)]

    def device_token(authorization: str | None) -> str:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or len(token) < 32:
            raise HTTPException(status_code=401, detail="valid device token required")
        return token

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/session", response_model=AdminSessionResponse)
    def login(body: AdminSessionRequest, response: Response) -> AdminSessionResponse:
        if not secrets.compare_digest(body.token, settings.admin_token):
            raise HTTPException(status_code=401, detail="invalid administrator token")
        response.set_cookie(
            SESSION_COOKIE,
            make_session(),
            max_age=SESSION_SECONDS,
            httponly=True,
            samesite="strict",
            secure=settings.secure_cookie,
        )
        return AdminSessionResponse()

    @app.delete("/api/v1/session", response_model=AdminSessionResponse)
    def logout(response: Response) -> AdminSessionResponse:
        response.delete_cookie(SESSION_COOKIE)
        return AdminSessionResponse()

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
        if payload.reported_config.revision != payload.status.config_revision:
            raise HTTPException(status_code=400, detail="config revision mismatch")
        token = device_token(authorization)
        try:
            approved = database.upsert_heartbeat(payload, token)
        except DeviceAuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        desired_config = None
        commands = []
        if approved:
            desired_config = database.desired_config_for(
                payload.device_id, payload.status.config_revision
            )
            commands = database.deliver_commands(payload.device_id)
        return HubHeartbeatResponse(
            approved=approved,
            heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
            desired_config=desired_config,
            commands=commands,
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

    @app.get(
        "/api/v1/devices/{device_id}/stream-health",
        response_model=list[HubStreamHealth],
        dependencies=admin,
    )
    def stream_health(device_id: str) -> list[HubStreamHealth]:
        try:
            return database.stream_health(device_id)
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

    @app.put(
        "/api/v1/devices/{device_id}/config",
        response_model=HubPlaylistConfig,
        dependencies=admin,
    )
    def set_config(device_id: str, draft: HubPlaylistDraft) -> HubPlaylistConfig:
        try:
            return database.set_desired_config(device_id, draft)
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="device not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.get(
        "/api/v1/devices/{device_id}/config",
        response_model=HubPlaylistConfig,
        dependencies=admin,
    )
    def get_config(device_id: str) -> HubPlaylistConfig:
        try:
            return database.effective_config(device_id)
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="device not found") from exc

    @app.post(
        "/api/v1/devices/{device_id}/config-result",
        status_code=204,
    )
    def config_result(
        device_id: str,
        result: HubConfigResult,
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        token = device_token(authorization)
        try:
            database.authenticate_device(device_id, token)
            database.complete_config(device_id, result.revision, result.ok, result.message)
        except DeviceAuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="config not found") from exc

    @app.post(
        "/api/v1/devices/{device_id}/commands",
        response_model=HubCommandRecord,
        dependencies=admin,
    )
    def enqueue_command(
        device_id: str, request: HubCommandRequest
    ) -> HubCommandRecord:
        try:
            return database.enqueue_command(device_id, request.command)
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="device not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.get(
        "/api/v1/devices/{device_id}/commands",
        response_model=list[HubCommandRecord],
        dependencies=admin,
    )
    def commands(device_id: str) -> list[HubCommandRecord]:
        try:
            return database.list_commands(device_id)
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="device not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post(
        "/api/v1/devices/{device_id}/commands/{command_id}/result",
        status_code=204,
    )
    def command_result(
        device_id: str,
        command_id: str,
        result: HubCommandResult,
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        token = device_token(authorization)
        try:
            database.authenticate_device(device_id, token)
            database.complete_command(
                device_id, command_id, result.ok, result.message
            )
        except DeviceAuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="command not found") from exc

    if settings.ui_dir and settings.ui_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=settings.ui_dir, html=True), name="ui")

        @app.get("/", include_in_schema=False)
        def root() -> RedirectResponse:
            return RedirectResponse("/ui/")

    return app
