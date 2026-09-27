"""Copies of the database: daily, before migrations and restores, and on demand.

Backups sit beside the database, in its Backups folder, one file per copy,
named ``<database>_<YYYYmmdd-HHMMSS>_<kind>.db`` so that names sort by time and
the sandbox's copies never mix with production's. VACUUM INTO writes a compact
copy that is byte-stable: an unchanged graph gives an identical file, so a
daily copy identical to the newest backup is dropped rather than using up a
retention slot.

The app makes the daily backup at startup. Run as a script
(``python backup.py``) it makes the same backup of the production database,
for anyone who still schedules it.
"""
import hashlib
import logging
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import database

logger = logging.getLogger(__name__)

# Copies of each kind to keep. Daily copies skip the days the graph didn't
# change, so thirty of them are thirty different states, not thirty days.
KEEP = {
    "daily": 30,
    "manual": 10,
    "pre-migration": 10,
    "before-restore": 10,
    "before-import": 10,
}
_STAMP = "%Y%m%d-%H%M%S"


def backup_dir() -> Path:
    """The Backups folder beside the database (Data/Backups for the app)."""
    return Path(database.get_db_path()).parent / "Backups"


def _stem() -> str:
    """'skilltree' or 'sandbox_skilltree', the database's own name."""
    return Path(database.get_db_path()).stem


def describe(path) -> Optional[dict]:
    """``{"path", "kind", "when"}`` for one of this database's backups."""
    path = Path(path)
    prefix = _stem() + "_"
    if path.suffix != ".db" or not path.name.startswith(prefix):
        return None
    stamp, _, kind = path.stem[len(prefix):].partition("_")
    try:
        when = datetime.strptime(stamp, _STAMP)
    except ValueError:
        return None
    return {"path": path, "kind": kind, "when": when}


def list_backups(kind=None, directory=None) -> List[dict]:
    """This database's backups, oldest first, optionally of one kind."""
    directory = Path(directory) if directory else backup_dir()
    if not directory.is_dir():
        return []
    found = [info for info in map(describe, directory.glob(f"{_stem()}_*.db"))
             if info and (kind is None or info["kind"] == kind)]
    return sorted(found, key=lambda info: info["when"])


def _digest(path) -> str:
    """SHA-256 of a file, read in chunks so a large database never sits in memory."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_only_uri(path) -> str:
    # as_uri() percent-encodes the path, so a folder named with "?", "#" or
    # "%" can't be misread as part of the URI.
    return f"{Path(path).resolve().as_uri()}?mode=ro"


def opens_cleanly(path) -> bool:
    """Whether SQLite reads ``path`` as a database that passes quick_check.
    Read-only, so checking a backup never changes it."""
    try:
        conn = sqlite3.connect(_read_only_uri(path), uri=True,
                               timeout=database.BUSY_TIMEOUT_S)
    except sqlite3.Error:
        return False
    try:
        return conn.execute("PRAGMA quick_check").fetchall() == [("ok",)]
    except sqlite3.DatabaseError:
        return False
    finally:
        conn.close()


def newest_good_backup() -> Optional[dict]:
    """The newest of this database's backups that opens cleanly, or None."""
    for info in reversed(list_backups()):
        if opens_cleanly(info["path"]):
            return info
    return None


