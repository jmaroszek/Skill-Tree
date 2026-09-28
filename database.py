import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from app_paths import get_data_dir

logger = logging.getLogger(__name__)


# Snapshot of the resolved DB path on first call. Reading config.ENVIRONMENT
# on every call risks splitting a single process between sandbox and prod if
# the env var is ever mutated mid-run (test fixtures, REPL re-imports, etc.).
# Caching guarantees a process commits to one DB for its lifetime. Tests that
# need a different path monkeypatch get_db_path itself (see conftest), which
# bypasses this cache entirely.
_db_path_cache: Optional[str] = None

# One write operation may cross GraphManager, EventManager and ConfigManager.
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
                "SELECT id, name, kind, root_path, position "
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
    # Lazy import dodges the circular dependency: config imports
    # get_connection from this module at load time.
    from config import ENVIRONMENT, DB_FILENAME
    db_name = DB_FILENAME
    if ENVIRONMENT == "sandbox":
        db_name = "sandbox_" + DB_FILENAME
    _db_path_cache = str(get_data_dir() / db_name)
    return _db_path_cache


# How long a connection waits for another program's lock before giving up
# with SQLITE_BUSY. It is Python's own default, named so tests can shorten it.
BUSY_TIMEOUT_S = 5.0


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


_initialized = False

# Bump whenever a schema change lands that an existing DB can't pick up from
# the CREATE TABLE IF NOT EXISTS statements alone, and add the matching step
# to _migrate().
SCHEMA_VERSION = 11


def _utc_now_ts() -> int:
    """Current UTC instant as Unix seconds, shared by schema-history markers."""
    return int(time.time())


