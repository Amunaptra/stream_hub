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
    for dependency in ("curl", "ffmpeg", "mpv", "python3-venv", "sudo"):
        assert dependency in device
    for dependency in ("curl", "openssl", "python3-venv"):
        assert dependency in hub
    assert '"${INSTALL_ROOT}/venv/bin/pip" install' in device
    assert '"${INSTALL_ROOT}/venv/bin/pip" install' in hub
