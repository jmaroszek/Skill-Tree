"""
Event + dormant-node persistence and activation logic.

An Event has one of three trigger types — manual (user clicks "trigger"),
date-based (an ISO date is reached), or node-based (a specific node flips
to Done). Each Event owns zero or more *dormant* nodes that are not part
of the live graph until the event fires, at which point they are flipped
to active (with an optional per-node delay) via check_pending_events().
"""

import sqlite3
from datetime import date, timedelta
import database
from models import Node, Event
from typing import List, Dict, Optional


class EventManager:
    """Gateway for the Events and EventNodes tables.

    Mirrors the shape of GraphManager but scoped to event-related state.
    Construction runs database.init_db() defensively so the schema exists
    regardless of which module is imported first.
    """

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
                    "INSERT INTO Events (name, description, status, trigger_date, trigger_node) VALUES (?, ?, ?, ?, ?)",
                    (event.name, event.description, event.status, event.trigger_date, event.trigger_node)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Event with name '{event.name}' already exists.")

    def update_event(self, old_name: str, event: Event):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if old_name != event.name:
                cursor.execute("PRAGMA foreign_keys = OFF")
                cursor.execute(
                    "UPDATE Events SET name=?, description=?, status=?, trigger_date=?, trigger_node=? WHERE name=?",
                    (event.name, event.description, event.status, event.trigger_date, event.trigger_node, old_name)
                )
                cursor.execute(
                    "UPDATE EventNodes SET event_name=? WHERE event_name=?",
                    (event.name, old_name)
                )
                cursor.execute("PRAGMA foreign_keys = ON")
            else:
                cursor.execute(
                    "UPDATE Events SET description=?, status=?, trigger_date=?, trigger_node=? WHERE name=?",
                    (event.description, event.status, event.trigger_date, event.trigger_node, old_name)
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

    def add_node_to_event(self, event_name: str, node_name: str, delay_days: int = 0,
                          override_on_trigger: bool = False,
                          override_mode: Optional[str] = None):
        """Associates a node with an event and marks it dormant.

        override_on_trigger/override_mode persist the user's intent to apply a
        priority override when the event later triggers this node.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE Nodes SET dormant=1 WHERE name=?", (node_name,)
            )
            cursor.execute(
                "INSERT INTO EventNodes (event_name, node_name, delay_days, "
                "override_on_trigger, override_mode) VALUES (?, ?, ?, ?, ?)",
                (event_name, node_name, delay_days,
                 1 if override_on_trigger else 0,
                 override_mode if override_on_trigger else None)
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
        """Returns list of {node, delay_days, activation_date, activated,
        override_on_trigger, override_mode} for an event."""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT n.*, en.delay_days, en.activation_date, en.activated,
                       en.override_on_trigger, en.override_mode
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
                override_on_trigger = row_dict.pop('override_on_trigger', 0)
                override_mode = row_dict.pop('override_mode', None)
                node = Node(**row_dict)
                results.append({
                    'node': node,
                    'delay_days': delay_days,
                    'activation_date': activation_date,
                    'activated': activated,
                    'override_on_trigger': bool(override_on_trigger),
                    'override_mode': override_mode,
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

    def get_events_triggered_by_node(self, node_name: str) -> List['Event']:
        """Returns Pending events whose trigger_node matches this node name."""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM Events WHERE trigger_node=? AND status='Pending'",
                (node_name,)
            )
            return [Event(**dict(row)) for row in cursor.fetchall()]

    def get_trigger_node_names(self) -> set:
        """Returns names of nodes whose completion would trigger a Pending event."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT trigger_node FROM Events "
                "WHERE status='Pending' AND trigger_node IS NOT NULL"
            )
            return {row[0] for row in cursor.fetchall() if row[0]}

    def get_events_for_node(self, node_name: str) -> List[str]:
        """Returns list of event names that own this node."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT event_name FROM EventNodes WHERE node_name=?", (node_name,)
            )
            return [row[0] for row in cursor.fetchall()]

    # --- Activation ---

    def trigger_event(self, event_name: str, selected_nodes: Optional[List[str]] = None) -> Dict[str, list]:
        """Triggers an event, activating selected immediate nodes and scheduling delayed ones.

        Args:
            event_name: The event to trigger.
            selected_nodes: Optional list of node names to activate. If None, activates all.

        Returns dict with:
          'activated'      — immediate node names
          'scheduled'      — delayed node names
          'override_intent' — subset of activated+scheduled whose override_on_trigger=1
        """
        from graph_manager import GraphManager
        gm = GraphManager()

        result: Dict[str, list] = {'activated': [], 'scheduled': [], 'override_intent': []}
        today = date.today()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Mark event as triggered
            cursor.execute(
                "UPDATE Events SET status='Triggered' WHERE name=?", (event_name,)
            )

            # Get all event nodes
            cursor.execute(
                "SELECT node_name, delay_days, override_on_trigger "
                "FROM EventNodes WHERE event_name=? AND activated=0",
                (event_name,)
            )
            rows = cursor.fetchall()

            for node_name, delay_days, override_on_trigger in rows:
                # Skip if node is not in the selected set
                if selected_nodes is not None and node_name not in selected_nodes:
                    continue

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

                if override_on_trigger:
                    result['override_intent'].append(node_name)

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
        from config import ConfigManager
        gm = GraphManager()

        today = date.today().isoformat()
        activated: List[str] = []
        event_nodes_map: Dict[str, List[str]] = {}

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT node_name, event_name FROM EventNodes
                WHERE activation_date IS NOT NULL AND activation_date <= ? AND activated = 0
            ''', (today,))
            pending_rows = cursor.fetchall()

            for node_name, event_name in pending_rows:
                cursor.execute("UPDATE Nodes SET dormant=0 WHERE name=?", (node_name,))
                cursor.execute(
                    "UPDATE EventNodes SET activated=1 WHERE node_name=?", (node_name,)
                )
                activated.append(node_name)
                event_nodes_map.setdefault(event_name, []).append(node_name)

            conn.commit()

        for node_name in activated:
            gm._update_node_state(node_name)

        for event_name, nodes in event_nodes_map.items():
            ConfigManager.add_pending_event_notification({
                "kind": "delayed_activated",
                "event": event_name,
                "nodes": nodes,
                "when": today,
            })

        return activated

    def check_scheduled_triggers(self) -> List[str]:
        """Auto-triggers events whose trigger_date has arrived.

        Returns list of triggered event names.
        """
        from config import ConfigManager

        today = date.today().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM Events WHERE trigger_date IS NOT NULL "
                "AND trigger_date <= ? AND status = 'Pending'", (today,)
            )
            due = [row[0] for row in cursor.fetchall()]

        triggered = []
        for name in due:
            result = self.trigger_event(name)
            triggered.append(name)
            ConfigManager.add_pending_event_notification({
                "kind": "date_triggered",
                "event": name,
                "activated": result.get('activated', []),
                "scheduled": result.get('scheduled', []),
                "when": today,
            })
            self._apply_or_defer_override_intent(name, result.get('override_intent', []), today)
        return triggered

    def auto_trigger_by_node_completion(self, node_name: str) -> List[str]:
        """Silently auto-triggers every Pending event whose trigger_node matches node_name.

        All dormant nodes of those events are activated (no per-node user selection).
        Each auto-trigger appends a `node_triggered` notification entry for the app-load modal.

        Returns the list of event names that were triggered.
        """
        from config import ConfigManager

        pending = self.get_events_triggered_by_node(node_name)
        if not pending:
            return []

        today = date.today().isoformat()
        triggered: List[str] = []
        for event in pending:
            result = self.trigger_event(event.name)
            triggered.append(event.name)
            ConfigManager.add_pending_event_notification({
                "kind": "node_triggered",
                "event": event.name,
                "trigger_node": node_name,
                "activated": result.get('activated', []),
                "scheduled": result.get('scheduled', []),
                "when": today,
            })
            self._apply_or_defer_override_intent(event.name, result.get('override_intent', []), today)
        return triggered

    def _apply_or_defer_override_intent(self, event_name: str, intent_nodes: List[str], when: str):
        """On auto-trigger paths (date / node-completion), silently pin the nodes if no
        override is currently active; otherwise queue a conflict-resolution notification
        for the user to resolve on next app load.
        """
        from config import ConfigManager
        if not intent_nodes:
            return
        if not ConfigManager.has_any_override_active():
            ConfigManager.add_event_override_nodes(intent_nodes)
            return
        # Conflict: describe what's already active so the modal can show it to the user.
        existing = ConfigManager.get_override()
        if existing.get("parent"):
            descriptor = {"kind": "parent", "parent": existing.get("parent"), "mode": existing.get("mode", "hard")}
        else:
            descriptor = {"kind": "event_nodes", "nodes": list(ConfigManager.get_event_override_nodes())}
        ConfigManager.add_pending_event_notification({
            "kind": "override_conflict",
            "event": event_name,
            "current_override_descriptor": descriptor,
            "candidate_nodes": list(intent_nodes),
            "when": when,
        })

    # --- Convenience ---

    def create_dormant_node(self, node: Node, event_name: str, delay_days: int = 0,
                            override_on_trigger: bool = False,
                            override_mode: Optional[str] = None):
        """Creates a node as dormant and associates it with an event."""
        from graph_manager import GraphManager
        gm = GraphManager()

        node.dormant = 1
        gm.add_node(node)
        self.add_node_to_event(event_name, node.name, delay_days,
                               override_on_trigger=override_on_trigger,
                               override_mode=override_mode)
