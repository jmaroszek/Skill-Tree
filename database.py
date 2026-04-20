import sqlite3
from pathlib import Path


def get_db_path() -> str:
    """Returns the absolute path to the SQLite database file."""
    # Lazy import dodges the circular dependency: config imports
    # get_connection from this module at load time.
    from config import ENVIRONMENT, DB_FILENAME
    db_name = DB_FILENAME
    if ENVIRONMENT == "sandbox":
        db_name = "sandbox_" + DB_FILENAME
    return str(Path(__file__).parent / "data" / db_name)


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
            competence TEXT,
            context TEXT,
            subcontext TEXT,
            status TEXT NOT NULL,
            obsidian_path TEXT,
            google_drive_path TEXT,
            progress INTEGER DEFAULT 0,
            website TEXT,
            dormant INTEGER NOT NULL DEFAULT 0
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

    conn.close()
    _initialized = True


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
