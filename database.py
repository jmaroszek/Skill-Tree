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


def init_db():
    """Initializes the SQLite database with the required tables.

    Safe to call multiple times — only performs work on the first invocation.
    """
    global _initialized
    if _initialized:
        return
    conn = get_connection()
    cursor = conn.cursor()

    # Schema version stamp. v3.0 establishes the baseline; future versions can
    # branch migration behavior on this number. A higher value means the DB
    # was last touched by a newer app build than this one.
    current_v = cursor.execute("PRAGMA user_version").fetchone()[0]
    if current_v > 3:
        print(f"WARNING: SQLite DB user_version={current_v} is newer than app's 3. "
              "Some columns may be unrecognized.")

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
            habit_duration REAL NOT NULL DEFAULT 0,
            habit_duration_unit TEXT NOT NULL DEFAULT 'weeks',
            habit_intensity_o REAL NOT NULL DEFAULT 0,
            habit_intensity_m REAL NOT NULL DEFAULT 0,
            habit_intensity_p REAL NOT NULL DEFAULT 0,
            habit_intensity_unit TEXT NOT NULL DEFAULT 'min_per_day'
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
            trigger_node TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS EventNodes (
            event_name TEXT NOT NULL,
            node_name TEXT NOT NULL,
            delay_days INTEGER NOT NULL DEFAULT 0,
            activation_date TEXT,
            activated INTEGER NOT NULL DEFAULT 0,
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

    # --- Migrations ---
    # Add time_mode column (defaults to 'manual' for existing nodes)
    try:
        cursor.execute("ALTER TABLE Nodes ADD COLUMN time_mode TEXT NOT NULL DEFAULT 'manual'")
        conn.commit()
    except Exception:
        pass  # Column already exists

    # Add value_mode column. Mirrors time_mode: 'inherited' makes the node a
    # pure structural conduit whose own v/i/d ratings contribute 0 to its
    # intrinsic value in scoring. Defaults to 'manual' for existing rows.
    try:
        cursor.execute("ALTER TABLE Nodes ADD COLUMN value_mode TEXT NOT NULL DEFAULT 'manual'")
        conn.commit()
    except Exception:
        pass  # Column already exists

    # Store override intent on dormant nodes so it can be applied at event trigger time.
    try:
        cursor.execute("ALTER TABLE EventNodes ADD COLUMN override_on_trigger INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE EventNodes ADD COLUMN override_mode TEXT")
        conn.commit()
    except Exception:
        pass

    # Drop the deprecated Resource-completion `progress` column. DROP COLUMN
    # requires SQLite 3.35+; if unsupported or already removed, the except
    # swallows the error so startup doesn't fail on older builds.
    try:
        cursor.execute("ALTER TABLE Nodes DROP COLUMN progress")
        conn.commit()
    except Exception:
        pass

    # Habit-mode breakdown columns. Persisted alongside the computed
    # time_o/m/p so re-opening the editor restores the duration × intensity
    # form a user typed, not just the resulting hours.
    for stmt in (
        "ALTER TABLE Nodes ADD COLUMN habit_duration REAL NOT NULL DEFAULT 0",
        "ALTER TABLE Nodes ADD COLUMN habit_duration_unit TEXT NOT NULL DEFAULT 'weeks'",
        "ALTER TABLE Nodes ADD COLUMN habit_intensity_o REAL NOT NULL DEFAULT 0",
        "ALTER TABLE Nodes ADD COLUMN habit_intensity_m REAL NOT NULL DEFAULT 0",
        "ALTER TABLE Nodes ADD COLUMN habit_intensity_p REAL NOT NULL DEFAULT 0",
        "ALTER TABLE Nodes ADD COLUMN habit_intensity_unit TEXT NOT NULL DEFAULT 'min_per_day'",
    ):
        try:
            cursor.execute(stmt)
            conn.commit()
        except Exception:
            pass

    # One-time data migration: Goal nodes must use time_mode='inherited' (the
    # editor enforces this for new saves; this catches pre-existing rows).
    # Idempotent — once flipped, the WHERE clause matches no rows. time_o/m/p
    # values are preserved (Node.time short-circuits to 0 for inherited mode
    # but stored values stay intact, so a future type-change restores them).
    try:
        cursor.execute(
            "UPDATE Nodes SET time_mode='inherited' "
            "WHERE type='Goal' AND time_mode='manual'"
        )
        conn.commit()
    except Exception:
        pass

    cursor.execute("PRAGMA user_version = 3")
    conn.commit()

    conn.close()
    _initialized = True


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