def _has_column(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _migrate(cursor, from_version: int) -> None:
    """Applies incremental schema migrations to an already-created DB.

    The v1-v4 era of ALTER TABLE statements was deliberately folded into the
    CREATE TABLE definitions, since those are self-describing and a fresh DB
    needs no replay. That trick only works for brand-new databases, though:
    CREATE TABLE IF NOT EXISTS silently does nothing to an existing file. So
    anything added after v4 needs a real migration step here.

    Every step is written to be idempotent (guarded on the actual table shape,
    not just the version stamp) so a DB in a half-migrated state still lands
    correctly.
    """
    # --- v5: node-completion triggers become a set with AND/OR semantics ---
    if from_version < 5:
        if not _has_column(cursor, "Events", "trigger_mode"):
            cursor.execute(
                "ALTER TABLE Events ADD COLUMN trigger_mode TEXT NOT NULL DEFAULT 'any'"
            )
        if _has_column(cursor, "Events", "trigger_node"):
            # Carry each existing single trigger into the new table. The join
            # to Nodes drops trigger_node values left dangling by an older
            # build, which would otherwise violate the new foreign key.
            cursor.execute('''
                INSERT OR IGNORE INTO EventTriggerNodes (event_name, node_name)
                SELECT e.name, e.trigger_node FROM Events e
                JOIN Nodes n ON n.name = e.trigger_node
                WHERE e.trigger_node IS NOT NULL
            ''')
            # A one-element set under 'any' reproduces the old behavior
            # exactly, so no trigger_mode fixup is needed.
            try:
                cursor.execute("ALTER TABLE Events DROP COLUMN trigger_node")
            except Exception as exc:
                # DROP COLUMN needs SQLite 3.35+. On older builds the column
                # just lingers unused — every read path selects explicitly.
                logger.info("Left legacy Events.trigger_node in place (%s).", exc)

    # --- v6: the manual priority override is retired; the event intent it
    # carried becomes "add to Now on trigger" ---
    if from_version < 6:
        if not _has_column(cursor, "EventNodes", "now_on_trigger"):
            cursor.execute(
                "ALTER TABLE EventNodes ADD COLUMN now_on_trigger INTEGER NOT NULL DEFAULT 0"
            )
            if _has_column(cursor, "EventNodes", "override_on_trigger"):
                cursor.execute(
                    "UPDATE EventNodes SET now_on_trigger = override_on_trigger"
                )
        for column in ("override_on_trigger", "override_mode"):
            if not _has_column(cursor, "EventNodes", column):
                continue
            try:
                cursor.execute(f"ALTER TABLE EventNodes DROP COLUMN {column}")
            except Exception as exc:
                # DROP COLUMN needs SQLite 3.35+. On older builds the column
                # lingers unused — every read path selects explicitly.
                logger.info("Left legacy EventNodes.%s in place (%s).", column, exc)
        # The override's two Settings rows have no reader left.
        cursor.execute(
            "DELETE FROM Settings WHERE key IN ('OVERRIDE', 'EVENT_OVERRIDE_NODES')"
        )

    # --- v7: preserve every future Now/Done boundary instead of relying on the
    # Nodes table's deliberately lossy latest-date snapshots. Existing dates
    # cannot reconstruct prior cycles. The marker makes that coverage boundary
    # explicit, and a node already in Now gets a migration-snapshot start so a
    # later stop is recognizable as a partial interval rather than an orphan.
    if from_version < 7:
        started_at = _utc_now_ts()
        cursor.execute(
            "INSERT OR IGNORE INTO Settings (key, value) VALUES (?, ?)",
            ("lifecycle_history_started_at", str(started_at)),
        )
        cursor.execute('''
            INSERT INTO NodeLifecycleEvents
                (node_name, event_type, occurred_at, source)
            SELECT n.name, 'now_started', ?, 'migration_snapshot'
            FROM Nodes n
            WHERE n."now" > 0
              AND NOT EXISTS (
                  SELECT 1 FROM NodeLifecycleEvents h
                  WHERE h.node_name = n.name
                    AND h.event_type = 'now_started'
              )
        ''', (started_at,))

    # --- v8: a dormant node belongs to one event. Several used to be allowed,
    # with the first to fire waking the node, but that read as "all of them
    # must fire". A node still in several keeps the row that woke it, or else
    # the one added first, and loses the rest.
    if from_version < 8:
        cursor.execute('''
            DELETE FROM EventNodes WHERE rowid NOT IN (
                SELECT (SELECT keep.rowid FROM EventNodes keep
                        WHERE keep.node_name = en.node_name
                        ORDER BY keep.activated DESC, keep.rowid
                        LIMIT 1)
                FROM EventNodes en GROUP BY en.node_name
            )
        ''')
        if cursor.rowcount:
            logger.info("Removed %d extra event membership(s); a node now "
                        "belongs to one event.", cursor.rowcount)
        cursor.execute("DROP INDEX IF EXISTS idx_event_nodes_node")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_event_nodes_node "
                       "ON EventNodes(node_name)")

    # --- v9: existing resource links remain available after integrations
    # become opt-in. A fresh database has no links or paths, so both start off.
    if from_version < 9 and _has_column(cursor, "Nodes", "obsidian_path"):
        for setting_key, path_key, node_column in (
            ("OBSIDIAN_ENABLED", "OBSIDIAN_VAULT", "obsidian_path"),
            ("GDRIVE_ENABLED", "GDRIVE_ROOT_PATH", "google_drive_path"),
        ):
            path_row = cursor.execute(
                "SELECT value FROM Settings WHERE key = ?", (path_key,)
            ).fetchone()
            has_path = bool(path_row and path_row[0].strip())
            has_links = cursor.execute(
                f"SELECT 1 FROM Nodes WHERE {node_column} IS NOT NULL "
                f"AND TRIM({node_column}) NOT IN ('', '[]', 'null') LIMIT 1"
            ).fetchone() is not None
            cursor.execute(
                "INSERT OR IGNORE INTO Settings (key, value) VALUES (?, ?)",
                (setting_key, "1" if has_path or has_links else "0"),
            )
            if setting_key == "OBSIDIAN_ENABLED" and has_links and not has_path:
                # Older builds used ~/Documents/Obsidian without saving it.
                # Preserve that behavior for an existing vault on this host.
                from pathlib import Path
                legacy_vault = Path.home() / "Documents" / "Obsidian"
                if legacy_vault.is_dir():
                    cursor.execute(
                        "INSERT OR IGNORE INTO Settings (key, value) VALUES (?, ?)",
                        (path_key, str(legacy_vault)),
                    )

    # --- v10: named Resource sections and ordered per-node links. An older
    # database turns its three link columns into sections. A new one gets a
    # single neutral section; users name their own in Settings > Resources.
    if from_version < 10:
        from resource_links import parse_links, normalize_link
        has_legacy = _has_column(cursor, "Nodes", "obsidian_path")
        seeds = _LEGACY_RESOURCE_SECTIONS if has_legacy else _NEW_RESOURCE_SECTIONS
        for position, (section_id, name, kind, root_key, column) in enumerate(seeds):
            root_row = cursor.execute("SELECT value FROM Settings WHERE key=?", (root_key,)).fetchone() if root_key else None
            root = root_row[0] if root_row else ""
            cursor.execute("INSERT OR IGNORE INTO ResourceSections "
                           "(id, name, kind, root_path, position) VALUES (?, ?, ?, ?, ?)",
                           (section_id, name, kind, root, position))
            if not has_legacy:
                continue
            for node_name, raw in cursor.execute(
                    f"SELECT name, {column} FROM Nodes WHERE {column} IS NOT NULL").fetchall():
                for index, value in enumerate(parse_links(raw)):
                    stored = normalize_link(value, {"root_path": root, "kind": kind})
                    cursor.execute("INSERT OR IGNORE INTO NodeResourceLinks "
                                   "(node_name, section_id, position, target) VALUES (?, ?, ?, ?)",
                                   (node_name, section_id, index, stored))

    # --- v11: the named sections become the only copy. v10 kept the three
    # legacy link columns as a mirror and gave each section an on/off switch.
    # Any legacy link the table lacks is copied first; then the mirror
    # columns, the switch, and the old integration settings go.
    if from_version < 11:
        from resource_links import parse_links, normalize_link
        if _has_column(cursor, "Nodes", "obsidian_path"):
            for section_id, _name, kind, _root_key, column in _LEGACY_RESOURCE_SECTIONS:
                section = cursor.execute(
                    "SELECT root_path FROM ResourceSections WHERE id=?", (section_id,)
                ).fetchone()
                if section is None:
                    continue
                for node_name, raw in cursor.execute(
                        f"SELECT name, {column} FROM Nodes WHERE {column} IS NOT NULL").fetchall():
                    if cursor.execute(
                            "SELECT 1 FROM NodeResourceLinks WHERE node_name=? AND section_id=?",
                            (node_name, section_id)).fetchone():
                        continue
                    for index, value in enumerate(parse_links(raw)):
                        cursor.execute(
                            "INSERT OR IGNORE INTO NodeResourceLinks "
                            "(node_name, section_id, position, target) VALUES (?, ?, ?, ?)",
                            (node_name, section_id, index,
                             normalize_link(value, {"root_path": section[0], "kind": kind})))
            for _section_id, _name, _kind, _root_key, column in _LEGACY_RESOURCE_SECTIONS:
                cursor.execute(f"ALTER TABLE Nodes DROP COLUMN {column}")
        if _has_column(cursor, "ResourceSections", "enabled"):
            cursor.execute("ALTER TABLE ResourceSections DROP COLUMN enabled")
        cursor.execute("DELETE FROM Settings WHERE key IN "
                       "('OBSIDIAN_ENABLED', 'OBSIDIAN_VAULT', 'GDRIVE_ENABLED', 'GDRIVE_ROOT_PATH')")


