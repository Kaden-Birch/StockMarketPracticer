"""Scheduled SQLite backups with retention (PRD §27). Uses the SQLite
online-backup API, so a live database is copied consistently."""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

RETENTION = 7


def backup_database(db_url: str, data_dir: Path) -> Path | None:
    if not db_url.startswith("sqlite:///"):
        log.info("Backup job supports SQLite only (PostgreSQL: use pg_dump)")
        return None
    db_path = Path(db_url.removeprefix("sqlite:///"))
    if not db_path.exists():
        return None
    backup_dir = data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"aiptp-{stamp}.db"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    # retention: keep the newest RETENTION backups
    backups = sorted(backup_dir.glob("aiptp-*.db"))
    for old in backups[:-RETENTION]:
        old.unlink(missing_ok=True)
    log.info("Backup written: %s", target.name)
    return target


def list_backups(data_dir: Path) -> list[dict]:
    backup_dir = data_dir / "backups"
    if not backup_dir.is_dir():
        return []
    return [
        {"name": p.name, "size_bytes": p.stat().st_size,
         "created_at": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()}
        for p in sorted(backup_dir.glob("aiptp-*.db"), reverse=True)
    ]
