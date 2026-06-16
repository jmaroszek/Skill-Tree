"""Weekly production-DB backup script invoked by Windows Task Scheduler."""

import sqlite3
import os
from datetime import datetime

import database
from config import BACKUP_DIR, BACKUP_LOG_FILE


def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(BACKUP_LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


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

        # Atomic swap: if VACUUM above failed, the previous good backup is
        # still intact at backup_path. os.replace is atomic on the same
        # filesystem on Windows (Python >= 3.3).
        os.replace(tmp_path, backup_path)

        log(f"SUCCESS: Created backup at {backup_path}")

        # Keep at most 10 backups
        backups = [f for f in os.listdir(BACKUP_DIR) if f.startswith("skilltree_") and f.endswith(".db")]
        if len(backups) > 10:
            backups.sort()  # Sorts chronologically due to YYYY-MM-DD naming
            backups_to_delete = backups[:-10]
            for old_backup in backups_to_delete:
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