# The three link columns Nodes carried before v11, and the sections v10 made
# of them: (section id, name, kind, root-path setting key, Nodes column).
_LEGACY_RESOURCE_SECTIONS = (
    ("obsidian", "Obsidian", "obsidian", "OBSIDIAN_VAULT", "obsidian_path"),
    ("drive", "Google Drive", "mixed", "GDRIVE_ROOT_PATH", "google_drive_path"),
    ("website", "Website", "mixed", None, "website"),
)
# What a new database starts with: web pages and files, one list.
_NEW_RESOURCE_SECTIONS = (
    ("links", "Links", "mixed", None, None),
)


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


def _refusal_for(exc, path=None):
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


def _unreadable(exc, path=None):
    """A refusal for any SQLite failure while merely opening or checking."""
    return _refusal_for(exc, path) or DatabaseError(
        f"Skill Tree couldn't open its data file {path or get_db_path()} "
        f"({exc}). Nothing was changed.")


# DROP COLUMN (the v11 step) and VACUUM INTO (backups) need these features.
MIN_SQLITE_VERSION = (3, 35, 0)


def _inspect_database():
    """(user_version, whether any table exists), or DatabaseCorruptError."""
    conn = get_connection()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        has_tables = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone() is not None
    except sqlite3.DatabaseError as exc:  # e.g. "file is not a database"
        raise _unreadable(exc) from exc
    finally:
        conn.close()
    return version, has_tables


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
        raise _unreadable(exc, path) from exc
    finally:
        conn.close()
    if rows != ["ok"]:
        raise DatabaseCorruptError(_damaged_message("; ".join(rows[:3]), path))


