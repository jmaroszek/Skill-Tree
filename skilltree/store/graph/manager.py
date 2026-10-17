"""
Persistence + in-memory graph operations.

GraphManager is the single gateway between the Dash callbacks and the
SQLite store. It handles node/edge CRUD, cascade status updates, cycle
detection, filtering, and priority scoring — and owns the invalidation
counters that let the higher-level callback caches know when to rebuild.
"""

import contextlib
import contextvars
import logging
import sqlite3
import time
from collections import defaultdict, deque
from datetime import date
from skilltree.store import database
from skilltree.store.graph import queries as graph_queries
from skilltree.store.graph import taxonomy as graph_taxonomy
from skilltree.store.graph import scoring as graph_scoring
from skilltree.domain import rules as graph_rules
from skilltree.store.graph.repository import GraphRepository, record_ledger
from skilltree.store.graph.state import (
    SCORING_RELEVANT_FIELDS, GraphCaches, revisions,
)
from skilltree.domain.models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from skilltree.store.settings import ConfigManager
from typing import TYPE_CHECKING, List, Dict, Optional, Set, Tuple
from skilltree.domain.names import format_name

if TYPE_CHECKING:
    import networkx as nx

logger = logging.getLogger(__name__)

# The ranking a run of Now starts shares (see GraphManager.ranking_batch).
_rank_batch: contextvars.ContextVar = contextvars.ContextVar("rank_batch", default=None)


# A Done node of these types stays Done when a prerequisite reopens. A
# Milestone records a result the world confirmed. Unfinishing the work that
# was planned for it doesn't take the result back.
_KEEPS_DONE_TYPES = frozenset({'Milestone'})


def _ignore(name):
    """A listener that does nothing: a GraphManager on its own fires no events."""


def _utc_now_ts() -> int:
    """Current UTC instant as Unix seconds for append-only lifecycle history."""
    return int(time.time())


