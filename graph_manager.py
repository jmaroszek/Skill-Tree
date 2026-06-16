"""
Persistence + in-memory graph operations.

GraphManager is the single gateway between the Dash callbacks and the
SQLite store. It handles node/edge CRUD, cascade status updates, cycle
detection, filtering, and priority scoring — and owns the invalidation
counters that let the higher-level callback caches know when to rebuild.
"""

import sqlite3
import threading
from datetime import date
import database
import networkx as nx
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from config import ConfigManager
from scoring import score_nodes
from typing import List, Dict, Optional, Set, Tuple


# Fields whose mutation changes a node's priority_score. Anything else
# (description, paths, context, aliases) is cosmetic
# for scoring purposes and must not invalidate the scoring memo.
_SCORING_RELEVANT_FIELDS = frozenset({
    'type', 'value', 'interest', 'difficulty',
    'time_o', 'time_m', 'time_p', 'time_mode',
    'value_mode',
    'status', 'dormant',
})


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
    _graph_version: int = 0
    _scoring_version: int = 0
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

    def __init__(self):
        database.init_db()
        self._community_cache: Dict[tuple, List[Set[str]]] = {}
        self._scoring_memo: Dict[str, float] = {}
        self._scoring_memo_key: Optional[tuple] = None
        # (goal_name, sorted_edge_types_tuple) -> (graph_version, frozenset of reachable nodes)
        self._goal_subtree_cache: Dict[tuple, tuple] = {}
        self._cache_lock = threading.Lock()

    def _bump_version(self, scoring: bool = True) -> None:
        """Invalidate memoization caches. Called by every node/edge mutator.

        Pass scoring=False for cosmetic-only node edits (e.g. description,
        tags, paths) — graph_version still bumps so UI re-renders, but the
        scoring memo stays valid and the next get_suggestions() is near-free.
        """
        GraphManager._graph_version += 1
        if scoring:
            GraphManager._scoring_version += 1

    def get_connection(self) -> sqlite3.Connection:
        """Returns a new database connection with foreign keys enabled."""
        return database.get_connection()

    # --- Node Operations ---

    def add_node(self, node: Node):
        """Add a new node to the database."""
        if not node.context:
            raise ValueError(
                f"Node '{node.name}' must have a context. "
                "Uncategorized nodes are no longer permitted."
            )
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                data = node.to_dict()
                data.pop('priority_score', None)
                data.pop('time', None)  # time is a computed property
                cursor.execute('''
                    INSERT INTO Nodes (name, type, description, value, time_o, time_m, time_p, interest, difficulty, context, subcontext, status, obsidian_path, google_drive_path, website, dormant, time_mode, value_mode, habit_duration, habit_duration_unit, habit_intensity_o, habit_intensity_m, habit_intensity_p, habit_intensity_unit, habit_days, actual_time_lower, actual_time_upper, actual_time_point, actual_time_unit, calibration_dismissed, "now", start_date, done_date, reflect_value, reflect_interest, reflect_difficulty)
                    VALUES (:name, :type, :description, :value, :time_o, :time_m, :time_p, :interest, :difficulty, :context, :subcontext, :status, :obsidian_path, :google_drive_path, :website, :dormant, :time_mode, :value_mode, :habit_duration, :habit_duration_unit, :habit_intensity_o, :habit_intensity_m, :habit_intensity_p, :habit_intensity_unit, :habit_days, :actual_time_lower, :actual_time_upper, :actual_time_point, :actual_time_unit, :calibration_dismissed, :now, :start_date, :done_date, :reflect_value, :reflect_interest, :reflect_difficulty)
                ''', data)
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Node with name '{node.name}' already exists.")
        self._bump_version()

    def update_node(self, node: Node):
        """Updates an existing node."""
        if not node.context:
            raise ValueError(
                f"Node '{node.name}' must have a context. "
                "Uncategorized nodes are no longer permitted."
            )
        prior = self.get_node(node.name)
        # --- Auto-stamp lifecycle dates and clear Now on completion ---
        # start_date is refreshed to today on every fresh off→on Now flip, so
        # re-engaging a node after a gap anchors the time estimate to the most
        # recent work session rather than a stale first-ever flip. Turning Now
        # *off* deliberately leaves start_date intact — otherwise toggling off
        # and immediately marking Done would lose the anchor and record no
        # elapsed time. done_date is stamped on each fresh Open/Blocked→Done
        # transition. When the user marks the node Done while it is currently
        # flagged Now, we clear the flag automatically (the user's mental
        # model: Now until Done). Reverting Done→Open/Blocked clears done_date
        # so the next completion re-stamps with the real date rather than
        # keeping the first one.
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
                    obsidian_path=:obsidian_path, google_drive_path=:google_drive_path,
                    website=:website,
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
            conn.commit()
            self._update_dependent_nodes_state(node.name)
        # Skip scoring-cache invalidation if only cosmetic fields changed.
        # _update_dependent_nodes_state may have touched other nodes' status
        # (a scoring-relevant field), so it sets _scoring_version directly.
        scoring_changed = prior is None or any(
            getattr(prior, f, None) != getattr(node, f, None)
            for f in _SCORING_RELEVANT_FIELDS
        )
        self._bump_version(scoring=scoring_changed)
        # If this update flipped the node to Done and it was the System A
        # override parent, clear the override — the boost on its dependents
        # is no longer meaningful. Done is only ever set here (the cascade
        # in _update_dependent_nodes_state only flips Blocked/Open).
        if node.status == STATUS_DONE:
            ConfigManager.clear_override_if_parent(node.name)
            # Fire any event whose trigger_node matches this name, but only
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

    def delete_node(self, node_name: str):
        """Deletes a node by name.

        Cleans up references that aren't FK-cascaded:
          - `Events.trigger_node` is plain TEXT (no FK) — NULLed in-place so
            those events demote to manual-trigger instead of orphaning their
            dormant nodes forever. Affected event names are queued as a
            one-shot announcement so the user sees the demotion.
          - Config-side references (priority_goals, override.parent,
            event_override_nodes) — delegated to
            ConfigManager.delete_node_references, mirroring how
            rename_node delegates to rename_node_references.
        """
        from datetime import date
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Find dependents before deleting edges so we can recalculate their state
            cursor.execute("SELECT target FROM Edges WHERE source=? AND type='Needs_Hard'", (node_name,))
            dependents = [row[0] for row in cursor.fetchall()]
            # Snapshot affected events before NULLing trigger_node so the
            # notification can name them.
            cursor.execute(
                "SELECT name FROM Events WHERE trigger_node=? AND status='Pending'",
                (node_name,),
            )
            affected_events = [row[0] for row in cursor.fetchall()]
            if affected_events:
                cursor.execute(
                    "UPDATE Events SET trigger_node=NULL WHERE trigger_node=?",
                    (node_name,),
                )
            cursor.execute("DELETE FROM Edges WHERE source=? OR target=?", (node_name, node_name))
            cursor.execute("DELETE FROM Nodes WHERE name=?", (node_name,))
            conn.commit()
        for dept in dependents:
            self._update_node_state(dept)
        if affected_events:
            ConfigManager.add_pending_event_notification({
                "kind": "trigger_node_deleted",
                "events": affected_events,
                "deleted_node": node_name,
                "when": date.today().isoformat(),
            })
        ConfigManager.delete_node_references(node_name)
        self._bump_version()

    def rename_node(self, old_name: str, new_name: str):
        """Renames a node, updating all edge and event references atomically.

        FKs are temporarily disabled so the Nodes row can be renamed before
        Edges/Events/EventNodes/Aliases catch up. The whole sequence runs in
        an explicit transaction; any error rolls back to the pre-rename state
        so a partial rename can never be left in the DB. The PRAGMA reset is
        in a finally so FKs are restored even on failure.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = OFF")
            try:
                cursor.execute("BEGIN")
                cursor.execute("UPDATE Nodes SET name=? WHERE name=?", (new_name, old_name))
                cursor.execute("UPDATE Edges SET source=? WHERE source=?", (new_name, old_name))
                cursor.execute("UPDATE Edges SET target=? WHERE target=?", (new_name, old_name))
                # Update event trigger_node references
                cursor.execute("UPDATE Events SET trigger_node=? WHERE trigger_node=?", (new_name, old_name))
                # Also update EventNodes mapping table
                cursor.execute("UPDATE EventNodes SET node_name=? WHERE node_name=?", (new_name, old_name))
                # Update Aliases table
                cursor.execute("UPDATE Aliases SET node_name=? WHERE node_name=?", (new_name, old_name))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.execute("PRAGMA foreign_keys = ON")
        ConfigManager.rename_node_references(old_name, new_name)
        self._bump_version()

    def get_node(self, name: str) -> Optional[Node]:
        """Retrieves a specific node by name."""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Nodes WHERE name=?", (name,))
            row = cursor.fetchone()
            if row:
                return Node(**dict(row))
            return None

    def get_aliases(self, node_name: str) -> list:
        """Return all aliases for a node."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT alias FROM Aliases WHERE node_name=?", (node_name,))
            return [row[0] for row in cursor.fetchall()]

    def set_aliases(self, node_name: str, aliases: list):
        """Replace all aliases for a node."""
        from config import ConfigManager
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Aliases WHERE node_name=?", (node_name,))
            for alias in aliases:
                if alias and alias.strip():
                    clean = ConfigManager.apply_titlecase_linter(alias.strip())
                    cursor.execute(
                        "INSERT OR IGNORE INTO Aliases (alias, node_name) VALUES (?, ?)",
                        (clean, node_name))
            conn.commit()

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
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if include_dormant:
                cursor.execute("SELECT * FROM Nodes")
            else:
                cursor.execute("SELECT * FROM Nodes WHERE dormant = 0")
            return [Node(**dict(row)) for row in cursor.fetchall()]

    def get_now_nodes(self) -> List[Node]:
        """Return all nodes flagged Now (currently being worked on).

        Dormant nodes are excluded — a shelved node should not also be
        "currently being worked on", and the Now section should never
        surface one.
        """
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM Nodes WHERE "now" > 0 AND dormant = 0 ORDER BY "now" ASC, name ASC')
            return [Node(**dict(row)) for row in cursor.fetchall()]

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
        if edge_type == EDGE_HELPS and source > target:
            return target, source
        return source, target

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

    def add_edge(self, source: str, target: str, edge_type: str):
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
            self._check_pair_conflict(cursor, source, target, edge_type)
            try:
                cursor.execute("INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)", (source, target, edge_type))
                conn.commit()
                if edge_type == EDGE_NEEDS_HARD:
                    self._update_node_state(target)
            except sqlite3.IntegrityError:
                pass  # Exact duplicate row — silently no-op
        self._bump_version()

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
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Edges")
            return [dict(row) for row in cursor.fetchall()]

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

            # Clear existing edges whose other endpoint is non-dormant. The
            # editor's edge dropdowns hide dormant nodes, so callers always
            # pass `needs_*` / `supports_*` / `helps` lists with dormant
            # entries already filtered out. Deleting dormant edges here would
            # silently drop them (the INSERT loop below can't re-add them
            # because they're not in the input lists), corrupting the graph
            # on every save of a node that has dormant relationships.
            cursor.execute(
                """DELETE FROM Edges
                   WHERE target=? AND type IN ('Needs_Hard', 'Needs_Soft')
                     AND source IN (SELECT name FROM Nodes WHERE dormant = 0)""",
                (node_name,),
            )
            cursor.execute(
                """DELETE FROM Edges
                   WHERE source=? AND type IN ('Needs_Hard', 'Needs_Soft')
                     AND target IN (SELECT name FROM Nodes WHERE dormant = 0)""",
                (node_name,),
            )
            cursor.execute(
                """DELETE FROM Edges
                   WHERE type = 'Helps'
                     AND ((target = ? AND source IN (SELECT name FROM Nodes WHERE dormant = 0))
                       OR (source = ? AND target IN (SELECT name FROM Nodes WHERE dormant = 0)))""",
                (node_name, node_name),
            )

            def _insert_edge(src, trgt, etype):
                src, trgt = self._canonicalize_edge(src, trgt, etype)
                if etype in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT) and self._will_create_cycle(src, trgt):
                    return
                # Pair-conflict against surviving (dormant-anchored) edges
                # — silently skip rather than raise, since the form-level
                # validation above already caught intra-form conflicts and
                # this would only fire on edges to dormant nodes the user
                # can't see.
                try:
                    self._check_pair_conflict(cursor, src, trgt, etype)
                except ValueError:
                    return
                try:
                    cursor.execute("INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)", (src, trgt, etype))
                except sqlite3.IntegrityError:
                    pass

            for src in needs_hard: _insert_edge(src, node_name, EDGE_NEEDS_HARD)
            for src in needs_soft: _insert_edge(src, node_name, EDGE_NEEDS_SOFT)

            for trgt in supports_hard: _insert_edge(node_name, trgt, EDGE_NEEDS_HARD)
            for trgt in supports_soft: _insert_edge(node_name, trgt, EDGE_NEEDS_SOFT)

            for linked in helps: _insert_edge(node_name, linked, EDGE_HELPS)

            conn.commit()

        # Recalculate state for the saved node and all nodes affected by its edges
        self._update_node_state(node_name)
        for trgt in supports_hard:
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
        if not p_node:
            return False
        return p_node.status == STATUS_DONE

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
        queue: List[str] = list(seeds)
        seen: Set[str] = set()
        while queue:
            node_name = queue.pop(0)
            if node_name in seen:
                continue
            seen.add(node_name)

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
                "UPDATE Nodes SET status=? WHERE name=?", (new_status, node_name),
            )
            cursor.execute(
                "SELECT target FROM Edges WHERE source=? AND type='Needs_Hard'",
                (node_name,),
            )
            for (dependent,) in cursor.fetchall():
                if dependent not in seen:
                    queue.append(dependent)

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

    def calculate_priority_scores(self, now_nodes: List[Node], priority_goals: Optional[List[str]] = None) -> List[Node]:
        """Delegates scoring to the scoring module.

        Reuses a per-manager total_value memo across calls: a filter toggle,
        priority-goal change, or cosmetic edit (description, tags, paths)
        doesn't alter scoring inputs, so the expensive recursive cascade
        doesn't need re-walking. Invalidated only when _scoring_version
        advances (a scoring-relevant node/edge mutation) or a TV-affecting
        hyperparam changes. Cost params (w_e, w_t, beta), goal_boost, and the
        context-adjustment params (alpha, context_weights) don't affect the
        cached TV cascade, so they are excluded from the key.
        """
        hypers = ConfigManager.get_hyperparams()
        hypers['context_weights'] = ConfigManager.get_context_weights()
        TV_AFFECTING_KEYS = ('w_v', 'w_i', 'd_H', 'd_S', 'd_Syn_pair', 'd_Syn_mul',
                             'cross_context_mult')
        hypers_key = tuple((k, hypers.get(k)) for k in TV_AFFECTING_KEYS)
        cache_key = (self._scoring_version, hypers_key)
        with self._cache_lock:
            if cache_key != self._scoring_memo_key:
                self._scoring_memo = {}
                self._scoring_memo_key = cache_key
            memo = self._scoring_memo

        if ConfigManager.get_show_scoring_perf() and not GraphManager._startup_perf_recorded:
            from perf import append_perf_log
            scored, timings = score_nodes(
                now_nodes, self.get_all_nodes(),
                self.get_edges(), hypers,
                priority_goals=priority_goals,
                external_memo=memo,
                time_phases=True,
            )
            GraphManager._last_perf_timings = timings
            GraphManager._startup_perf_recorded = True
            append_perf_log(timings)
            return scored

        return score_nodes(
            now_nodes, self.get_all_nodes(),
            self.get_edges(), hypers,
            priority_goals=priority_goals,
            external_memo=memo,
        )

    def get_directly_unlocked_nodes(self, node_name: str) -> List[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT target FROM Edges
                JOIN Nodes ON Edges.target = Nodes.name
                WHERE source=? AND Edges.type='Needs_Hard' AND Nodes.status=?
            ''', (node_name, STATUS_BLOCKED))
            return [row[0] for row in cursor.fetchall()]

    def get_directly_unlocked_nodes_by_type(self, node_name: str) -> Dict[str, List[str]]:
        """Returns nodes directly unlocked by completing this node, separated by edge type."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT target, Edges.type FROM Edges
                JOIN Nodes ON Edges.target = Nodes.name
                WHERE source=? AND Edges.type IN ('Needs_Hard', 'Needs_Soft')
                AND Nodes.status IN (?, ?)
            ''', (node_name, STATUS_BLOCKED, STATUS_OPEN))
            hard, soft = [], []
            for row in cursor.fetchall():
                if row[1] == 'Needs_Hard':
                    hard.append(row[0])
                else:
                    soft.append(row[0])
            return {'hard': hard, 'soft': soft}

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
        if edge_types is None:
            edge_types = (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT)

        # Cache lookup: select_detail_node alone calls this 4x per invocation
        # with overlapping (goal, edge_types) combinations. Without caching
        # each call re-runs the BFS + DB queries against an unchanged graph.
        cache_key = (goal_name, tuple(sorted(edge_types)))
        with self._cache_lock:
            cached = self._goal_subtree_cache.get(cache_key)
            if cached is not None and cached[0] == self._graph_version:
                return set(cached[1])

        # Separate directed and bidirectional edge types
        directed_types = tuple(t for t in edge_types if t != EDGE_HELPS)
        include_helps = EDGE_HELPS in edge_types

        with self.get_connection() as conn:
            cursor = conn.cursor()
            visited = set()
            queue = []

            # Seed with direct prerequisites of the goal (directed edges)
            if directed_types:
                placeholders = ','.join('?' for _ in directed_types)
                cursor.execute(
                    f"SELECT source FROM Edges WHERE target=? AND type IN ({placeholders})",
                    (goal_name, *directed_types)
                )
                queue.extend(row[0] for row in cursor.fetchall())

            # Seed with Helps partners of the goal (bidirectional, 1 step only)
            if include_helps:
                cursor.execute(
                    "SELECT source FROM Edges WHERE target=? AND type=?",
                    (goal_name, EDGE_HELPS)
                )
                queue.extend(row[0] for row in cursor.fetchall())
                cursor.execute(
                    "SELECT target FROM Edges WHERE source=? AND type=?",
                    (goal_name, EDGE_HELPS)
                )
                queue.extend(row[0] for row in cursor.fetchall())

            while queue:
                node = queue.pop()
                if node in visited:
                    continue
                visited.add(node)

                # Only directed edges are followed during BFS — Helps does not
                # chain past the seed step.
                if directed_types:
                    placeholders = ','.join('?' for _ in directed_types)
                    cursor.execute(
                        f"SELECT source FROM Edges WHERE target=? AND type IN ({placeholders})",
                        (node, *directed_types)
                    )
                    for row in cursor.fetchall():
                        if row[0] not in visited:
                            queue.append(row[0])

        with self._cache_lock:
            self._goal_subtree_cache[cache_key] = (self._graph_version, frozenset(visited))
        return visited

    def get_goal_completion(self, goal_name: str, include_soft: bool = True, include_transitive: bool = True) -> dict:
        """Returns completion stats for a goal based on its subtree.

        Args:
            include_soft: If False, only traverse hard-need edges.
            include_transitive: If False, only count direct children of the goal.

        Returns dict with: total, done, pct, remaining_time
        """
        edge_types = (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT) if include_soft else (EDGE_NEEDS_HARD,)
        subtree = self.get_goal_subtree(goal_name, edge_types=edge_types)
        if include_transitive is False:
            # Restrict to direct children only
            with self.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ','.join('?' for _ in edge_types)
                cursor.execute(
                    f"SELECT source FROM Edges WHERE target=? AND type IN ({placeholders})",
                    (goal_name, *edge_types)
                )
                direct = {row[0] for row in cursor.fetchall()}
            subtree = subtree & direct
        if not subtree:
            return {"total": 0, "done": 0, "pct": 0, "remaining_time": 0.0}

        nodes = [self.get_node(name) for name in subtree]
        nodes = [n for n in nodes if n is not None]
        total = len(nodes)
        done = sum(1 for n in nodes if n.status == STATUS_DONE)
        blocked = sum(1 for n in nodes if n.status == STATUS_BLOCKED)
        remaining_time = sum(n.time for n in nodes if n.status != STATUS_DONE)
        pct = round(done / total * 100) if total > 0 else 0
        
        # A goal is considered blocked if ALL of its remaining subtasks are blocked
        is_blocked = (done + blocked == total) and (blocked > 0)

        return {"total": total, "done": done, "pct": pct, "remaining_time": round(remaining_time, 1), "is_blocked": is_blocked}

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
        node = self.get_node(node_name)
        if not node:
            return 0.0

        if node.time_mode != 'inherited':
            return node.time

        # Inherited mode: sum subtree times
        subtree = self.get_goal_subtree(node_name)
        total = 0.0
        for name in subtree:
            child = self.get_node(name)
            if child and child.status != STATUS_DONE:
                total += child.time
        return round(total, 2)

    def filter_nodes(self, nodes: List[Node], filters: Dict) -> List[Node]:
        result = nodes

        # Dormant gate: hide dormant nodes unless the show_dormant filter is on.
        # Single point of dormant inclusion/exclusion for the whole filter
        # pipeline — generate_elements always fetches with include_dormant=True
        # and lets this gate decide.
        if not filters.get('show_dormant'):
            result = [n for n in result if not n.dormant]

        if 'context_subcontext_union' in filters:
            # Selective union: each pair is (context, subcontexts_or_None).
            # None means no subcontext restriction for that context.
            allowed: Set[str] = set()
            for ctx, subs in filters['context_subcontext_union']:
                if subs is None:
                    allowed.update(n.name for n in result if n.context == ctx)
                else:
                    allowed.update(n.name for n in result if n.context == ctx and n.subcontext in subs)
            result = [n for n in result if n.name in allowed]
        else:
            if 'context' in filters:
                ctx = filters['context']
                if isinstance(ctx, list):
                    result = [n for n in result if n.context in ctx]
                else:
                    result = [n for n in result if n.context == ctx]

            if 'subcontext' in filters:
                sub = filters['subcontext']
                if isinstance(sub, list):
                    result = [n for n in result if n.subcontext in sub]
                else:
                    result = [n for n in result if n.subcontext == sub]

        if 'min_value' in filters:
            result = [n for n in result if n.value >= int(filters['min_value'])]

        if 'min_interest' in filters:
            result = [n for n in result if n.interest >= int(filters['min_interest'])]

        if 'max_time' in filters:
            result = [n for n in result if getattr(n, 'time', 1.0) <= float(filters['max_time'])]

        if 'max_difficulty' in filters:
            result = [n for n in result if n.difficulty <= int(filters['max_difficulty'])]

        if 'node_types' in filters:
            result = [n for n in result if n.type in filters['node_types']]

        if 'hide_done' in filters and filters['hide_done']:
            result = [n for n in result if n.status != STATUS_DONE]

        if 'hide_blocked' in filters and filters['hide_blocked']:
            result = [n for n in result if n.status != STATUS_BLOCKED]

        if 'search' in filters and filters['search']:
            search_val = filters['search'].lower()
            result = [n for n in result if search_val in n.name.lower()]

        return result

    def get_prerequisite_chains(self, target_name: str) -> List[List[str]]:
        target_node = self.get_node(target_name)
        if not target_node:
            return []

        chains = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, status FROM Nodes")
            status_lookup = {row[0]: row[1] for row in cursor.fetchall()}

            def dfs(current_path):
                curr_node = current_path[-1]
                cursor.execute("SELECT source FROM Edges WHERE target=? AND type IN ('Needs_Hard', 'Needs_Soft')", (curr_node,))
                prereqs = [row[0] for row in cursor.fetchall()]

                if not prereqs:
                    has_incomplete = any(
                        status_lookup.get(p, STATUS_OPEN) != STATUS_DONE
                        for p in current_path
                    )
                    if has_incomplete:
                        chains.append(list(reversed(current_path)))
                    return

                for prereq in prereqs:
                    if prereq not in current_path:
                        dfs(current_path + [prereq])

            dfs([target_name])

        return chains

    def get_prerequisite_chains_typed(self, target_name: str) -> List[tuple]:
        """Returns prerequisite chains classified as 'Hard' or 'Soft'.

        Each result is (chain, type_str) where type_str is 'Hard' if all edges
        in the chain are Needs_Hard, else 'Soft'.
        """
        target_node = self.get_node(target_name)
        if not target_node:
            return []

        typed_chains = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, status FROM Nodes")
            status_lookup = {row[0]: row[1] for row in cursor.fetchall()}

            def dfs(current_path, has_soft):
                curr_node = current_path[-1]
                cursor.execute(
                    "SELECT source, type FROM Edges WHERE target=? AND type IN ('Needs_Hard', 'Needs_Soft')",
                    (curr_node,))
                prereqs = cursor.fetchall()

                if not prereqs:
                    has_incomplete = any(
                        status_lookup.get(p, STATUS_OPEN) != STATUS_DONE
                        for p in current_path
                    )
                    if has_incomplete:
                        chain = list(reversed(current_path))
                        typed_chains.append((chain, "Soft" if has_soft else "Hard"))
                    return

                for prereq_name, edge_type in prereqs:
                    if prereq_name not in current_path:
                        dfs(current_path + [prereq_name],
                            has_soft or edge_type == 'Needs_Soft')

            dfs([target_name], False)

        return typed_chains

    def _build_nx_graph(self, allowed_names: Optional[Set[str]] = None) -> nx.Graph:
        G = nx.Graph()
        nodes = self.get_all_nodes()
        edges = self.get_edges()
        for n in nodes:
            if allowed_names is None or n.name in allowed_names:
                G.add_node(n.name)
        for e in edges:
            if e['source'] in G.nodes and e['target'] in G.nodes:
                G.add_edge(e['source'], e['target'])
        return G

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

    def find_orphaned_subcontext_pairs(self, old_subcontexts: Dict, new_subcontexts: Dict,
                                       new_contexts: list) -> Dict[str, List[Node]]:
        """Find nodes whose (context, subcontext) pair no longer exists in the new structure.

        Subcontext identity is the (context, subcontext) tuple, not the bare name —
        moving a subcontext between parents leaves the bare name in the flat list but
        invalidates the pair. Returns a dict keyed by 'ctx › sub' display labels.

        Includes dormant nodes for the same reason as find_orphaned_nodes: their
        stale (context, subcontext) pair would survive a config delete and only
        manifest as a broken reference at event-trigger time.
        """
        from callback_helpers import compute_orphaned_subcontext_pairs
        pairs = compute_orphaned_subcontext_pairs(old_subcontexts, new_subcontexts, new_contexts)
        if not pairs:
            return {}

        all_nodes = self.get_all_nodes(include_dormant=True)
        orphans = {}
        for ctx, sub in pairs:
            affected = [n for n in all_nodes if n.context == ctx and n.subcontext == sub]
            if affected:
                orphans[f"{ctx} › {sub}"] = affected
        return orphans

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

    def name_community(self, community: Set[str]) -> str:
        """Generate a descriptive name for a community based on member node attributes.

        Strategy (in priority order):
        1. If a dominant context covers >=50% of nodes, use it.
           - If a subcontext also dominates within that context, append it.
        2. Otherwise, if a dominant node type covers >=60%, use it as the label.
        3. Otherwise, find the most frequent meaningful word across node names.
        """
        if not community:
            return "Empty"

        nodes = [self.get_node(name) for name in community]
        nodes = [n for n in nodes if n is not None]
        if not nodes:
            return "Unknown"

        from collections import Counter

        # --- Strategy 1: Dominant context ---
        contexts = [n.context for n in nodes if n.context]
        if contexts:
            ctx_counts = Counter(contexts)
            top_ctx, top_count = ctx_counts.most_common(1)[0]
            if top_count / len(nodes) >= 0.5:
                # Check for dominant subcontext within this context
                subcontexts = [n.subcontext for n in nodes if n.context == top_ctx and n.subcontext]
                if subcontexts:
                    sub_counts = Counter(subcontexts)
                    top_sub, sub_count = sub_counts.most_common(1)[0]
                    if sub_count / top_count >= 0.5:
                        return f"{top_ctx} › {top_sub}"
                return top_ctx

        # --- Strategy 2: Dominant type ---
        types = [n.type for n in nodes if n.type]
        if types:
            type_counts = Counter(types)
            top_type, type_count = type_counts.most_common(1)[0]
            if type_count / len(nodes) >= 0.6:
                return f"{top_type}s"

        # --- Strategy 3: Common words in node names ---
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'of', 'to', 'in', 'for', 'with',
            'on', 'at', 'by', 'is', 'it', 'as', 'be', 'do', 'how', 'my',
            'i', 'me', 'up', 'so', 'no', 'not', 'but', 'get', 'set', '&',
            '-', '1', '2', '3', '4', '5',
        }
        all_words: list[str] = []
        for n in nodes:
            words = n.name.lower().replace('-', ' ').replace('_', ' ').split()
            all_words.extend(w for w in words if len(w) > 2 and w not in stop_words)
        if all_words:
            word_counts = Counter(all_words)
            top_word, _ = word_counts.most_common(1)[0]
            return top_word.title()

        # Final fallback
        return "Mixed"

    def detect_communities(self, method: str = "components", filters: Optional[Dict] = None) -> List[Set[str]]:
        if filters:
            all_nodes = self.get_all_nodes()
            filtered_nodes = self.filter_nodes(all_nodes, filters)
            allowed_names = {n.name for n in filtered_nodes}
        else:
            allowed_names = None

        # Cache keyed by (method, sorted allowed names, graph_version). The
        # version key makes invalidation automatic: any mutator bumps the
        # version, so subsequent calls miss and recompute.
        allowed_key = tuple(sorted(allowed_names)) if allowed_names is not None else None
        cache_key = (method, allowed_key, self._graph_version)
        with self._cache_lock:
            cached = self._community_cache.get(cache_key)
        if cached is not None:
            return [set(c) for c in cached]

        G = self._build_nx_graph(allowed_names=allowed_names)
        if len(G.nodes) == 0:
            result: List[Set[str]] = []
            with self._cache_lock:
                self._community_cache[cache_key] = result
            return result

        if method == "orphans":
            # Each isolated node (degree 0 in the filtered graph) is its own "community"
            result = [{node} for node in G.nodes if G.degree(node) == 0]
            with self._cache_lock:
                self._community_cache[cache_key] = result
            return [set(c) for c in result]

        if method == "louvain":
            communities = []
            for component in nx.connected_components(G):
                subgraph = G.subgraph(component)
                if len(subgraph.nodes) <= 2 or len(subgraph.edges) == 0:
                    communities.append(set(subgraph.nodes))
                else:
                    sub_communities = nx.community.louvain_communities(subgraph, seed=42)
                    communities.extend(sub_communities)
            communities = sorted(communities, key=len, reverse=True)
        else:
            communities = sorted(nx.connected_components(G), key=len, reverse=True)

        with self._cache_lock:
            self._community_cache[cache_key] = communities
        return [set(c) for c in communities]