def init_db():
    """Create or upgrade the schema. Only the first call does any work.

    Refuses (DatabaseError) a database this build can't safely open: one saved
    by a newer version, or one failing SQLite's integrity check. Neither is
    touched. An existing database that needs upgrading is backed up first, and
    the whole upgrade (tables, migration steps, version stamp) is one
    transaction, so a failure part-way leaves it exactly as it was.
    """
    global _initialized
    if _initialized:
        return
    if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
        raise SQLiteTooOldError(
            "Skill Tree needs SQLite {} or newer, and this Python has {}.".format(
                ".".join(map(str, MIN_SQLITE_VERSION)), sqlite3.sqlite_version))
    try:
        _open_and_upgrade()
    except sqlite3.Error as exc:
        refusal = _refusal_for(exc)
        if refusal is None:
            raise
        raise refusal from exc
    _initialized = True


def _open_and_upgrade():
    """init_db's work, with SQLite's own errors left for init_db to name."""
    # Schema version stamp. The baseline schema is v4, defined in full by the
    # CREATE TABLE statements in _create_tables (CREATE TABLE IF NOT EXISTS is
    # a no-op on an existing DB). Changes past v4 live in _migrate() as a
    # version ladder.
    current_v, has_tables = _inspect_database()
    if current_v > SCHEMA_VERSION:
        # Stamping it down, as this used to, would hide the newer version's
        # columns from itself the next time it opened the file.
        raise NewerDatabaseError(
            f"The Skill Tree data file {get_db_path()} was saved by a newer "
            f"version of Skill Tree (data format {current_v}; this version "
            f"reads up to {SCHEMA_VERSION}). Install the newer version to open "
            "it. Nothing was changed.")
    if has_tables:
        check_integrity()
        if current_v < SCHEMA_VERSION:
            import backup
            backup.create_backup("pre-migration")

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        _create_tables(cursor)
        _migrate(cursor, current_v)
        cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _create_tables(cursor):
    """The full current schema, for a new database; a no-op on an existing one."""
    # Full Nodes schema. Every column the app reads lives here — there are no
    # follow-up ALTER TABLE migrations. (This consolidates an earlier era where
    # the table was created with a partial column set and incrementally extended
    # by ALTERs; folding them in keeps the schema self-describing.) Column
    # groups: core attributes, lifecycle flags, scoring modes, habit-mode
    # breakdown, time-calibration actuals, and retrospective reflection ratings.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Nodes (
            name TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            description TEXT NOT NULL,
            value INTEGER NOT NULL,
            time_o REAL NOT NULL,
            time_m REAL NOT NULL,
            time_p REAL NOT NULL,
            interest INTEGER NOT NULL,
            difficulty INTEGER NOT NULL,
            context TEXT,
            subcontext TEXT,
            status TEXT NOT NULL,
            dormant INTEGER NOT NULL DEFAULT 0,
            -- Scoring modes: 'manual' | 'inherited' (time also allows 'habit').
            -- 'inherited' makes the dimension flow up from children in scoring.
            time_mode TEXT NOT NULL DEFAULT 'manual',
            value_mode TEXT NOT NULL DEFAULT 'manual',
            -- Habit-mode breakdown: persisted so re-opening the editor restores
            -- the duration x intensity form, not just the resulting time_o/m/p.
            habit_duration REAL NOT NULL DEFAULT 0,
            habit_duration_unit TEXT NOT NULL DEFAULT 'weeks',
            habit_intensity_o REAL NOT NULL DEFAULT 0,
            habit_intensity_m REAL NOT NULL DEFAULT 0,
            habit_intensity_p REAL NOT NULL DEFAULT 0,
            habit_intensity_unit TEXT NOT NULL DEFAULT 'min_per_day',
            habit_days TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',
            -- Time-calibration actuals, captured at Done. NULL = "not captured"
            -- (meaningfully distinct from 0). Stored in canonical hours.
            actual_time_lower REAL,
            actual_time_upper REAL,
            actual_time_point REAL,
            actual_time_unit TEXT,
            calibration_dismissed INTEGER NOT NULL DEFAULT 0,
            -- 'now' is an orthogonal integer (separate from status) marking the
            -- node as currently-being-worked. 0 = not Now; positive integers
            -- encode display order (1 = leftmost card). start_date/done_date
            -- retain the latest activation/completion snapshots; the append-
            -- only NodeLifecycleEvents table retains repeated transitions.
            -- reflect_* are retrospective ratings.
            now INTEGER NOT NULL DEFAULT 0,
            start_date TEXT,
            done_date TEXT,
            reflect_value INTEGER,
            reflect_interest INTEGER,
            reflect_difficulty INTEGER
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ResourceSections (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('obsidian', 'mixed')),
            root_path TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS NodeResourceLinks (
            node_name TEXT NOT NULL,
            section_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            target TEXT NOT NULL,
            PRIMARY KEY (node_name, section_id, position),
            FOREIGN KEY (node_name) REFERENCES Nodes(name) ON DELETE CASCADE,
            FOREIGN KEY (section_id) REFERENCES ResourceSections(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Edges (
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            type TEXT NOT NULL,
            PRIMARY KEY (source, target, type),
            FOREIGN KEY (source) REFERENCES Nodes(name) ON DELETE CASCADE,
            FOREIGN KEY (target) REFERENCES Nodes(name) ON DELETE CASCADE
        )
    ''')
    # Accelerate target-side graph traversal (WHERE target=? AND type=?) used
    # by cycle detection, reverse adjacency, and status cascades. The PK's
    # auto-index (source, target, type) already covers source-side queries, so
    # no separate source-type index is needed.
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_target_type ON Edges(target, type)")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Events (
            name TEXT PRIMARY KEY,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pending',
            trigger_date TEXT,
            trigger_mode TEXT NOT NULL DEFAULT 'any'
        )
    ''')

    # Node-completion triggers. Normalized into its own table so an event can
    # watch several nodes; `Events.trigger_mode` ('any' = OR, 'all' = AND) says
    # how to combine them. The FK to Nodes gives delete-narrowing for free:
    # removing a node drops it from every trigger set automatically.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS EventTriggerNodes (
            event_name TEXT NOT NULL,
            node_name TEXT NOT NULL,
            PRIMARY KEY (event_name, node_name),
            FOREIGN KEY (event_name) REFERENCES Events(name) ON DELETE CASCADE,
            FOREIGN KEY (node_name) REFERENCES Nodes(name) ON DELETE CASCADE
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_trigger_node "
                   "ON EventTriggerNodes(node_name)")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS EventNodes (
            event_name TEXT NOT NULL,
            node_name TEXT NOT NULL,
            delay_days INTEGER NOT NULL DEFAULT 0,
            activation_date TEXT,
            activated INTEGER NOT NULL DEFAULT 0,
            -- Add the node to the Now list when the event triggers, subject
            -- to the Now cap.
            now_on_trigger INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (event_name, node_name),
            FOREIGN KEY (event_name) REFERENCES Events(name) ON DELETE CASCADE,
            FOREIGN KEY (node_name) REFERENCES Nodes(name) ON DELETE CASCADE
        )
    ''')
    # A node belongs to at most one event. The unique index that enforces it
    # is created by the v8 step in _migrate, which first folds any node an
    # older database still has in several events down to one.

    # Append-only user lifecycle boundaries. start_date/done_date on Nodes stay
    # as convenient latest-state snapshots; this table is the prospective,
    # lossless history for repeated Now and Done cycles.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS NodeLifecycleEvents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_name TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN (
                'now_started', 'now_stopped', 'completed', 'reopened'
            )),
            occurred_at INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'live'
                CHECK(source IN ('live', 'migration_snapshot')),
            FOREIGN KEY (node_name) REFERENCES Nodes(name) ON DELETE CASCADE
        )
    ''')
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_node_lifecycle_events_node_time "
        "ON NodeLifecycleEvents(node_name, occurred_at, id)"
    )
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Aliases (
            alias TEXT PRIMARY KEY,
            node_name TEXT NOT NULL,
            FOREIGN KEY (node_name) REFERENCES Nodes(name) ON DELETE CASCADE
        )
    ''')


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
