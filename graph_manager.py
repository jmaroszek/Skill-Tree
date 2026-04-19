import sqlite3
import threading
import database
import networkx as nx
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, EDGE_RESOURCE
from config import ConfigManager
from scoring import score_nodes
from typing import List, Dict, Optional, Set


class GraphManager:
    def __init__(self):
        database.init_db()
        self._graph_version: int = 0
        self._community_cache: Dict[tuple, List[Set[str]]] = {}
        self._cache_lock = threading.Lock()

    def _bump_version(self) -> None:
        """Invalidate memoization caches. Called by every node/edge mutator."""
        self._graph_version += 1

    def get_connection(self) -> sqlite3.Connection:
        """Returns a new database connection with foreign keys enabled."""
        return database.get_connection()

    # --- Node Operations ---

    def add_node(self, node: Node):
        """Add a new node to the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                data = node.to_dict()
                data.pop('priority_score', None)
                data.pop('time', None)  # time is a computed property
                cursor.execute('''
                    INSERT INTO Nodes (name, type, description, value, time_o, time_m, time_p, interest, difficulty, competence, context, subcontext, status, obsidian_path, google_drive_path, progress, website, dormant, time_mode)
                    VALUES (:name, :type, :description, :value, :time_o, :time_m, :time_p, :interest, :difficulty, :competence, :context, :subcontext, :status, :obsidian_path, :google_drive_path, :progress, :website, :dormant, :time_mode)
                ''', data)
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Node with name '{node.name}' already exists.")
        self._bump_version()

    def update_node(self, node: Node):
        """Updates an existing node."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            data = node.to_dict()
            data.pop('priority_score', None)
            data.pop('time', None)
            cursor.execute('''
                UPDATE Nodes
                SET type=:type, description=:description, value=:value, time_o=:time_o, time_m=:time_m, time_p=:time_p,
                    interest=:interest, difficulty=:difficulty, competence=:competence,
                    context=:context, subcontext=:subcontext, status=:status,
                    obsidian_path=:obsidian_path, google_drive_path=:google_drive_path,
                    progress=:progress, website=:website,
                    dormant=:dormant, time_mode=:time_mode
                WHERE name=:name
            ''', data)
            conn.commit()
            self._update_dependent_nodes_state(node.name)
        self._bump_version()

    def delete_node(self, node_name: str):
        """Deletes a node by name."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Find dependents before deleting edges so we can recalculate their state
            cursor.execute("SELECT target FROM Edges WHERE source=? AND type='Needs_Hard'", (node_name,))
            dependents = [row[0] for row in cursor.fetchall()]
            cursor.execute("DELETE FROM Edges WHERE source=? OR target=?", (node_name, node_name))
            cursor.execute("DELETE FROM Nodes WHERE name=?", (node_name,))
            conn.commit()
        for dept in dependents:
            self._update_node_state(dept)
        self._bump_version()

    def rename_node(self, old_name: str, new_name: str):
        """Renames a node, updating all edge and event references atomically."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Temporarily disable FK checks so we can rename node + edges atomically
            cursor.execute("PRAGMA foreign_keys = OFF")
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
        """Return {alias: node_name} mapping for all aliases."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT alias, node_name FROM Aliases")
            return {row[0]: row[1] for row in cursor.fetchall()}

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

    # --- Edge Operations ---

    def add_edge(self, source: str, target: str, edge_type: str):
        """Adds an edge to the DB, ensuring no cycle if Needs_Hard or Needs_Soft edge."""
        if edge_type in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
            if self._will_create_cycle(source, target):
                raise ValueError(f"Adding edge {source} -> {target} creates a cycle.")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)", (source, target, edge_type))
                conn.commit()
                if edge_type == EDGE_NEEDS_HARD:
                    self._update_node_state(target)
            except sqlite3.IntegrityError:
                pass  # Edge already exists
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

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Clear existing edges for this node
            cursor.execute("DELETE FROM Edges WHERE target=? AND type IN ('Needs_Hard', 'Needs_Soft')", (node_name,))
            cursor.execute("DELETE FROM Edges WHERE source=? AND type IN ('Needs_Hard', 'Needs_Soft')", (node_name,))
            cursor.execute("DELETE FROM Edges WHERE (target=? OR source=?) AND type='Helps'", (node_name, node_name))

            def _insert_edge(src, trgt, etype):
                if etype in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT) and self._will_create_cycle(src, trgt):
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
        return p_node.status == 'Done'

    def _update_node_state(self, node_name: str):
        node = self.get_node(node_name)
        if not node or node.status == "Done":
            return
        # Goal nodes use their own status, not the auto-calculated status
        if node.type == 'Goal':
            return

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT source FROM Edges WHERE target=? AND type='Needs_Hard'", (node_name,))
            prereqs = [row[0] for row in cursor.fetchall()]

            is_blocked = False
            for prereq_name in prereqs:
                p_node = self.get_node(prereq_name)
                if not self._is_prereq_satisfied(p_node):
                    is_blocked = True
                    break

            new_status = "Blocked" if is_blocked else "Open"
            if node.status == "In Progress" and new_status == "Open":
                new_status = "In Progress"

            if node.status != new_status:
                cursor.execute("UPDATE Nodes SET status=? WHERE name=?", (new_status, node_name))
                conn.commit()
                self._update_dependent_nodes_state(node_name)

    def _update_dependent_nodes_state(self, node_name: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT target FROM Edges WHERE source=? AND type='Needs_Hard'", (node_name,))
            dependents = [row[0] for row in cursor.fetchall()]

        for dept in dependents:
            self._update_node_state(dept)

    # --- Logic ---

    def calculate_priority_scores(self, active_nodes: List[Node], priority_goals: Optional[List[str]] = None) -> List[Node]:
        """Delegates scoring to the scoring module."""
        return score_nodes(
            active_nodes, self.get_all_nodes(),
            self.get_edges(), ConfigManager.get_hyperparams(),
            priority_goals=priority_goals
        )

    def get_directly_unlocked_nodes(self, node_name: str) -> List[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT target FROM Edges
                JOIN Nodes ON Edges.target = Nodes.name
                WHERE source=? AND Edges.type='Needs_Hard' AND Nodes.status='Blocked'
            ''', (node_name,))
            return [row[0] for row in cursor.fetchall()]

    def get_directly_unlocked_nodes_by_type(self, node_name: str) -> Dict[str, List[str]]:
        """Returns nodes directly unlocked by completing this node, separated by edge type."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT target, Edges.type FROM Edges
                JOIN Nodes ON Edges.target = Nodes.name
                WHERE source=? AND Edges.type IN ('Needs_Hard', 'Needs_Soft')
                AND Nodes.status IN ('Blocked', 'Open')
            ''', (node_name,))
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

        For the bidirectional Helps edge type, traversal follows both directions
        so that synergy partners are discovered.

        Args:
            goal_name: The goal node to start from.
            edge_types: Tuple of edge types to traverse. Defaults to (Needs_Hard, Needs_Soft).
        """
        if edge_types is None:
            edge_types = (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT)

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

            # Seed with Helps partners of the goal (bidirectional)
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

                # Follow directed edges
                if directed_types:
                    placeholders = ','.join('?' for _ in directed_types)
                    cursor.execute(
                        f"SELECT source FROM Edges WHERE target=? AND type IN ({placeholders})",
                        (node, *directed_types)
                    )
                    for row in cursor.fetchall():
                        if row[0] not in visited:
                            queue.append(row[0])

                # Follow Helps edges bidirectionally
                if include_helps:
                    cursor.execute(
                        "SELECT source FROM Edges WHERE target=? AND type=?",
                        (node, EDGE_HELPS)
                    )
                    for row in cursor.fetchall():
                        if row[0] not in visited:
                            queue.append(row[0])
                    cursor.execute(
                        "SELECT target FROM Edges WHERE source=? AND type=?",
                        (node, EDGE_HELPS)
                    )
                    for row in cursor.fetchall():
                        if row[0] not in visited:
                            queue.append(row[0])

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
        done = sum(1 for n in nodes if n.status == "Done")
        blocked = sum(1 for n in nodes if n.status == "Blocked")
        remaining_time = sum(n.time for n in nodes if n.status != "Done")
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
            if child and child.status != 'Done':
                total += child.time
        return round(total, 2)

    def filter_nodes(self, nodes: List[Node], filters: Dict) -> List[Node]:
        result = nodes
        
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
            result = [n for n in result if n.status != 'Done']

        if 'search' in filters and filters['search']:
            search_val = filters['search'].lower()
            result = [n for n in result if search_val in n.name.lower()]

        if 'goal' in filters and filters['goal']:
            goals = filters['goal'] if isinstance(filters['goal'], list) else [filters['goal']]
            combined: Set[str] = set()
            for g in goals:
                subtree = self.get_goal_subtree(g)
                subtree.add(g)
                combined.update(subtree)
            result = [n for n in result if n.name in combined]

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
                        status_lookup.get(p, 'Open') != 'Done'
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
                        status_lookup.get(p, 'Open') != 'Done'
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
        """
        removed = set(old_values) - set(new_values)
        if not removed:
            return {}

        all_nodes = self.get_all_nodes()
        orphans = {}
        for val in removed:
            affected = [n for n in all_nodes if getattr(n, field, None) == val]
            if affected:
                orphans[val] = affected
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

                if field == 'type' and new_val is not None:
                    # Clear type-specific fields when changing away from Resource
                    cursor.execute("SELECT name, type FROM Nodes WHERE type=?", (old_val,))
                    rows = cursor.fetchall()
                    for name, old_type in rows:
                        if old_type == 'Resource' and new_val != 'Resource':
                            cursor.execute("UPDATE Nodes SET progress=NULL WHERE name=?", (name,))

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

            if field == 'type' and actual_val is not None:
                cursor.execute("SELECT type FROM Nodes WHERE name=?", (node_name,))
                row = cursor.fetchone()
                if row and row[0] == 'Resource' and actual_val != 'Resource':
                    cursor.execute("UPDATE Nodes SET progress=NULL WHERE name=?", (node_name,))

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
