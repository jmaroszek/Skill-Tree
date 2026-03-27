import sqlite3
import os
from pathlib import Path

DB_FILENAME = "skilltree.db"


def get_db_path() -> str:
    """Returns the absolute path to the SQLite database file."""
    from config import ENVIRONMENT
    db_name = DB_FILENAME
    if ENVIRONMENT == "sandbox":
        db_name = "sandbox_" + DB_FILENAME
    return str(Path(__file__).parent / db_name)


def get_connection() -> sqlite3.Connection:
    """Creates and returns a new database connection with foreign keys enabled."""
    conn = sqlite3.connect(get_db_path())
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initializes the SQLite database with the required tables."""
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
            frequency TEXT,
            session_lower REAL,
            session_expected REAL,
            session_upper REAL,
            habit_status TEXT DEFAULT 'Active',
            progress INTEGER DEFAULT 0,
            website TEXT
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Events (
            name TEXT PRIMARY KEY,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pending'
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

    # Migrations: add columns that may not exist in older databases
    cursor.execute("PRAGMA table_info(Nodes)")
    node_columns = [row[1] for row in cursor.fetchall()]
    if 'dormant' not in node_columns:
        cursor.execute("ALTER TABLE Nodes ADD COLUMN dormant INTEGER NOT NULL DEFAULT 0")

    cursor.execute("PRAGMA table_info(Events)")
    event_columns = [row[1] for row in cursor.fetchall()]
    if 'trigger_date' not in event_columns:
        cursor.execute("ALTER TABLE Events ADD COLUMN trigger_date TEXT")
    if 'trigger_node' not in event_columns:
        cursor.execute("ALTER TABLE Events ADD COLUMN trigger_node TEXT")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
