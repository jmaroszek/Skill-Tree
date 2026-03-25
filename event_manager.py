import sqlite3
from datetime import date, timedelta
import database
from models import Node, Event
from typing import List, Dict, Optional


class EventManager:
    def __init__(self):
        database.init_db()

    def get_connection(self) -> sqlite3.Connection:
        return database.get_connection()

    # --- Event CRUD ---

    def add_event(self, event: Event):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO Events (name, description, status, trigger_date) VALUES (?, ?, ?, ?)",
                    (event.name, event.description, event.status, event.trigger_date)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Event with name '{event.name}' already exists.")

    def update_event(self, old_name: str, event: Event):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if old_name != event.name:
                # Temporarily disable FK checks for the rename
                cursor.execute("PRAGMA foreign_keys = OFF")
                cursor.execute(
                    "UPDATE Events SET name=?, description=?, status=?, trigger_date=? WHERE name=?",
                    (event.name, event.description, event.status, event.trigger_date, old_name)
                )
                cursor.execute(
                    "UPDATE EventNodes SET event_name=? WHERE event_name=?",
                    (event.name, old_name)
                )
                cursor.execute("PRAGMA foreign_keys = ON")
            else:
                cursor.execute(
                    "UPDATE Events SET description=?, status=?, trigger_date=? WHERE name=?",
                    (event.description, event.status, event.trigger_date, old_name)
                )
            conn.commit()

    def delete_event(self, event_name: str, delete_nodes: bool = True):
        """Deletes an event. If delete_nodes is True, also deletes its dormant nodes.
        If False, activates them instead."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if delete_nodes:
                # Get dormant node names, then delete them
                cursor.execute(
                    "SELECT node_name FROM EventNodes WHERE event_name=? AND activated=0",
                    (event_name,)
                )
                dormant_names = [row[0] for row in cursor.fetchall()]
                for name in dormant_names:
                    cursor.execute("DELETE FROM Edges WHERE source=? OR target=?", (name, name))
                    cursor.execute("DELETE FROM Nodes WHERE name=?", (name,))
            else:
                # Activate all dormant nodes instead of deleting
                cursor.execute(
                    "UPDATE Nodes SET dormant=0 WHERE name IN "
                    "(SELECT node_name FROM EventNodes WHERE event_name=? AND activated=0)",
                    (event_name,)
                )

            cursor.execute("DELETE FROM Events WHERE name=?", (event_name,))
            conn.commit()

    def get_event(self, name: str) -> Optional[Event]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Events WHERE name=?", (name,))
            row = cursor.fetchone()
            if row:
                return Event(**dict(row))
            return None

    def get_all_events(self) -> List[Event]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Events ORDER BY status, name")
            return [Event(**dict(row)) for row in cursor.fetchall()]

    # --- Event-Node Association ---

    def add_node_to_event(self, event_name: str, node_name: str, delay_days: int = 0):
        """Associates a node with an event and marks it dormant."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE Nodes SET dormant=1 WHERE name=?", (node_name,)
            )
            cursor.execute(
                "INSERT INTO EventNodes (event_name, node_name, delay_days) VALUES (?, ?, ?)",
                (event_name, node_name, delay_days)
            )
            conn.commit()

    def remove_node_from_event(self, event_name: str, node_name: str):
        """Removes a dormant node from an event and deletes it."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM EventNodes WHERE event_name=? AND node_name=?",
                (event_name, node_name)
            )
            cursor.execute("DELETE FROM Edges WHERE source=? OR target=?", (node_name, node_name))
            cursor.execute("DELETE FROM Nodes WHERE name=?", (node_name,))
            conn.commit()

    def get_event_nodes(self, event_name: str) -> List[Dict]:
        """Returns list of {node, delay_days, activation_date, activated} for an event."""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT n.*, en.delay_days, en.activation_date, en.activated
                FROM EventNodes en
                JOIN Nodes n ON en.node_name = n.name
                WHERE en.event_name=?
                ORDER BY en.delay_days, n.name
            ''', (event_name,))
            results = []
            for row in cursor.fetchall():
                row_dict = dict(row)
                delay_days = row_dict.pop('delay_days')
                activation_date = row_dict.pop('activation_date')
                activated = row_dict.pop('activated')
                node = Node(**row_dict)
                results.append({
                    'node': node,
                    'delay_days': delay_days,
                    'activation_date': activation_date,
                    'activated': activated,
                })
            return results

    def get_event_node_count(self, event_name: str) -> Dict[str, int]:
        """Returns counts of total and activated nodes for an event."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM EventNodes WHERE event_name=?", (event_name,)
            )
            total = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM EventNodes WHERE event_name=? AND activated=1",
                (event_name,)
            )
            activated = cursor.fetchone()[0]
            return {'total': total, 'activated': activated}

    def set_node_delay(self, event_name: str, node_name: str, delay_days: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE EventNodes SET delay_days=? WHERE event_name=? AND node_name=?",
                (delay_days, event_name, node_name)
            )
            conn.commit()

    def get_events_for_node(self, node_name: str) -> List[str]:
        """Returns list of event names that own this node."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT event_name FROM EventNodes WHERE node_name=?", (node_name,)
            )
            return [row[0] for row in cursor.fetchall()]

    # --- Activation ---

    def trigger_event(self, event_name: str) -> Dict[str, list]:
        """Triggers an event, activating immediate nodes and scheduling delayed ones.

        Returns dict with 'activated' (immediate) and 'scheduled' (delayed) node names.
        """
        from graph_manager import GraphManager
        gm = GraphManager()

        result = {'activated': [], 'scheduled': []}
        today = date.today()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Mark event as triggered
            cursor.execute(
                "UPDATE Events SET status='Triggered' WHERE name=?", (event_name,)
            )

            # Get all event nodes
            cursor.execute(
                "SELECT node_name, delay_days FROM EventNodes WHERE event_name=? AND activated=0",
                (event_name,)
            )
            rows = cursor.fetchall()

            for node_name, delay_days in rows:
                if delay_days == 0:
                    # Immediate activation
                    cursor.execute("UPDATE Nodes SET dormant=0 WHERE name=?", (node_name,))
                    cursor.execute(
                        "UPDATE EventNodes SET activated=1, activation_date=? WHERE event_name=? AND node_name=?",
                        (today.isoformat(), event_name, node_name)
                    )
                    result['activated'].append(node_name)
                else:
                    # Scheduled activation
                    activation_date = today + timedelta(days=delay_days)
                    cursor.execute(
                        "UPDATE EventNodes SET activation_date=? WHERE event_name=? AND node_name=?",
                        (activation_date.isoformat(), event_name, node_name)
                    )
                    result['scheduled'].append(node_name)

            conn.commit()

        # Cascade state updates for immediately activated nodes
        for node_name in result['activated']:
            gm._update_node_state(node_name)

        return result

    def check_pending_activations(self) -> List[str]:
        """Checks for delayed nodes whose activation date has arrived.

        Returns list of newly activated node names.
        """
        from graph_manager import GraphManager
        gm = GraphManager()

        today = date.today().isoformat()
        activated = []

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT node_name FROM EventNodes
                WHERE activation_date IS NOT NULL AND activation_date <= ? AND activated = 0
            ''', (today,))
            pending = [row[0] for row in cursor.fetchall()]

            for node_name in pending:
                cursor.execute("UPDATE Nodes SET dormant=0 WHERE name=?", (node_name,))
                cursor.execute(
                    "UPDATE EventNodes SET activated=1 WHERE node_name=?", (node_name,)
                )
                activated.append(node_name)

            conn.commit()

        # Cascade state updates
        for node_name in activated:
            gm._update_node_state(node_name)

        return activated

    # --- Convenience ---

    def create_dormant_node(self, node: Node, event_name: str, delay_days: int = 0):
        """Creates a node as dormant and associates it with an event."""
        from graph_manager import GraphManager
        gm = GraphManager()

        node.dormant = 1
        gm.add_node(node)
        self.add_node_to_event(event_name, node.name, delay_days)
