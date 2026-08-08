import sqlite3
from pathlib import Path
from typing import Optional


# Snapshot of the resolved DB path on first call. Reading config.ENVIRONMENT
# on every call risks splitting a single process between sandbox and prod if
# the env var is ever mutated mid-run (test fixtures, REPL re-imports, etc.).
# Caching guarantees a process commits to one DB for its lifetime. Tests that
# need a different path monkeypatch get_db_path itself (see conftest), which
# bypasses this cache entirely.
_db_path_cache: Optional[str] = None


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
    _db_path_cache = str(Path(__file__).parent / "data" / db_name)
    return _db_path_cache


def get_connection() -> sqlite3.Connection:
    """Creates and returns a new database connection with foreign keys enabled."""
    conn = sqlite3.connect(get_db_path())
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_initialized = False

# Bump whenever a schema change lands that an existing DB can't pick up from
# the CREATE TABLE IF NOT EXISTS statements alone, and add the matching step
# to _migrate().
SCHEMA_VERSION = 5


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
                print(f"NOTE: left legacy Events.trigger_node in place ({exc}).")


def init_db():
    """Initializes the SQLite database with the required tables.

    Safe to call multiple times — only performs work on the first invocation.
    """
    global _initialized
    if _initialized:
        return
    conn = get_connection()
    cursor = conn.cursor()

    # Schema version stamp. The baseline schema is v4, defined in full by the
    # CREATE TABLE statements below (CREATE TABLE IF NOT EXISTS is a no-op on an
    # existing DB, so the tables aren't rebuilt). Changes past v4 can't ride on
    # CREATE TABLE for existing DBs, so they live in _migrate() as a version
    # ladder. A stored value higher than SCHEMA_VERSION means the DB was last
    # touched by a newer app build than this one — warn, since this app may not
    # recognize columns a future version added.
    current_v = cursor.execute("PRAGMA user_version").fetchone()[0]
    if current_v > SCHEMA_VERSION:
        print(f"WARNING: SQLite DB user_version={current_v} is newer than app's "
              f"{SCHEMA_VERSION}. Some columns may be unrecognized.")

    # Full Nodes schema. Every column the app reads lives here — there are no
    # follow-up ALTER TABLE migrations. (This consolidates an earlier era where
    # the table was created with a partial column set and incrementally extended
    # by ALTERs; folding them in keeps the schema self-describing.) Column
    # groups: core attributes, links, lifecycle flags, scoring modes, habit-mode
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
            obsidian_path TEXT,
            google_drive_path TEXT,
            website TEXT,
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
            -- auto-stamp on first activation / first Done. reflect_* are
            -- retrospective ratings.
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
            -- Override intent applied to the node when the event triggers.
            override_on_trigger INTEGER NOT NULL DEFAULT 0,
            override_mode TEXT,
            PRIMARY KEY (event_name, node_name),
            FOREIGN KEY (event_name) REFERENCES Events(name) ON DELETE CASCADE,
            FOREIGN KEY (node_name) REFERENCES Nodes(name) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Aliases (
            alias TEXT PRIMARY KEY,
            node_name TEXT NOT NULL,
            FOREIGN KEY (node_name) REFERENCES Nodes(name) ON DELETE CASCADE
        )
    ''')

    conn.commit()

    _migrate(cursor, current_v)

    cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()

    conn.close()
    _initialized = True


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
