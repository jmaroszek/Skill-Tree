import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import logging
import threading
from pathlib import Path
from typing import Optional

from skilltree.runtime import paths
from skilltree.runtime.paths import get_data_dir

logger = logging.getLogger(__name__)


# Snapshot of the resolved DB path on first call. Reading paths.ENVIRONMENT
# on every call risks splitting a single process between sandbox and prod if
# the env var is ever mutated mid-run (test fixtures, REPL re-imports, etc.).
# Caching guarantees a process commits to one DB for its lifetime. Tests that
# need a different path monkeypatch get_db_path itself (see conftest), which
# bypasses this cache entirely.
_db_path_cache: Optional[str] = None

# One write operation may cross GraphManager, EventManager and the settings.
# The lease keeps their nested context managers/commit calls from committing
# part of that operation. ContextVar isolates concurrent Dash request threads.
_session = ContextVar("skilltree_db_session", default=None)
_snapshot = ContextVar("skilltree_read_snapshot", default=None)
state_lock = threading.RLock()


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


class ReadSnapshot:
    """Detached rows from one SQLite read transaction, scoped to an operation."""
    def __init__(self):
        with get_connection() as conn:
            conn.execute("BEGIN")
            conn.row_factory = sqlite3.Row
            self.nodes = {row["name"]: dict(row) for row in conn.execute("SELECT * FROM Nodes")}
            self.edges = [dict(row) for row in conn.execute("SELECT * FROM Edges")]
            self.settings = dict(conn.execute("SELECT key, value FROM Settings").fetchall())
            self.resource_sections = [dict(row) for row in conn.execute(
                "SELECT id, name, root_path, position "
                "FROM ResourceSections ORDER BY position")]
            self.resource_links = {}
            for row in conn.execute(
                    "SELECT node_name, section_id, target FROM NodeResourceLinks "
                    "ORDER BY node_name, section_id, position"):
                self.resource_links.setdefault(row[0], {}).setdefault(row[1], []).append(row[2])
            self.trigger_names = {row[0] for row in conn.execute(
                "SELECT DISTINCT etn.node_name FROM EventTriggerNodes etn "
                "JOIN Events e ON e.name=etn.event_name WHERE e.status='Pending'")}
        self.invalid = False
        # The repository normalizes each requested row once, then returns
        # detached copies. Templates live only as long as this read scope.
        self.node_templates = {}


def current_snapshot():
    snapshot = _snapshot.get()
    return snapshot if snapshot is not None and not snapshot.invalid else None


@contextmanager
def read_snapshot():
    """Reuse graph/settings rows in nested helpers; never retain across requests.

    The SQL connection is closed before computation starts. The coordination
    lock keeps the snapshot and versioned caches consistent with local writes.
    A write within this scope invalidates it, so subsequent reads see that write.
    """
    if in_transaction() or current_snapshot() is not None:
        yield current_snapshot()
        return
    with state_lock:
        snapshot = ReadSnapshot()
        token = _snapshot.set(snapshot)
        try:
            yield snapshot
        finally:
            _snapshot.reset(token)


