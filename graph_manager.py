"""
Persistence + in-memory graph operations.

GraphManager is the single gateway between the Dash callbacks and the
SQLite store. It handles node/edge CRUD, cascade status updates, cycle
detection, filtering, and priority scoring — and owns the invalidation
counters that let the higher-level callback caches know when to rebuild.
"""

import sqlite3
import time
from collections import deque
from datetime import date
import database
import graph_queries
import graph_scoring
import graph_rules
from graph_repository import GraphRepository
from graph_state import GraphCaches, CacheValue, RevisionValue, revisions
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from config import ConfigManager
from typing import TYPE_CHECKING, List, Dict, Optional, Set, Tuple

if TYPE_CHECKING:
    import networkx as nx


# Fields whose mutation changes a node's priority_score. Anything else
# (description, paths, aliases) is cosmetic
# for scoring purposes and must not invalidate the scoring memo.
# context/subcontext are in the list because they are what a node is
# discounted against for suggestion variety, and they also pick its context
# weight and decide which cascade hops count as cross-context.
# `now` is in the list because Now *membership* changes other nodes' numbers:
# scoring.variety_divisors builds its pool from the non-Now nodes, so flipping
# one both drops its own divisor and stops it charging a repetition against its
# context peers, and get_priority_normalizer takes its max over non-Now nodes.
# Only membership matters, not rank -- reorder_now_nodes writes the rank in raw
# SQL and correctly stays scoring=False.
_SCORING_RELEVANT_FIELDS = frozenset({
    'type', 'value', 'interest', 'difficulty',
    'time_o', 'time_m', 'time_p', 'time_mode',
    'value_mode',
    'status', 'dormant', 'now',
    'context', 'subcontext',
})


def _utc_now_ts() -> int:
    """Current UTC instant as Unix seconds for append-only lifecycle history."""
    return int(time.time())


