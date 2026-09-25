"""SQLite row persistence; the manager owns transactions and graph side effects."""
import sqlite3
from typing import List, Dict, Optional
import database
from models import Node
from resource_links import save_node_links


class GraphRepository:
    def __init__(self, connection_factory):
        self.get_connection = connection_factory

    def _with_resources(self, nodes):
        """Attach one batch of named links without a query per node."""
        snapshot = database.current_snapshot()
        if snapshot is not None:
            links = snapshot.resource_links
        else:
            links = {}
            if nodes:
                names = [node.name for node in nodes]
                with self.get_connection() as conn:
                    for start in range(0, len(names), 500):
                        batch = names[start:start + 500]
                        placeholders = ','.join('?' for _ in batch)
                        for name, section_id, target in conn.execute(
                                "SELECT node_name, section_id, target FROM NodeResourceLinks "
                                f"WHERE node_name IN ({placeholders}) "
                                "ORDER BY node_name, section_id, position", batch):
                            links.setdefault(name, {}).setdefault(section_id, []).append(target)
        for node in nodes:
            node.resource_links = {key: list(values) for key, values in
                                   links.get(node.name, {}).items()}
        return nodes

    def get_node(self, name: str) -> Optional[Node]:
        """Retrieves a specific node by name."""
        snapshot = database.current_snapshot()
        if snapshot is not None:
            row = snapshot.nodes.get(name)
            return self._with_resources([Node(**row)])[0] if row is not None else None
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Nodes WHERE name=?", (name,))
            row = cursor.fetchone()
            if row:
                return self._with_resources([Node(**dict(row))])[0]
            return None


    def get_node_lifecycle_events(self, node_name: str) -> List[dict]:
        """Return one node's lifecycle boundaries in stable occurrence order."""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, node_name, event_type, occurred_at, source "
                "FROM NodeLifecycleEvents WHERE node_name=? "
                "ORDER BY occurred_at, id",
                (node_name,),
            ).fetchall()
        return [dict(row) for row in rows]


    def get_aliases(self, node_name: str) -> list:
        """Return all aliases for a node."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT alias FROM Aliases WHERE node_name=?", (node_name,))
            return [row[0] for row in cursor.fetchall()]


    def get_all_aliases(self) -> dict:
        """Return {alias: node_name} mapping for all aliases.

        Keys are the stored (titlecase-linted) form. For case-insensitive
        lookups use :py:meth:`resolve_alias`.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT alias, node_name FROM Aliases")
            return {row[0]: row[1] for row in cursor.fetchall()}


    def resolve_alias(self, alias_input: str) -> Optional[str]:
        """Look up the node name for an alias, case-insensitively.

        Aliases are stored titlecase-linted, but the user may type any case
        (e.g. ``alias:mathnotes`` matches a stored ``MathNotes``). Returns
        the node name on hit, or ``None`` on miss.
        """
        if not alias_input:
            return None
        target = alias_input.strip().casefold()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # SQLite's LOWER is ASCII-only but our aliases are user-controlled
            # text — fall back to a Python loop so casefold (which handles
            # full Unicode) is the source of truth.
            cursor.execute("SELECT alias, node_name FROM Aliases")
            for alias, node_name in cursor.fetchall():
                if alias.casefold() == target:
                    return node_name
        return None


    def get_all_nodes(self, include_dormant: bool = False) -> List[Node]:
        """Retrieves all nodes. Excludes dormant nodes by default."""
        snapshot = database.current_snapshot()
        if snapshot is not None:
            return self._with_resources([Node(**row) for row in snapshot.nodes.values()
                    if include_dormant or not row['dormant']])
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if include_dormant:
                cursor.execute("SELECT * FROM Nodes")
            else:
                cursor.execute("SELECT * FROM Nodes WHERE dormant = 0")
            return self._with_resources([Node(**dict(row)) for row in cursor.fetchall()])


    def get_now_nodes(self) -> List[Node]:
        """Return all nodes flagged Now (currently being worked on).

        Dormant nodes are excluded — a shelved node should not also be
        "currently being worked on", and the Now section should never
        surface one.
        """
        if database.current_snapshot() is not None:
            return sorted((n for n in self.get_all_nodes() if n.now > 0),
                          key=lambda n: (n.now, n.name))
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM Nodes WHERE "now" > 0 AND dormant = 0 ORDER BY "now" ASC, name ASC')
            return self._with_resources([Node(**dict(row)) for row in cursor.fetchall()])


    def get_edges(self) -> List[Dict[str, str]]:
        """Retrieves all edges."""
        snapshot = database.current_snapshot()
        if snapshot is not None:
            return [dict(edge) for edge in snapshot.edges]
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Edges")
            return [dict(row) for row in cursor.fetchall()]


    def insert_node(self, node):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                data = node.to_dict()
                data.pop('priority_score', None)
                data.pop('time', None)  # time is a computed property
                cursor.execute('''
                    INSERT INTO Nodes (name, type, description, value, time_o, time_m, time_p, interest, difficulty, context, subcontext, status, dormant, time_mode, value_mode, habit_duration, habit_duration_unit, habit_intensity_o, habit_intensity_m, habit_intensity_p, habit_intensity_unit, habit_days, actual_time_lower, actual_time_upper, actual_time_point, actual_time_unit, calibration_dismissed, "now", start_date, done_date, reflect_value, reflect_interest, reflect_difficulty)
                    VALUES (:name, :type, :description, :value, :time_o, :time_m, :time_p, :interest, :difficulty, :context, :subcontext, :status, :dormant, :time_mode, :value_mode, :habit_duration, :habit_duration_unit, :habit_intensity_o, :habit_intensity_m, :habit_intensity_p, :habit_intensity_unit, :habit_days, :actual_time_lower, :actual_time_upper, :actual_time_point, :actual_time_unit, :calibration_dismissed, :now, :start_date, :done_date, :reflect_value, :reflect_interest, :reflect_difficulty)
                ''', data)
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Node with name '{node.name}' already exists.")
        # Links live in their own table. A new node may arrive with some (a
        # script building a node); an update never rewrites them, since the
        # editor saves them itself through save_node_links.
        if node.resource_links:
            save_node_links(node.name, node.resource_links)


    def write_node(self, node, lifecycle_event_types, clock):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            data = node.to_dict()
            data.pop('priority_score', None)
            data.pop('time', None)
            cursor.execute('''
                UPDATE Nodes
                SET type=:type, description=:description, value=:value, time_o=:time_o, time_m=:time_m, time_p=:time_p,
                    interest=:interest, difficulty=:difficulty,
                    context=:context, subcontext=:subcontext, status=:status,
                    dormant=:dormant, time_mode=:time_mode, value_mode=:value_mode,
                    habit_duration=:habit_duration, habit_duration_unit=:habit_duration_unit,
                    habit_intensity_o=:habit_intensity_o, habit_intensity_m=:habit_intensity_m,
                    habit_intensity_p=:habit_intensity_p, habit_intensity_unit=:habit_intensity_unit,
                    habit_days=:habit_days,
                    actual_time_lower=:actual_time_lower, actual_time_upper=:actual_time_upper,
                    actual_time_point=:actual_time_point, actual_time_unit=:actual_time_unit,
                    calibration_dismissed=:calibration_dismissed,
                    "now"=:now, start_date=:start_date, done_date=:done_date,
                    reflect_value=:reflect_value, reflect_interest=:reflect_interest,
                    reflect_difficulty=:reflect_difficulty
                WHERE name=:name
            ''', data)
            if lifecycle_event_types:
                occurred_at = clock()
                cursor.executemany(
                    "INSERT INTO NodeLifecycleEvents "
                    "(node_name, event_type, occurred_at, source) "
                    "VALUES (?, ?, ?, 'live')",
                    [(node.name, event_type, occurred_at)
                     for event_type in lifecycle_event_types],
                )
            conn.commit()


    def rename_node(self, old_name, new_name):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Nodes SET name=? WHERE name=?", (new_name, old_name))
            cursor.execute("UPDATE Edges SET source=? WHERE source=?", (new_name, old_name))
            cursor.execute("UPDATE Edges SET target=? WHERE target=?", (new_name, old_name))
            cursor.execute("UPDATE EventTriggerNodes SET node_name=? WHERE node_name=?", (new_name, old_name))
            cursor.execute("UPDATE EventNodes SET node_name=? WHERE node_name=?", (new_name, old_name))
            cursor.execute("UPDATE NodeLifecycleEvents SET node_name=? WHERE node_name=?", (new_name, old_name))
            cursor.execute("UPDATE Aliases SET node_name=? WHERE node_name=?", (new_name, old_name))
            cursor.execute("UPDATE NodeResourceLinks SET node_name=? WHERE node_name=?", (new_name, old_name))