def snapshot_read(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        with read_snapshot():
            return func(*args, **kwargs)
    return wrapped


class _ConnectionLease:
    def __init__(self, session):
        object.__setattr__(self, "session", session)

    def __getattr__(self, name):
        return getattr(self.session["connection"], name)

    def __setattr__(self, name, value):
        setattr(self.session["connection"], name, value)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.session["failed"] = True
        return False

    def commit(self):
        pass  # Only the outer transaction may commit.

    def rollback(self):
        self.session["failed"] = True

    def close(self):
        pass  # The outer transaction owns the connection.


@contextmanager
def transaction():
    """Join one atomic write, rolling back even if a nested failure is caught.

    BEGIN IMMEDIATE serializes validation with other writers. Deferred foreign
    keys allow renames without disabling referential integrity. Notifications
    and cache invalidations run only after the complete write commits.
    """
    existing = _session.get()
    if existing is not None:
        try:
            yield _ConnectionLease(existing)
        except BaseException:
            existing["failed"] = True
            raise
        return
    with state_lock:
        snapshot = _snapshot.get()
        if snapshot is not None:
            snapshot.invalid = True
        conn = get_connection()
        session = {"connection": conn, "failed": False, "callbacks": {}, "first": {}}
        token = _session.set(session)
        committed = False
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("PRAGMA defer_foreign_keys = ON")
            yield _ConnectionLease(session)
            if session["failed"]:
                # A nested write failed and its caller caught the error, so
                # the block finished normally. Nothing is saved; say so, since
                # the caller may go on to report success.
                logger.warning("Rolled back a transaction whose nested write failed")
                conn.rollback()
            else:
                conn.commit()
                committed = True
        except BaseException:
            conn.rollback()
            raise
        finally:
            _session.reset(token)
            conn.close()
        if committed:
            for callback in session["callbacks"].values():
                callback()


def atomic(func):
    """Make a manager operation (or compound save) a transaction boundary."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        with transaction():
            return func(*args, **kwargs)
    return wrapped


def serialized(func):
    """Hold the write lock across a check and the writes it guards.

    Each write is its own transaction, so a caller that reads (how many nodes
    are on Now, say) and then writes could interleave with another request
    doing the same, and both would pass the check. Writes inside still take
    the lock again, which an RLock allows.
    """
    @wraps(func)
    def wrapped(*args, **kwargs):
        with state_lock:
            return func(*args, **kwargs)
    return wrapped


def on_commit(callback, key=None):
    """Run ``callback`` once the outer transaction commits, or now outside one.

    A later callback registered under the same ``key`` replaces the earlier
    one, so a callback must not depend on when in the transaction it was
    registered. State from before the transaction belongs in
    first_in_transaction.
    """
    session = _session.get()
    if session is None:
        callback()
    else:
        session["callbacks"][key if key is not None else id(callback)] = callback


def first_in_transaction(key, value):
    """The value first recorded under ``key`` in this transaction.

    One transaction can write the same row more than once, as a compound save
    does. A write that compares old against new should compare against the
    row as it was before the transaction, which is what its first write saw.
    Outside a transaction there is nothing earlier, so ``value`` comes back.
    """
    session = _session.get()
    if session is None:
        return value
    return session["first"].setdefault(key, value)


def in_transaction():
    return _session.get() is not None


def consistent_read(func):
    """Keep a graph read and its cache publication on the same revision."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        with state_lock:
            return func(*args, **kwargs)
    return wrapped


def get_db_path() -> str:
    """Returns the absolute path to the SQLite database file."""
    global _db_path_cache
    if _db_path_cache is not None:
        return _db_path_cache
    db_name = paths.DB_FILENAME
    if paths.ENVIRONMENT == "sandbox":
        db_name = "sandbox_" + paths.DB_FILENAME
    _db_path_cache = str(get_data_dir() / db_name)
    return _db_path_cache


# How long a connection waits for another program's lock before giving up
# with SQLITE_BUSY. It is Python's own default, named so tests can shorten it.
BUSY_TIMEOUT_S = 5.0


def resolved_db_path():
    """The database path this process resolved, or None before the first
    get_db_path() call."""
    return _db_path_cache


def get_connection() -> sqlite3.Connection:
    """Creates and returns a new database connection with foreign keys enabled."""
    session = _session.get()
    if session is not None:
        return _ConnectionLease(session)
    db_path = Path(get_db_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_S, factory=_ClosingConnection)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn




class DatabaseError(RuntimeError):
    """A database this build refuses to open, with a message for the user.

    ``exit_code`` is what the launcher exits with, so the desktop shell can
    tell the cases apart without parsing text.
    """
    exit_code = 2


class NewerDatabaseError(DatabaseError):
    exit_code = 3


class DatabaseCorruptError(DatabaseError):
    exit_code = 4


class SQLiteTooOldError(DatabaseError):
    exit_code = 5


class DatabaseLockedError(DatabaseError):
    """Another program holds the file (a sync or backup tool, a DB viewer)."""
    exit_code = 6


class DatabaseUnwritableError(DatabaseError):
    """The file or its folder is read-only, or the disk is full."""
    exit_code = 7


def refusal_for(exc, path=None):
    """The DatabaseError an SQLite failure amounts to, or None if it is none of
    the known cases.

    Only a file SQLite itself calls damaged is reported as damaged: the desktop
    shell offers to restore a backup over it, which would throw away a good
    database that was merely busy or read-only.
    """
    name = getattr(exc, "sqlite_errorname", "") or ""
    path = path or get_db_path()
    if name.startswith(("SQLITE_NOTADB", "SQLITE_CORRUPT")):
        return DatabaseCorruptError(_damaged_message(str(exc), path))
    if name.startswith(("SQLITE_BUSY", "SQLITE_LOCKED")):
        return DatabaseLockedError(
            f"The Skill Tree data file {path} is in use by another program "
            "(perhaps a backup or sync tool, or a database viewer). Close it "
            "and try again. Nothing was changed.")
    if name.startswith("SQLITE_FULL"):
        return DatabaseUnwritableError(
            f"Skill Tree can't write its data file {path} because the disk is "
            "full. Free some space and try again. Nothing was changed.")
    if name.startswith(("SQLITE_READONLY", "SQLITE_CANTOPEN", "SQLITE_PERM")):
        return DatabaseUnwritableError(
            f"Skill Tree can't write its data file {path}. The file or its "
            "folder may be read-only, or Skill Tree lacks permission to change "
            "it. Nothing was changed.")
    return None


def unreadable(exc, path=None):
    """A refusal for any SQLite failure while merely opening or checking."""
    return refusal_for(exc, path) or DatabaseError(
        f"Skill Tree couldn't open its data file {path or get_db_path()} "
        f"({exc}). Nothing was changed.")


def _damaged_message(detail, path=None):
    backups = Path(get_db_path()).parent / "Backups"
    return (f"The Skill Tree data file {path or get_db_path()} is damaged ({detail}). "
            f"Nothing was changed. Backups are in {backups}; restore the newest "
            "one that opens.")


def check_integrity(path=None):
    """Raise DatabaseCorruptError unless SQLite's quick_check passes."""
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_S) if path else get_connection()
    try:
        rows = [row[0] for row in conn.execute("PRAGMA quick_check").fetchall()]
    except sqlite3.DatabaseError as exc:
        raise unreadable(exc, path) from exc
    finally:
        conn.close()
    if rows != ["ok"]:
        raise DatabaseCorruptError(_damaged_message("; ".join(rows[:3]), path))
