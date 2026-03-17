import sqlite3
import database
import networkx as nx
from models import Node
from constants import DEFAULT_WN, DEFAULT_WH
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
                cursor.execute('''
                    INSERT INTO Nodes (name, type, description, value, time, interest, effort, competence, context, subcontext, status)
                    VALUES (:name, :type, :description, :value, :time, :interest, :effort, :competence, :context, :subcontext, :status)
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
            cursor.execute('''
                UPDATE Nodes
                SET type=:type, description=:description, value=:value, time=:time, 
                    interest=:interest, effort=:effort, competence=:competence, 
                    context=:context, subcontext=:subcontext, status=:status
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

    # --- Settings Operations ---

    def get_setting(self, key: str, default: str = None) -> str:
        """Retrieves a setting value by key, or returns the default."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM Settings WHERE key=?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str):
        """Inserts or updates a setting."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO Settings (key, value) VALUES (?, ?)",
                (key, str(value))
            )
            conn.commit()

    def get_hyperparams(self) -> dict:
        """Returns the persisted Wn/Wh hyperparameters (or defaults)."""
        wn = float(self.get_setting('Wn', str(DEFAULT_WN)))
        wh = float(self.get_setting('Wh', str(DEFAULT_WH)))
        return {'Wn': wn, 'Wh': wh}

    def save_hyperparams(self, wn: float, wh: float):
        """Persists Wn/Wh hyperparameters to the database."""
        self.set_setting('Wn', str(wn))
        self.set_setting('Wh', str(wh))

    # --- Edge Operations ---

    def add_edge(self, source: str, target: str, edge_type: str):
        """Adds an edge to the DB, ensuring no cycle if 'Needs' edge."""
        if edge_type == 'Needs':
            if self._will_create_cycle(source, target):
                raise ValueError(f"Adding edge {source} -> {target} creates a cycle.")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)", (source, target, edge_type))
                conn.commit()
                if edge_type == 'Needs':
                    self._update_node_state(target)
            except sqlite3.IntegrityError:
                pass  # Edge already exists

    def remove_edge(self, source: str, target: str, edge_type: str):
        """Removes a specific edge."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Edges WHERE source=? AND target=? AND type=?", (source, target, edge_type))
            conn.commit()
            if edge_type == 'Needs':
                self._update_node_state(target)

    def get_edges(self) -> List[Dict[str, str]]:
        """Retrieves all edges."""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Edges")
            return [dict(row) for row in cursor.fetchall()]

    def sync_edges(self, node_name: str, needs: list, supports: list, helps: list, resources: list):
        """
        Replaces all edges for a node in a single transaction.
        
        Args:
            node_name:  The node whose edges are being synced.
            needs:      List of prerequisite node names (source -> node_name via Needs).
            supports:   List of dependent node names (node_name -> target via Needs).
            helps:      List of synergistic node names (bidirectional Helps).
            resources:  List of resource node names (source -> node_name via Resource).
        """
        needs = needs or []
        supports = supports or []
        helps = helps or []
        resources = resources or []

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Clear existing edges for this node
            cursor.execute("DELETE FROM Edges WHERE target=? AND type='Needs'", (node_name,))
            cursor.execute("DELETE FROM Edges WHERE source=? AND type='Needs'", (node_name,))
            cursor.execute("DELETE FROM Edges WHERE (target=? OR source=?) AND type='Helps'", (node_name, node_name))
            cursor.execute("DELETE FROM Edges WHERE target=? AND type='Resource'", (node_name,))

            # Re-add Needs: prerequisite -> node_name
            for src in needs:
                try:
                    if self._will_create_cycle(src, node_name):
                        continue
                    cursor.execute("INSERT INTO Edges (source, target, type) VALUES (?, ?, 'Needs')", (src, node_name))
                except sqlite3.IntegrityError:
                    pass

            # Re-add Supports: node_name -> dependent (also a Needs edge)
            for trgt in supports:
                try:
                    if self._will_create_cycle(node_name, trgt):
                        continue
                    cursor.execute("INSERT INTO Edges (source, target, type) VALUES (?, ?, 'Needs')", (node_name, trgt))
                except sqlite3.IntegrityError:
                    pass

            # Re-add Helps
            for linked in helps:
                try:
                    cursor.execute("INSERT INTO Edges (source, target, type) VALUES (?, ?, 'Helps')", (node_name, linked))
                except sqlite3.IntegrityError:
                    pass

            # Re-add Resources
            for r_src in resources:
                try:
                    cursor.execute("INSERT INTO Edges (source, target, type) VALUES (?, ?, 'Resource')", (r_src, node_name))
                except sqlite3.IntegrityError:
                    pass

            conn.commit()

        # Update blocked/open state after edge mutations
        self._update_node_state(node_name)

    # --- Integrity and State ---

    def _will_create_cycle(self, source: str, target: str) -> bool:
        """Checks if adding a Needs edge from source -> target creates a DAG cycle."""
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
                cursor.execute("SELECT target FROM Edges WHERE source=? AND type='Needs'", (curr,))
                for row in cursor.fetchall():
                    if row[0] not in visited:
                        queue.append(row[0])

        return False

    def _update_node_state(self, node_name: str):
        """Calculates and updates a specific node's blocked/open state based on its dependencies."""
        node = self.get_node(node_name)
        if not node or node.status == "Done":
            return

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT source FROM Edges 
                WHERE target=? AND type='Needs'
            """, (node_name,))
            prereqs = [row[0] for row in cursor.fetchall()]

            is_blocked = False
            for prereq_name in prereqs:
                p_node = self.get_node(prereq_name)
                if not p_node or p_node.status != "Done":
                    is_blocked = True
                    break

            new_status = "Blocked" if is_blocked else "Open"

            # Preserve "In Progress" if the node is not being blocked
            if node.status == "In Progress" and new_status == "Open":
                new_status = "In Progress"

            if node.status != new_status:
                cursor.execute("UPDATE Nodes SET status=? WHERE name=?", (new_status, node_name))
                conn.commit()
                self._update_dependent_nodes_state(node_name)

    def _update_dependent_nodes_state(self, node_name: str):
        """Recursively update dependent nodes (nodes that Need this node)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT target FROM Edges WHERE source=? AND type='Needs'", (node_name,))
            dependents = [row[0] for row in cursor.fetchall()]

        for dept in dependents:
            self._update_node_state(dept)

    # --- Logic ---

    def calculate_priority_scores(self, active_nodes: List[Node],
                                  Wn: float = DEFAULT_WN, Wh: float = DEFAULT_WH) -> List[Node]:
        """
        Calculates priority score for given active nodes.
        Formula: (Value*Interest)/(Time*Effort) + (Wn*N) + (Wh*H)
        """
        scored_nodes = []

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Pre-fetch all node statuses to avoid per-node queries
            cursor.execute("SELECT name, status FROM Nodes")
            status_lookup = {row[0]: row[1] for row in cursor.fetchall()}

            for node in active_nodes:
                if node.status in ["Done", "Blocked"]:
                    node.priority_score = -1.0
                    scored_nodes.append(node)
                    continue

                # N = count of blocked nodes that directly need this node
                cursor.execute("""
                    SELECT COUNT(target) FROM Edges
                    JOIN Nodes ON Edges.target = Nodes.name
                    WHERE source=? AND Edges.type='Needs' AND Nodes.status='Blocked'
                """, (node.name,))
                N = cursor.fetchone()[0]

                # H = count of active Helps connections (using pre-fetched statuses)
                cursor.execute("""
                    SELECT target FROM Edges WHERE source=? AND type='Helps'
                    UNION
                    SELECT source FROM Edges WHERE target=? AND type='Helps'
                """, (node.name, node.name))
                H = sum(1 for row in cursor.fetchall()
                        if status_lookup.get(row[0]) in ('Open', 'In Progress'))

                base_score = (node.value * node.interest) / (node.time * node.effort)
                score = base_score + (Wn * N) + (Wh * H)

                node.priority_score = round(score, 2)
                scored_nodes.append(node)

        return sorted(scored_nodes, key=lambda n: getattr(n, 'priority_score', -1), reverse=True)

    def get_directly_unlocked_nodes(self, node_name: str) -> List[str]:
        """Returns the names of nodes that 'Need' this node and are currently 'Blocked'."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT target FROM Edges
                JOIN Nodes ON Edges.target = Nodes.name
                WHERE source=? AND Edges.type='Needs' AND Nodes.status='Blocked'
            """, (node_name,))
            return [row[0] for row in cursor.fetchall()]

    def filter_nodes(self, nodes: List[Node], filters: Dict) -> List[Node]:
        """Applies dictionary of filters to node list."""
        result = nodes

        if 'context' in filters:
            result = [n for n in result if n.context == filters['context']]

        if 'min_value' in filters:
            result = [n for n in result if n.value >= int(filters['min_value'])]

        if 'hide_done' in filters and filters['hide_done']:
            result = [n for n in result if n.status != 'Done']

        if 'search' in filters and filters['search']:
            search_val = filters['search'].lower()
            result = [n for n in result if search_val in n.name.lower()]

        return result

    def get_prerequisite_chains(self, target_name: str) -> List[List[str]]:
        """
        Traverses the DAG backward from the target_name via 'Needs' edges.
        Returns a list of prerequisite chains (each chain is a list of node names).
        Only includes chains that contain incomplete (not 'Done') nodes.
        """
        target_node = self.get_node(target_name)
        if not target_node:
            return []

        chains = []

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Pre-fetch all node statuses
            cursor.execute("SELECT name, status FROM Nodes")
            status_lookup = {row[0]: row[1] for row in cursor.fetchall()}

            def dfs(current_path):
                curr_node = current_path[-1]
                cursor.execute("SELECT source FROM Edges WHERE target=? AND type='Needs'", (curr_node,))
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

    # --- Community Detection ---

    def _build_nx_graph(self) -> nx.Graph:
        """Builds an undirected NetworkX graph from all nodes and edges in the DB."""
        G = nx.Graph()
        nodes = self.get_all_nodes()
        edges = self.get_edges()
        for n in nodes:
            G.add_node(n.name)
        for e in edges:
            G.add_edge(e['source'], e['target'])
        return G

    def detect_communities(self, method: str = "components") -> List[Set[str]]:
        """
        Detects communities/islands in the graph.
        
        Args:
            method: 'components' for Connected Components (finds fully disconnected islands),
                     'louvain' for Louvain Modularity (finds loosely connected sub-clusters).
        
        Returns:
            List of sets, each set containing node names in one community,
            sorted by size (largest first).
        """
        G = self._build_nx_graph()

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
