import sqlite3
import json
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

    # Migration
    existing_cols = {row[1] for row in cursor.execute('PRAGMA table_info(Nodes)').fetchall()}
    
    if 'time' in existing_cols:
        cursor.execute('ALTER TABLE Nodes RENAME COLUMN time TO time_m')
        cursor.execute('ALTER TABLE Nodes RENAME COLUMN effort TO difficulty')
        cursor.execute('ALTER TABLE Nodes ADD COLUMN time_o REAL DEFAULT 1.0')
        cursor.execute('ALTER TABLE Nodes ADD COLUMN time_p REAL DEFAULT 1.0')
        cursor.execute('UPDATE Nodes SET time_o = time_m, time_p = time_m')
        
    if 'obsidian_path' not in existing_cols:
        cursor.execute('ALTER TABLE Nodes ADD COLUMN obsidian_path TEXT')
        
    if 'google_drive_path' not in existing_cols:
        cursor.execute('ALTER TABLE Nodes ADD COLUMN google_drive_path TEXT')
        
    if 'subcontext' not in existing_cols:
        cursor.execute('ALTER TABLE Nodes ADD COLUMN subcontext TEXT')

    if 'frequency' not in existing_cols:
        cursor.execute('ALTER TABLE Nodes ADD COLUMN frequency TEXT')
    if 'session_lower' not in existing_cols:
        cursor.execute('ALTER TABLE Nodes ADD COLUMN session_lower REAL')
    if 'session_expected' not in existing_cols:
        cursor.execute('ALTER TABLE Nodes ADD COLUMN session_expected REAL')
    if 'session_upper' not in existing_cols:
        cursor.execute('ALTER TABLE Nodes ADD COLUMN session_upper REAL')
    if 'habit_status' not in existing_cols:
        cursor.execute("ALTER TABLE Nodes ADD COLUMN habit_status TEXT DEFAULT 'Active'")
    if 'progress' not in existing_cols:
        cursor.execute('ALTER TABLE Nodes ADD COLUMN progress INTEGER DEFAULT 0')
    if 'website' not in existing_cols:
        cursor.execute('ALTER TABLE Nodes ADD COLUMN website TEXT')

    # Migrate Topic/Skill types to Learn
    cursor.execute("UPDATE Nodes SET type='Learn' WHERE type IN ('Topic', 'Skill')")

    # Migrate stored NODE_TYPES setting: replace Topic/Skill with Learn
    cursor.execute("SELECT value FROM Settings WHERE key='NODE_TYPES'")
    row = cursor.fetchone()
    if row:
        try:
            types = json.loads(row[0])
            old_types = set(types)
            if 'Topic' in old_types or 'Skill' in old_types:
                new_types = []
                learn_added = False
                for t in types:
                    if t in ('Topic', 'Skill'):
                        if not learn_added:
                            new_types.append('Learn')
                            learn_added = True
                    else:
                        new_types.append(t)
                cursor.execute("UPDATE Settings SET value=? WHERE key='NODE_TYPES'", (json.dumps(new_types),))
        except (json.JSONDecodeError, TypeError):
            pass

    # Migrate stored NODE_SHAPES setting: replace Topic/Skill keys with Learn
    cursor.execute("SELECT value FROM Settings WHERE key='NODE_SHAPES'")
    row = cursor.fetchone()
    if row:
        try:
            shapes = json.loads(row[0])
            if 'Topic' in shapes or 'Skill' in shapes:
                shapes['Learn'] = shapes.pop('Topic', shapes.pop('Skill', 'ellipse'))
                shapes.pop('Topic', None)
                shapes.pop('Skill', None)
                cursor.execute("UPDATE Settings SET value=? WHERE key='NODE_SHAPES'", (json.dumps(shapes),))
        except (json.JSONDecodeError, TypeError):
            pass

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
    
    # Edge migration for Needs -> Needs_Hard
    cursor.execute("UPDATE Edges SET type='Needs_Hard' WHERE type='Needs'")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
