"""The database's tables.

_create_tables defines the current schema in full, and SCHEMA_VERSION stamps
it. A database from an older version is refused, not upgraded: every database
this app opens is at the current schema. A change to the tables bumps
SCHEMA_VERSION and needs a step in init_db that brings a database at the
previous version up to it, backed up first."""
import sqlite3
import time

from skilltree.store import database
from skilltree.store.database import (
    DatabaseError, NewerDatabaseError, SQLiteTooOldError, refusal_for, unreadable,
)


SCHEMA_VERSION = 13


def _utc_now_ts() -> int:
    """Current UTC instant as Unix seconds, shared by schema-history markers."""
    return int(time.time())


# The oldest SQLite this app supports. Backups use VACUUM INTO, from 3.27.
MIN_SQLITE_VERSION = (3, 35, 0)


def _inspect_database():
    """(user_version, whether any table exists), or DatabaseCorruptError."""
    conn = database.get_connection()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        has_tables = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone() is not None
    except sqlite3.DatabaseError as exc:  # e.g. "file is not a database"
        raise unreadable(exc) from exc
    finally:
        conn.close()
    return version, has_tables


# The databases this process has checked are at the current schema, by path.
_current = set()


def init_db(*, recheck=False):
    """Create the database database.get_db_path() names, or check an existing one.

    Each database is checked once per process. recheck=True checks it again,
    as after a restore replaces its file.

    Refuses (DatabaseError) a database this build can't safely open: one saved
    by a newer or an older version, or one failing SQLite's integrity check.
    None of them is touched.
    """
    path = database.get_db_path()
    if path in _current and not recheck:
        return
    # Only a check that finishes makes the file current again.
    _current.discard(path)
    if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
        raise SQLiteTooOldError(
            "Skill Tree needs SQLite {} or newer, and this Python has {}.".format(
                ".".join(map(str, MIN_SQLITE_VERSION)), sqlite3.sqlite_version))
    try:
        _open_or_create()
    except sqlite3.Error as exc:
        refusal = refusal_for(exc)
        if refusal is None:
            raise
        raise refusal from exc
    _current.add(path)


def mark_current(path):
    """Record that the database at `path` is at the current schema, such as a
    copy of one init_db made, so init_db skips it."""
    _current.add(path)


def forget(path):
    """Make the next init_db check the database at `path` again, as after its
    file was replaced or damaged behind init_db's back."""
    _current.discard(path)


def _open_or_create():
    """init_db's work, with SQLite's own errors left for init_db to name."""
    current_v, has_tables = _inspect_database()
    if current_v > SCHEMA_VERSION:
        # Stamping it down would hide the newer version's columns from itself
        # the next time it opened the file.
        raise NewerDatabaseError(
            f"The Skill Tree data file {database.get_db_path()} was saved by a newer "
            f"version of Skill Tree (data format {current_v}; this version "
            f"reads up to {SCHEMA_VERSION}). Install the newer version to open "
            "it. Nothing was changed.")
    if has_tables:
        if current_v < SCHEMA_VERSION:
            raise DatabaseError(
                f"The Skill Tree data file {database.get_db_path()} was saved by an "
                f"older version of Skill Tree (data format {current_v}; this version "
                f"reads {SCHEMA_VERSION}), and this version doesn't upgrade one. "
                "Nothing was changed.")
        database.check_integrity()

    conn = database.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        _create_tables(cursor)
        if not has_tables:
            _seed_new_database(cursor)
        cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _seed_new_database(cursor):
    """What a new database starts with besides its tables: one Resource
    section for web pages and files, which users rename or add to in
    Settings > Resources, and when the two histories began. A node already
    in the graph has no history from before them."""
    cursor.execute("INSERT INTO ResourceSections (id, name, kind, root_path, position) "
                   "VALUES ('links', 'Links', 'mixed', '', 0)")
    started_at = str(_utc_now_ts())
    cursor.executemany("INSERT INTO Settings (key, value) VALUES (?, ?)",
                       [("lifecycle_history_started_at", started_at),
                        ("node_ledger_started_at", started_at)])


def _create_tables(cursor):
    """The full current schema, for a new database; a no-op on an existing one."""
    # Every column the app reads. Column groups: core attributes, lifecycle
    # flags, scoring modes, habit-mode breakdown, time-calibration actuals,
    # and retrospective reflection ratings.
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
            reflect_difficulty INTEGER,
            reflect_notes TEXT
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
    # A node belongs to at most one event.
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_event_nodes_node "
                   "ON EventNodes(node_name)")

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
            -- 'migration_snapshot': a Now start recorded, when this history
            -- began, for a node already in Now.
            source TEXT NOT NULL DEFAULT 'live'
                CHECK(source IN ('live', 'migration_snapshot')),
            -- On a now_started row: the node's place in the recommendation
            -- ranking just before it entered Now (1 = top), and how many
            -- nodes were ranked. rank is NULL when the node wasn't ranked
            -- (Blocked, a Goal), and both are NULL on older rows.
            rank INTEGER,
            ranked_of INTEGER,
            FOREIGN KEY (node_name) REFERENCES Nodes(name) ON DELETE CASCADE
        )
    ''')
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_node_lifecycle_events_node_time "
        "ON NodeLifecycleEvents(node_name, occurred_at, id)"
    )
    # Nodes entering and leaving the graph, with the estimate each carried.
    # No foreign key: a deleted node's rows must outlive it. hours is the
    # node's own expected time (0 for one whose time comes from its
    # children) and status what it was at that moment, so deleting finished
    # work can be told from dropping planned work.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS NodeLedger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_name TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN ('created', 'deleted')),
            occurred_at INTEGER NOT NULL,
            node_type TEXT NOT NULL,
            context TEXT,
            hours REAL NOT NULL,
            status TEXT NOT NULL
        )
    ''')
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_node_ledger_time "
        "ON NodeLedger(occurred_at, id)"
    )
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Aliases (
            alias TEXT PRIMARY KEY,
            node_name TEXT NOT NULL,
            FOREIGN KEY (node_name) REFERENCES Nodes(name) ON DELETE CASCADE
        )
    ''')
