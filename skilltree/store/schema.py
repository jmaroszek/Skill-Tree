"""The database's tables, and upgrading an older file to them.

_create_tables defines the baseline (schema v4) in full. Every later change is
a step in _migrate's version ladder, and SCHEMA_VERSION is the newest."""
import logging
import sqlite3
import time
from pathlib import Path

from skilltree.store import backup
from skilltree.store import database
from skilltree.store.database import (
    NewerDatabaseError, SQLiteTooOldError, refusal_for, unreadable,
)
from skilltree.store.resources import normalize_link, parse_links

logger = logging.getLogger(__name__)


# Bump whenever a schema change lands that an existing DB can't pick up from
# the CREATE TABLE IF NOT EXISTS statements alone, and add the matching step
# to _migrate().
SCHEMA_VERSION = 13


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
        has_legacy = _has_column(cursor, "Nodes", "obsidian_path")
        seeds = LEGACY_RESOURCE_SECTIONS if has_legacy else _NEW_RESOURCE_SECTIONS
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
        if _has_column(cursor, "Nodes", "obsidian_path"):
            for section_id, _name, kind, _root_key, column in LEGACY_RESOURCE_SECTIONS:
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
            for _section_id, _name, _kind, _root_key, column in LEGACY_RESOURCE_SECTIONS:
                cursor.execute(f"ALTER TABLE Nodes DROP COLUMN {column}")
        if _has_column(cursor, "ResourceSections", "enabled"):
            cursor.execute("ALTER TABLE ResourceSections DROP COLUMN enabled")
        cursor.execute("DELETE FROM Settings WHERE key IN "
                       "('OBSIDIAN_ENABLED', 'OBSIDIAN_VAULT', 'GDRIVE_ENABLED', 'GDRIVE_ROOT_PATH')")

    # --- v12: history to answer two questions later. Does work enter the
    # graph faster than it leaves? NodeLedger (created by _create_tables)
    # records each node added and deleted from now on, with its estimate; the
    # marker says when that coverage began, since nodes already here have no
    # creation date to give. Do you follow the recommendations? A Now start
    # records the node's place in the ranking, in two new columns.
    if from_version < 12:
        cursor.execute(
            "INSERT OR IGNORE INTO Settings (key, value) VALUES (?, ?)",
            ("node_ledger_started_at", str(_utc_now_ts())),
        )
        for column in ("rank", "ranked_of"):
            if not _has_column(cursor, "NodeLifecycleEvents", column):
                cursor.execute(
                    f"ALTER TABLE NodeLifecycleEvents ADD COLUMN {column} INTEGER")

    # --- v13: a written reflection beside the reflect ratings.
    if from_version < 13:
        if not _has_column(cursor, "Nodes", "reflect_notes"):
            cursor.execute("ALTER TABLE Nodes ADD COLUMN reflect_notes TEXT")


# The three link columns Nodes carried before v11, and the sections v10 made
# of them: (section id, name, kind, root-path setting key, Nodes column).
LEGACY_RESOURCE_SECTIONS = (
    ("obsidian", "Obsidian", "obsidian", "OBSIDIAN_VAULT", "obsidian_path"),
    ("drive", "Google Drive", "mixed", "GDRIVE_ROOT_PATH", "google_drive_path"),
    ("website", "Website", "mixed", None, "website"),
)


# What a new database starts with: web pages and files, one list.
_NEW_RESOURCE_SECTIONS = (
    ("links", "Links", "mixed", None, None),
)


# DROP COLUMN (the v11 step) and VACUUM INTO (backups) need these features.
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


# The databases this process has brought to the current schema, by path.
_current = set()


def init_db(*, recheck=False):
    """Create or upgrade the schema of the database database.get_db_path() names.

    Each database is checked once per process. recheck=True checks it again,
    as after a restore replaces its file.

    Refuses (DatabaseError) a database this build can't safely open: one saved
    by a newer version, or one failing SQLite's integrity check. Neither is
    touched. An existing database that needs upgrading is backed up first, and
    the whole upgrade (tables, migration steps, version stamp) is one
    transaction, so a failure part-way leaves it exactly as it was.
    """
    path = database.get_db_path()
    if path in _current and not recheck:
        return
    # Only an upgrade that finishes makes the file current again.
    _current.discard(path)
    if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
        raise SQLiteTooOldError(
            "Skill Tree needs SQLite {} or newer, and this Python has {}.".format(
                ".".join(map(str, MIN_SQLITE_VERSION)), sqlite3.sqlite_version))
    try:
        _open_and_upgrade()
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
            f"The Skill Tree data file {database.get_db_path()} was saved by a newer "
            f"version of Skill Tree (data format {current_v}; this version "
            f"reads up to {SCHEMA_VERSION}). Install the newer version to open "
            "it. Nothing was changed.")
    if has_tables:
        database.check_integrity()
        if current_v < SCHEMA_VERSION:
            backup.create_backup("pre-migration")

    conn = database.get_connection()
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
