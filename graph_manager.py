import sqlite3
import database
from models import Node
from typing import List, Dict, Tuple

class GraphManager:
    def __init__(self):
        # We ensure DB exists on initialization
        database.init_db()
        self.db_path = database.get_db_path()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    # --- Node Operations ---

    def add_node(self, node: Node):
        """Add a new node to the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Exclude priority_score from insert
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
            
            # If status changes, trigger state updates
            # (In a real scenario, compare old status vs new status before triggering)
            self._update_dependent_nodes_state(node.name)

    def delete_node(self, node_name: str):
        """Deletes a node by name."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Foreign keys PRAGMA needs to be on for cascading, but we can explicitly delete edges
            cursor.execute("DELETE FROM Edges WHERE source=? OR target=?", (node_name, node_name))
            cursor.execute("DELETE FROM Nodes WHERE name=?", (node_name,))
            conn.commit()

    def get_node(self, name: str) -> Node:
        """Retrieves a specific node by name."""
        with self.get_connection() as conn:
            # Important: Set row factory to access dict by column name
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
        """Adds an edge to the DB, ensuring no cycle if 'Needs' edge."""
        if edge_type == 'Needs':
            if self._will_create_cycle(source, target):
                raise ValueError(f"Adding edge {source} -> {target} creates a cycle.")
                
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)", (source, target, edge_type))
                conn.commit()
                # Adding a rule might block the target 
                if edge_type == 'Needs':
                    self._update_node_state(target)
            except sqlite3.IntegrityError:
                # Edge exists
                pass

    def remove_edge(self, source: str, target: str, edge_type: str):
        """Removes a specific edge."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Edges WHERE source=? AND target=? AND type=?", (source, target, edge_type))
            conn.commit()
            if edge_type == 'Needs':
               # Target might become unlocked
               self._update_node_state(target)

    def get_edges(self) -> List[Dict[str, str]]:
        """Retrieves all edges"""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Edges")
            return [dict(row) for row in cursor.fetchall()]

    # --- Integrity and State ---

    def _will_create_cycle(self, source: str, target: str) -> bool:
        """Checks if adding Needs edge from source -> target creates a DAG cycle."""
        # Simple DFS/BFS through 'Needs' edges from 'target' to see if we can reach 'source'
        # If target reaches source, adding source->target creates a loop
        if source == target:
            return True # self loops disallowed 
            
        visited = set()
        queue = [target]
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            while queue:
                curr = queue.pop()
                if curr == source:
                    return True # Loop detected
                visited.add(curr)
                # Find nodes this `curr` node "Needs"
                cursor.execute("SELECT target FROM Edges WHERE source=? AND type='Needs'", (curr,))
                children = [row[0] for row in cursor.fetchall()]
                for child in children:
                    if child not in visited:
                        queue.append(child)
                        
        return False

    def _update_node_state(self, node_name: str):
        """Calculates specific node state based on dependencies."""
        node = self.get_node(node_name)
        if not node or node.status == "Done":
            return # Don't retroactively reopen "Done" items automatically right here

        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Does this node depend on anything that is NOT done?
            # i.e., "prerequisite -> Needs -> node_name". 
            # In our data model, Prereq -> Needs -> Target
            # Therefore we look where `target=node_name`
            cursor.execute("""
                SELECT source FROM Edges 
                WHERE target=? AND type='Needs'
            """, (node_name,))
            prereqs = [row[0] for row in cursor.fetchall()]
            
            is_blocked = False
            for prereq_name in prereqs:
                p_node = self.get_node(prereq_name)
                # If prereq is missing entirely, treat as blocking (integrity error state)
                if not p_node or p_node.status != "Done":
                     is_blocked = True
                     break
                     
            new_status = "Blocked" if is_blocked else "Open"
            
            # If the node's previous status was something else like "In Progress"
            # and it is suddenly blocked, downgrade it. Otherwise keep In Progress if it's still open
            if node.status == "In Progress" and new_status == "Open":
                new_status = "In Progress"

            if node.status != new_status:
                 cursor.execute("UPDATE Nodes SET status=? WHERE name=?", (new_status, node_name))
                 conn.commit()
                 # If we changed to Blocked or Open, dependents might change 
                 self._update_dependent_nodes_state(node_name)


    def _update_dependent_nodes_state(self, node_name: str):
        """Recursively update dependent nodes (nodes this node points TO with 'Needs')"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Find nodes that depend on 'node_name'.
            # node_name -> Needs -> Target
            cursor.execute("SELECT target FROM Edges WHERE source=? AND type='Needs'", (node_name,))
            dependents = [row[0] for row in cursor.fetchall()]
            
        for dept in dependents:
            self._update_node_state(dept)

    # --- Logic ---

    def calculate_priority_scores(self, active_nodes: List[Node], Wn: float = 2.0, Wh: float = 1.0) -> List[Node]:
        """
        Calculates priority score for given active nodes.
        Formula: (Value*Interest)/(Time*Effort) + (Wn*N) + (Wh*H)
        N = # of blocked nodes directly unlocked (nodes that need this node)
        H = # of synergistic Helps connections
        """
        # We need a quick way to find N and H
        scored_nodes = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            for node in active_nodes:
                if node.status in ["Done", "Blocked"]:
                    # Do not score blocked or done
                    node.priority_score = -1.0
                    scored_nodes.append(node)
                    continue

                # N = count(target where source=node.name and type=Needs AND target.status=Blocked)
                # Note: directly unlocked means unlocking immediately. For simplicity we check
                # how many specific nodes have a 'Needs' coming from here that are Blocked.
                cursor.execute("""
                    SELECT COUNT(target) FROM Edges
                    JOIN Nodes ON Edges.target = Nodes.name
                    WHERE source=? AND Edges.type='Needs' AND Nodes.status='Blocked'
                """, (node.name,))
                N = cursor.fetchone()[0]
                
                # H = count(Helps edges where source=node or target=node)
                # Ensure they are connected to active nodes.
                # 'Helps' is undirected in intent, but we store it as one or two directed edges. 
                # According to spec: Node A <-> Node C
                cursor.execute("""
                    SELECT target FROM Edges WHERE source=? AND type='Helps'
                    UNION
                    SELECT source FROM Edges WHERE target=? AND type='Helps'
                """, (node.name, node.name))
                helped_names = [row[0] for row in cursor.fetchall()]
                
                # Only count 'Helps' if the connected node is active (Open/In Progress)
                H = 0
                for h_name in helped_names:
                    cursor.execute("SELECT status FROM Nodes WHERE name=?", (h_name,))
                    res = cursor.fetchone()
                    if res and res[0] in ['Open', 'In Progress']:
                        H += 1

                # Prevent div by 0 just in case
                time_val = max(0.1, node.time)
                effort_val = max(1, node.effort) # Already mapped to int in model
                
                base_score = (node.value * node.interest) / (time_val * effort_val)
                score = base_score + (Wn * N) + (Wh * H)
                
                # Assign to the instance
                node.priority_score = round(score, 2)
                scored_nodes.append(node)
                
        return sorted(scored_nodes, key=lambda n: getattr(n, 'priority_score', -1), reverse=True)


    def filter_nodes(self, nodes: List[Node], filters: Dict) -> List[Node]:
         """Applies dictionary of filters to node list { "context": "Mind", "min_value": 5 }"""
         result = nodes 
         
         if 'context' in filters and filters['context']:
             result = [n for n in result if n.context == filters['context']]
             
         if 'min_value' in filters:
             result = [n for n in result if n.value >= int(filters['min_value'])]
             
         if 'hide_done' in filters and filters['hide_done']:
             result = [n for n in result if n.status != 'Done']
             
         # Extensible for more properties
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
            
            def dfs(current_path):
                curr_node = current_path[-1]
                # Find what this node "Needs"
                cursor.execute("SELECT source FROM Edges WHERE target=? AND type='Needs'", (curr_node,))
                prereqs = [row[0] for row in cursor.fetchall()]
                
                if not prereqs:
                    # End of chain, evaluate condition
                    has_incomplete = False
                    for p in current_path:
                        n = self.get_node(p)
                        if n and n.status != 'Done':
                             has_incomplete = True
                             break
                    if has_incomplete:
                        # Append the reverse because it makes more intuitive sense Source -> Target
                        chains.append(list(reversed(current_path)))
                    return
                
                for prereq in prereqs:
                    if prereq not in current_path: # Prevent loops just in case
                        dfs(current_path + [prereq])

            dfs([target_name])
            
        return chains
