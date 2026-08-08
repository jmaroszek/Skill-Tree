"""
Event + dormant-node persistence and activation logic.

An Event has one of three trigger types — manual (user clicks "trigger"),
date-based (an ISO date is reached), or node-based (a set of nodes flips
to Done, combined with OR or AND). Each Event owns zero or more *dormant*
nodes that are not part of the live graph until the event fires, at which
point they are awakened into the live graph (with an optional per-node
delay) via check_pending_events(). "Activation" in this module refers
exclusively to this awakening — it does NOT touch the orthogonal Node.now
flag.
"""

import sqlite3
from datetime import date, timedelta
import database
from models import Node, Event, STATUS_DONE, TRIGGER_MODE_ALL, TRIGGER_MODE_ANY
from typing import List, Dict, Optional


# Columns hydrated onto Event. Listed explicitly rather than via SELECT * so a
# legacy column left behind by a migration can't reach the dataclass.
_EVENT_COLUMNS = ("name", "description", "status", "trigger_date", "trigger_mode")


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

    # --- Hydration helpers ---

    @staticmethod
    def _normalize_mode(mode: Optional[str]) -> str:
        """Anything that isn't an explicit 'all' is treated as 'any'.

        Keeps a malformed stored value from silently turning an OR trigger
        into an AND one, which would leave an event stuck forever.
        """
        return TRIGGER_MODE_ALL if mode == TRIGGER_MODE_ALL else TRIGGER_MODE_ANY

    def _trigger_map(self, cursor, event_names: Optional[List[str]] = None) -> Dict[str, List[str]]:
        """Returns {event_name: [trigger node names]} in one query.

        Fetching the whole map up front keeps list views off the N+1 path.
        """
        if event_names is None:
            cursor.execute(
                "SELECT event_name, node_name FROM EventTriggerNodes ORDER BY node_name"
            )
        elif not event_names:
            return {}
        else:
            placeholders = ",".join("?" * len(event_names))
            cursor.execute(
                f"SELECT event_name, node_name FROM EventTriggerNodes "
                f"WHERE event_name IN ({placeholders}) ORDER BY node_name",
                tuple(event_names),
            )
        out: Dict[str, List[str]] = {}
        for event_name, node_name in cursor.fetchall():
            out.setdefault(event_name, []).append(node_name)
        return out

    def _hydrate(self, rows, trigger_map: Dict[str, List[str]]) -> List[Event]:
        events = []
        for row in rows:
            d = {k: row[k] for k in _EVENT_COLUMNS}
            d["trigger_mode"] = self._normalize_mode(d.get("trigger_mode"))
            d["trigger_nodes"] = trigger_map.get(d["name"], [])
            events.append(Event(**d))
        return events

    def _write_trigger_nodes(self, cursor, event_name: str, trigger_nodes: List[str]) -> None:
        """Replaces an event's trigger set wholesale.

        Delete-then-insert rather than a diff: the sets are tiny, and it keeps
        the write idempotent regardless of what was there before.
        """
        cursor.execute("DELETE FROM EventTriggerNodes WHERE event_name=?", (event_name,))
        seen = set()
        for node_name in trigger_nodes or []:
            if not node_name or node_name in seen:
                continue
            seen.add(node_name)
            cursor.execute(
                "INSERT OR IGNORE INTO EventTriggerNodes (event_name, node_name) VALUES (?, ?)",
                (event_name, node_name),
            )

    # --- Event CRUD ---

    def add_event(self, event: Event):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO Events (name, description, status, trigger_date, trigger_mode) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (event.name, event.description, event.status, event.trigger_date,
                     self._normalize_mode(event.trigger_mode))
                )
                self._write_trigger_nodes(cursor, event.name, event.trigger_nodes)
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Event with name '{event.name}' already exists.")

    def update_event(self, old_name: str, event: Event):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if old_name != event.name:
                cursor.execute("PRAGMA foreign_keys = OFF")
                cursor.execute(
                    "UPDATE Events SET name=?, description=?, status=?, trigger_date=?, "
                    "trigger_mode=? WHERE name=?",
                    (event.name, event.description, event.status, event.trigger_date,
                     self._normalize_mode(event.trigger_mode), old_name)
                )
                cursor.execute(
                    "UPDATE EventNodes SET event_name=? WHERE event_name=?",
                    (event.name, old_name)
                )
                cursor.execute(
                    "UPDATE EventTriggerNodes SET event_name=? WHERE event_name=?",
                    (event.name, old_name)
                )
                cursor.execute("PRAGMA foreign_keys = ON")
            else:
                cursor.execute(
                    "UPDATE Events SET description=?, status=?, trigger_date=?, "
                    "trigger_mode=? WHERE name=?",
                    (event.description, event.status, event.trigger_date,
                     self._normalize_mode(event.trigger_mode), old_name)
                )
            self._write_trigger_nodes(cursor, event.name, event.trigger_nodes)
            conn.commit()

    def delete_event(self, event_name: str, delete_nodes: bool = True):
        """Deletes an event. If delete_nodes is True, also deletes its dormant nodes.
        If False, activates them instead."""
        activated_names: List[str] = []
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
                # Activate all dormant nodes instead of deleting. Capture names
                # so we can run the cascade after the bulk update — otherwise
                # an activated node with un-Done prereqs would stay Open in
                # the DB until the next manual edit.
                cursor.execute(
                    "SELECT node_name FROM EventNodes WHERE event_name=? AND activated=0",
                    (event_name,)
                )
                activated_names = [row[0] for row in cursor.fetchall()]
                cursor.execute(
                    "UPDATE Nodes SET dormant=0 WHERE name IN "
                    "(SELECT node_name FROM EventNodes WHERE event_name=? AND activated=0)",
                    (event_name,)
                )

            cursor.execute("DELETE FROM Events WHERE name=?", (event_name,))
            conn.commit()

        # Re-derive status for any newly-activated node so a Blocked-on-prereqs
        # node doesn't sit stuck at Open. Done-status nodes also fire any
        # pending node-completion events tied to them.
        if activated_names:
            from graph_manager import GraphManager
            gm = GraphManager()
            for name in activated_names:
                gm._update_node_state(name)
                node = gm.get_node(name)
                if node and node.status == STATUS_DONE:
                    try:
                        self.auto_trigger_by_node_completion(name)
                    except Exception:
                        pass

    def get_event(self, name: str) -> Optional[Event]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Events WHERE name=?", (name,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._hydrate([row], self._trigger_map(cursor, [name]))[0]

    def get_all_events(self) -> List[Event]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Events ORDER BY status, name")
            rows = cursor.fetchall()
            return self._hydrate(rows, self._trigger_map(cursor))

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

    def detach_node_from_all_events(self, node_name: str):
        """Severs a node's event associations and brings it back into play.

        Distinct from `remove_node_from_event`, which deletes the node entirely
        — this preserves the node, removes any EventNodes rows, sets
        dormant=0, and re-runs the status cascade so the node's Open/Blocked
        state reflects current edges. Called from the editor's Dormant
        toggle-off flow when the user wants to bring a deferred node back
        without losing it.
        """
        from graph_manager import GraphManager
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM EventNodes WHERE node_name=?", (node_name,))
            cursor.execute("UPDATE Nodes SET dormant=0 WHERE name=?", (node_name,))
            conn.commit()
        GraphManager()._update_node_state(node_name)

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
        """Returns Pending events that watch this node.

        "Watches" only means the node is in the trigger set — for an AND
        event that is necessary but not sufficient. Use
        `is_trigger_condition_met` to decide whether it should actually fire.
        """
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT e.* FROM Events e "
                "JOIN EventTriggerNodes etn ON etn.event_name = e.name "
                "WHERE etn.node_name=? AND e.status='Pending' ORDER BY e.name",
                (node_name,)
            )
            rows = cursor.fetchall()
            names = [row["name"] for row in rows]
            return self._hydrate(rows, self._trigger_map(cursor, names))

    def is_trigger_condition_met(self, event: Event) -> bool:
        """True when `event`'s node-completion condition is satisfied.

        OR is satisfied by any one Done node; AND needs every node in the set.
        An empty set is never satisfied — that's a manual/date event, and
        firing on vacuous truth would wake it the moment its last trigger node
        was deleted.
        """
        if not event.trigger_nodes:
            return False
        with self.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(event.trigger_nodes))
            cursor.execute(
                f"SELECT COUNT(*) FROM Nodes WHERE name IN ({placeholders}) AND status=?",
                (*event.trigger_nodes, STATUS_DONE),
            )
            done_count = cursor.fetchone()[0]
        if self._normalize_mode(event.trigger_mode) == TRIGGER_MODE_ALL:
            return done_count >= len(event.trigger_nodes)
        return done_count >= 1

    def get_trigger_node_names(self) -> set:
        """Returns names of nodes whose completion could trigger a Pending event."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT etn.node_name FROM EventTriggerNodes etn "
                "JOIN Events e ON e.name = etn.event_name WHERE e.status='Pending'"
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

        # Cascade state updates for immediately activated nodes. If any was
        # stored as Done while dormant, it just became visible in the live
        # graph — fire any node-completion events tied to it.
        for node_name in result['activated']:
            gm._update_node_state(node_name)
            node = gm.get_node(node_name)
            if node and node.status == STATUS_DONE:
                try:
                    self.auto_trigger_by_node_completion(node_name)
                except Exception:
                    pass

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
            node = gm.get_node(node_name)
            if node and node.status == STATUS_DONE:
                try:
                    self.auto_trigger_by_node_completion(node_name)
                except Exception:
                    pass

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
        """Silently auto-triggers every Pending event whose condition node_name just satisfied.

        Every event watching this node is re-evaluated: an OR event fires
        immediately, an AND event only once its whole set is Done. Watching
        events that aren't satisfied yet are left Pending and re-checked on
        the next completion.

        All dormant nodes of the fired events are activated (no per-node user
        selection). Each auto-trigger appends a `node_triggered` notification
        entry for the app-load modal.

        Returns the list of event names that were triggered.
        """
        from config import ConfigManager

        watching = self.get_events_triggered_by_node(node_name)
        if not watching:
            return []

        today = date.today().isoformat()
        triggered: List[str] = []
        for event in watching:
            if not self.is_trigger_condition_met(event):
                continue
            result = self.trigger_event(event.name)
            triggered.append(event.name)
            ConfigManager.add_pending_event_notification({
                "kind": "node_triggered",
                "event": event.name,
                "trigger_node": node_name,
                "trigger_nodes": list(event.trigger_nodes),
                "trigger_mode": self._normalize_mode(event.trigger_mode),
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

    def update_dormant_node(self, event_name: str, old_node_name: str, node: Node,
                            delay_days: int = 0,
                            override_on_trigger: bool = False,
                            override_mode: Optional[str] = None):
        """Update an existing dormant node's content + EventNodes row in place.

        Edges are NOT handled here — the caller runs graph_manager.sync_edges
        afterward, matching the create path's convention.
        """
        from graph_manager import GraphManager
        gm = GraphManager()

        if node.name != old_node_name:
            gm.rename_node(old_node_name, node.name)

        node.dormant = 1
        gm.update_node(node)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE EventNodes SET delay_days=?, override_on_trigger=?, "
                "override_mode=? WHERE event_name=? AND node_name=?",
                (delay_days,
                 1 if override_on_trigger else 0,
                 override_mode if override_on_trigger else None,
                 event_name, node.name)
            )
            if cursor.rowcount == 0:
                raise ValueError(
                    f"Dormant node '{old_node_name}' not found in event '{event_name}'."
                )
            conn.commit()
