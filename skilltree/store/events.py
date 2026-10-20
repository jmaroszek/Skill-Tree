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

import logging
import sqlite3
from datetime import date, timedelta
from skilltree.domain import rules as graph_rules
from skilltree.store import database
from skilltree.store.graph.state import revisions
from skilltree.store import settings
from skilltree.domain.models import Node, Event, STATUS_DONE, TRIGGER_MODE_ALL, TRIGGER_MODE_ANY
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# Columns hydrated onto Event. Listed explicitly rather than via SELECT * so a
# column the dataclass lacks can't reach it.
_EVENT_COLUMNS = ("name", "description", "status", "trigger_date", "trigger_mode")

# The longest delay a node can wait after its event fires. A date past year
# 9999 can't be computed, and one bad delay stopped every event sweep.
MAX_DELAY_DAYS = 100 * 365


class EventManager:
    """Gateway for the Events and EventNodes tables.

    Mirrors the shape of GraphManager but scoped to event-related state.
    Application startup initializes the schema before managers are used.
    """


    def __init__(self, graph):
        # The GraphManager it deletes, wakes and re-derives nodes through.
        # AppServices passes its own, so the two share one set of caches.
        self.graph = graph

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
            # The picker is built once, so a node deleted since can still be
            # chosen. Without this the foreign key refused it as a raw error.
            if cursor.execute("SELECT 1 FROM Nodes WHERE name=?", (node_name,)).fetchone() is None:
                raise ValueError(f"There is no node named '{node_name}' any more. "
                                 "Pick another trigger node.")
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
            revisions.changed()
        return repaired

    # --- Event CRUD ---

    @staticmethod
    def _date_or_none(value):
        """A trigger date as stored: None when there is none. An empty
        string reads as a date before every other, so it was always due."""
        if isinstance(value, str):
            value = value.strip()
        return value or None

    @staticmethod
    def _stored_date(value) -> Optional[date]:
        """A stored date as a date, or None when it holds none. Only its first
        ten characters count, as an import checks them: one written with a
        time after it is still that day, and must not stop the sweep that
        fires every other event due with it."""
        if not isinstance(value, str):
            return None
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None

    @staticmethod
    def _check_name(name):
        problem = graph_rules.name_problem(name, "Event name")
        if problem:
            raise ValueError(problem)

    @database.atomic
    def add_event(self, event: Event):
        self._check_name(event.name)
        # A new event holds nothing yet. One that fired as it was saved would
        # wake nothing, and nothing could be added to it after.
        done = self._done_trigger_nodes(event.trigger_nodes)
        if self._condition_holds(event, done):
            if self._normalize_mode(event.trigger_mode) == TRIGGER_MODE_ALL and len(done) > 1:
                problem = "Its trigger nodes are all complete already"
            else:
                problem = f"'{done[0]}' is complete already"
            raise ValueError(f"{problem}, so the event would fire as soon as it "
                             "was saved. Pick a trigger node that isn't finished.")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO Events (name, description, status, trigger_date, trigger_mode) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (event.name, event.description, event.status,
                     self._date_or_none(event.trigger_date),
                     self._normalize_mode(event.trigger_mode))
                )
                self._write_trigger_nodes(cursor, event.name, event.trigger_nodes)
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Event with name '{event.name}' already exists.") from exc

        revisions.changed(scoring=False)

    @database.atomic
    def update_event(self, old_name: str, event: Event):
        if old_name != event.name:
            self._check_name(event.name)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Deleted from another window, the update would change no row
            # and the page would still say Saved.
            if cursor.execute("SELECT 1 FROM Events WHERE name=?", (old_name,)).fetchone() is None:
                raise ValueError(f"There is no event named '{old_name}' any more, "
                                 "so nothing was saved.")
            if event.trigger_nodes:
                placeholders = ",".join("?" * len(event.trigger_nodes))
                asleep = cursor.execute(
                    f"SELECT node_name FROM EventNodes WHERE event_name=? "
                    f"AND activated=0 AND node_name IN ({placeholders}) "
                    "ORDER BY node_name",
                    (old_name, *event.trigger_nodes)).fetchone()
                if asleep is not None:
                    raise ValueError(self._own_trigger_message(asleep[0], event.name))
            if old_name != event.name:
                try:
                    cursor.execute(
                        "UPDATE Events SET name=?, description=?, status=?, trigger_date=?, "
                        "trigger_mode=? WHERE name=?",
                        (event.name, event.description, event.status,
                         self._date_or_none(event.trigger_date),
                         self._normalize_mode(event.trigger_mode), old_name)
                    )
                except sqlite3.IntegrityError as exc:
                    raise ValueError(f"Event with name '{event.name}' already exists.") from exc
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
                    (event.description, event.status,
                     self._date_or_none(event.trigger_date),
                     self._normalize_mode(event.trigger_mode), old_name)
                )
            self._write_trigger_nodes(cursor, event.name, event.trigger_nodes)
            conn.commit()
        if old_name != event.name:
            settings.EVENT_ORDER.rename(old_name, event.name)
        self.fire_if_met_after_commit(event.name)
        revisions.changed(scoring=False)

    @database.atomic
    def delete_event(self, event_name: str, delete_nodes: bool = True) -> Dict[str, List[str]]:
        """Deletes an event. If delete_nodes is True, also deletes its dormant
        nodes; otherwise wakes them.

        Returns {'woken': [...], 'deleted': [...]} so the caller can say what
        became of the nodes.
        """
        activated_names: List[str] = []
        result: Dict[str, List[str]] = {'woken': [], 'deleted': []}
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT node_name FROM EventNodes WHERE event_name=? AND activated=0",
                (event_name,)
            )
            dormant_names = [row[0] for row in cursor.fetchall()]
            if delete_nodes:
                for name in dormant_names:
                    self.graph.delete_node(name)
                result['deleted'] = dormant_names
            else:
                # Wake the event's nodes instead of deleting them. A node
                # belongs to one event, so this was their only home.
                activated_names = dormant_names
                if activated_names:
                    placeholders = ",".join("?" * len(activated_names))
                    cursor.execute(
                        f"UPDATE Nodes SET dormant=0 WHERE name IN ({placeholders})",
                        tuple(activated_names),
                    )
                result['woken'] = list(activated_names)

            cursor.execute("DELETE FROM Events WHERE name=?", (event_name,))
            conn.commit()
        settings.EVENT_ORDER.drop(event_name)
        revisions.changed()

        # Re-derive status for any newly-activated node so a Blocked-on-prereqs
        # node doesn't sit stuck at Open. Done-status nodes also fire any
        # pending node-completion events tied to them.
        if activated_names:
            gm = self.graph
            for name in activated_names:
                gm.update_node_state(name)
                node = gm.get_node(name)
                if node and node.status == STATUS_DONE:
                    self._fire_completion_events_after_commit(name)

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

        Also refuses a node that already has an event. A node belongs to one
        event; `move_node_to_event` re-homes it. A node its event has already
        woken keeps that row, so it can never go back to sleep.
        """
        gm = self.graph
        node = gm.get_node(node_name)
        if node is None:
            raise ValueError(f"There is no node named '{node_name}' any more.")
        if node.status == STATUS_DONE:
            raise ValueError(f"Reopen '{node_name}' before putting it to sleep.")
        delay_days = self._checked_delay(delay_days)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM Events WHERE name=?", (event_name,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"There is no event named '{event_name}' any more.")
            if row[0] == "Triggered":
                raise ValueError(
                    f"'{event_name}' has already been triggered, so a node "
                    "added to it would never wake."
                )
            self._check_not_own_trigger(cursor, event_name, node_name)
            cursor.execute(
                "SELECT event_name, activated FROM EventNodes WHERE node_name=?",
                (node_name,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                current, activated = existing
                if activated:
                    raise ValueError(
                        f"'{node_name}' already woke from '{current}', so it "
                        "can't go back to sleep."
                    )
                raise ValueError(f"'{node_name}' is already in '{current}'.")
            cursor.execute(
                "INSERT INTO EventNodes (event_name, node_name, delay_days, "
                "now_on_trigger) VALUES (?, ?, ?, ?)",
                (event_name, node_name, delay_days,
                 1 if now_on_trigger else 0)
            )
            # Sleeping ends current work through the same lifecycle writer
            # as the editor. A later wake can only pin via now_on_trigger.
            node.dormant = 1
            gm.update_node(node)
            self._sync_dormant_flag(cursor, node_name)
            conn.commit()
        revisions.changed(scoring=True)

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
            self.graph.delete_node(node_name)
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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM EventNodes WHERE node_name=?", (node_name,))
            cursor.execute("UPDATE Nodes SET dormant=0 WHERE name=?", (node_name,))
            conn.commit()
        revisions.changed(scoring=True)
        self.graph.update_node_state(node_name)

    @database.atomic
    def move_node_to_event(self, from_event: str, node_name: str, to_event: str,
                           delay_days: Optional[int] = None,
                           now_on_trigger: Optional[bool] = None) -> None:
        """Re-homes a dormant node under a different event.

        This is what replaced staged release. Firing an event now takes every
        node it holds, so "not this one yet" is expressed by moving the node
        somewhere that has not fired rather than by leaving it behind in one
        that has.

        `delay_days` and `now_on_trigger` default to carrying the source row's
        values over. The destination row always starts unfired: a delay
        measures from its own event's firing, which is the whole point of one
        unambiguous origin per delay.
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

            self._check_not_own_trigger(cursor, to_event, node_name)
            new_delay = (source_delay if delay_days is None
                         else self._checked_delay(delay_days))
            new_now = source_now if now_on_trigger is None else int(bool(now_on_trigger))

            # The node's one row changes event and starts over unfired.
            cursor.execute(
                "UPDATE EventNodes SET event_name=?, delay_days=?, "
                "now_on_trigger=?, activation_date=NULL, activated=0 "
                "WHERE event_name=? AND node_name=?",
                (to_event, new_delay, new_now, from_event, node_name),
            )
            self._sync_dormant_flag(cursor, node_name)
            conn.commit()

        revisions.changed(scoring=True)

    def get_event_nodes(self, event_name: str) -> List[Dict]:
        """Returns list of {node, delay_days, activation_date, activated,
        now_on_trigger} for an event."""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT n.*, en.delay_days, en.activation_date, en.activated,
                       en.now_on_trigger
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
                node = Node(**row_dict)
                results.append({
                    'node': node,
                    'delay_days': delay_days,
                    'activation_date': activation_date,
                    'activated': activated,
                    'now_on_trigger': bool(now_on_trigger),
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

    @staticmethod
    def _check_still_in(cursor, event_name, node_name):
        """After an UPDATE of one EventNodes row: refuse when there was none,
        rather than report a change that went nowhere."""
        if cursor.rowcount == 0:
            raise ValueError(f"'{node_name}' isn't in '{event_name}' any more.")

    @database.atomic
    def set_node_delay(self, event_name: str, node_name: str, delay_days: int):
        delay_days = self._checked_delay(delay_days)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE EventNodes SET delay_days=? WHERE event_name=? AND node_name=?",
                (delay_days, event_name, node_name)
            )
            self._check_still_in(cursor, event_name, node_name)
            conn.commit()
        revisions.changed(scoring=False)

    @database.atomic
    def set_now_on_trigger(self, event_name: str, node_name: str,
                           now_on_trigger: bool):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE EventNodes SET now_on_trigger=? WHERE event_name=? AND node_name=?",
                (1 if now_on_trigger else 0, event_name, node_name)
            )
            self._check_still_in(cursor, event_name, node_name)
            conn.commit()
        revisions.changed(scoring=False)

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
        revisions.changed(scoring=False)

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
        return self._condition_holds(event, [None] * done_count)

    def _condition_holds(self, event: Event, done: List) -> bool:
        """Whether ``done``, the event's trigger nodes that are complete,
        satisfy its condition. OR needs one; AND needs every node."""
        if not event.trigger_nodes:
            return False
        if self._normalize_mode(event.trigger_mode) == TRIGGER_MODE_ALL:
            return len(done) >= len(set(event.trigger_nodes))
        return len(done) >= 1

    def _done_trigger_nodes(self, names: List[str]) -> List[str]:
        """The awake nodes among ``names`` that are Done, sorted. A sleeping
        node stored as Done counts once it wakes, which fires its events then
        (see _fire_completion_events_after_commit)."""
        if not names:
            return []
        with self.get_connection() as conn:
            placeholders = ",".join("?" * len(names))
            return [row[0] for row in conn.execute(
                f"SELECT name FROM Nodes WHERE name IN ({placeholders}) "
                "AND status=? AND dormant=0 ORDER BY name",
                (*names, STATUS_DONE),
            )]

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

    def get_event_for_node(self, node_name: str) -> Optional[str]:
        """The event that holds this node, or None."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT event_name FROM EventNodes WHERE node_name=?", (node_name,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_nodes_in_events(self) -> set:
        """Every node that has an event, waiting or already woken."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT node_name FROM EventNodes")
            return {row[0] for row in cursor.fetchall()}

    def woke_from(self, node_name: str) -> Optional[str]:
        """The event that woke the node, while it still holds the row; or None."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT event_name FROM EventNodes WHERE node_name=? AND activated=1",
                (node_name,)).fetchone()
        return row[0] if row else None

    def get_node_membership(self, node_name: str) -> Optional[Dict]:
        """The node's event row while it is still waiting, or None.

        What the node editor's Event field edits. A row that has already
        activated is history, not a setting, so it reads as None.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT en.event_name, en.delay_days, en.activation_date, "
                "en.now_on_trigger, e.status FROM EventNodes en "
                "JOIN Events e ON e.name = en.event_name "
                "WHERE en.node_name=? AND en.activated=0",
                (node_name,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            event_name, delay_days, activation_date, now_on_trigger, status = row
            return {
                'event': event_name,
                'delay_days': delay_days or 0,
                'activation_date': activation_date,
                'now_on_trigger': bool(now_on_trigger),
                'event_status': status,
            }

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
          'already_awake' — nodes that were awake before it fired
          'now_intent'    — subset of 'activated' to put on Now straight away
          'now_deferred'  — subset of 'scheduled' to put on Now when they wake

        Firing is latched (see models.Event): an event that isn't Pending
        does nothing and every list comes back empty. A second firing would
        otherwise re-date each delayed node still waiting, pushing it later.

        Delays count from the event's occurrence: its date when that has
        passed, so a firing processed late (the app was closed on the day)
        wakes each node when it was due, and today otherwise. A node already
        past its wake date wakes now.
        """
        gm = self.graph

        result: Dict[str, list] = {'activated': [], 'scheduled': [],
                                   'already_awake': [], 'now_intent': [],
                                   'now_deferred': []}
        today = date.today()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT status, trigger_date FROM Events WHERE name=?",
                (event_name,)).fetchone()
            if row is None or row[0] != 'Pending':
                return result
            stored = self._stored_date(row[1])
            occurrence = min(stored, today) if stored else today

            # Mark event as triggered
            cursor.execute(
                "UPDATE Events SET status='Triggered' WHERE name=?", (event_name,)
            )

            # `dormant` rides along so a node that is somehow awake already is
            # recognised rather than being woken a second time.
            cursor.execute(
                "SELECT en.node_name, en.delay_days, en.now_on_trigger, n.dormant "
                "FROM EventNodes en JOIN Nodes n ON n.name = en.node_name "
                "WHERE en.event_name=? AND en.activated=0",
                (event_name,)
            )
            rows = cursor.fetchall()

            for node_name, delay_days, now_on_trigger, dormant in rows:
                # Clamped: a delay saved before the limit can't stop the firing.
                wake_date = occurrence + timedelta(
                    days=min(max(delay_days or 0, 0), MAX_DELAY_DAYS))
                if not dormant:
                    # Close its row out, but with no future date, or the
                    # delayed sweep would later "wake" an already-live node
                    # and announce it.
                    cursor.execute(
                        "UPDATE EventNodes SET activated=1, activation_date=? "
                        "WHERE event_name=? AND node_name=?",
                        (today.isoformat(), event_name, node_name)
                    )
                    result['already_awake'].append(node_name)
                elif wake_date <= today:
                    cursor.execute(
                        "UPDATE EventNodes SET activated=1, activation_date=? "
                        "WHERE event_name=? AND node_name=?",
                        (wake_date.isoformat(), event_name, node_name)
                    )
                    self._sync_dormant_flag(cursor, node_name)
                    result['activated'].append(node_name)
                    if now_on_trigger:
                        result['now_intent'].append(node_name)
                else:
                    cursor.execute(
                        "UPDATE EventNodes SET activation_date=? "
                        "WHERE event_name=? AND node_name=?",
                        (wake_date.isoformat(), event_name, node_name)
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
            gm.update_node_state(node_name)
            node = gm.get_node(node_name)
            if node and node.status == STATUS_DONE:
                self._fire_completion_events_after_commit(node_name)

        # Even a no-op firing changes the event's own status, and the sidebar
        # reads that. Only a woken node is scoring-relevant.
        revisions.changed(scoring=bool(result['activated']))

        return result

    # What each date sweep looks for. The core engine runs both sweeps on
    # every interaction, and nearly always nothing is due, so each checks on a
    # plain read first. The sweep itself is a write transaction, which takes
    # the database's write lock and waits on anything else holding it.
    _DUE_ACTIVATIONS = ("SELECT 1 FROM EventNodes WHERE activation_date IS NOT NULL "
                        "AND activation_date <= ? AND activated = 0 LIMIT 1")
    # An empty date, saved before the editor refused one, is no date.
    _DUE_TRIGGERS = ("SELECT 1 FROM Events WHERE trigger_date IS NOT NULL "
                     "AND trigger_date <> '' "
                     "AND trigger_date <= ? AND status = 'Pending' LIMIT 1")

    def _anything_due(self, query) -> bool:
        with self.get_connection() as conn:
            return conn.execute(query, (date.today().isoformat(),)).fetchone() is not None

    def check_pending_activations(self) -> List[str]:
        """Wakes delayed nodes whose activation date has arrived.

        Returns list of newly activated node names.
        """
        if not self._anything_due(self._DUE_ACTIVATIONS):
            return []
        return self._wake_due_nodes()

    @database.atomic
    def _wake_due_nodes(self) -> List[str]:
        gm = self.graph

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
            gm.update_node_state(node_name)
            node = gm.get_node(node_name)
            if node and node.status == STATUS_DONE:
                self._fire_completion_events_after_commit(node_name)

        # The Now intent a delayed node carried used to be applied at trigger
        # time, while the node was still dormant — and Now skips dormant
        # nodes, so it was dropped and never retried. Here the node is awake,
        # which is the moment the user actually meant.
        now_pinned, now_skipped = self._apply_now_intent(now_wanted)
        pinned_set, skipped_set = set(now_pinned), set(now_skipped)

        for event_name, nodes in event_nodes_map.items():
            names = set(nodes)
            settings.add_event_notification({
                "kind": "delayed_activated",
                "event": event_name,
                "nodes": nodes,
                "now_pinned": sorted(names & pinned_set),
                "now_skipped": sorted(names & skipped_set),
                "when": today,
            })

        if activated:
            revisions.changed()

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
        firing woke, not only the ones flagged "Add to Now" in advance. When
        Now hasn't room for them all, the flagged ones go first, then the rest
        in recommendation order (see _pin_all_order).

        Returns `trigger_event`'s result plus 'now_pinned' and 'now_skipped'.
        Raises ValueError when the event is gone or has already fired, as it
        can have from another window or on its date, so the page can say so.
        """

        event = self.get_event(event_name)
        if event is None:
            raise ValueError(f"There is no event named '{event_name}' any more.")
        if event.status != "Pending":
            raise ValueError(f"'{event_name}' had already been triggered, so nothing changed.")
        result = self.trigger_event(event_name)
        candidates = (self._pin_all_order(result['activated'], result['now_intent'])
                      if pin_all_now else result['now_intent'])
        now_pinned, now_skipped = self._apply_now_intent(candidates)
        result['now_pinned'] = now_pinned
        result['now_skipped'] = now_skipped

        # A manual firing used to leave no durable record at all: it reported
        # inline into a status line that clears itself on a timer.
        settings.add_event_notification({
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

    def run_sweeps(self) -> bool:
        """Wake the delayed nodes that are due, fire the date events that
        are, and return whether anything changed. A failure is logged, not
        raised: every click runs the sweeps, so one bad event would otherwise
        break them all."""
        changed = False
        for sweep in ("check_pending_activations", "check_scheduled_triggers"):
            try:
                changed = bool(getattr(self, sweep)()) or changed
            except Exception:
                logger.exception("The event sweep %s failed", sweep)
        return changed

    @staticmethod
    def _checked_delay(delay_days) -> int:
        """``delay_days`` as whole days, or a ValueError the editor can show."""
        try:
            days = int(delay_days or 0)
        except (TypeError, ValueError):
            raise ValueError("A delay must be a whole number of days.") from None
        if days < 0:
            raise ValueError("A delay can't be negative.")
        if days > MAX_DELAY_DAYS:
            raise ValueError("A delay can be at most 100 years.")
        return days

    @staticmethod
    def _own_trigger_message(node_name: str, event_name: str) -> str:
        return (f"'{node_name}' triggers '{event_name}', so it can't sleep "
                f"until '{event_name}' fires: it would never wake.")

    def _check_not_own_trigger(self, cursor, event_name: str, node_name: str) -> None:
        """Refuse to put a node to sleep under an event it triggers."""
        if cursor.execute(
                "SELECT 1 FROM EventTriggerNodes WHERE event_name=? AND node_name=?",
                (event_name, node_name)).fetchone():
            raise ValueError(self._own_trigger_message(node_name, event_name))

    def check_scheduled_triggers(self) -> List[str]:
        """Auto-triggers events whose trigger_date has arrived.

        Returns list of triggered event names.
        """
        if not self._anything_due(self._DUE_TRIGGERS):
            return []
        return self._fire_due_events()

    @database.atomic
    def _fire_due_events(self) -> List[str]:

        today = date.today().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM Events WHERE trigger_date IS NOT NULL "
                "AND trigger_date <> '' "
                "AND trigger_date <= ? AND status = 'Pending'", (today,)
            )
            due = [row[0] for row in cursor.fetchall()]

        triggered = []
        for name in due:
            result = self.trigger_event(name)
            triggered.append(name)
            now_pinned, now_skipped = self._apply_now_intent(result.get('now_intent', []))
            settings.add_event_notification({
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

    def _fire_completion_events_after_commit(self, node_name: str) -> None:
        """Fire the events watching a woken Done node, once the wake commits.

        A dormant node stored as Done joins the live graph when it wakes, and
        that can satisfy another event's trigger. It runs after the commit,
        as GraphManager.update_node fires completions, so a failure there is
        logged instead of silently rolling the wake back with it. Catching the
        error inside this transaction would not have been enough: the failed
        nested write marks the whole transaction for rollback.
        """
        def fire():
            try:
                self.auto_trigger_by_node_completion(node_name)
            except Exception:
                logger.exception("Chained event trigger failed for %s", node_name)
        database.on_commit(fire, key=("completion-events", node_name))

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
        watching = self.get_events_triggered_by_node(node_name)
        if not watching:
            return []

        triggered: List[str] = []
        for event in watching:
            if not self.is_trigger_condition_met(event):
                continue
            self._fire_on_completion(event, node_name)
            triggered.append(event.name)
        return triggered

    def _fire_on_completion(self, event: Event, trigger_node: str,
                            already_met: bool = False) -> None:
        """Fire ``event`` because its completion condition holds, and queue
        the announcement. ``already_met`` says no save just finished
        ``trigger_node``: the event was satisfied some other way."""

        result = self.trigger_event(event.name)
        now_pinned, now_skipped = self._apply_now_intent(result.get('now_intent', []))
        entry = {
            "kind": "node_triggered",
            "event": event.name,
            "trigger_node": trigger_node,
            "trigger_nodes": list(event.trigger_nodes),
            "trigger_mode": self._normalize_mode(event.trigger_mode),
            "activated": result.get('activated', []),
            "scheduled": result.get('scheduled', []),
            "already_awake": result.get('already_awake', []),
            "now_pinned": now_pinned,
            "now_skipped": now_skipped,
            "when": date.today().isoformat(),
        }
        if already_met:
            entry["already_met"] = True
        settings.add_event_notification(entry)

    @database.atomic
    def fire_if_condition_met(self, event_name: str) -> bool:
        """Fire a Pending event whose completion condition already holds.

        A completion fires the events watching it only on the save that
        marks the node Done. An event can come to be satisfied another way:
        an edit that drops its unfinished trigger nodes or switches it to
        OR, or a deleted trigger node. It used to wait until one of the
        others was reopened and finished again.

        Returns whether the event fired.
        """
        event = self.get_event(event_name)
        if event is None or event.status != "Pending":
            return False
        done = self._done_trigger_nodes(event.trigger_nodes)
        if not self._condition_holds(event, done):
            return False
        self._fire_on_completion(event, done[0], already_met=True)
        return True

    def fire_if_met_after_commit(self, event_name: str) -> None:
        """Run ``fire_if_condition_met`` once the current write commits.

        After the commit, as a completion fires its events, so a failure to
        fire is logged instead of rolling back the edit that satisfied it.
        """
        def fire():
            try:
                self.fire_if_condition_met(event_name)
            except Exception:
                logger.exception("Firing the satisfied event %s failed", event_name)
        database.on_commit(fire, key=("condition-met", event_name))

    def fire_satisfied_events(self) -> List[str]:
        """Startup safety net: fire every Pending event whose completion
        condition already holds, and return their names. Catches events left
        waiting before saves and deletions checked, or brought in by an
        import."""
        with self.get_connection() as conn:
            names = [row[0] for row in conn.execute(
                "SELECT DISTINCT e.name FROM Events e "
                "JOIN EventTriggerNodes etn ON etn.event_name = e.name "
                "WHERE e.status='Pending' ORDER BY e.name")]
        return [name for name in names if self.fire_if_condition_met(name)]

    def _pin_all_order(self, activated: List[str], flagged: List[str]) -> List[str]:
        """Every woken node, in the order Now takes them while it has room:
        the ones flagged "Add to Now" first, then the rest as the
        recommendations rank them. Alphabetical order chose arbitrarily, and
        passed over the nodes the user had flagged."""
        first = [name for name in flagged if name in activated]
        rest = sorted(set(activated) - set(first))
        if len(rest) > 1:
            gm = self.graph
            try:
                scored = gm.calculate_priority_scores(
                    [n for n in gm.get_all_nodes() if not n.now],
                    priority_goals=settings.PRIORITY_GOALS.get())
            except Exception:
                logger.exception("Couldn't rank the woken nodes; pinning them by name")
                scored = []
            place = {n.name: i for i, n in enumerate(scored)
                     if getattr(n, 'priority_score', -1) >= 0}
            rest.sort(key=lambda name: (place.get(name, len(place)), name))
        return first + rest

    @database.serialized  # the cap check and the writes, as one step
    def _apply_now_intent(self, intent_nodes: List[str]) -> Tuple[List[str], List[str]]:
        """Move the nodes an event just woke onto the Now list.

        The Now cap wins: a triggering event should not be able to blow past
        the limit the user set by hand, so once the list is full the remaining
        nodes are simply left awake and un-pinned. Returns
        ``(pinned, skipped)`` so the caller's announcement can name both and a
        skip is visible rather than silent. Ranks continue from the current
        maximum, which puts new arrivals at the right-hand end of the row.

        There is no conflict to resolve here — that was the anchored override's
        problem, and Now is a plain list. A node that wakes already Done stays
        off Now: there is nothing left to work on.
        """
        if not intent_nodes:
            return [], []

        gm = self.graph
        current = gm.get_now_nodes()
        room = settings.NOW_NODE_CAP.get() - len(current)
        rank = max((n.now for n in current), default=0)

        pinned, skipped = [], []
        with gm.ranking_batch():
            for name in intent_nodes:
                node = gm.get_node(name)
                if node is None or node.dormant or node.now > 0 or node.status == STATUS_DONE:
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
        gm = self.graph

        node.dormant = 1
        gm.add_node(node)
        self.add_node_to_event(event_name, node.name, delay_days,
                               now_on_trigger=now_on_trigger)