def restore_over_damaged(name) -> Path:
    """Put the backup called ``name`` where the damaged database is. Returns
    where the damaged file was kept.

    Refuses (ValueError) a name that isn't one of this database's backups, or
    a backup that is damaged itself, and then changes nothing. The damaged
    file is kept, and any journal beside it is moved aside with it: SQLite
    would roll a hot journal from the damaged file into the restored copy.
    The database never goes missing on the way, since the backup is copied in
    beside it and then swapped into its place in one step.
    """
    chosen = next((info for info in list_backups() if info["path"].name == name), None)
    if chosen is None:
        raise ValueError(f"there's no backup called {name!r} in {backup_dir()}")
    if not opens_cleanly(chosen["path"]):
        raise ValueError(f"the backup {name} is damaged too")
    live = Path(database.get_db_path())
    stamp = datetime.now().strftime(_STAMP)
    staging = live.with_name(f"{live.name}.restoring")
    shutil.copyfile(chosen["path"], staging)
    kept = live.with_name(f"{live.name}.damaged-{stamp}")
    if live.exists():
        shutil.copyfile(live, kept)
    for suffix in ("-journal", "-wal", "-shm"):
        side = Path(f"{live}{suffix}")
        if side.exists():
            os.replace(side, side.with_name(f"{side.name}.damaged-{stamp}"))
    os.replace(staging, live)
    return kept


def copy_database(destination) -> None:
    """Write a consistent, compact copy of the database to ``destination``."""
    destination = Path(destination)
    destination.unlink(missing_ok=True)  # VACUUM INTO needs a new file
    # Under the coordination lock the copy can't interleave with this
    # process's own writes. SQLite's own locking covers everyone else.
    with database.state_lock:
        conn = sqlite3.connect(_read_only_uri(database.get_db_path()), uri=True,
                               timeout=database.BUSY_TIMEOUT_S)
        try:
            conn.execute("VACUUM INTO ?", (str(destination),))
        finally:
            conn.close()


def create_backup(kind="manual", *, dedupe=False) -> Optional[Path]:
    """Copy the database into the Backups folder and return the new file.

    Returns None when there is no database yet or, with ``dedupe``, when the
    copy is identical to the newest backup, which already covers it.
    """
    if kind not in KEEP:
        raise ValueError(f"Unknown backup kind {kind!r}")
    if not Path(database.get_db_path()).exists():
        return None
    directory = backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / f"{_stem()}_{datetime.now().strftime(_STAMP)}_{kind}.db"
    tmp = final.with_name(final.name + ".tmp")
    copy_database(tmp)
    existing = list_backups()
    if dedupe and existing and _digest(tmp) == _digest(existing[-1]["path"]):
        tmp.unlink()
        return None
    os.replace(tmp, final)
    _prune(kind, directory)
    logger.info("Backed up the database to %s", final)
    return final


def _prune(kind, directory) -> None:
    backups = list_backups(kind, directory)
    for info in backups[:max(0, len(backups) - KEEP[kind])]:
        try:
            info["path"].unlink()
        except OSError as exc:
            logger.warning("Could not remove old backup %s: %s", info["path"], exc)


def mirror(path) -> Optional[Path]:
    """Copy a backup into the extra folder chosen in Settings, if there is one.

    A missing or unreachable folder (a cloud drive that isn't mounted, say) is
    logged and skipped: the local backup already exists.
    """
    from config import ConfigManager
    extra = (ConfigManager.get_backup_extra_dir() or "").strip()
    if not path or not extra:
        return None
    target_dir = Path(extra)
    if not target_dir.is_dir():
        logger.warning("Extra backup folder %s is not available; skipped", target_dir)
        return None
    try:
        target = target_dir / Path(path).name
        shutil.copy2(path, target)
        info = describe(path)
        if info:
            _prune(info["kind"], target_dir)
        return target
    except OSError as exc:
        logger.warning("Could not copy the backup to %s: %s", target_dir, exc)
        return None


def run_daily_backup(now=None) -> Optional[Path]:
    """The day's automatic backup: at most one per calendar day, skipped when
    nothing changed since the newest backup. Never raises; a failed backup is
    logged and must not stop the app."""
    try:
        today = (now or datetime.now()).date()
        if any(info["when"].date() == today for info in list_backups("daily")):
            return None
        path = create_backup("daily", dedupe=True)
        mirror(path)
        return path
    except Exception:
        logger.exception("Daily backup failed")
        return None


if __name__ == "__main__":
    from app_paths import get_log_dir
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_dir / "backup.log"), level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s")
    run_daily_backup()
