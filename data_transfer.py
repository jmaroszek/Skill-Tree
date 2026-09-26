"""Moving a whole graph in and out: JSON export and import, and restore.

An export holds every row of every table, not a view of them, so importing it
into an empty graph reproduces the original: nodes, relationships, aliases,
events, resources, lifecycle history and settings. A restore copies a backup
over the live database in place, through SQLite's backup API, so the app keeps
running and the next page load shows the restored graph.
"""
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import backup
import database
from graph_state import revisions
from version import __version__

logger = logging.getLogger(__name__)

EXPORT_FORMAT = "skill-tree-export"
EXPORT_VERSION = 1
# Parents before children, so the rows satisfy their foreign keys in order.
TABLES = ("Settings", "ResourceSections", "Nodes", "Aliases", "NodeResourceLinks",
          "Edges", "Events", "EventTriggerNodes", "EventNodes", "NodeLifecycleEvents")


class TransferRefused(ValueError):
    """An import or restore that can't go ahead, with a message for the user."""


# --- Export -----------------------------------------------------------------

def export_data() -> dict:
    """Every row of every table, read in one transaction."""
    with database.state_lock:
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            tables = {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
                      for table in TABLES}
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "app_version": __version__,
        "schema_version": database.SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tables": tables,
    }


def export_json() -> str:
    return json.dumps(export_data(), ensure_ascii=False, indent=1)


def export_database_bytes() -> bytes:
    """A consistent, compact copy of the database file, as bytes."""
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / "skilltree.db"
        backup.copy_database(copy)
        return copy.read_bytes()


# --- Import -----------------------------------------------------------------

def _validated_tables(bundle) -> dict:
    if not isinstance(bundle, dict) or bundle.get("format") != EXPORT_FORMAT:
        raise TransferRefused("That file isn't a Skill Tree export.")
    version = bundle.get("version")
    schema = bundle.get("schema_version")
    if not isinstance(version, int) or not isinstance(schema, int):
        raise TransferRefused("That export is missing its version, so it can't be read safely.")
    if version > EXPORT_VERSION or schema > database.SCHEMA_VERSION:
        raise TransferRefused("That export was made by a newer version of Skill Tree. "
                              "Update Skill Tree to import it.")
    tables = bundle.get("tables")
    if not isinstance(tables, dict):
        raise TransferRefused("That export has no tables in it.")
    for table in TABLES:
        rows = tables.get(table, [])
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise TransferRefused(f"That export's {table} table is malformed.")
    return tables


def import_data(bundle) -> dict:
    """Load an export into this database, which must hold no graph yet.

    The export's settings and resource sections replace the ones a new
    database starts with, so the graph arrives as it was. Everything commits
    in one transaction; a bad row rejects the whole import. Returns the number
    of rows loaded per table.
    """
    tables = _validated_tables(bundle)
    with database.get_connection() as conn:
        nodes = conn.execute("SELECT COUNT(*) FROM Nodes").fetchone()[0]
        events = conn.execute("SELECT COUNT(*) FROM Events").fetchone()[0]
    if nodes or events:
        raise TransferRefused(
            f"Import only fills an empty graph, and this one has {nodes} node(s) "
            f"and {events} event(s). To bring back an earlier graph, restore a "
            "backup instead.")
    backup.create_backup("before-import")
    counts = {}
    try:
        with database.transaction() as conn:
            conn.execute("DELETE FROM ResourceSections")
            conn.execute("DELETE FROM Settings")
            for table in TABLES:
                columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                rows = tables.get(table, [])
                for row in rows:
                    keys = [key for key in row if key in columns]
                    if not keys:
                        continue
                    conn.execute(
                        f"INSERT INTO {table} ({', '.join(keys)}) "
                        f"VALUES ({', '.join('?' for _ in keys)})",
                        [row[key] for key in keys])
                counts[table] = len(rows)
    except sqlite3.DatabaseError as exc:
        raise TransferRefused(f"That export couldn't be imported ({exc}). "
                              "Nothing was changed.") from exc
    _after_replacing_the_graph()
    logger.info("Imported an export: %s", counts)
    return counts


# --- Restore ----------------------------------------------------------------

def _user_version(path) -> int:
    conn = sqlite3.connect(backup._read_only_uri(path), uri=True)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def restore_backup(path) -> None:
    """Replace the live database with a backup's contents, in place.

    The backup must open, pass SQLite's integrity check, and not come from a
    newer version. The current database is backed up before it is replaced,
    and a backup from an older version is upgraded afterwards.
    """
    path = Path(path)
    if not path.is_file():
        raise TransferRefused("That backup no longer exists.")
    try:
        database.check_integrity(str(path))
        version = _user_version(path)
    except (database.DatabaseError, sqlite3.DatabaseError) as exc:
        logger.warning("Refused to restore %s: %s", path, exc)
        raise TransferRefused("That backup is damaged and can't be restored.") from exc
    if version > database.SCHEMA_VERSION:
        raise TransferRefused("That backup was made by a newer version of Skill Tree.")
    backup.create_backup("before-restore")
    with database.state_lock:
        source = sqlite3.connect(backup._read_only_uri(path), uri=True)
        target = sqlite3.connect(database.get_db_path())
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()
        # The restored copy may predate the current schema.
        database._initialized = False
        database.init_db()
    _after_replacing_the_graph()
    logger.info("Restored the database from %s", path)


def _after_replacing_the_graph():
    """Nothing in memory may describe the graph that was just replaced."""
    from graph_manager import GraphManager
    manager = GraphManager()
    manager.pop_auto_done_candidates()
    manager.recompute_all_statuses()
    revisions.changed(scoring=True)
