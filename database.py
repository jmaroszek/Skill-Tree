import sqlite3
import os

DB_FILENAME = "skilltree.db"

def get_db_path():
    """Returns the absolute path to the SQLite database file."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, DB_FILENAME)


def init_db():
    """Initializes the SQLite database with the required tables."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create Nodes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Nodes (
            name TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            description TEXT NOT NULL,
            value INTEGER NOT NULL,
            time INTEGER NOT NULL,
            interest INTEGER NOT NULL,
            effort INTEGER NOT NULL,
            competence TEXT,
            context TEXT,
            subcontext TEXT,
            status TEXT NOT NULL
        )
    ''')

    # Create Edges table
    # Source constraints are NOT enforced as foreign keys at the DB level 
    # right now to allow flexible graph managers, though we could enforce them.
    # We will enforce node existence in the Python layer instead.
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

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
