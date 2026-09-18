"""Daily production-DB backup script invoked by Windows Task Scheduler."""

import hashlib
import sqlite3
import os
from datetime import datetime
from pathlib import Path

import database
from config import BACKUP_DIR, BACKUP_KEEP, BACKUP_LOG_FILE


def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    Path(BACKUP_LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(BACKUP_LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def _digest(path):
    """SHA-256 of a file, read in chunks so a large DB never lands in memory."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _existing_backups():
    """Backup filenames, oldest first. YYYY-MM-DD naming sorts chronologically."""
    names = [
        f for f in os.listdir(BACKUP_DIR)
        if f.startswith("skilltree_") and f.endswith(".db")
    ]
    names.sort()
    return names


def run_backup():
    # config.ENVIRONMENT defaults to "production" at import time, so
    # database.get_db_path() returns the production DB regardless of
    # anything else in the process. Backup never targets the sandbox.
    db_source = database.get_db_path()
    try:
        if not os.path.exists(db_source):
            log(f"FAILED: Source database not found at {db_source}. Check for typos!")
            return

        if not os.path.exists(BACKUP_DIR):
            log(f"FAILED: Backup directory not found: {BACKUP_DIR}")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d")
        backup_path = os.path.join(BACKUP_DIR, f"skilltree_{timestamp}.db")
        tmp_path = f"{backup_path}.tmp"

        # Clean any stale .tmp from a prior crashed run; VACUUM INTO requires
        # the target path to not exist.
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        conn = sqlite3.connect(f"file:{db_source}?mode=ro", uri=True)
        conn.execute(f"VACUUM INTO '{tmp_path}'")
        conn.close()

        # VACUUM INTO is byte-stable: an unchanged graph vacuums to an
        # identical file every run. So comparing digests against the newest
        # backup tells us whether anything actually changed, and idle days
        # cost no retention slot.
        backups = _existing_backups()
        if backups:
            newest = os.path.join(BACKUP_DIR, backups[-1])
            if _digest(tmp_path) == _digest(newest):
                os.remove(tmp_path)
                log(f"SKIPPED: Database unchanged since {backups[-1]}")
                return

        # Atomic swap: if VACUUM above failed, the previous good backup is
        # still intact at backup_path. os.replace is atomic on the same
        # filesystem on Windows (Python >= 3.3).
        os.replace(tmp_path, backup_path)

        log(f"SUCCESS: Created backup at {backup_path}")

        # Keep at most BACKUP_KEEP backups
        backups = _existing_backups()
        if len(backups) > BACKUP_KEEP:
            for old_backup in backups[:-BACKUP_KEEP]:
                old_backup_path = os.path.join(BACKUP_DIR, old_backup)
                try:
                    os.remove(old_backup_path)
                    log(f"INFO: Pruned old backup {old_backup}")
                except Exception as e_rm:
                    log(f"WARNING: Failed to delete old backup {old_backup}: {e_rm}")

    except Exception as e:
        log(f"CRITICAL ERROR: {str(e)}")


if __name__ == "__main__":
    run_backup()
