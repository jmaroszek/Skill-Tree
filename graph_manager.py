import sqlite3
import database
import networkx as nx
from models import Node
from config import ConfigManager
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
                    INSERT INTO Nodes (name, type, description, value, time_o, time_m, time_p, interest, difficulty, competence, context, subcontext, status, obsidian_path, google_drive_path)
                    VALUES (:name, :type, :description, :value, :time_o, :time_m, :time_p, :interest, :difficulty, :competence, :context, :subcontext, :status, :obsidian_path, :google_drive_path)
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
                    obsidian_path=:obsidian_path, google_drive_path=:google_drive_path
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
        """Adds an edge to the DB, ensuring no cycle if 'Needs_Hard' or 'Needs_Soft' edge."""
        if edge_type in ('Needs_Hard', 'Needs_Soft'):
            if self._will_create_cycle(source, target):
                raise ValueError(f"Adding edge {source} -> {target} creates a cycle.")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)", (source, target, edge_type))
                conn.commit()
                if edge_type == 'Needs_Hard':
                    self._update_node_state(target)
            except sqlite3.IntegrityError:
                pass  # Edge already exists

    def remove_edge(self, source: str, target: str, edge_type: str):
        """Removes a specific edge."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Edges WHERE source=? AND target=? AND type=?", (source, target, edge_type))
            conn.commit()
            if edge_type == 'Needs_Hard':
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
                if etype in ('Needs_Hard', 'Needs_Soft') and self._will_create_cycle(src, trgt):
                    return
                try:
                    cursor.execute("INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)", (src, trgt, etype))
                except sqlite3.IntegrityError:
                    pass

            for src in needs_hard: _insert_edge(src, node_name, 'Needs_Hard')
            for src in needs_soft: _insert_edge(src, node_name, 'Needs_Soft')
            
            for trgt in supports_hard: _insert_edge(node_name, trgt, 'Needs_Hard')
            for trgt in supports_soft: _insert_edge(node_name, trgt, 'Needs_Soft')
            
            for linked in helps: _insert_edge(node_name, linked, 'Helps')
            for r_src in resources: _insert_edge(r_src, node_name, 'Resource')

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

    def _update_node_state(self, node_name: str):
        node = self.get_node(node_name)
        if not node or node.status == "Done":
            return

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT source FROM Edges WHERE target=? AND type='Needs_Hard'", (node_name,))
            prereqs = [row[0] for row in cursor.fetchall()]

            is_blocked = False
            for prereq_name in prereqs:
                p_node = self.get_node(prereq_name)
                if not p_node or p_node.status != "Done":
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
        hp = ConfigManager.get_hyperparams()
        wv = hp.get('w_v', 1.0)
        wi = hp.get('w_i', 1.0)
        dH = hp.get('d_H', 0.6)
        dS = hp.get('d_S', 0.25)
        dSyn = hp.get('d_Syn', 0.35)
        we = hp.get('w_e', 2.5)
        wt = hp.get('w_t', 1.0)
        beta = hp.get('beta', 0.85)

        scored_nodes = []
        all_nodes_dict = {n.name: n for n in self.get_all_nodes()}
        edges = self.get_edges()

        # Build adjacency lists
        H_out = {}
        S_out = {}
        Syn = {}
        Hard_in = {}

        for n in all_nodes_dict.keys():
            H_out[n] = []
            S_out[n] = []
            Syn[n] = set()
            Hard_in[n] = []

        for e in edges:
            src, trg, etype = e['source'], e['target'], e['type']
            if trg not in all_nodes_dict or src not in all_nodes_dict: continue
            
            if etype == 'Needs_Hard':
                H_out[src].append(trg)
                Hard_in[trg].append(src)
            elif etype == 'Needs_Soft':
                S_out[src].append(trg)
            elif etype == 'Helps':
                Syn[src].add(trg)
                Syn[trg].add(src)

        def calculate_TV_n(node_name: str, visited: set) -> float:
            if node_name in visited:
                return 0.0
            node = all_nodes_dict.get(node_name)
            if not node: return 0.0

            # Intrinsic Value
            iv = (wv * node.value) + (wi * node.interest)

            # Prevent infinite loops
            new_visited = visited.union({node_name})

            nv_sum = 0.0

            # Network values
            for x in H_out.get(node_name, []):
                if x not in visited:
                    nv_sum += dH * calculate_TV_n(x, new_visited)

            for y in S_out.get(node_name, []):
                if y not in visited:
                    nv_sum += dS * calculate_TV_n(y, new_visited)

            for z in Syn.get(node_name, set()):
                if z not in visited:
                    nv_sum += dSyn * calculate_TV_n(z, new_visited)

            return iv + nv_sum

        for node in active_nodes:
            if node.status in ["Done", "Blocked"]:
                node.priority_score = -1.0
                scored_nodes.append(node)
                continue

            # Eligibility filter delta_n
            delta_n = 1
            for req in Hard_in.get(node.name, []):
                req_node = all_nodes_dict.get(req)
                if not req_node or req_node.status != "Done":
                    delta_n = 0
                    break

            if delta_n == 0:
                node.priority_score = -1.0
                scored_nodes.append(node)
                continue

            # Perceived Cost
            Cn = 1.0 + (we * node.difficulty) + (wt * (node.time ** beta))

            # Recursively calculate Total Value
            tv_n = calculate_TV_n(node.name, set())

            node.priority_score = round(tv_n / Cn, 2)
            scored_nodes.append(node)

        return sorted(scored_nodes, key=lambda n: getattr(n, 'priority_score', -1.0), reverse=True)

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

    def _build_nx_graph(self) -> nx.Graph:
        G = nx.Graph()
        nodes = self.get_all_nodes()
        edges = self.get_edges()
        for n in nodes:
            G.add_node(n.name)
        for e in edges:
            G.add_edge(e['source'], e['target'])
        return G

    def detect_communities(self, method: str = "components") -> List[Set[str]]:
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
