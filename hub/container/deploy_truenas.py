#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import time
import urllib.request
from pathlib import Path


APP_NAME = "stream-hub"
IMAGE = "stream-hub:0.1.0"
APPS_UID = 568
APPS_GID = 568


def run(command: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def midclt(method: str, *arguments: object, job: bool = False) -> object:
    command = ["midclt", "call"]
    if job:
        command.append("-j")
    command.append(method)
    command.extend(json.dumps(argument) for argument in arguments)
    output = run(command, capture=True)
    return json.loads(output) if output else None


def ensure_dataset(name: str) -> Path:
    datasets = midclt("pool.dataset.query")
    if not any(item["id"] == name for item in datasets):
        midclt("pool.dataset.create", {"name": name})
    mountpoint = Path("/mnt") / name
    mountpoint.mkdir(parents=True, exist_ok=True)
    return mountpoint


def protected_value(path: Path, value_factory) -> str:
    if not path.exists():
        path.write_text(value_factory() + "\n", encoding="utf-8")
    os.chown(path, 0, 0)
    os.chmod(path, 0o600)
    return path.read_text(encoding="utf-8").strip()


def ensure_storage(dataset: Path) -> tuple[Path, Path, str, str]:
    data = dataset / "data"
    backups = dataset / "backups"
    deployment = dataset / "deployment"
    for directory in (data, backups):
        directory.mkdir(parents=True, exist_ok=True)
        os.chown(directory, APPS_UID, APPS_GID)
        os.chmod(directory, 0o750)
    deployment.mkdir(parents=True, exist_ok=True)
    os.chmod(deployment, 0o700)
    username = protected_value(deployment / "admin-username", lambda: "admin")
    password = protected_value(
        deployment / "admin-password", lambda: secrets.token_urlsafe(18)
    )
    legacy_token = deployment / "admin-token"
    if legacy_token.exists():
        legacy_token.unlink()
    return data, backups, username, password


def render_compose(
    template: Path, data: Path, backups: Path, username: str, password: str
) -> str:
    compose = template.read_text(encoding="utf-8")
    return (
        compose.replace(
            "${STREAM_HUB_ADMIN_USERNAME:?administrator username required}", username
        )
        .replace(
            "${STREAM_HUB_ADMIN_PASSWORD:?administrator password required}", password
        )
        .replace("${STREAM_HUB_DATA_PATH:?data path required}", str(data))
        .replace("${STREAM_HUB_BACKUP_PATH:?backup path required}", str(backups))
    )


def deploy(compose: str) -> None:
    apps = midclt("app.query")
    existing = next((item for item in apps if item["id"] == APP_NAME), None)
    if existing:
        midclt(
            "app.update",
            APP_NAME,
            {"custom_compose_config_string": compose},
            job=True,
        )
    else:
        midclt(
            "app.create",
            {
                "app_name": APP_NAME,
                "custom_app": True,
                "custom_compose_config_string": compose,
            },
            job=True,
        )


def wait_until_healthy(timeout_seconds: int = 180) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_state = "unknown"
    while time.monotonic() < deadline:
        apps = midclt("app.query")
        app = next((item for item in apps if item["id"] == APP_NAME), None)
        last_state = app["state"] if app else "missing"
        if last_state == "RUNNING":
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:8788/healthz", timeout=3
                ) as response:
                    if response.status == 200:
                        return
            except OSError:
                pass
        time.sleep(3)
    raise RuntimeError(f"Hub failed health validation; app state={last_state}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy Stream Hub on TrueNAS SCALE")
    parser.add_argument("--pool", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("run as root")

    root = Path(__file__).resolve().parents[2]
    dataset = ensure_dataset(f"{args.pool}/stream-hub")
    data, backups, username, password = ensure_storage(dataset)

    run(
        [
            "docker",
            "build",
            "--pull",
            "-f",
            str(root / "hub/container/Dockerfile"),
            "-t",
            IMAGE,
            str(root),
        ]
    )
    compose = render_compose(
        root / "hub/container/compose.truenas.yml",
        data,
        backups,
        username,
        password,
    )
    deployment_dir = dataset / "deployment"
    rendered = deployment_dir / "compose.yml"
    rendered.write_text(compose, encoding="utf-8")
    os.chown(rendered, 0, 0)
    os.chmod(rendered, 0o600)
    deploy(compose)
    wait_until_healthy()
    print("Stream Hub deployment is healthy")
    print("Dashboard: http://<TRUENAS-IP>:8788/ui/")
    print(f"Administrator username file: {deployment_dir / 'admin-username'}")
    print(f"Administrator password file: {deployment_dir / 'admin-password'}")


if __name__ == "__main__":
    main()
