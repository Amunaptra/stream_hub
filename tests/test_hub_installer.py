from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_backup_creates_consistent_copy_and_limits_retention(tmp_path) -> None:
    database = tmp_path / "hub.sqlite3"
    backups = tmp_path / "backups"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES ('working')")

    backups.mkdir()
    for index in range(9):
        old = backups / f"hub-202607{index + 1:02d}T000000Z.sqlite3"
        old.write_bytes(b"old")

    env = {
        **os.environ,
        "STREAM_HUB_DATABASE": str(database),
        "STREAM_HUB_BACKUP_DIR": str(backups),
    }
    result = subprocess.run(
        [sys.executable, str(ROOT / "hub" / "installer" / "backup_sqlite.py")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    remaining = sorted(backups.glob("hub-*.sqlite3"))
    assert len(remaining) <= 7
    valid = [path for path in remaining if path.stat().st_size > 3]
    assert len(valid) == 1
    with sqlite3.connect(valid[0]) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "working"


def test_installer_preserves_database_credentials_and_bounds_logs() -> None:
    installer = (ROOT / "hub" / "installer" / "install.sh").read_text(encoding="utf-8")
    journal = (ROOT / "hub" / "installer" / "journald.conf").read_text(encoding="utf-8")

    assert 'if [[ ! -f "${ENV_FILE}" ]]' in installer
    assert "rm -rf \"${DATA_DIR}\"" not in installer
    assert "chpasswd" not in installer
    assert "stream-hub-backup.timer" in installer
    assert "SystemMaxUse=1G" in journal
    assert "SystemKeepFree=2G" in journal
    assert "MaxRetentionSec=7day" in journal