class GraphManager:
    """Single gateway for all graph state reads and writes.

    Every callback module constructs its own GraphManager instance, but
    the underlying SQLite file and the invalidation version counters are
    shared (class-level) so a mutation in one instance is seen by every
    other instance's cache.
    """
    # Versions are class-level because every GraphManager instance in this
    # codebase (one per callback module) reads the same DB. Per-instance
    # versions would diverge when instance A mutates the DB but instance B's
    # cache only checks its own unchanged counter. Versions only ever advance,
    # so the monotonic contract still holds for cache invalidation.
    _graph_version = RevisionValue("graph")
    _scoring_version = RevisionValue("scoring")
    # Class-level queue of Goal/Milestone names whose hard prereqs just became
    # all Done as a side-effect of an update_node call. Drained by the UI to
    # surface a "Mark Done?" suggestion modal. Class-level (not instance) for
    # the same reason as _graph_version: every GraphManager touches the same
    # DB and needs to see the same pending candidates regardless of which
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

    _community_cache = CacheValue('communities')
    _scoring_memo = CacheValue('scoring_memo')
    _scoring_memo_key = CacheValue('scoring_key')
    _normalizer = CacheValue('normalizer')
    _normalizer_key = CacheValue('normalizer_key')
    _goal_subtree_cache = CacheValue('subtrees')
    _read_cache_epoch = CacheValue('read_epoch')
    _cache_lock = CacheValue('lock')

    def __init__(self):
        self._repository = GraphRepository(lambda: self.get_connection())
        self.caches = GraphCaches()

    def _prepare_read_caches(self):
        epoch = (database.get_db_path(), self._graph_version)
        if epoch != self.caches.read_epoch:
            self.caches.communities.clear()
            self.caches.subtrees.clear()
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

    @database.atomic
    def add_node(self, node: Node):
        """Add a new node to the database."""
        if not node.context:
            raise ValueError(
                f"Node '{node.name}' must have a context. "
                "Uncategorized nodes are no longer permitted."
            )
        self._repository.insert_node(node)
        self._bump_version()

    @database.atomic
    def update_node(self, node: Node):
        """Updates an existing node."""
        if not node.context:
            raise ValueError(
                f"Node '{node.name}' must have a context. "
                "Uncategorized nodes are no longer permitted."
            )
        prior = self.get_node(node.name)
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
        self._repository.write_node(node, lifecycle_event_types, _utc_now_ts)
        self._update_dependent_nodes_state(node.name)
        # Skip scoring-cache invalidation if only cosmetic fields changed.
        # _update_dependent_nodes_state may have touched other nodes' status
        # (a scoring-relevant field), so it sets _scoring_version directly.
        scoring_changed = prior is None or any(
            getattr(prior, f, None) != getattr(node, f, None)
            for f in _SCORING_RELEVANT_FIELDS
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
            # Done node should be a no-op for events. Lazy import to avoid
            # the event_manager ↔ graph_manager circular dependency.
            if prior is None or prior.status != STATUS_DONE:
                try:
                    from event_manager import EventManager
                    EventManager().auto_trigger_by_node_completion(node.name)
                except Exception:
                    # Event-firing must never block a node save. Failures here
                    # are logged but the node update remains committed.
                    import logging
                    logging.getLogger(__name__).exception(
                        "auto_trigger_by_node_completion failed for %s", node.name
                    )
                # Auto-Done suggestion: any direct Hard dependent that is a
                # Goal/Milestone whose prereqs are now ALL Done (and isn't
                # already Done itself) becomes a candidate the UI surfaces
                # via a "Mark Done?" modal. Detection is scoped to true Done
                # transitions so re-saves and graph edits don't spam.
                self._collect_auto_done_candidates(node.name)

        if node.status == STATUS_DONE:
            database.on_commit(completed, key=("completion", node.name))

    def _collect_auto_done_candidates(self, just_done_name: str) -> None:
        """Append direct container dependents of ``just_done_name`` whose
        hard prereqs are now all Done to the class-level candidate queue.

        Eligible dependents: Goals, Milestones, and any node with
        ``time_mode='inherited'`` (its "work" is its descendants' work, so
        when those are Done it should be too).

        Only direct dependents are inspected: a transitive container can't be
        "ready" yet because its own prereq (the direct dependent) is still
        Open/Blocked. If the user marks the direct candidate Done via the
        modal, that update_node call will detect the transitive container.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT n.name, n.type, n.status, n.time_mode FROM Edges e "
                "JOIN Nodes n ON e.target = n.name "
                "WHERE e.source=? AND e.type='Needs_Hard'",
                (just_done_name,),
            )
            dependents = cursor.fetchall()
            for dep_name, dep_type, dep_status, dep_time_mode in dependents:
                if dep_type not in ('Goal', 'Milestone') and dep_time_mode != 'inherited':
                    continue
                if dep_status == STATUS_DONE:
                    continue
                # Verify ALL of dep's hard prereqs are Done.
                cursor.execute(
                    "SELECT n.status FROM Edges e "
                    "JOIN Nodes n ON e.source = n.name "
                    "WHERE e.target=? AND e.type='Needs_Hard'",
                    (dep_name,),
                )
                prereqs = cursor.fetchall()
                if not prereqs:
                    continue  # No prereqs = "all done" is vacuously true; skip
                if any(s != STATUS_DONE for (s,) in prereqs):
                    continue
                if dep_name not in GraphManager._auto_done_candidates:
                    GraphManager._auto_done_candidates.append(dep_name)

    @database.consistent_read
    def pop_auto_done_candidates(self) -> List[str]:
        """Return and clear the queued auto-Done candidate names.

        Caller is the Dash drain callback that pushes pending candidates into
        the editor's modal-trigger store. Each candidate represents a
        Goal/Milestone whose hard prereqs are now all Done — the UI offers
        the user a one-click "Mark Done?" suggestion for it.
        """
        candidates = list(GraphManager._auto_done_candidates)
        GraphManager._auto_done_candidates = []
        return candidates

    @database.atomic
    def delete_node(self, node_name: str):
        """Deletes a node by name.

        Cleans up references that aren't FK-cascaded:
          - `NodeLifecycleEvents` rows ARE FK-cascaded with their node.
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
            self._update_node_state(dept)
        if affected_events:
            ConfigManager.add_pending_event_notification({
                "kind": "trigger_node_deleted",
                "events": affected_events,
                "demoted": demoted,
                "narrowed": narrowed,
                "deleted_node": node_name,
                "when": date.today().isoformat(),
            })
        ConfigManager.delete_node_references(node_name)
        self._bump_version()

    @database.atomic
    def rename_node(self, old_name: str, new_name: str):
        """Rename a node and its SQL/settings references in one transaction."""
        self._repository.rename_node(old_name, new_name)
        ConfigManager.rename_node_references(old_name, new_name)
        self._bump_version()

    def get_node(self, name: str) -> Optional[Node]:
        """Retrieves a specific node by name."""
        return self._repository.get_node(name)

    def get_node_lifecycle_events(self, node_name: str) -> List[dict]:
        """Return one node's lifecycle boundaries in stable occurrence order."""
        return self._repository.get_node_lifecycle_events(node_name)

    def get_aliases(self, node_name: str) -> list:
        """Return all aliases for a node."""
        return self._repository.get_aliases(node_name)

    @database.atomic
    def set_aliases(self, node_name: str, aliases: list):
        """Replace all aliases for a node."""
        from config import ConfigManager
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Aliases WHERE node_name=?", (node_name,))
            for alias in aliases:
                if alias and alias.strip():
                    clean = ConfigManager.apply_name_formatting(alias.strip())
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
    def _canonicalize_edge(source: str, target: str, edge_type: str) -> Tuple[str, str]:
        """Helps is bidirectional: (A,B,Helps) and (B,A,Helps) describe the
        same fact (verified in scoring.build_adjacency, which mirrors Syn for
        either row). Canonicalize so only one row per pair can exist by
        sorting endpoints lexically. Hard/Soft direction is meaningful and
        kept as-is.
        """
        return graph_rules._canonicalize_edge(source, target, edge_type)

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

        source, target = self._canonicalize_edge(source, target, edge_type)

        if edge_type in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
            if self._will_create_cycle(source, target):
                raise ValueError(f"Adding edge {source} -> {target} creates a cycle.")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            for name in (source, target):
                if cursor.execute("SELECT 1 FROM Nodes WHERE name=?", (name,)).fetchone() is None:
                    raise ValueError(f"Cannot link missing node '{name}'.")
            self._check_pair_conflict(cursor, source, target, edge_type)
            cursor.execute("INSERT OR IGNORE INTO Edges (source, target, type) VALUES (?, ?, ?)", (source, target, edge_type))
            changed = cursor.rowcount > 0
            if changed and not _defer_updates and edge_type == EDGE_NEEDS_HARD:
                self._update_node_state(target)
        if changed and not _defer_updates:
            self._bump_version()

    @database.atomic
    def remove_edge(self, source: str, target: str, edge_type: str):
        """Removes a specific edge."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Edges WHERE source=? AND target=? AND type=?", (source, target, edge_type))
            conn.commit()
            if edge_type == EDGE_NEEDS_HARD:
                self._update_node_state(target)
        self._bump_version()

    def get_edges(self) -> List[Dict[str, str]]:
        """Retrieves all edges."""
        return self._repository.get_edges()

    @database.atomic
    def sync_edges(self, node_name: str, needs_hard: list, needs_soft: list, supports_hard: list, supports_soft: list, helps: list):
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
        self._update_node_state(node_name)
        for trgt in set(supports_hard) | set(previous_dependents):
            self._update_node_state(trgt)
        for trgt in supports_soft:
            self._update_node_state(trgt)
        for src in needs_hard:
            self._update_dependent_nodes_state(src)

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
    def _is_prereq_satisfied(p_node) -> bool:
        """Check if a prerequisite node is satisfied (Done)."""
        return graph_rules._is_prereq_satisfied(p_node)

    @database.atomic
    def _update_node_state(self, node_name: str):
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
        status. Caller owns the connection commit.
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

        Walks Hard out-edges transitively from `node_name` and returns every
        Done node found. Used to warn the user before they un-Done a node:
        these are the dependents that will flip Done → Blocked once the
        cascade runs.
        """
        result: List[str] = []
        seen: Set[str] = {node_name}
        stack: List[str] = [node_name]
        with self.get_connection() as conn:
            cursor = conn.cursor()
            while stack:
                current = stack.pop()
                cursor.execute(
                    "SELECT target FROM Edges WHERE source=? AND type='Needs_Hard'",
                    (current,),
                )
                for (target,) in cursor.fetchall():
                    if target in seen:
                        continue
                    seen.add(target)
                    target_node = self.get_node(target)
                    if target_node and target_node.status == STATUS_DONE:
                        result.append(target)
                    stack.append(target)
        return result

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
        asymmetric state.
        """
        import logging
        logger = logging.getLogger(__name__)

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
            if derived[name] == STATUS_DONE and not is_blocked:
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
            with self.get_connection() as conn:            # connection 3
                conn.executemany(
                    "UPDATE Nodes SET status=? WHERE name=?",
                    [(derived[name], name) for name in changed_names],
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
        do not need re-walking. Invalidated only when _scoring_version
        advances (a scoring-relevant node/edge mutation) or a TV-affecting
        hyperparam changes. Cost params (w_e, w_t, beta), goal_boost, and the
        context-adjustment params (alpha, context_weights) don't affect the
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

    def get_directly_unlocked_nodes(self, node_name: str) -> List[str]:
        return graph_queries.get_directly_unlocked_nodes(self, node_name)

    def get_directly_unlocked_nodes_by_type(self, node_name: str) -> Dict[str, List[str]]:
        """Returns nodes directly unlocked by completing this node, separated by edge type."""
        return graph_queries.get_directly_unlocked_nodes_by_type(self, node_name)

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

        For nodes with time_mode='manual', returns the PERT-computed time
        from the node's own time_o/m/p values.

        For nodes with time_mode='inherited', sums the PERT-computed times
        of all incomplete nodes in the node's dependency subtree, treating
        the node itself as a container with zero direct time.

        Returns:
            Time in hours.
        """
        return graph_queries.get_effective_time(self, node_name)

    def filter_nodes(self, nodes: List[Node], filters: Dict) -> List[Node]:
        return graph_queries.filter_nodes(self, nodes, filters)

    def get_prerequisite_chains(self, target_name: str) -> List[List[str]]:
        return graph_queries.get_prerequisite_chains(self, target_name)

    def get_prerequisite_chains_typed(self, target_name: str) -> List[tuple]:
        """Returns prerequisite chains classified as 'Hard' or 'Soft'.

        Each result is (chain, type_str) where type_str is 'Hard' if all edges
        in the chain are Needs_Hard, else 'Soft'.
        """
        return graph_queries.get_prerequisite_chains_typed(self, target_name)

    def _build_nx_graph(self, allowed_names: Optional[Set[str]] = None) -> "nx.Graph":
        return graph_queries._build_nx_graph(self, allowed_names)

    # --- Migration ---

    def find_orphaned_nodes(self, field: str, old_values: list, new_values: list) -> Dict[str, List[Node]]:
        """Find nodes that reference removed values for a given field.

        Returns a dict mapping each removed value to the list of nodes that still reference it.
        Only includes entries where at least one node is affected.

        Includes dormant nodes — they reference config values too, and silently
        leaving them out means a context/type/subcontext can be deleted while
        dormant nodes still hold the stale value, only surfacing as broken
        config when the event later triggers them back into play.
        """
        removed = set(old_values) - set(new_values)
        if not removed:
            return {}

        all_nodes = self.get_all_nodes(include_dormant=True)
        orphans = {}
        for val in removed:
            affected = [n for n in all_nodes if getattr(n, field, None) == val]
            if affected:
                orphans[val] = affected
        return orphans

    def find_nodes_by_pairs(self, pairs) -> Dict[str, List[Node]]:
        """Group nodes by the (context, subcontext) pairs they still reference.

        Keyed by 'ctx > sub' display labels, and only for pairs that actually
        hold nodes. Includes dormant nodes — see find_orphaned_nodes.
        """
        pairs = [tuple(p) for p in pairs or []]
        if not pairs:
            return {}

        all_nodes = self.get_all_nodes(include_dormant=True)
        found = {}
        for ctx, sub in pairs:
            affected = [n for n in all_nodes if n.context == ctx and n.subcontext == sub]
            if affected:
                found[f"{ctx} > {sub}"] = affected
        return found

    def find_orphaned_subcontext_pairs(self, old_subcontexts: Dict, new_subcontexts: Dict,
                                       new_contexts: list) -> Dict[str, List[Node]]:
        """Find nodes whose (context, subcontext) pair no longer exists in the new structure.

        Subcontext identity is the (context, subcontext) tuple, not the bare name —
        moving a subcontext between parents leaves the bare name in the flat list but
        invalidates the pair. Returns a dict keyed by 'ctx > sub' display labels.

        This compares taxonomies by name. The Contexts editor tracks each row's
        origin instead, so it names the dropped pairs itself and calls
        find_nodes_by_pairs directly.
        """
        from context_rules import compute_orphaned_subcontext_pairs
        pairs = compute_orphaned_subcontext_pairs(old_subcontexts, new_subcontexts, new_contexts)
        return self.find_nodes_by_pairs(pairs)

    def count_nodes_by_context(self):
        """Return ({context: n}, {(context, subcontext): n}) across every node.

        Feeds the blast-radius counts in the Contexts editor, so it counts
        dormant nodes too: they hold config values just the same, and a
        deletion strands them just the same.
        """
        ctx_counts: Dict[str, int] = {}
        pair_counts: Dict[tuple, int] = {}
        for node in self.get_all_nodes(include_dormant=True):
            if not node.context:
                continue
            ctx_counts[node.context] = ctx_counts.get(node.context, 0) + 1
            if node.subcontext:
                key = (node.context, node.subcontext)
                pair_counts[key] = pair_counts.get(key, 0) + 1
        return ctx_counts, pair_counts

    @database.atomic
    def apply_taxonomy_migration(self, ctx_renames: Dict[str, str],
                                 pair_moves) -> None:
        """Carry context renames and (context, subcontext) moves onto the nodes.

        Pair moves run first, while the rows still hold their original values;
        the context renames that follow then only reach the nodes no pair move
        claimed — those with no subcontext, or with one being dropped. Doing it
        the other way round would leave a renamed context's pairs unmatchable.
        """
        pair_moves = [tuple(m) for m in pair_moves or []]
        if not ctx_renames and not pair_moves:
            return

        with self.get_connection() as conn:
            cursor = conn.cursor()
            for old_ctx, old_sub, new_ctx, new_sub in pair_moves:
                cursor.execute(
                    "UPDATE Nodes SET context=?, subcontext=? "
                    "WHERE context=? AND subcontext=?",
                    (new_ctx, new_sub, old_ctx, old_sub),
                )
            for old_ctx, new_ctx in (ctx_renames or {}).items():
                cursor.execute("UPDATE Nodes SET context=? WHERE context=?",
                               (new_ctx, old_ctx))
            conn.commit()
        self._bump_version(scoring=True)

    @database.atomic
    def apply_migration(self, field: str, remap: Dict[str, str], new_subcontexts: Optional[Dict] = None):
        """Remap node attribute values in bulk.

        Args:
            field: 'context', 'subcontext', or 'type'
            remap: maps old_value -> new_value (or None to clear)
            new_subcontexts: when field is 'context', used to check if subcontexts are still valid
        """
        if not remap:
            return

        with self.get_connection() as conn:
            cursor = conn.cursor()
            for old_val, new_val in remap.items():
                if new_val == '__clear__':
                    new_val = None

                # Apply the remap
                cursor.execute(f"UPDATE Nodes SET [{field}]=? WHERE [{field}]=?", (new_val, old_val))

                # When context changes, clear subcontexts that don't exist under the new context
                if field == 'context' and new_val is not None and new_subcontexts is not None:
                    valid_subs = set(new_subcontexts.get(new_val, []))
                    if valid_subs:
                        # Clear subcontext if it's not valid under the new context
                        cursor.execute(
                            "SELECT name, subcontext FROM Nodes WHERE context=? AND subcontext IS NOT NULL",
                            (new_val,)
                        )
                        for name, sub in cursor.fetchall():
                            if sub not in valid_subs:
                                cursor.execute("UPDATE Nodes SET subcontext=NULL WHERE name=?", (name,))
                    else:
                        # New context has no subcontexts — clear them all
                        cursor.execute("UPDATE Nodes SET subcontext=NULL WHERE context=?", (new_val,))

            conn.commit()
        # Every field these migrations accept (context / subcontext / type) is
        # scoring-relevant, so a bulk remap must invalidate the scoring caches.
        # Keying off the field set keeps this honest if the accepted fields grow.
        self._bump_version(scoring=field in _SCORING_RELEVANT_FIELDS)
        if field == 'type':
            self.recompute_all_statuses()

    @database.atomic
    def apply_node_migration(self, node_name: str, field: str, new_val: str,
                             new_subcontexts: Optional[Dict] = None):
        """Remap a single node's attribute value.

        Args:
            node_name: name (primary key) of the node to update
            field: 'context', 'subcontext', or 'type'
            new_val: the new value, or '__clear__' to set NULL
            new_subcontexts: when field is 'context', used to check if subcontexts are still valid
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            actual_val = None if new_val == '__clear__' else new_val

            cursor.execute(f"UPDATE Nodes SET [{field}]=? WHERE name=?", (actual_val, node_name))

            # When context changes, clear subcontext if invalid under the new context
            if field == 'context' and actual_val is not None and new_subcontexts is not None:
                valid_subs = set(new_subcontexts.get(actual_val, []))
                cursor.execute("SELECT subcontext FROM Nodes WHERE name=?", (node_name,))
                row = cursor.fetchone()
                if row and row[0] and row[0] not in valid_subs:
                    cursor.execute("UPDATE Nodes SET subcontext=NULL WHERE name=?", (node_name,))

            conn.commit()
        # Every field these migrations accept (context / subcontext / type) is
        # scoring-relevant, so a bulk remap must invalidate the scoring caches.
        # Keying off the field set keeps this honest if the accepted fields grow.
        self._bump_version(scoring=field in _SCORING_RELEVANT_FIELDS)
        if field == 'type':
            self.recompute_all_statuses()

    def name_community(self, community: Set[str]) -> str:
        """Generate a descriptive name for a community based on member node attributes.

        Strategy (in priority order):
        1. If a dominant context covers >=50% of nodes, use it.
           - If a subcontext also dominates within that context, append it.
        2. Otherwise, if a dominant node type covers >=60%, use it as the label.
        3. Otherwise, find the most frequent meaningful word across node names.
        """
        return graph_queries.name_community(self, community)

    @database.consistent_read
    def detect_communities(self, method: str = "components", filters: Optional[Dict] = None) -> List[Set[str]]:
        return graph_queries.detect_communities(self, method, filters)
