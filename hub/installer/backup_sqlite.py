#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


DATABASE = Path(os.environ.get("STREAM_HUB_DATABASE", "/var/lib/stream-hub/hub.sqlite3"))
BACKUP_DIR = Path(os.environ.get("STREAM_HUB_BACKUP_DIR", "/var/backups/stream-hub"))
RETENTION_DAYS = 7


def main() -> int:
    if not DATABASE.exists():
        print(f"database does not exist yet: {DATABASE}")
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = BACKUP_DIR / f"hub-{stamp}.sqlite3"
    with sqlite3.connect(DATABASE) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    os.chmod(destination, 0o600)
    print(f"created SQLite backup: {destination}")

    cutoff = time.time() - RETENTION_DAYS * 86400
    backups = sorted(BACKUP_DIR.glob("hub-*.sqlite3"), key=lambda path: path.stat().st_mtime)
    for backup in backups:
        if backup.stat().st_mtime < cutoff:
            backup.unlink(missing_ok=True)
            print(f"removed expired backup: {backup}")
    remaining = sorted(BACKUP_DIR.glob("hub-*.sqlite3"), key=lambda path: path.stat().st_mtime)
    for backup in remaining[:-RETENTION_DAYS]:
        backup.unlink(missing_ok=True)
        print(f"removed excess backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
