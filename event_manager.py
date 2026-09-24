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
from typing import Any, List, Dict, Optional, Tuple


# Columns hydrated onto Event. Listed explicitly rather than via SELECT * so a
# legacy column left behind by a migration can't reach the dataclass.
_EVENT_COLUMNS = ("name", "description", "status", "trigger_date", "trigger_mode")


class EventManager:
    """Gateway for the Events and EventNodes tables.

    Mirrors the shape of GraphManager but scoped to event-related state.
    Application startup initializes the schema before managers are used.
    """


    @staticmethod
    def _graph_changed(scoring=True):
        from graph_manager import GraphManager
        GraphManager()._bump_version(scoring=scoring)

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

    # --- The dormant flag ---
    #
    # A node with at least one EventNodes row is awake exactly when one of
    # those rows says activated. That is a policy, not a fact about the data:
    # `Nodes.dormant` is a single per-node bit while membership is a set, so
    # nothing keeps them agreeing unless every writer says so.
    #
    # The two halves are deliberately asymmetric. Waking is mechanical -- an
    # activated row means the node is live, full stop. Sleeping is a decision,
    # so the sleep half only runs where putting the node back under an event
    # is what the user asked for, and it refuses while any row still holds it
    # awake. A node with no rows at all is untouched by both: plain non-event
    # nodes must not be reachable from here.

    @staticmethod
    def _sync_dormant_flag(cursor, node_name: str) -> None:
        """Re-derive `Nodes.dormant` for one node from its EventNodes rows."""
        cursor.execute(
            "UPDATE Nodes SET dormant=0 WHERE name=? AND dormant=1 AND EXISTS ("
            "  SELECT 1 FROM EventNodes WHERE node_name=? AND activated=1)",
            (node_name, node_name),
        )
        cursor.execute(
            "UPDATE Nodes SET dormant=1 WHERE name=? AND dormant=0"
            "  AND EXISTS (SELECT 1 FROM EventNodes WHERE node_name=?)"
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM EventNodes WHERE node_name=? AND activated=1)",
            (node_name, node_name, node_name),
        )

    @database.atomic
    def reconcile_dormant_flags(self) -> int:
        """Startup safety net: wake any node whose rows say it already woke.

        Only the wake half, because only the wake half is unambiguous -- a row
        marked activated is a firing that happened, and honouring it cannot
        lose information. Re-sleeping on the strength of a missing row could
        pull a node the user is actively working on off the canvas, so that
        stays out of the automatic path.

        Deliberately not a migration. A schema step runs once at a version
        bump; this runs every launch, so it still catches drift introduced
        after the bump. It is a no-op on a database with no EventNodes rows.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE Nodes SET dormant=0 WHERE dormant=1 AND name IN ("
                "  SELECT node_name FROM EventNodes WHERE activated=1)"
            )
            repaired = cursor.rowcount or 0
            conn.commit()
        if repaired:
            self._graph_changed()
        return repaired

    # --- Event CRUD ---

    @database.atomic
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

        self._graph_changed(scoring=False)

    @database.atomic
    def update_event(self, old_name: str, event: Event):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if old_name != event.name:
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
            else:
                cursor.execute(
                    "UPDATE Events SET description=?, status=?, trigger_date=?, "
                    "trigger_mode=? WHERE name=?",
                    (event.description, event.status, event.trigger_date,
                     self._normalize_mode(event.trigger_mode), old_name)
                )
            self._write_trigger_nodes(cursor, event.name, event.trigger_nodes)
            conn.commit()
        self._graph_changed(scoring=False)

    @database.atomic
    def delete_event(self, event_name: str, delete_nodes: bool = True) -> Dict[str, List[str]]:
        """Deletes an event. If delete_nodes is True, also deletes its dormant nodes.
        If False, wakes the ones no other Pending event still claims.

        Returns {'woken': [...], 'still_dormant': [...], 'deleted': [...]} so
        the caller can say what became of the nodes.
        """
        activated_names: List[str] = []
        result: Dict[str, List[str]] = {'woken': [], 'still_dormant': [], 'deleted': []}
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
                    from graph_manager import GraphManager
                    GraphManager().delete_node(name)
                result['deleted'] = dormant_names
            else:
                # Wake the event's nodes instead of deleting them -- but only
                # the ones this event was the last home for. A node also held
                # by another Pending event is dormant by intent, and waking it
                # here is what put two sandbox nodes on the canvas while their
                # Music rows still called them dormant. A row on an already
                # Triggered event is a dead claim and does not count as a home.
                cursor.execute(
                    "SELECT node_name FROM EventNodes WHERE event_name=? AND activated=0",
                    (event_name,)
                )
                candidates = [row[0] for row in cursor.fetchall()]
                for name in candidates:
                    cursor.execute(
                        "SELECT 1 FROM EventNodes en JOIN Events e ON e.name = en.event_name "
                        "WHERE en.node_name=? AND en.event_name<>? AND e.status='Pending' "
                        "LIMIT 1",
                        (name, event_name),
                    )
                    if cursor.fetchone():
                        result['still_dormant'].append(name)
                    else:
                        activated_names.append(name)
                if activated_names:
                    placeholders = ",".join("?" * len(activated_names))
                    cursor.execute(
                        f"UPDATE Nodes SET dormant=0 WHERE name IN ({placeholders})",
                        tuple(activated_names),
                    )
                result['woken'] = list(activated_names)

            cursor.execute("DELETE FROM Events WHERE name=?", (event_name,))
            conn.commit()
        self._graph_changed()

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

        return result

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

    @database.atomic
    def add_node_to_event(self, event_name: str, node_name: str, delay_days: int = 0,
                          now_on_trigger: bool = False):
        """Associates a node with an event and marks it dormant.

        now_on_trigger persists the user's intent to move this node onto the
        Now list when the event later wakes it.

        Refuses a Triggered event. It will not fire again, so a node added to
        one would sit dormant forever with nothing left to wake it -- the same
        stranding that selective triggering used to cause. The pickers filter
        to Pending events, but they are built once and never re-checked, so
        the rule is enforced here where it cannot be raced.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM Events WHERE name=?", (event_name,))
            row = cursor.fetchone()
            if row and row[0] == "Triggered":
                raise ValueError(
                    f"'{event_name}' has already been triggered, so a node "
                    "added to it would never wake."
                )
            cursor.execute(
                "INSERT INTO EventNodes (event_name, node_name, delay_days, "
                "now_on_trigger) VALUES (?, ?, ?, ?)",
                (event_name, node_name, delay_days,
                 1 if now_on_trigger else 0)
            )
            # Was an unconditional `SET dormant=1`. That re-slept a node another
            # event had already woken, which multi-event membership puts one
            # click away: adding a live node to a second event would silently
            # pull it off the canvas.
            self._sync_dormant_flag(cursor, node_name)
            conn.commit()
        self._graph_changed(scoring=True)

    @database.atomic
    def delete_dormant_node(self, event_name: str, node_name: str):
        """Deletes a dormant node outright, and with it every event's row.

        Named `remove_node_from_event` until the move operation arrived, at
        which point "remove from event" was exactly the thing it does not do.
        Use `move_node_to_event` to re-home a node and
        `detach_node_from_all_events` to wake one without losing it.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM EventNodes WHERE event_name=? AND node_name=?",
                (event_name, node_name)
            )
            from graph_manager import GraphManager
            GraphManager().delete_node(node_name)
            conn.commit()

    @database.atomic
    def detach_node_from_all_events(self, node_name: str):
        """Severs a node's event associations and brings it back into play.

        Distinct from `delete_dormant_node`, which deletes the node entirely
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
        self._graph_changed(scoring=True)
        GraphManager()._update_node_state(node_name)

    @database.atomic
    def move_node_to_event(self, from_event: str, node_name: str, to_event: str,
                           delay_days: Optional[int] = None,
                           now_on_trigger: Optional[bool] = None) -> Dict[str, Any]:
        """Re-homes a dormant node under a different event.

        This is what replaced staged release. Firing an event now takes every
        node it holds, so "not this one yet" is expressed by moving the node
        somewhere that has not fired rather than by leaving it behind in one
        that has.

        `delay_days` and `now_on_trigger` default to carrying the source row's
        values over. The destination row always starts unfired: a delay
        measures from its own event's firing, which is the whole point of one
        unambiguous origin per delay.

        Returns {'merged': bool} — True when the node was already in
        `to_event` and the two rows were folded together.
        """
        if from_event == to_event:
            raise ValueError(f"'{node_name}' is already in '{to_event}'.")

        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT delay_days, now_on_trigger, activated FROM EventNodes "
                "WHERE event_name=? AND node_name=?",
                (from_event, node_name),
            )
            source = cursor.fetchone()
            if source is None:
                raise ValueError(
                    f"Dormant node '{node_name}' not found in event '{from_event}'."
                )
            source_delay, source_now, source_activated = source

            if source_activated:
                # A move that re-sleeps a live node is an un-trigger wearing a
                # different hat, and un-triggering is deliberately absent.
                raise ValueError(
                    f"'{node_name}' is already awake; moving it would not put "
                    "it back to sleep."
                )

            cursor.execute("SELECT status FROM Events WHERE name=?", (to_event,))
            destination = cursor.fetchone()
            if destination is None:
                raise ValueError(f"Event '{to_event}' does not exist.")
            if destination[0] == "Triggered":
                raise ValueError(
                    f"'{to_event}' has already been triggered, so a node moved "
                    "into it would never wake."
                )

            new_delay = source_delay if delay_days is None else int(delay_days)
            new_now = source_now if now_on_trigger is None else int(bool(now_on_trigger))

            # The PK is (event_name, node_name), and multi-event membership
            # puts this collision one click away, so merge rather than fail.
            cursor.execute(
                "SELECT 1 FROM EventNodes WHERE event_name=? AND node_name=?",
                (to_event, node_name),
            )
            merged = cursor.fetchone() is not None
            if merged:
                # Nothing explicit was passed, so the destination's own
                # settings win over the row being folded into it.
                if delay_days is not None or now_on_trigger is not None:
                    cursor.execute(
                        "UPDATE EventNodes SET delay_days=?, now_on_trigger=?, "
                        "activated=0, activation_date=NULL "
                        "WHERE event_name=? AND node_name=?",
                        (new_delay, new_now, to_event, node_name),
                    )
            else:
                cursor.execute(
                    "INSERT INTO EventNodes (event_name, node_name, delay_days, "
                    "activation_date, activated, now_on_trigger) "
                    "VALUES (?, ?, ?, NULL, 0, ?)",
                    (to_event, node_name, new_delay, new_now),
                )

            cursor.execute(
                "DELETE FROM EventNodes WHERE event_name=? AND node_name=?",
                (from_event, node_name),
            )
            # The source row vanishing can change the answer: it may have been
            # the only row keeping the node awake.
            self._sync_dormant_flag(cursor, node_name)
            conn.commit()

        self._graph_changed(scoring=True)
        return {'merged': merged}

    def get_event_nodes(self, event_name: str) -> List[Dict]:
        """Returns list of {node, delay_days, activation_date, activated,
        now_on_trigger, woken_by} for an event.

        `woken_by` names a *different* event that already woke this node, or
        None. Under multi-event membership the first event to fire wins, and
        without this the losing event's table would still call a live node
        dormant. The subquery orders by activation_date so "first to fire"
        is literal rather than alphabetical.
        """
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT n.*, en.delay_days, en.activation_date, en.activated,
                       en.now_on_trigger,
                       (SELECT other.event_name FROM EventNodes other
                         WHERE other.node_name = en.node_name
                           AND other.activated = 1
                           AND other.event_name <> en.event_name
                         ORDER BY other.activation_date, other.event_name
                         LIMIT 1) AS woken_by
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
                now_on_trigger = row_dict.pop('now_on_trigger', 0)
                woken_by = row_dict.pop('woken_by', None)
                node = Node(**row_dict)
                results.append({
                    'node': node,
                    'delay_days': delay_days,
                    'activation_date': activation_date,
                    'activated': activated,
                    'now_on_trigger': bool(now_on_trigger),
                    'woken_by': woken_by,
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

    def get_event_node_counts(self) -> Dict[str, Dict[str, int]]:
        """Total and activated counts for every event, in one query.

        The list views need a count per card. Asking per event turned a page
        render into one query per row; the sidebar's "has pending work"
        predicate would have made that worse by needing the count for every
        event rather than only the ones it draws.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT event_name, COUNT(*), COALESCE(SUM(activated), 0) "
                "FROM EventNodes GROUP BY event_name"
            )
            counts = {
                event_name: {'total': total, 'activated': activated}
                for event_name, total, activated in cursor.fetchall()
            }
            # An event with no dormant nodes has no rows to group, so it is
            # absent above rather than zero. Callers key off event names they
            # already hold, so fill the gap here instead of at every call site.
            cursor.execute("SELECT name FROM Events")
            for (name,) in cursor.fetchall():
                counts.setdefault(name, {'total': 0, 'activated': 0})
        return counts

    @database.atomic
    def set_node_delay(self, event_name: str, node_name: str, delay_days: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE EventNodes SET delay_days=? WHERE event_name=? AND node_name=?",
                (delay_days, event_name, node_name)
            )
            conn.commit()
        self._graph_changed(scoring=False)

    @database.atomic
    def set_now_on_trigger(self, event_name: str, node_name: str,
                           now_on_trigger: bool):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE EventNodes SET now_on_trigger=? WHERE event_name=? AND node_name=?",
                (1 if now_on_trigger else 0, event_name, node_name)
            )
            conn.commit()
        self._graph_changed(scoring=False)

    @database.atomic
    def set_node_wake_date(self, event_name: str, node_name: str,
                           wake_date: Optional[str]) -> None:
        """Moves a scheduled node's wake date.

        Only meaningful once the event has fired. Before that the row has no
        date and `set_node_delay` is the thing to call; after it, the delay has
        nothing left to measure from, because `Events` records no firing time.
        Editing the date directly is what keeps a committed delay changeable.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE EventNodes SET activation_date=? "
                "WHERE event_name=? AND node_name=? AND activated=0",
                (wake_date or None, event_name, node_name),
            )
            conn.commit()
        self._graph_changed(scoring=False)

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
        snapshot = database.current_snapshot()
        if snapshot is not None:
            return set(snapshot.trigger_names)
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

    def get_node_memberships(self, node_name: str) -> List[Dict]:
        """The node's still-waiting EventNodes rows, one per event, by event name.

        What the node editor's Events section edits. A row that has already
        activated is history, not a setting, so it is left out.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT en.event_name, en.delay_days, en.activation_date, "
                "en.now_on_trigger, e.status FROM EventNodes en "
                "JOIN Events e ON e.name = en.event_name "
                "WHERE en.node_name=? AND en.activated=0 ORDER BY en.event_name",
                (node_name,),
            )
            return [{
                'event': event_name,
                'delay_days': delay_days or 0,
                'activation_date': activation_date,
                'now_on_trigger': bool(now_on_trigger),
                'event_status': status,
            } for event_name, delay_days, activation_date, now_on_trigger, status
                in cursor.fetchall()]

    # --- Activation ---

    @database.atomic
    def trigger_event(self, event_name: str) -> Dict[str, list]:
        """Fires an event. Every node it holds participates.

        Selective firing used to live here as a `selected_nodes` filter, but
        the event was marked Triggered either way, so the nodes left out could
        never be released through it again. Per-node delays are what staging
        is for.

        Returns dict with:
          'activated'     — nodes woken now
          'scheduled'     — delayed nodes given a future activation date
          'already_awake' — nodes some other event had already woken
          'now_intent'    — subset of 'activated' to put on Now straight away
          'now_deferred'  — subset of 'scheduled' to put on Now when they wake
        """
        from graph_manager import GraphManager
        gm = GraphManager()

        result: Dict[str, list] = {'activated': [], 'scheduled': [],
                                   'already_awake': [], 'now_intent': [],
                                   'now_deferred': []}
        today = date.today()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Mark event as triggered
            cursor.execute(
                "UPDATE Events SET status='Triggered' WHERE name=?", (event_name,)
            )

            # `dormant` rides along so a node another event already woke is
            # recognised rather than being woken a second time.
            cursor.execute(
                "SELECT en.node_name, en.delay_days, en.now_on_trigger, n.dormant "
                "FROM EventNodes en JOIN Nodes n ON n.name = en.node_name "
                "WHERE en.event_name=? AND en.activated=0",
                (event_name,)
            )
            rows = cursor.fetchall()

            for node_name, delay_days, now_on_trigger, dormant in rows:
                if not dormant:
                    # First event to fire wins. This one still covers the node,
                    # so close its row out — but with no future date, or the
                    # delayed sweep would later "wake" an already-live node and
                    # announce it. Now was settled by whichever event won.
                    cursor.execute(
                        "UPDATE EventNodes SET activated=1, activation_date=? "
                        "WHERE event_name=? AND node_name=?",
                        (today.isoformat(), event_name, node_name)
                    )
                    result['already_awake'].append(node_name)
                elif delay_days == 0:
                    cursor.execute(
                        "UPDATE EventNodes SET activated=1, activation_date=? "
                        "WHERE event_name=? AND node_name=?",
                        (today.isoformat(), event_name, node_name)
                    )
                    self._sync_dormant_flag(cursor, node_name)
                    result['activated'].append(node_name)
                    if now_on_trigger:
                        result['now_intent'].append(node_name)
                else:
                    activation_date = today + timedelta(days=delay_days)
                    cursor.execute(
                        "UPDATE EventNodes SET activation_date=? "
                        "WHERE event_name=? AND node_name=?",
                        (activation_date.isoformat(), event_name, node_name)
                    )
                    result['scheduled'].append(node_name)
                    # Deliberately not now_intent. The node is still dormant
                    # and Now skips dormant nodes, so pinning it here dropped
                    # the intent on the floor. The delayed sweep does it.
                    if now_on_trigger:
                        result['now_deferred'].append(node_name)

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

        # Even a no-op firing changes the event's own status, and the sidebar
        # reads that. Only a woken node is scoring-relevant.
        self._graph_changed(scoring=bool(result['activated']))

        return result

    @database.atomic
    def check_pending_activations(self) -> List[str]:
        """Wakes delayed nodes whose activation date has arrived.

        Returns list of newly activated node names.
        """
        from graph_manager import GraphManager
        from config import ConfigManager
        gm = GraphManager()

        today = date.today().isoformat()
        activated: List[str] = []
        event_nodes_map: Dict[str, List[str]] = {}
        now_wanted: List[str] = []

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT node_name, event_name, now_on_trigger FROM EventNodes "
                "WHERE activation_date IS NOT NULL AND activation_date <= ? "
                "AND activated = 0",
                (today,)
            )
            pending_rows = cursor.fetchall()

            for node_name, event_name, now_on_trigger in pending_rows:
                # Scoped to this event. Without the event_name predicate a node
                # held by two events had both rows marked activated here, so
                # the second event skipped it forever and lost its Now intent.
                cursor.execute(
                    "UPDATE EventNodes SET activated=1 "
                    "WHERE event_name=? AND node_name=?",
                    (event_name, node_name)
                )
                self._sync_dormant_flag(cursor, node_name)
                activated.append(node_name)
                event_nodes_map.setdefault(event_name, []).append(node_name)
                if now_on_trigger:
                    now_wanted.append(node_name)

            conn.commit()

        for node_name in activated:
            gm._update_node_state(node_name)
            node = gm.get_node(node_name)
            if node and node.status == STATUS_DONE:
                try:
                    self.auto_trigger_by_node_completion(node_name)
                except Exception:
                    pass

        # The Now intent a delayed node carried used to be applied at trigger
        # time, while the node was still dormant — and Now skips dormant
        # nodes, so it was dropped and never retried. Here the node is awake,
        # which is the moment the user actually meant.
        now_pinned, now_skipped = self._apply_now_intent(now_wanted)
        pinned_set, skipped_set = set(now_pinned), set(now_skipped)

        for event_name, nodes in event_nodes_map.items():
            names = set(nodes)
            ConfigManager.add_pending_event_notification({
                "kind": "delayed_activated",
                "event": event_name,
                "nodes": nodes,
                "now_pinned": sorted(names & pinned_set),
                "now_skipped": sorted(names & skipped_set),
                "when": today,
            })

        if activated:
            self._graph_changed()

        return activated

    @database.atomic
    def trigger_event_manually(self, event_name: str,
                               pin_all_now: bool = False) -> Dict[str, list]:
        """Fires an event because the user clicked Trigger.

        The same firing as the date and node-completion paths, plus the Now
        pinning and the announcement those two already did for themselves.
        Keeping it here means all four paths behave identically and the
        callback no longer reaches into `_apply_now_intent` on its own.

        `pin_all_now` is the confirm modal's switch: pin every node this
        firing woke, not only the ones flagged "Add to Now" in advance.

        Returns `trigger_event`'s result plus 'now_pinned' and 'now_skipped'.
        """
        from config import ConfigManager

        result = self.trigger_event(event_name)
        candidates = (sorted(result['activated']) if pin_all_now
                      else result['now_intent'])
        now_pinned, now_skipped = self._apply_now_intent(candidates)
        result['now_pinned'] = now_pinned
        result['now_skipped'] = now_skipped

        # A manual firing used to leave no durable record at all: it reported
        # inline into a status line that clears itself on a timer.
        ConfigManager.add_pending_event_notification({
            "kind": "manual_triggered",
            "event": event_name,
            "activated": result['activated'],
            "scheduled": result['scheduled'],
            "already_awake": result['already_awake'],
            "now_pinned": now_pinned,
            "now_skipped": now_skipped,
            "when": date.today().isoformat(),
        })
        return result

    @database.atomic
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
            now_pinned, now_skipped = self._apply_now_intent(result.get('now_intent', []))
            ConfigManager.add_pending_event_notification({
                "kind": "date_triggered",
                "event": name,
                "activated": result.get('activated', []),
                "scheduled": result.get('scheduled', []),
                "already_awake": result.get('already_awake', []),
                "now_pinned": now_pinned,
                "now_skipped": now_skipped,
                "when": today,
            })
        return triggered

    @database.atomic
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
            now_pinned, now_skipped = self._apply_now_intent(result.get('now_intent', []))
            ConfigManager.add_pending_event_notification({
                "kind": "node_triggered",
                "event": event.name,
                "trigger_node": node_name,
                "trigger_nodes": list(event.trigger_nodes),
                "trigger_mode": self._normalize_mode(event.trigger_mode),
                "activated": result.get('activated', []),
                "scheduled": result.get('scheduled', []),
                "already_awake": result.get('already_awake', []),
                "now_pinned": now_pinned,
                "now_skipped": now_skipped,
                "when": today,
            })
        return triggered

    def _apply_now_intent(self, intent_nodes: List[str]) -> Tuple[List[str], List[str]]:
        """Move the nodes an event just woke onto the Now list.

        The Now cap wins: a triggering event should not be able to blow past
        the limit the user set by hand, so once the list is full the remaining
        nodes are simply left awake and un-pinned. Returns
        ``(pinned, skipped)`` so the caller's announcement can name both and a
        skip is visible rather than silent. Ranks continue from the current
        maximum, which puts new arrivals at the right-hand end of the row.

        There is no conflict to resolve here — that was the anchored override's
        problem, and Now is a plain list.
        """
        from config import ConfigManager
        from graph_manager import GraphManager
        if not intent_nodes:
            return [], []

        gm = GraphManager()
        current = gm.get_now_nodes()
        room = ConfigManager.get_now_node_cap() - len(current)
        rank = max((n.now for n in current), default=0)

        pinned, skipped = [], []
        for name in intent_nodes:
            node = gm.get_node(name)
            if node is None or node.dormant or node.now > 0:
                continue
            if room <= 0:
                skipped.append(name)
                continue
            rank += 1
            node.now = rank
            gm.update_node(node)
            room -= 1
            pinned.append(name)
        return pinned, skipped

    # --- Convenience ---

    @database.atomic
    def create_dormant_node(self, node: Node, event_name: str, delay_days: int = 0,
                            now_on_trigger: bool = False):
        """Creates a node as dormant and associates it with an event."""
        from graph_manager import GraphManager
        gm = GraphManager()

        node.dormant = 1
        gm.add_node(node)
        self.add_node_to_event(event_name, node.name, delay_days,
                               now_on_trigger=now_on_trigger)
