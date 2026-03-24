import sqlite3
import database
import networkx as nx
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, EDGE_RESOURCE
from config import ConfigManager
from scoring import score_nodes
from typing import List, Dict, Set


class GraphManager:
    def __init__(self):
        database.init_db()

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
                    INSERT INTO Nodes (name, type, description, value, time_o, time_m, time_p, interest, difficulty, competence, context, subcontext, status, obsidian_path, google_drive_path, frequency, session_lower, session_expected, session_upper, habit_status, progress, website)
                    VALUES (:name, :type, :description, :value, :time_o, :time_m, :time_p, :interest, :difficulty, :competence, :context, :subcontext, :status, :obsidian_path, :google_drive_path, :frequency, :session_lower, :session_expected, :session_upper, :habit_status, :progress, :website)
                ''', data)
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Node with name '{node.name}' already exists.")

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
                    frequency=:frequency, session_lower=:session_lower, session_expected=:session_expected,
                    session_upper=:session_upper, habit_status=:habit_status, progress=:progress, website=:website
                WHERE name=:name
            ''', data)
            conn.commit()
            self._update_dependent_nodes_state(node.name)

    def delete_node(self, node_name: str):
        """Deletes a node by name."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Edges WHERE source=? OR target=?", (node_name, node_name))
            cursor.execute("DELETE FROM Nodes WHERE name=?", (node_name,))
            conn.commit()

    def get_node(self, name: str) -> Node:
        """Retrieves a specific node by name."""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Nodes WHERE name=?", (name,))
            row = cursor.fetchone()
            if row:
                return Node(**dict(row))
            return None

    def get_all_nodes(self) -> List[Node]:
        """Retrieves all nodes."""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Nodes")
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

    def remove_edge(self, source: str, target: str, edge_type: str):
        """Removes a specific edge."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Edges WHERE source=? AND target=? AND type=?", (source, target, edge_type))
            conn.commit()
            if edge_type == EDGE_NEEDS_HARD:
                self._update_node_state(target)

    def get_edges(self) -> List[Dict[str, str]]:
        """Retrieves all edges."""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Edges")
            return [dict(row) for row in cursor.fetchall()]

    def sync_edges(self, node_name: str, needs_hard: list, needs_soft: list, supports_hard: list, supports_soft: list, helps: list, resources: list):
        needs_hard = needs_hard or []
        needs_soft = needs_soft or []
        supports_hard = supports_hard or []
        supports_soft = supports_soft or []
        helps = helps or []
        resources = resources or []

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Clear existing edges for this node
            cursor.execute("DELETE FROM Edges WHERE target=? AND type IN ('Needs_Hard', 'Needs_Soft', 'Resource')", (node_name,))
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
            for r_src in resources: _insert_edge(r_src, node_name, EDGE_RESOURCE)

            conn.commit()

        self._update_node_state(node_name)

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
        """Check if a prerequisite node is satisfied.

        Habit nodes are satisfied only when Active.
        All other nodes are satisfied when Done.
        """
        if not p_node:
            return False
        if p_node.type == 'Habit':
            return p_node.habit_status == 'Active'
        return p_node.status == 'Done'

    def _update_node_state(self, node_name: str):
        node = self.get_node(node_name)
        if not node or node.status == "Done":
            return
        # Habit nodes use habit_status, not the auto-calculated status
        if node.type == 'Habit':
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

    def calculate_priority_scores(self, active_nodes: List[Node]) -> List[Node]:
        """Delegates scoring to the scoring module."""
        return score_nodes(
            active_nodes, self.get_all_nodes(),
            self.get_edges(), ConfigManager.get_hyperparams()
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

    def filter_nodes(self, nodes: List[Node], filters: Dict) -> List[Node]:
        result = nodes
        
        if 'context' in filters:
            result = [n for n in result if n.context == filters['context']]

        if 'subcontext' in filters:
            result = [n for n in result if n.subcontext == filters['subcontext']]

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

    def _build_nx_graph(self, allowed_names: Set[str] = None) -> nx.Graph:
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

    def detect_communities(self, method: str = "components", filters: Dict = None) -> List[Set[str]]:
        if filters:
            all_nodes = self.get_all_nodes()
            filtered_nodes = self.filter_nodes(all_nodes, filters)
            allowed_names = {n.name for n in filtered_nodes}
        else:
            allowed_names = None

        G = self._build_nx_graph(allowed_names=allowed_names)
        if len(G.nodes) == 0:
            return []

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

        return communities
