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
import graph_rules
from graph_state import revisions
from models import ALL_STATUSES, EDGE_HELPS, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT
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


def _shown(name) -> str:
    """A name as a refusal quotes it: in quotes, and cut short if long."""
    text = str(name)
    return repr(text if len(text) <= 60 else text[:57] + "...")


def _refuse(message) -> TransferRefused:
    return TransferRefused(f"That export can't be imported. {message} Nothing was changed.")


def _validated_graph(tables) -> dict:
    """The tables, checked against the rules the editor enforces on every save.

    Import writes rows as they are, so a hand-edited or damaged export could
    load a graph the app could never have built: a name that can't travel
    through menus and the canvas, prerequisites that loop, or one pair
    related as two kinds of prerequisite. Such a graph is refused whole.

    A Helps row whose ends are the wrong way round is put in order instead,
    since a rename in the exporting app can leave one that way. Returns a
    copy of the tables with Edges in that order and without duplicates.
    """
    names = set()
    for row in tables.get("Nodes", []):
        name = row.get("name")
        problem = graph_rules.name_problem(name, "A node name")
        if problem:
            raise _refuse(f"{problem} ({_shown(name)})")
        if row.get("status") not in ALL_STATUSES:
            raise _refuse(f"The node {_shown(name)} has an unknown status, "
                          f"{_shown(row.get('status'))}.")
        names.add(name)
    for table, column, label in (("Events", "name", "An event name"),
                                 ("Aliases", "alias", "An alias")):
        for row in tables.get(table, []):
            problem = graph_rules.name_problem(row.get(column), label)
            if problem:
                raise _refuse(f"{problem} ({_shown(row.get(column))})")

    edges, prerequisite_pairs = {}, {}
    for row in tables.get("Edges", []):
        source, target, kind = row.get("source"), row.get("target"), row.get("type")
        if kind not in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS):
            raise _refuse(f"A relationship has an unknown type, {_shown(kind)}.")
        for end in (source, target):
            if end not in names:
                raise _refuse(f"A relationship names {_shown(end)}, a node "
                              "the export doesn't include.")
        if source == target:
            raise _refuse(f"The node {_shown(source)} is related to itself.")
        source, target = graph_rules._canonicalize_edge(source, target, kind)
        edges[source, target, kind] = {**row, "source": source, "target": target}
        if kind != EDGE_HELPS:
            pair = frozenset((source, target))
            if prerequisite_pairs.setdefault(pair, (source, target, kind)) != (source, target, kind):
                first, second = sorted(pair)
                raise _refuse(f"{_shown(first)} and {_shown(second)} are linked by "
                              "more than one prerequisite. Only one prerequisite "
                              "is allowed between two nodes.")
    looped = graph_rules.cyclic_nodes(
        (source, target) for source, target, _kind in prerequisite_pairs.values())
    if looped:
        listed = ", ".join(_shown(name) for name in sorted(looped)[:4])
        more = f" and {len(looped) - 4} more" if len(looped) > 4 else ""
        raise _refuse(f"Its prerequisites loop back on themselves, through "
                      f"{listed}{more}. Prerequisites have to run one way.")
    return {**tables, "Edges": list(edges.values())}


def import_data(bundle) -> dict:
    """Load an export into this database, which must hold no graph yet.

    The export's settings and resource sections replace the ones a new
    database starts with, so the graph arrives as it was. Everything commits
    in one transaction; a bad row rejects the whole import, and so does a
    graph the editor couldn't have built (_validated_graph). Returns the
    number of rows loaded per table.
    """
    tables = _validated_graph(_validated_tables(bundle))
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
    conn = sqlite3.connect(backup._read_only_uri(path), uri=True,
                           timeout=database.BUSY_TIMEOUT_S)
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
    except sqlite3.DatabaseError as exc:
        refusal = database._refusal_for(exc, str(path))
        raise _refused_backup(path, refusal or exc) from exc
    except database.DatabaseError as exc:
        raise _refused_backup(path, exc) from exc
    if version > database.SCHEMA_VERSION:
        raise TransferRefused("That backup was made by a newer version of Skill Tree.")
    try:
        # Nothing is restored unless the current graph was backed up first.
        backup.create_backup("before-restore")
        with database.state_lock:
            _copy_into_live_database(path)
            # The restored copy may predate the current schema.
            database._initialized = False
            database.init_db()
    except sqlite3.Error as exc:
        refusal = database._refusal_for(exc)
        if refusal is None:
            raise
        logger.warning("Couldn't restore %s: %s", path, exc)
        raise TransferRefused(str(refusal)) from exc
    except database.DatabaseError as exc:
        # The copy is in place; only its upgrade was refused. Startup retries it.
        logger.error("Restored %s, but couldn't upgrade it: %s", path, exc)
        raise TransferRefused(f"The backup was restored, but it couldn't be "
                              f"prepared for this version: {exc} Restart "
                              "Skill Tree to finish.") from exc
    _after_replacing_the_graph()
    logger.info("Restored the database from %s", path)


def _copy_into_live_database(path):
    source = sqlite3.connect(backup._read_only_uri(path), uri=True,
                             timeout=database.BUSY_TIMEOUT_S)
    target = sqlite3.connect(database.get_db_path(), timeout=database.BUSY_TIMEOUT_S)
    try:
        # One step, so a failure leaves the live database as it was.
        source.backup(target)
    finally:
        source.close()
        target.close()


def _refused_backup(path, problem):
    """Why a backup can't be restored, in terms of the backup, not the live file."""
    logger.warning("Refused to restore %s: %s", path, problem)
    if isinstance(problem, database.DatabaseLockedError):
        return TransferRefused("That backup is in use by another program. Close it "
                               "and try again.")
    if isinstance(problem, database.DatabaseUnwritableError):
        return TransferRefused("That backup can't be opened. Skill Tree may lack "
                               "permission to read it.")
    return TransferRefused("That backup is damaged and can't be restored.")


def _after_replacing_the_graph():
    """Nothing in memory may describe the graph that was just replaced.

    The new graph never went through a startup either, so the startup safety
    nets run on it: statuses from prerequisites, and dormant flags from
    events that already woke their nodes.
    """
    from event_manager import EventManager
    from graph_manager import GraphManager
    manager = GraphManager()
    manager.pop_auto_done_candidates()
    manager.recompute_all_statuses()
    EventManager().reconcile_dormant_flags()
    revisions.changed(scoring=True)