class GraphManager:
    """Single gateway for all graph state reads and writes.

    Every callback module constructs its own GraphManager instance. They
    share the SQLite file and the revisions in graph.state that their caches
    are keyed on, so a mutation through one is seen by every other's cache.
    """
    # Class-level queue of container names whose hard prereqs just became
    # all Done as a side-effect of an update_node call. Drained by the UI to
    # surface a "Mark Done?" suggestion modal. Class-level (not instance) because
    # every GraphManager touches the same DB and needs to see the same pending candidates regardless of which
    # instance initiated the mutation.
    _auto_done_candidates: List[str] = []
    # Latest scoring-run timings (dict with adj_ms/goals_ms/score_ms/rank_ms/
    # total_ms/n_nodes). Written by calculate_priority_scores on the single
    # startup run; read-and-consumed by the Next-tab perf overlay.
    _last_perf_timings: Optional[dict] = None
    # Startup-only gate: timed scoring happens at most once per process. Once
    # True, subsequent scoring runs skip the timing path even if the setting
    # is on. Reset across test boundaries by the tmp_perf_log fixture.
    _startup_perf_recorded: bool = False

    def __init__(self):
        self._repository = GraphRepository(lambda: self.get_connection())
        self.caches = GraphCaches()
        # Called with a node's name when it turns Done, and with an event's
        # name when deleting a node narrows that event's trigger set, each
        # after the commit. AppServices points them at its EventManager.
        self.on_node_done = _ignore
        self.on_trigger_set_narrowed = _ignore

    def _prepare_read_caches(self):
        epoch = (database.get_db_path(), revisions.graph)
        if epoch != self.caches.read_epoch:
            self.caches.communities.clear()
            self.caches.subtrees.clear()
            self.caches.inherited_times = None
            self.caches.read_epoch = epoch

    def _cache_communities(self, key, communities):
        if database.in_transaction():
            return
        with self.caches.lock:
            self.caches.communities[key] = communities
            while len(self.caches.communities) > 32:
                self.caches.communities.popitem(last=False)

    def _bump_version(self, scoring: bool = True) -> None:
        """Invalidate memoization caches. Called by every node/edge mutator.

        Pass scoring=False for cosmetic-only node edits (e.g. description,
        tags, paths) — graph_version still bumps so UI re-renders, but the
        scoring memo stays valid and the next get_suggestions() is near-free.
        """
        revisions.changed(scoring=scoring)

    def get_connection(self) -> sqlite3.Connection:
        """Returns a new database connection with foreign keys enabled."""
        return database.get_connection()

    # --- Node Operations ---

    def _name_taken(self, name: str, own: Optional[str] = None) -> Optional[str]:
        """The existing node, other than ``own``, whose name is ``name`` ignoring
        case (casefold, as the editor compares), or None."""
        wanted = name.casefold()
        with self.get_connection() as conn:
            for (existing,) in conn.execute("SELECT name FROM Nodes"):
                if existing != own and existing.casefold() == wanted:
                    return existing
        return None

    def _unfinished_prerequisites(self, name: str) -> List[str]:
        """The hard prerequisites of ``name`` that aren't Done."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT e.source FROM Edges e JOIN Nodes n ON n.name = e.source "
                "WHERE e.target = ? AND e.type = ? AND n.status != ? ORDER BY e.source",
                (name, EDGE_NEEDS_HARD, STATUS_DONE)).fetchall()
        return [row[0] for row in rows]

    def completion_order(self, names: List[str]) -> List[str]:
        """``names`` with every hard prerequisite ahead of what it unlocks, so
        completing them one by one never meets a blocked node. Otherwise the
        order is kept."""
        chosen = list(dict.fromkeys(names))
        wanted = set(chosen)
        prerequisites = {name: set() for name in chosen}
        for edge in self.get_edges():
            if (edge['type'] == EDGE_NEEDS_HARD and edge['source'] in wanted
                    and edge['target'] in wanted):
                prerequisites[edge['target']].add(edge['source'])
        ordered, placed = [], set()
        while len(ordered) < len(chosen):
            ready = [n for n in chosen if n not in placed and prerequisites[n] <= placed]
            if not ready:  # a cycle can't form among Needs edges; keep the rest as given
                ready = [n for n in chosen if n not in placed]
            ordered.append(ready[0])
            placed.add(ready[0])
        return ordered

    @database.atomic
    def add_node(self, node: Node):
        """Add a new node to the database."""
        problem = graph_rules.name_problem(node.name, "Node name")
        if problem:
            raise ValueError(problem)
        taken = self._name_taken(node.name)
        if taken:
            raise ValueError(f"A node named '{taken}' already exists.")
        if not node.context:
            raise ValueError(
                f"'{node.name}' must have a context: choose the area of life "
                "it belongs to."
            )
        self._normalize_activity(node)
        if node.status == STATUS_DONE and node.done_date is None:
            node.done_date = date.today().isoformat()
        self._repository.insert_node(node, _utc_now_ts)
        self._bump_version()

    @staticmethod
    def _normalize_activity(node, prior=None):
        """Hold the rules between sleeping, finished and current work for
        every writer: the editor, the node menu, events and suggestions.

        A node can't be Dormant and Done at once: a sleeping node isn't
        finished, and its completion would fire the events watching it. A
        Dormant or Done node isn't current work, so it leaves Now. Blocked
        nodes and Goals may stay on Now; there they stand for the steps that
        unblock them.
        """
        if node.dormant and node.status == STATUS_DONE:
            if prior is not None and prior.status == STATUS_DONE:
                raise ValueError(f"Reopen '{node.name}' before putting it to sleep.")
            raise ValueError(f"Wake '{node.name}' before marking it Done.")
        if node.dormant or node.status == STATUS_DONE:
            node.now = 0

    @database.atomic
    def update_node(self, node: Node):
        """Updates an existing node."""
        if not node.context:
            raise ValueError(
                f"'{node.name}' must have a context: choose the area of life "
                "it belongs to."
            )
        prior = self.get_node(node.name)
        self._normalize_activity(node, prior)
        # Goals have no Blocked state. A Blocked node turned into a Goal kept
        # it, and the cascade, which leaves Goals alone, never cleared it.
        if node.type == "Goal" and node.status == STATUS_BLOCKED:
            node.status = STATUS_OPEN
        # Completion is judged against the node as it was before this whole
        # transaction. A compound save can write the node again after marking
        # it Done, and that later write sees it Done already.
        was_done = database.first_in_transaction(
            ("was-done", node.name), prior is not None and prior.status == STATUS_DONE)
        # A node is Done only once its hard prerequisites are: that is what
        # Blocked means, and the launch repair (recompute_all_statuses) would
        # put it back to Blocked otherwise. Goals are the user's to complete.
        # A Milestone is a result, not work: it can be hit before the work
        # planned for it is finished (see _KEEPS_DONE_TYPES).
        # A Done Milestone turned into another type has to meet that type's
        # rule, or the launch repair would block it.
        if (node.status == STATUS_DONE and node.type not in ("Goal", "Milestone")
                and (prior is None or prior.status != STATUS_DONE
                     or prior.type != node.type)):
            blockers = self._unfinished_prerequisites(node.name)
            if blockers:
                listed = ", ".join(f"'{b}'" for b in blockers[:3])
                more = f" and {len(blockers) - 3} more" if len(blockers) > 3 else ""
                raise ValueError(
                    f"'{node.name}' can't be Done yet: it needs {listed}{more} first. "
                    "Finish those, or remove the requirement.")
        # --- Auto-stamp lifecycle snapshots and clear Now on completion ---
        # start_date is refreshed to today on every fresh off→on Now flip, so
        # it remains the convenient latest-start snapshot used by existing UI.
        # Turning Now *off* deliberately leaves it intact. done_date is likewise
        # the latest completion snapshot and is cleared on reopen. The lossless
        # record of every boundary is NodeLifecycleEvents below.
        lifecycle_event_types = []
        if prior is not None:
            today_iso = date.today().isoformat()
            if node.now > 0 and prior.now == 0:
                node.start_date = today_iso
            if (node.status == STATUS_DONE
                    and prior.status != STATUS_DONE):
                if prior.done_date is None:
                    node.done_date = today_iso
                if node.now > 0:
                    node.now = 0
            elif (node.status != STATUS_DONE
                    and prior.status == STATUS_DONE):
                node.done_date = None
            # Compare the stored state with the final state after completion's
            # automatic Now-clear. Positive Now ranks all mean the same active
            # membership, so drag reordering never creates history noise.
            if prior.now > 0 and node.now == 0:
                lifecycle_event_types.append('now_stopped')
            if prior.status == STATUS_DONE and node.status != STATUS_DONE:
                lifecycle_event_types.append('reopened')
            if prior.status != STATUS_DONE and node.status == STATUS_DONE:
                lifecycle_event_types.append('completed')
            if prior.now == 0 and node.now > 0:
                lifecycle_event_types.append('now_started')
        # Read before the write, so the ranking is the one the node left.
        now_rank = (self._recommendation_rank(node.name)
                    if 'now_started' in lifecycle_event_types else (None, None))
        self._repository.write_node(node, lifecycle_event_types, _utc_now_ts, now_rank)
        # A priority rank belongs to an unfinished Goal: it boosts the work
        # leading into it. A Goal turned into another type kept its rank, so
        # its old subtree stayed boosted, in a slot nothing could clear. A
        # finished Goal frees its slot for the next one.
        if prior is not None and prior.type == "Goal" and (
                node.type != "Goal"
                or (node.status == STATUS_DONE and prior.status != STATUS_DONE)):
            ConfigManager.drop_priority_goal(node.name)
        # The node's own Blocked or Open follows its prerequisites, whatever
        # the form said: a Goal turned into an Action kept Open with
        # unfinished prerequisites until the next launch repaired it.
        if node.type != "Goal" and node.status != STATUS_DONE:
            self.update_node_state(node.name)
        self._update_dependent_nodes_state(node.name)
        # Skip scoring-cache invalidation if only cosmetic fields changed.
        # _update_dependent_nodes_state may have touched other nodes' status
        # (a scoring-relevant field), so it bumps the scoring revision itself.
        scoring_changed = prior is None or any(
            getattr(prior, f, None) != getattr(node, f, None)
            for f in SCORING_RELEVANT_FIELDS
        )
        self._bump_version(scoring=scoring_changed)
        # Done is only ever set here — the cascade in
        # _update_dependent_nodes_state only flips Blocked/Open — so this is
        # the one place completion side-effects belong.
        def completed():
            saved = self.get_node(node.name)
            if saved is None or saved.status != STATUS_DONE:
                return
            # Fire any event whose trigger condition this completion satisfies
            # (OR fires on this node alone; AND needs its whole set Done), but only
            # on a true Open/Blocked → Done transition. Re-saving an already-
            # Done node should be a no-op for events.
            if not was_done:
                try:
                    self.on_node_done(node.name)
                except Exception:
                    # Event-firing must never block a node save. Failures here
                    # are logged but the node update remains committed.
                    logger.exception("Firing events for %s's completion failed",
                                     node.name)
                # Auto-Done suggestion: any direct Hard dependent that is a
                # Goal or inherited-time container (never a Milestone) whose
                # prereqs are now ALL Done (and isn't already Done itself)
                # becomes a candidate the UI surfaces via a "Mark Done?" modal. Detection is scoped to true Done
                # transitions so re-saves and graph edits don't spam.
                self._collect_auto_done_candidates(node.name)

        if node.status == STATUS_DONE:
            database.on_commit(completed, key=("completion", node.name))

    def _collect_auto_done_candidates(self, just_done_name: str) -> None:
        """Append direct container dependents of ``just_done_name`` whose
        hard prereqs are now all Done to the class-level candidate queue.

        Eligible dependents: Goals and any non-Milestone node with
        ``time_mode='inherited'`` (its "work" is its descendants' work, so
        when those are Done it should be too). See ``is_auto_done_ready``.

        Only direct dependents are inspected: a transitive container can't be
        "ready" yet because its own prereq (the direct dependent) is still
        Open/Blocked. If the user marks the direct candidate Done via the
        modal, that update_node call will detect the transitive container.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT n.name FROM Edges e "
                "JOIN Nodes n ON e.target = n.name "
                "WHERE e.source=? AND e.type='Needs_Hard'",
                (just_done_name,),
            )
            dependents = cursor.fetchall()
            for (dep_name,) in dependents:
                if not self.is_auto_done_ready(dep_name):
                    continue
                if dep_name not in GraphManager._auto_done_candidates:
                    GraphManager._auto_done_candidates.append(dep_name)

    @database.consistent_read
    def is_auto_done_ready(self, name: str) -> bool:
        """Whether "Mark Done?" may be offered for ``name`` right now.

        A container (Goal or inherited-time node) that isn't Done or asleep,
        with at least one hard prerequisite and every one of them Done.
        Checked when a suggestion is queued, shown and accepted, since the
        graph can change in between and Goals never auto-block. Marking a
        Goal Done by judgment doesn't go through here.

        Milestones are never offered. Finishing the work beneath one isn't
        evidence the target was hit: the user marks it Done after the test.
        """
        node = self.get_node(name)
        if (node is None or node.dormant or node.status == STATUS_DONE
                or node.type == 'Milestone'
                or (node.type != 'Goal' and node.time_mode != 'inherited')):
            return False
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT n.status FROM Edges e JOIN Nodes n ON n.name=e.source "
                "WHERE e.target=? AND e.type=?", (name, EDGE_NEEDS_HARD)).fetchall()
        return bool(rows) and all(status == STATUS_DONE for (status,) in rows)

    @database.atomic
    def complete_suggested_node(self, name: str) -> bool:
        """Revalidate and accept a suggestion in the same write transaction."""
        if not self.is_auto_done_ready(name):
            return False
        node = self.get_node(name)
        node.status = STATUS_DONE
        self.update_node(node)
        return True

    @database.consistent_read
    def pop_auto_done_candidates(self) -> List[str]:
        """Return and clear the queued auto-Done candidate names.

        Caller is the Dash drain callback that pushes pending candidates into
        the editor's modal-trigger store. Each candidate is a Goal or
        inherited-time container whose hard prereqs are now all Done — the UI
        offers the user a one-click "Mark Done?" suggestion for it.
        """
        candidates = list(GraphManager._auto_done_candidates)
        GraphManager._auto_done_candidates = []
        return candidates

    @database.atomic
    def delete_node(self, node_name: str):
        """Deletes a node by name.

        Cleans up references that aren't FK-cascaded:
          - `NodeLifecycleEvents` rows ARE FK-cascaded with their node.
          - `NodeLedger` gains a 'deleted' row and keeps the node's earlier
            ones: it has no foreign key, so work that left the graph stays
            on record.
          - `EventTriggerNodes` rows ARE FK-cascaded, so deleting a node
            narrows every trigger set that watched it. An event that still
            has other triggers keeps working with one fewer condition; an
            event left with an empty set has no way to fire on completion
            any more, so it demotes to manual-trigger. Both outcomes are
            queued as a one-shot announcement, since a silently narrowed
            AND condition is exactly the kind of change a user needs told.
          - Config-side references (priority_goals) — delegated to
            ConfigManager.delete_node_references, mirroring how
            rename_node delegates to rename_node_references.
        """
        from datetime import date
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Find dependents before deleting edges so we can recalculate their state
            cursor.execute("SELECT target FROM Edges WHERE source=? AND type='Needs_Hard'", (node_name,))
            dependents = [row[0] for row in cursor.fetchall()]
            # Snapshot the watching events before the FK cascade removes the
            # rows, so the notification can name them and tell narrowed apart
            # from demoted.
            cursor.execute(
                "SELECT e.name FROM Events e "
                "JOIN EventTriggerNodes etn ON etn.event_name = e.name "
                "WHERE etn.node_name=? AND e.status='Pending'",
                (node_name,),
            )
            affected_events = [row[0] for row in cursor.fetchall()]
            doomed = self.get_node(node_name)
            if doomed is not None:
                record_ledger(cursor, doomed, 'deleted', _utc_now_ts())
            cursor.execute("DELETE FROM Edges WHERE source=? OR target=?", (node_name, node_name))
            cursor.execute("DELETE FROM Nodes WHERE name=?", (node_name,))
            demoted: List[str] = []
            narrowed: List[str] = []
            for ev in affected_events:
                cursor.execute(
                    "SELECT COUNT(*) FROM EventTriggerNodes WHERE event_name=?", (ev,)
                )
                (demoted if cursor.fetchone()[0] == 0 else narrowed).append(ev)
            conn.commit()
        for dept in dependents:
            self.update_node_state(dept)
        if affected_events:
            ConfigManager.add_pending_event_notification({
                "kind": "trigger_node_deleted",
                "events": affected_events,
                "demoted": demoted,
                "narrowed": narrowed,
                "deleted_node": node_name,
                "when": date.today().isoformat(),
            })
        # The nodes left in a narrowed set may all be Done already.
        for ev in narrowed:
            self.on_trigger_set_narrowed(ev)
        ConfigManager.delete_node_references(node_name)
        self._bump_version()

    @database.atomic
    def canonicalize_helps_edges(self) -> int:
        """Store every Synergy the way round add_edge does, and return how
        many rows changed. Older builds left some back to front, and add_edge
        then stored the same pair a second time."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT source, target FROM Edges WHERE type=?", (EDGE_HELPS,)).fetchall()
            stored = set(rows)
            fixed = 0
            for source, target in rows:
                canonical = self.canonicalize_edge(source, target, EDGE_HELPS)
                if canonical == (source, target):
                    continue
                conn.execute("DELETE FROM Edges WHERE source=? AND target=? AND type=?",
                             (source, target, EDGE_HELPS))
                if canonical not in stored:
                    conn.execute("INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)",
                                 (*canonical, EDGE_HELPS))
                    stored.add(canonical)
                fixed += 1
        if fixed:
            self._bump_version()
        return fixed

    @database.atomic
    def prune_priority_goals(self) -> List[str]:
        """Take the priority ranks of names that aren't unfinished Goals,
        and return those names. A save drops a rank when its Goal changes
        type or is finished; this catches data from before that, or from an
        import or a script."""
        goals = {n.name for n in self.get_all_nodes(include_dormant=True)
                 if n.type == "Goal" and n.status != STATUS_DONE}
        stale = [name for name in ConfigManager.get_priority_goals()
                 if name not in goals]
        for name in stale:
            ConfigManager.drop_priority_goal(name)
        return stale

    @database.atomic
    def rename_node(self, old_name: str, new_name: str):
        """Rename a node and its SQL/settings references in one transaction."""
        problem = graph_rules.name_problem(new_name, "Node name")
        if problem:
            raise ValueError(problem)
        taken = self._name_taken(new_name, own=old_name)
        if taken:
            raise ValueError(f"A node named '{taken}' already exists.")
        self._repository.rename_node(old_name, new_name)
        ConfigManager.rename_node_references(old_name, new_name)
        self._bump_version()

    def get_node(self, name: str) -> Optional[Node]:
        """Retrieves a specific node by name."""
        return self._repository.get_node(name)

    def get_node_lifecycle_events(self, node_name: str) -> List[dict]:
        """Return one node's lifecycle boundaries in stable occurrence order."""
        return self._repository.get_node_lifecycle_events(node_name)

    def get_node_ledger(self, node_name: Optional[str] = None) -> List[dict]:
        """Nodes added to and deleted from the graph, oldest first."""
        return self._repository.get_node_ledger(node_name)

    def _recommendation_rank(self, node_name: str):
        """(rank, ranked_of): ``node_name``'s place in the recommendation
        ranking, 1 at the top, and how many nodes it ranks. The ranking is
        the Next tab's without its filters: every node not in Now that
        scores at or above zero. rank is None for a node it leaves out.

        Recorded when a node enters Now, to tell later whether picks follow
        the recommendations. It is a side record, so a scoring failure
        records nothing rather than blocking the save. Inside ranking_batch
        the whole run shares one ranking."""
        batch = _rank_batch.get()
        if batch is not None and batch["ranked"] is not None:
            ranked = batch["ranked"]
        else:
            try:
                scored = self.calculate_priority_scores(
                    [n for n in self.get_all_nodes() if not n.now],
                    priority_goals=ConfigManager.get_priority_goals())
            except Exception:
                logger.exception("Couldn't rank %s as it entered Now", node_name)
                return None, None
            ranked = [n.name for n in scored if getattr(n, 'priority_score', -1) >= 0]
            if batch is not None:
                batch["ranked"] = ranked
        if batch is not None:
            # The nodes this run already moved have left the pool.
            ranked = [name for name in ranked if name not in batch["moved"]]
            batch["moved"].add(node_name)
        rank = ranked.index(node_name) + 1 if node_name in ranked else None
        return rank, len(ranked)

    @staticmethod
    @contextlib.contextmanager
    def ranking_batch():
        """Rank once for a run of nodes entering Now together.

        Each start records the node's place in the recommendations, and that
        scored the whole graph, so a bulk Add to Now, or an event waking
        several nodes onto Now, scored it once per node. In a batch the first
        start scores, and each later one reads the same ranking without the
        nodes moved before it. The rank is a side record, so a snapshot is
        close enough."""
        if _rank_batch.get() is not None:
            yield
            return
        token = _rank_batch.set({"ranked": None, "moved": set()})
        try:
            yield
        finally:
            _rank_batch.reset(token)

    def get_aliases(self, node_name: str) -> list:
        """Return all aliases for a node."""
        return self._repository.get_aliases(node_name)

    @database.atomic
    def set_aliases(self, node_name: str, aliases: list):
        """Replace all aliases for a node."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Aliases WHERE node_name=?", (node_name,))
            for alias in aliases:
                if alias and alias.strip():
                    clean = format_name(alias.strip(), ConfigManager.get_name_formatting())
                    problem = graph_rules.name_problem(clean, "Alias")
                    if problem:
                        raise ValueError(problem)
                    owner = cursor.execute("SELECT node_name FROM Aliases WHERE alias=?", (clean,)).fetchone()
                    if owner and owner[0] != node_name:
                        raise ValueError(f"Alias '{clean}' already belongs to '{owner[0]}'.")
                    cursor.execute(
                        "INSERT OR IGNORE INTO Aliases (alias, node_name) VALUES (?, ?)",
                        (clean, node_name))
            conn.commit()
        self._bump_version(scoring=False)

    def get_all_aliases(self) -> dict:
        """Return {alias: node_name} mapping for all aliases.

        Keys are the stored (titlecase-linted) form. For case-insensitive
        lookups use :py:meth:`resolve_alias`.
        """
        return self._repository.get_all_aliases()

    def resolve_alias(self, alias_input: str) -> Optional[str]:
        """Look up the node name for an alias, case-insensitively.

        Aliases are stored titlecase-linted, but the user may type any case
        (e.g. ``alias:mathnotes`` matches a stored ``MathNotes``). Returns
        the node name on hit, or ``None`` on miss.
        """
        return self._repository.resolve_alias(alias_input)

    def get_all_nodes(self, include_dormant: bool = False) -> List[Node]:
        """Retrieves all nodes. Excludes dormant nodes by default."""
        return self._repository.get_all_nodes(include_dormant)

    def get_now_nodes(self) -> List[Node]:
        """Return all nodes flagged Now (currently being worked on).

        Dormant nodes are excluded — a shelved node should not also be
        "currently being worked on", and the Now section should never
        surface one.
        """
        return self._repository.get_now_nodes()

    @database.atomic
    def reorder_now_nodes(self, ordered_names: List[str]):
        """Update the "now" rank for the provided nodes to match their order in the list.

        Only updates nodes that are currently flagged Now (now > 0).
        A stale DOM state could include a card that was just unpinned;
        blindly setting its rank would re-pin it.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for i, name in enumerate(ordered_names, start=1):
                cursor.execute(
                    'UPDATE Nodes SET "now" = ? WHERE name = ? AND "now" > 0',
                    (i, name),
                )
            conn.commit()
        self._bump_version(scoring=False)

    # --- Edge Operations ---

    @staticmethod
    def canonicalize_edge(source: str, target: str, edge_type: str) -> Tuple[str, str]:
        """Helps is bidirectional: (A,B,Helps) and (B,A,Helps) describe the
        same fact (verified in scoring.build_adjacency, which mirrors Syn for
        either row). Canonicalize so only one row per pair can exist by
        sorting endpoints lexically. Hard/Soft direction is meaningful and
        kept as-is.
        """
        return graph_rules.canonicalize_edge(source, target, edge_type)

    def _check_pair_conflict(self, cursor, source: str, target: str, edge_type: str) -> None:
        """Raise if a CONFLICTING edge already exists between this pair.

        Helps is bidirectional and the schema's composite PK on (source,
        target, type) explicitly allows a directional Hard/Soft prereq to
        coexist with a Helps synergy on the same pair. Only the four
        directional buckets (Hard/Soft in either direction) are mutually
        exclusive. A duplicate of the exact same row is a no-op (handled
        separately by sqlite3.IntegrityError in the INSERT).
        """
        cursor.execute(
            "SELECT source, target, type FROM Edges "
            "WHERE (source=? AND target=?) OR (source=? AND target=?)",
            (source, target, target, source),
        )
        for ex_src, ex_tgt, ex_type in cursor.fetchall():
            if ex_src == source and ex_tgt == target and ex_type == edge_type:
                continue  # exact duplicate — INSERT will be a no-op via PK
            if EDGE_HELPS in (ex_type, edge_type):
                continue  # Helps coexists with directional edges on the same pair
            raise ValueError(
                f"An edge already exists between '{source}' and '{target}' "
                f"({ex_src} -> {ex_tgt}, type={ex_type}). "
                "Only one directional edge type is allowed per pair of nodes."
            )

    @database.atomic
    def add_edge(self, source: str, target: str, edge_type: str, *, _defer_updates=False):
        """Adds an edge to the DB, ensuring no self-loop, no cycle, and no
        conflicting edge type already on this pair."""
        if source == target:
            raise ValueError("Self-loop edges are not allowed.")

        source, target = self.canonicalize_edge(source, target, edge_type)

        if edge_type in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
            if self._will_create_cycle(source, target):
                raise ValueError(f"Adding edge {source} -> {target} creates a cycle.")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            for name in (source, target):
                if cursor.execute("SELECT 1 FROM Nodes WHERE name=?", (name,)).fetchone() is None:
                    raise ValueError(f"Cannot link missing node '{name}'.")
            self._check_pair_conflict(cursor, source, target, edge_type)
            # A Synergy row an older build left back to front is this one.
            reversed_helps = edge_type == EDGE_HELPS and cursor.execute(
                "SELECT 1 FROM Edges WHERE source=? AND target=? AND type=?",
                (target, source, edge_type)).fetchone() is not None
            changed = False
            if not reversed_helps:
                cursor.execute("INSERT OR IGNORE INTO Edges (source, target, type) VALUES (?, ?, ?)", (source, target, edge_type))
                changed = cursor.rowcount > 0
            if changed and not _defer_updates and edge_type == EDGE_NEEDS_HARD:
                self.update_node_state(target)
        if changed and not _defer_updates:
            self._bump_version()

    @database.atomic
    def remove_edge(self, source: str, target: str, edge_type: str):
        """Removes a specific edge. A Helps pair may be named either way round,
        like add_edge takes it, and a row an older rename left back to front
        goes too."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if edge_type == EDGE_HELPS:
                cursor.execute(
                    "DELETE FROM Edges WHERE type=? AND "
                    "((source=? AND target=?) OR (source=? AND target=?))",
                    (edge_type, source, target, target, source))
            else:
                cursor.execute("DELETE FROM Edges WHERE source=? AND target=? AND type=?",
                               (source, target, edge_type))
            changed = cursor.rowcount > 0
            conn.commit()
            if changed and edge_type == EDGE_NEEDS_HARD:
                self.update_node_state(target)
        if changed:
            self._bump_version()

    def get_edges(self) -> List[Dict[str, str]]:
        """Retrieves all edges."""
        return self._repository.get_edges()

    @database.atomic
    def sync_edges(self, node_name: str, needs_hard: list, needs_soft: list, supports_hard: list, supports_soft: list, helps: list,
                   *, defer_states=False):
        needs_hard = needs_hard or []
        needs_soft = needs_soft or []
        supports_hard = supports_hard or []
        supports_soft = supports_soft or []
        helps = helps or []

        # Validate the form upfront: catch directional conflicts on a pair
        # before any DB mutation so the user sees a single clear error
        # instead of a partial save. Helps is bidirectional and the schema's
        # composite PK on (source, target, type) explicitly allows a Hard/Soft
        # prereq edge to coexist with a Helps synergy on the same pair, so we
        # only reject conflicts among the four directional buckets.
        pair_to_buckets: Dict[frozenset, set] = {}
        bucket_pairs = [
            ('needs_hard', needs_hard),
            ('needs_soft', needs_soft),
            ('supports_hard', supports_hard),
            ('supports_soft', supports_soft),
            ('helps', helps),
        ]
        for bucket_name, others in bucket_pairs:
            for other in others:
                if other == node_name:
                    raise ValueError(
                        f"Self-loop edge on '{node_name}' (in {bucket_name}) is not allowed."
                    )
                pair = frozenset({node_name, other})
                existing = pair_to_buckets.setdefault(pair, set())
                for prior in existing:
                    if prior == bucket_name:
                        continue
                    if 'helps' in (prior, bucket_name):
                        continue  # helps coexists with directional edges
                    raise ValueError(
                        f"Edge between '{node_name}' and '{other}' declared in both "
                        f"'{prior}' and '{bucket_name}'. Only one edge type is allowed "
                        f"per pair (except Helps, which may coexist with directional edges)."
                    )
                existing.add(bucket_name)

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Every relationship picker includes dormant nodes, so the lists
            # passed here are a complete replacement for all incident edges.
            previous_dependents = [row[0] for row in cursor.execute(
                "SELECT target FROM Edges WHERE source=? AND type='Needs_Hard'", (node_name,)
            ).fetchall()]
            before_edges = {tuple(row) for row in cursor.execute(
                "SELECT source, target, type FROM Edges WHERE source=? OR target=?",
                (node_name, node_name)).fetchall()}
            cursor.execute(
                """DELETE FROM Edges
                   WHERE target=? AND type IN ('Needs_Hard', 'Needs_Soft')""",
                (node_name,),
            )
            cursor.execute(
                """DELETE FROM Edges
                   WHERE source=? AND type IN ('Needs_Hard', 'Needs_Soft')""",
                (node_name,),
            )
            cursor.execute(
                """DELETE FROM Edges
                   WHERE type = 'Helps'
                     AND (target = ? OR source = ?)""",
                (node_name, node_name),
            )

            def _insert_edge(src, trgt, etype):
                # Reuse the canonical validator on this transaction's current
                # graph, including both the removals and preceding inserts.
                self.add_edge(src, trgt, etype, _defer_updates=True)

            for src in needs_hard: _insert_edge(src, node_name, EDGE_NEEDS_HARD)
            for src in needs_soft: _insert_edge(src, node_name, EDGE_NEEDS_SOFT)

            for trgt in supports_hard: _insert_edge(node_name, trgt, EDGE_NEEDS_HARD)
            for trgt in supports_soft: _insert_edge(node_name, trgt, EDGE_NEEDS_SOFT)

            for linked in helps: _insert_edge(node_name, linked, EDGE_HELPS)

            conn.commit()

            after_edges = {tuple(row) for row in cursor.execute(
                "SELECT source, target, type FROM Edges WHERE source=? OR target=?",
                (node_name, node_name)).fetchall()}
            if before_edges != after_edges:
                self._bump_version()

        # Recalculate state for the saved node and all nodes affected by its edges
        def settle():
            self.update_node_state(node_name)
            for trgt in set(supports_hard) | set(previous_dependents):
                self.update_node_state(trgt)
            for trgt in supports_soft:
                self.update_node_state(trgt)
            for src in needs_hard:
                self._update_dependent_nodes_state(src)

        # The editor's save writes the node's own fields after its edges, so
        # completion is judged against the final graph. It settles states
        # itself, once that write is in.
        if defer_states:
            return settle
        settle()

    # --- Integrity and State ---

    def _will_create_cycle(self, source: str, target: str) -> bool:
        if source == target:
            return True

        visited = set()
        queue = [target]

        with self.get_connection() as conn:
            cursor = conn.cursor()
            while queue:
                curr = queue.pop()
                if curr == source:
                    return True
                visited.add(curr)
                cursor.execute("SELECT target FROM Edges WHERE source=? AND type IN ('Needs_Hard', 'Needs_Soft')", (curr,))
                for row in cursor.fetchall():
                    if row[0] not in visited:
                        queue.append(row[0])

        return False

    @staticmethod
    def is_prereq_satisfied(p_node) -> bool:
        """Check if a prerequisite node is satisfied (Done)."""
        return graph_rules.is_prereq_satisfied(p_node)

    @database.atomic
    def update_node_state(self, node_name: str):
        """Recompute Blocked/Open for ``node_name`` and cascade to dependents.

        Iterative BFS over the dependency frontier so a single SQLite
        connection is shared across the whole cascade — previous recursive
        version opened a new connection per level, which on a deep cascade
        meant 100+ short-lived connections per call.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._cascade_update_states([node_name], cursor)
            conn.commit()

    @database.atomic
    def _update_dependent_nodes_state(self, node_name: str):
        """Recompute every Hard-downstream dependent of ``node_name``."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT target FROM Edges WHERE source=? AND type='Needs_Hard'",
                (node_name,),
            )
            seeds = [row[0] for row in cursor.fetchall()]
            if seeds:
                self._cascade_update_states(seeds, cursor)
                conn.commit()

    def _cascade_update_states(self, seeds: List[str], cursor) -> None:
        """Iterative cascade: re-derive Blocked/Open for each seed and walk
        downstream Hard dependents on every actual status change.

        Cascade is exhaustive: a Done node whose prereqs are no longer all
        Done flips to Blocked, propagating downstream. A Done node whose
        prereqs ARE all Done stays Done — recomputing should never silently
        un-mark work the user said they finished. Goals retain user-set
        status, and a Done Milestone stays Done. Caller owns the connection
        commit.
        """
        queue = deque(dict.fromkeys(seeds))
        pending = set(queue)
        changed = False
        while queue:
            node_name = queue.popleft()
            pending.discard(node_name)

            cursor.execute(
                "SELECT type, status FROM Nodes WHERE name=?", (node_name,),
            )
            row = cursor.fetchone()
            if not row:
                continue
            node_type, current_status = row
            if node_type == 'Goal':
                continue
            if current_status == STATUS_DONE and node_type in _KEEPS_DONE_TYPES:
                continue

            cursor.execute(
                "SELECT n.status FROM Edges e "
                "JOIN Nodes n ON e.source = n.name "
                "WHERE e.target=? AND e.type='Needs_Hard'",
                (node_name,),
            )
            is_blocked = any(s != STATUS_DONE for (s,) in cursor.fetchall())

            # Done nodes only ever transition to Blocked. If they're not
            # Blocked, leave them Done — never silently un-finish work.
            if current_status == STATUS_DONE and not is_blocked:
                continue

            new_status = STATUS_BLOCKED if is_blocked else STATUS_OPEN
            if current_status == new_status:
                continue

            cursor.execute(
                "UPDATE Nodes SET status=?, done_date=NULL WHERE name=?", (new_status, node_name),
            )
            if current_status == STATUS_DONE:
                # The node lost its completion because a prerequisite did.
                # History records that like a manual reopen.
                cursor.execute(
                    "INSERT INTO NodeLifecycleEvents "
                    "(node_name, event_type, occurred_at, source) "
                    "VALUES (?, 'reopened', ?, 'live')",
                    (node_name, _utc_now_ts()),
                )
            changed = True
            cursor.execute(
                "SELECT target FROM Edges WHERE source=? AND type='Needs_Hard'",
                (node_name,),
            )
            for (dependent,) in cursor.fetchall():
                if dependent not in pending:
                    queue.append(dependent)
                    pending.add(dependent)
        if changed:
            self._bump_version()

    def get_downstream_done_dependents(self, node_name: str) -> List[str]:
        """Return Done downstream nodes that would re-block if `node_name` were un-Done.

        Used to warn the user before they un-Done a node: these are the
        dependents that will flip Done → Blocked once the cascade runs. It
        runs _cascade_update_states' rules in memory, without writing, since
        an editor save asks inside its own transaction. Every Done node past
        a Hard link used to be listed, including Goals, which keep their
        status, and the nodes beyond them, which the cascade never reaches.
        """
        with self.get_connection() as conn:
            rows = conn.execute("SELECT name, type, status FROM Nodes").fetchall()
            edges = conn.execute(
                "SELECT source, target FROM Edges WHERE type='Needs_Hard'").fetchall()
        kind = {name: node_type for name, node_type, _ in rows}
        status = {name: node_status for name, _, node_status in rows}
        prereqs: Dict[str, List[str]] = defaultdict(list)
        dependents: Dict[str, List[str]] = defaultdict(list)
        for source, target in edges:
            prereqs[target].append(source)
            dependents[source].append(target)

        status[node_name] = STATUS_OPEN
        reopened: List[str] = []
        queue = deque(dict.fromkeys(dependents[node_name]))
        pending = set(queue)
        while queue:
            name = queue.popleft()
            pending.discard(name)
            if kind.get(name, 'Goal') == 'Goal':
                continue
            current = status[name]
            if current == STATUS_DONE and kind[name] in _KEEPS_DONE_TYPES:
                continue
            blocked = any(status.get(p) != STATUS_DONE for p in prereqs[name])
            if current == STATUS_DONE and not blocked:
                continue
            new_status = STATUS_BLOCKED if blocked else STATUS_OPEN
            if new_status == current:
                continue
            if current == STATUS_DONE:
                reopened.append(name)
            status[name] = new_status
            for dependent in dependents[name]:
                if dependent not in pending:
                    queue.append(dependent)
                    pending.add(dependent)
        return reopened

    @database.atomic
    def recompute_all_statuses(self) -> int:
        """Re-derive every non-Goal node's Blocked/Open status from scratch.

        Safety net for any case where the incremental cascade was bypassed.
        Called on app launch (`app.py`) so every session starts in a
        consistent state. Returns the number of nodes whose status actually
        changed; logs a warning when drift is detected so silent bypass
        paths surface in the logs instead of being papered over.

        Done in memory off a single nodes-load and a single edges-load, then
        persisted as one batched UPDATE — three DB connections total rather
        than the ~two-per-node the old per-node cascade opened.

        Goal status is user-controlled, so Goals keep their Open/Done status;
        their stored status still feeds dependents. The one exception is a Goal
        stored as Blocked — Goals have no Blocked state, so that's drift and is
        normalized back to Open (otherwise it sits red forever, invisible to
        every other recompute path). Done nodes ARE re-derived so a
        Done node whose prereqs were un-Done outside the cascade (raw SQL,
        restored backup, etc.) flips to Blocked rather than sitting in an
        asymmetric state. Done Milestones are the exception: they keep their
        Done, as the cascade lets them.
        """
        nodes = self.get_all_nodes(include_dormant=True)   # connection 1
        edges = self.get_edges()                           # connection 2

        stored = {n.name: n.status for n in nodes}
        node_type = {n.name: n.type for n in nodes}

        # Hard-prereq adjacency, restricted to edges whose endpoints both
        # exist (mirrors the JOIN-Nodes guard the per-node cascade relied on,
        # so an orphaned edge can't phantom-block a node).
        prereqs_of: Dict[str, List[str]] = {name: [] for name in stored}
        dependents_of: Dict[str, List[str]] = {name: [] for name in stored}
        for e in edges:
            if e['type'] != EDGE_NEEDS_HARD:
                continue
            src, tgt = e['source'], e['target']
            if src in stored and tgt in stored:
                prereqs_of[tgt].append(src)
                dependents_of[src].append(tgt)

        # Derive statuses to a fixpoint. A node is Blocked when any hard
        # prereq isn't Done; a Done node only ever flips to Blocked, never
        # silently back to Open. Re-derivation never *marks* a node Done, so
        # the Done set only shrinks — that makes "blocked" monotonic and bounds
        # each node to at most one transition, so the worklist always settles
        # (no acyclicity assumption needed).
        derived = dict(stored)

        def _derive(name: str) -> str:
            is_blocked = any(derived[p] != STATUS_DONE for p in prereqs_of[name])
            if derived[name] == STATUS_DONE and (
                    not is_blocked or node_type[name] in _KEEPS_DONE_TYPES):
                return STATUS_DONE
            return STATUS_BLOCKED if is_blocked else STATUS_OPEN

        queue: List[str] = [name for name in stored if node_type[name] != 'Goal']
        while queue:
            name = queue.pop()
            if node_type[name] == 'Goal':
                continue
            new_status = _derive(name)
            if new_status != derived[name]:
                derived[name] = new_status
                queue.extend(dependents_of[name])

        # Goals are scoring sinks and have no Blocked state — a Goal stored as
        # Blocked is drift (e.g. stamped before Goals were exempted from the
        # cascade) that the renderer would paint red. The fixpoint loop never
        # touches Goals, so normalize such a Goal back to Open here. Open/Done
        # Goals are user-controlled and left alone.
        for name in stored:
            if node_type[name] == 'Goal' and stored[name] == STATUS_BLOCKED:
                derived[name] = STATUS_OPEN

        changed_names = [
            name for name in stored
            if derived[name] != stored[name]
        ]
        if changed_names:
            # Re-derivation only ever un-marks Done, so no repaired node ends
            # up Done. Each one sheds its completion date the way the cascade
            # sheds it, and a completion it loses is recorded as a reopen.
            reopened = [name for name in changed_names if stored[name] == STATUS_DONE]
            with self.get_connection() as conn:            # connection 3
                conn.executemany(
                    "UPDATE Nodes SET status=?, done_date=NULL WHERE name=?",
                    [(derived[name], name) for name in changed_names],
                )
                if reopened:
                    occurred_at = _utc_now_ts()
                    conn.executemany(
                        "INSERT INTO NodeLifecycleEvents "
                        "(node_name, event_type, occurred_at, source) "
                        "VALUES (?, 'reopened', ?, 'live')",
                        [(name, occurred_at) for name in reopened],
                    )
                conn.commit()
            logger.warning(
                "recompute_all_statuses: repaired %d drifted node(s): %s",
                len(changed_names),
                ", ".join(changed_names[:10]) + ("..." if len(changed_names) > 10 else ""),
            )
            self._bump_version()
        return len(changed_names)

    # --- Logic ---

    @database.consistent_read
    def calculate_priority_scores(self, now_nodes: List[Node], priority_goals: Optional[List[str]] = None) -> List[Node]:
        """Delegates scoring to the scoring module.

        Reuses per-manager route and required-work maps across calls: a filter toggle,
        priority-goal change, or cosmetic edit (description, tags, paths)
        doesn't alter scoring inputs, so the strongest-route and prerequisite maps
        do not need re-walking. Invalidated only when the scoring revision
        advances (a scoring-relevant node/edge mutation) or a TV-affecting
        hyperparam changes. Cost params (w_e, w_t, beta), goal_boost, and the
        context weights don't affect the
        cached structural maps, so they are excluded from the key.
        """
        return graph_scoring.calculate_priority_scores(self, now_nodes, priority_goals)

    @database.consistent_read
    def get_priority_normalizer(self) -> float:
        """The priority score that displays as 100 everywhere in the app.

        Every surface that prints a 0–100 priority divides by this one
        number, so the same node reads the same on the Home tab, in a
        subtask table and in the Explain modal. Normalizing against
        whichever nodes happen to be on screen would make the figure a
        property of the current list instead of the node.

        The base is the top score among nodes that can actually be
        recommended: Now nodes are excluded because the Next list pulls
        them into their own section, and a cheap Now node is often the
        top score overall — including it would shrink every bar on the
        tab below it. Returns 0.0 when nothing is scorable.

        Cached against the scoring version and every hyperparameter that
        can move a score: the Home tab and the subtask tables each want
        this number alongside a ranking they already paid for, and a
        second full scoring pass per render is worth avoiding.
        """
        return graph_scoring.get_priority_normalizer(self)

    @database.consistent_read
    def get_unblocking_steps(self, target_names, limit: int = 3,
                             priority_goals: Optional[List[str]] = None) -> List[Tuple[Node, str]]:
        """The best actionable work toward each target you cannot start yet.

        A target that can already be recommended needs no steps — its own row
        is the answer, and on a real graph its hard prerequisites are all Done
        by definition, so the walk would return nothing anyway. So this only
        answers for targets carrying a negative score: Blocked nodes, Goals and
        Milestones (never scorable by type), and anything else `_is_scorable`
        rejects.

        For those, walk the transitive ``Needs_Hard`` prerequisite subtree and
        keep the top `limit` by score. Filtering on ``priority_score >= 0``
        drops prerequisites that are themselves blocked, so what comes back is
        always startable today.

        Returns ``[(step_node, target_name), ...]``, targets in the order given
        and steps in descending score within each target. A node already
        claimed by an earlier target is not repeated.
        """
        return graph_queries.get_unblocking_steps(self, target_names, limit, priority_goals)

    @database.consistent_read
    def get_goal_subtree(self, goal_name: str, edge_types=None) -> Set[str]:
        """Returns all node names reachable as prerequisites of a goal (BFS over specified edge types).

        The goal node itself is excluded from the returned set.

        For directed edge types (Needs_Hard, Needs_Soft), traversal follows
        source → target direction (source is a prerequisite of target).

        Helps is bidirectional but fires only at the seed step — direct synergy
        partners of the goal are added, then BFS hops follow only the directed
        types in ``edge_types``. There is no transitive Helps chaining. This
        keeps Synergies-on subtrees focused on "direct partners + what you'd
        need to unlock them" instead of the entire connected neighborhood.

        Args:
            goal_name: The goal node to start from.
            edge_types: Tuple of edge types to traverse. Defaults to (Needs_Hard, Needs_Soft).
        """
        return graph_queries.get_goal_subtree(self, goal_name, edge_types)

    @database.snapshot_read
    def get_dependency_view(self, root_name: str, *, include_soft: bool = True,
                            include_synergies: bool = False,
                            max_depth: int | None = None,
                            filters: dict | None = None) -> dict:
        """Resolve the deterministic, filter-aware local view for ``root_name``.

        Hard prerequisites are always traversed. Soft prerequisites are
        optional. Synergy partners are seeded only from the root; Helps edges
        never chain. Prerequisites beneath a direct synergy partner continue
        to follow the enabled Needs edge types.

        The returned mapping contains ``node_names`` (including the root),
        ``depth_by_name``, and ``discovery_edges`` as ``(source, target, type)``
        tuples. Discovery edges form the stable spanning tree used when the
        Details graph hides cross-links.
        """
        return graph_queries.get_dependency_view(self, root_name, include_soft=include_soft, include_synergies=include_synergies, max_depth=max_depth, filters=filters)

    @database.snapshot_read
    def get_goal_completion(self, goal_name: str, include_soft: bool = True,
                            include_transitive: bool = True,
                            max_depth: int | None = None) -> dict:
        """Returns completion stats for a goal based on its subtree.

        Args:
            include_soft: If False, only traverse hard-need edges.
            include_transitive: If False, only count direct children of the goal.

        Returns dict with: total, done, pct, remaining_time
        """
        return graph_queries.get_goal_completion(self, goal_name, include_soft, include_transitive, max_depth)

    @database.snapshot_read
    def get_effective_time(self, node_name: str) -> float:
        """Returns the effective time estimate for a node.

        For nodes with time_mode='manual', returns the node's expected time
        (`Node.time`, weighted from its own time_o/m/p bracket).

        For nodes with time_mode='inherited', sums the expected times of all
        incomplete nodes among its Hard prerequisites, transitively, treating
        the node itself as a container with zero direct time. Soft
        prerequisites are optional, so they are not part of what it inherits.

        Returns:
            Time in hours.
        """
        return graph_queries.get_effective_time(self, node_name)

    def filter_nodes(self, nodes: List[Node], filters: Dict) -> List[Node]:
        return graph_queries.filter_nodes(self, nodes, filters)

    def hidden_by_status(self, nodes: List[Node], filters: Dict) -> Dict[str, int]:
        return graph_queries.hidden_by_status(self, nodes, filters)

    def build_nx_graph(self, allowed_names: Optional[Set[str]] = None,
                        include_dormant: bool = False) -> "nx.Graph":
        return graph_queries.build_nx_graph(self, allowed_names, include_dormant)

    # --- Migration ---

    def find_orphaned_nodes(self, field: str, old_values: list, new_values: list) -> Dict[str, List[Node]]:
        return graph_taxonomy.find_orphaned_nodes(self, field, old_values, new_values)

    def find_nodes_by_pairs(self, pairs) -> Dict[str, List[Node]]:
        return graph_taxonomy.find_nodes_by_pairs(self, pairs)

    def find_orphaned_subcontext_pairs(self, old_subcontexts: Dict, new_subcontexts: Dict, new_contexts: list) -> Dict[str, List[Node]]:
        return graph_taxonomy.find_orphaned_subcontext_pairs(self, old_subcontexts, new_subcontexts, new_contexts)

    def count_nodes_by_context(self):
        return graph_taxonomy.count_nodes_by_context(self)

    def apply_taxonomy_migration(self, ctx_renames: Dict[str, str], pair_moves) -> None:
        return graph_taxonomy.apply_taxonomy_migration(self, ctx_renames, pair_moves)

    def apply_migration(self, field: str, remap: Dict[str, str], new_subcontexts: Optional[Dict]=None):
        return graph_taxonomy.apply_migration(self, field, remap, new_subcontexts)

    def apply_node_migration(self, node_name: str, field: str, new_val: str, new_subcontexts: Optional[Dict]=None):
        return graph_taxonomy.apply_node_migration(self, node_name, field, new_val, new_subcontexts)

    @database.consistent_read
    def name_community(self, community: Set[str]) -> str:
        """A community's label: an optional context prefix, then up to three
        hub nodes. See `community_labels`."""
        return graph_queries.name_community(self, community)

    @database.consistent_read
    def list_communities(self, method: str = "louvain", filters: Optional[Dict] = None):
        """The Community filter's rows, labelled, ranked and capped, as
        (label, members) pairs."""
        return graph_queries.list_communities(self, method, filters)

    @database.consistent_read
    def detect_communities(self, method: str = "components", filters: Optional[Dict] = None) -> List[Set[str]]:
        return graph_queries.detect_communities(self, method, filters)
