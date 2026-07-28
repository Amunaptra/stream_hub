from __future__ import annotations

import hashlib
import subprocess
import sys
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_release_builder_creates_independent_one_command_packages(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "packaging" / "build_packages.py"),
            "--output-dir",
            str(tmp_path),
            "--version",
            "test",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    odroid = tmp_path / "stream-hub-odroid-test.tar.gz"
    hub = tmp_path / "stream-hub-server-test.tar.gz"
    assert odroid.is_file()
    assert hub.is_file()

    with tarfile.open(odroid, "r:gz") as bundle:
        names = set(bundle.getnames())
        installer = bundle.getmember("stream-hub-odroid-test/install.sh")
        wrapper = bundle.extractfile(installer)
        assert wrapper is not None
        wrapper_text = wrapper.read().decode("utf-8")
        assert installer.mode == 0o755
        assert "STREAM_HUB_SOURCE_ROOT" in wrapper_text
        assert "stream-hub-odroid-test/device/agent/stream_agent/main.py" in names
        assert "stream-hub-odroid-test/device/player/stream_player.py" in names
        assert "stream-hub-odroid-test/requirements-device.txt" in names
        assert "stream-hub-odroid-test/MANIFEST.sha256" in names
        assert not any("__pycache__" in name for name in names)

    with tarfile.open(hub, "r:gz") as bundle:
        names = set(bundle.getnames())
        installer = bundle.getmember("stream-hub-server-test/install.sh")
        wrapper = bundle.extractfile(installer)
        assert wrapper is not None
        wrapper_text = wrapper.read().decode("utf-8")
        assert installer.mode == 0o755
        assert "STREAM_HUB_SOURCE_ROOT" in wrapper_text
        assert "stream-hub-server-test/hub/backend/pyproject.toml" in names
        assert "stream-hub-server-test/hub/container/Dockerfile" in names
        assert "stream-hub-server-test/hub/container/compose.truenas.yml" in names
        assert "stream-hub-server-test/hub/container/deploy_truenas.py" in names
        assert "stream-hub-server-test/hub/ui/index.html" in names
        assert "stream-hub-server-test/hub/installer/backup_sqlite.py" in names
        assert "stream-hub-server-test/MANIFEST.sha256" in names
        assert not any("__pycache__" in name for name in names)

    checksum_lines = (tmp_path / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert checksum_lines == [
        f"{sha256(odroid)}  {odroid.name}",
        f"{sha256(hub)}  {hub.name}",
    ]


def test_installers_install_runtime_dependencies_and_accept_package_root() -> None:
    device = (ROOT / "device" / "installer" / "install.sh").read_text(encoding="utf-8")
    hub = (ROOT / "hub" / "installer" / "install.sh").read_text(encoding="utf-8")

    assert "STREAM_HUB_SOURCE_ROOT" in device
    assert "STREAM_HUB_SOURCE_ROOT" in hub
    for dependency in (
        "cloud-guest-utils",
        "curl",
        "ffmpeg",
        "gir1.2-gstreamer-1.0",
        "gstreamer1.0-libav",
        "gstreamer1.0-plugins-bad",
        "gstreamer1.0-plugins-base",
        "gstreamer1.0-plugins-good",
        "gstreamer1.0-tools",
        "mpv",
        "python3-gi",
        "python3-venv",
        "sudo",
    ):
        assert dependency in device
    for dependency in ("curl", "openssl", "python3-venv"):
        assert dependency in hub
    assert '"${INSTALL_ROOT}/venv/bin/pip" install' in device
    assert '"${INSTALL_ROOT}/venv/bin/pip" install' in hub


def test_device_package_supports_ubuntu_2204_python() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.10"' in project


def test_device_installer_supports_static_hub_and_waits_for_agent() -> None:
    installer = (ROOT / "device" / "installer" / "install.sh").read_text(
        encoding="utf-8"
    )
    player = (ROOT / "device" / "player" / "stream_player.py").read_text(
        encoding="utf-8"
    )
    controller = (
        ROOT / "device" / "agent" / "stream_agent" / "system.py"
    ).read_text(encoding="utf-8")
    assert 'readonly HUB_URL="${STREAM_HUB_URL:-}"' in installer
    assert "stream-agent.service.d/hub.conf" in installer
    assert "for _attempt in $(seq 1 20)" in installer
    assert "--force-reinstall" in installer
    assert "--no-cache-dir" in installer
    assert '"${INSTALL_ROOT}/build"' in installer
    assert '"${INSTALL_ROOT}/device/agent/"*.egg-info' in installer
    assert "os.fchmod(fd, 0o640)" in player
    assert "class GstCrossfadeBackend" in player
    assert '"fbdevsink"' in player
    assert '"uridecodebin"' in player
    assert '"compositor"' in player
    assert '["systemctl", "is-active"' in controller


def test_device_package_prepares_golden_image_clones_safely() -> None:
    installer = (ROOT / "device" / "installer" / "install.sh").read_text(
        encoding="utf-8"
    )
    firstboot = (
        ROOT
        / "device"
        / "installer"
        / "firstboot"
        / "stream-hub-clone-firstboot.sh"
    ).read_text(encoding="utf-8")
    unit = (
        ROOT
        / "device"
        / "installer"
        / "systemd"
        / "stream-hub-clone-firstboot.service"
    ).read_text(encoding="utf-8")
    agent_unit = (
        ROOT / "device" / "installer" / "systemd" / "stream-agent.service"
    ).read_text(encoding="utf-8")
    player_unit = (
        ROOT / "device" / "installer" / "systemd" / "stream-player.service"
    ).read_text(encoding="utf-8")

    assert "stream-hub-clone-firstboot.service" in installer
    assert "cloud-guest-utils" in installer
    assert "ConditionPathExists=/etc/stream-hub/golden-image" in unit
    assert "Before=network-pre.target ssh.service stream-agent.service" in unit
    assert "systemd-machine-id-setup" in firstboot
    assert "/var/lib/systemd/random-seed" in firstboot
    assert "ssh-keygen -A" in firstboot
    assert '"${DATA_DIR}/device.json"' in firstboot
    assert 'partition_file="/sys/class/block/${root_block_name}/partition"' in firstboot
    assert 'partition_number="$(<"${partition_file}")"' in firstboot
    assert 'growpart "/dev/${parent_name}" "${partition_number}"' in firstboot
    assert 'resize2fs "${root_device}"' in firstboot
    assert "STREAM_HUB_IMAGE_CAPTURE_KEY" in firstboot
    assert "ConditionPathExists=!/etc/stream-hub/golden-image" in agent_unit
    assert "ConditionPathExists=!/etc/stream-hub/golden-image" in player_unit
    assert "NoNewPrivileges=no" in agent_unit
    for incompatible_option in (
        "ProtectKernelTunables=yes",
        "ProtectKernelModules=yes",
        "ProtectControlGroups=yes",
        "LockPersonality=yes",
    ):
        assert incompatible_option not in agent_unit


def test_truenas_container_is_non_root_persistent_and_bounded() -> None:
    dockerfile = (ROOT / "hub" / "container" / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "hub" / "container" / "compose.truenas.yml").read_text(encoding="utf-8")

    assert "USER 568:568" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "network_mode: host" in compose
    assert 'STREAM_HUB_MDNS: "0"' in compose
    assert "avahi-publish-service" in compose
    assert "/run/dbus/system_bus_socket:/run/dbus/system_bus_socket" in compose
    assert compose.count("disable: true") == 2
    assert "STREAM_HUB_DATABASE: /data/hub.sqlite3" in compose
    assert "backup_sqlite.py" in compose
    assert "max-size: 10m" in compose
    assert 'max-file: "7"' in compose

    deployer = (ROOT / "hub" / "container" / "deploy_truenas.py").read_text(encoding="utf-8")
    assert 'ensure_dataset(f"{args.pool}/stream-hub")' in deployer
    assert 'deployment / "admin-username"' in deployer
    assert 'deployment / "admin-password"' in deployer
    assert 'deployment / "admin-token"' in deployer
    assert "legacy_token.unlink()" in deployer
    assert "os.chmod(path, 0o600)" in deployer
    assert '"app.create"' in deployer
    assert '"app.update"' in deployer
    assert "wait_until_healthy()" in deployer
