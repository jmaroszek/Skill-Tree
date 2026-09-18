"""Graph traversal and view queries, called through GraphManager."""
from typing import List, Dict, Optional, Set, Tuple
import database
import networkx as nx
from config import ConfigManager
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE


def get_unblocking_steps(manager, target_names, limit: int = 3,
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
    targets = [t for t in (target_names or []) if t]
    if not targets or limit <= 0:
        return []

    if priority_goals is None:
        priority_goals = ConfigManager.get_priority_goals()
    # One pass over the whole graph rather than one per target: scoring is
    # graph-wide anyway (see calculate_priority_scores) and the subtree
    # lookups below are already cached against the graph version.
    scored = {n.name: n for n in manager.calculate_priority_scores(
        manager.get_all_nodes(), priority_goals=priority_goals)}

    def score_of(name):
        return getattr(scored.get(name), 'priority_score', -1.0)

    steps: List[Tuple[Node, str]] = []
    claimed = set(targets)
    for target in targets:
        if target not in scored or score_of(target) >= 0:
            continue
        subtree = manager.get_goal_subtree(target, edge_types=(EDGE_NEEDS_HARD,))
        actionable = [scored[name] for name in subtree
                      if name not in claimed and score_of(name) >= 0]
        actionable.sort(key=lambda n: (-n.priority_score, n.name))
        for node in actionable[:limit]:
            claimed.add(node.name)
            steps.append((node, target))
    return steps


def get_directly_unlocked_nodes(manager, node_name: str) -> List[str]:
    with manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT target FROM Edges
            JOIN Nodes ON Edges.target = Nodes.name
            WHERE source=? AND Edges.type='Needs_Hard' AND Nodes.status=?
        ''', (node_name, STATUS_BLOCKED))
        return [row[0] for row in cursor.fetchall()]


def get_directly_unlocked_nodes_by_type(manager, node_name: str) -> Dict[str, List[str]]:
    """Returns nodes directly unlocked by completing this node, separated by edge type."""
    with manager.get_connection() as conn:
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


def get_goal_subtree(manager, goal_name: str, edge_types=None) -> Set[str]:
    """Returns all node names reachable as prerequisites of a goal (BFS over specified edge types).

    The goal node itmanager is excluded from the returned set.

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
    with manager.caches.lock:
        manager._prepare_read_caches()
        cached = manager.caches.subtrees.get(cache_key)
        if not database.in_transaction() and cached is not None and cached[0] == manager._graph_version:
            return set(cached[1])

    # Separate directed and bidirectional edge types
    directed_types = tuple(t for t in edge_types if t != EDGE_HELPS)
    include_helps = EDGE_HELPS in edge_types

    incoming = {}
    queue = []
    for edge in manager.get_edges():
        source, target, kind = edge['source'], edge['target'], edge['type']
        if kind in directed_types:
            incoming.setdefault(target, []).append(source)
        elif include_helps and kind == EDGE_HELPS:
            if source == goal_name:
                queue.append(target)
            elif target == goal_name:
                queue.append(source)
    queue.extend(incoming.get(goal_name, ()))
    visited = set()
    while queue:
        name = queue.pop()
        if name in visited:
            continue
        visited.add(name)
        queue.extend(n for n in incoming.get(name, ()) if n not in visited)

    if not database.in_transaction():
        with manager.caches.lock:
            if len(manager.caches.subtrees) >= 128:
                manager.caches.subtrees.pop(next(iter(manager.caches.subtrees)))
            manager.caches.subtrees[cache_key] = (manager._graph_version, frozenset(visited))
    return visited


def get_dependency_view(manager, root_name: str, *, include_soft: bool = True,
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
    root = manager.get_node(root_name)
    if root is None:
        return {
            "node_names": set(),
            "depth_by_name": {},
            "discovery_edges": set(),
        }

    depth_limit = None if not max_depth or max_depth <= 0 else int(max_depth)
    allowed_need_types = {EDGE_NEEDS_HARD}
    if include_soft:
        allowed_need_types.add(EDGE_NEEDS_SOFT)

    edges = sorted(
        manager.get_edges(),
        key=lambda e: (e['target'], e['source'], e['type']),
    )
    incoming = {}
    root_synergies = []
    for edge in edges:
        edge_type = edge['type']
        if edge_type in allowed_need_types:
            incoming.setdefault(edge['target'], []).append(edge)
        elif include_synergies and edge_type == EDGE_HELPS:
            if edge['target'] == root_name:
                root_synergies.append((edge['source'], edge))
            elif edge['source'] == root_name:
                root_synergies.append((edge['target'], edge))
    root_synergies.sort(key=lambda pair: (pair[0], pair[1]['source'], pair[1]['target']))

    def traverse(allowed_names=None):
        visited = {root_name}
        depth_by_name = {root_name: 0}
        discovery_edges = set()
        queue = [root_name]
        cursor = 0

        while cursor < len(queue):
            current = queue[cursor]
            cursor += 1
            current_depth = depth_by_name[current]
            if depth_limit is not None and current_depth >= depth_limit:
                continue

            candidates = [
                (edge['source'], edge)
                for edge in incoming.get(current, ())
            ]
            if current == root_name:
                candidates.extend(root_synergies)
            candidates.sort(
                key=lambda pair: (pair[0], pair[1]['type'],
                                  pair[1]['source'], pair[1]['target'])
            )

            for neighbor, edge in candidates:
                if allowed_names is not None and neighbor not in allowed_names:
                    continue
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                depth_by_name[neighbor] = current_depth + 1
                discovery_edges.add(
                    (edge['source'], edge['target'], edge['type'])
                )
                queue.append(neighbor)

        return visited, depth_by_name, discovery_edges

    candidate_names, _, _ = traverse()
    if filters is not None:
        candidate_nodes = [
            manager.get_node(name) for name in candidate_names
            if name != root_name
        ]
        candidate_nodes = [node for node in candidate_nodes if node is not None]
        filtered_names = {
            node.name for node in manager.filter_nodes(candidate_nodes, filters)
        }
        allowed_names = filtered_names | {root_name}
        node_names, depth_by_name, discovery_edges = traverse(allowed_names)
    else:
        node_names, depth_by_name, discovery_edges = traverse()

    return {
        "node_names": node_names,
        "depth_by_name": depth_by_name,
        "discovery_edges": discovery_edges,
    }


def get_goal_completion(manager, goal_name: str, include_soft: bool = True,
                        include_transitive: bool = True,
                        max_depth: int | None = None) -> dict:
    """Returns completion stats for a goal based on its subtree.

    Args:
        include_soft: If False, only traverse hard-need edges.
        include_transitive: If False, only count direct children of the goal.

    Returns dict with: total, done, pct, remaining_time
    """
    edge_types = (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT) if include_soft else (EDGE_NEEDS_HARD,)
    if max_depth and max_depth > 0:
        view = manager.get_dependency_view(
            goal_name,
            include_soft=include_soft,
            include_synergies=False,
            max_depth=max_depth,
        )
        subtree = set(view["node_names"]) - {goal_name}
    else:
        subtree = manager.get_goal_subtree(goal_name, edge_types=edge_types)
    if include_transitive is False and not max_depth:
        direct = {e['source'] for e in manager.get_edges()
                  if e['target'] == goal_name and e['type'] in edge_types}
        subtree = subtree & direct
    if not subtree:
        return {"total": 0, "done": 0, "pct": 0, "remaining_time": 0.0}

    nodes = [manager.get_node(name) for name in subtree]
    nodes = [n for n in nodes if n is not None]
    total = len(nodes)
    done = sum(1 for n in nodes if n.status == STATUS_DONE)
    blocked = sum(1 for n in nodes if n.status == STATUS_BLOCKED)
    remaining_time = sum(n.time for n in nodes if n.status != STATUS_DONE)
    pct = round(done / total * 100) if total > 0 else 0

    # A goal is considered blocked if ALL of its remaining subtasks are blocked
    is_blocked = (done + blocked == total) and (blocked > 0)

    return {"total": total, "done": done, "pct": pct, "remaining_time": round(remaining_time, 1), "is_blocked": is_blocked}


def get_effective_time(manager, node_name: str) -> float:
    """Returns the effective time estimate for a node.

    For nodes with time_mode='manual', returns the PERT-computed time
    from the node's own time_o/m/p values.

    For nodes with time_mode='inherited', sums the PERT-computed times
    of all incomplete nodes in the node's dependency subtree, treating
    the node itmanager as a container with zero direct time.

    Returns:
        Time in hours.
    """
    node = manager.get_node(node_name)
    if not node:
        return 0.0

    if node.time_mode != 'inherited':
        return node.time

    # Inherited mode: sum subtree times
    subtree = manager.get_goal_subtree(node_name)
    total = 0.0
    for name in subtree:
        child = manager.get_node(name)
        if child and child.status != STATUS_DONE:
            total += child.time
    return round(total, 2)


def filter_nodes(manager, nodes: List[Node], filters: Dict) -> List[Node]:
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


def get_prerequisite_chains(manager, target_name: str) -> List[List[str]]:
    target_node = manager.get_node(target_name)
    if not target_node:
        return []

    chains = []
    with manager.get_connection() as conn:
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


def get_prerequisite_chains_typed(manager, target_name: str) -> List[tuple]:
    """Returns prerequisite chains classified as 'Hard' or 'Soft'.

    Each result is (chain, type_str) where type_str is 'Hard' if all edges
    in the chain are Needs_Hard, else 'Soft'.
    """
    target_node = manager.get_node(target_name)
    if not target_node:
        return []

    typed_chains = []
    with manager.get_connection() as conn:
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


def _build_nx_graph(manager, allowed_names: Optional[Set[str]] = None) -> nx.Graph:
    G = nx.Graph()
    nodes = manager.get_all_nodes()
    edges = manager.get_edges()
    for n in nodes:
        if allowed_names is None or n.name in allowed_names:
            G.add_node(n.name)
    for e in edges:
        if e['source'] in G.nodes and e['target'] in G.nodes:
            G.add_edge(e['source'], e['target'])
    return G


def name_community(manager, community: Set[str]) -> str:
    """Generate a descriptive name for a community based on member node attributes.

    Strategy (in priority order):
    1. If a dominant context covers >=50% of nodes, use it.
       - If a subcontext also dominates within that context, append it.
    2. Otherwise, if a dominant node type covers >=60%, use it as the label.
    3. Otherwise, find the most frequent meaningful word across node names.
    """
    if not community:
        return "Empty"

    nodes = [manager.get_node(name) for name in community]
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
                    return f"{top_ctx} > {top_sub}"
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


def detect_communities(manager, method: str = "components", filters: Optional[Dict] = None) -> List[Set[str]]:
    if filters:
        all_nodes = manager.get_all_nodes()
        filtered_nodes = manager.filter_nodes(all_nodes, filters)
        allowed_names = {n.name for n in filtered_nodes}
    else:
        allowed_names = None

    # Cache keyed by (method, sorted allowed names, graph_version). The
    # version key makes invalidation automatic: any mutator bumps the
    # version, so subsequent calls miss and recompute.
    allowed_key = tuple(sorted(allowed_names)) if allowed_names is not None else None
    cache_key = (method, allowed_key, manager._graph_version)
    with manager.caches.lock:
        manager._prepare_read_caches()
        cached = manager.caches.communities.get(cache_key)
        if cached is not None:
            manager.caches.communities.move_to_end(cache_key)
    if cached is not None and not database.in_transaction():
        return [set(c) for c in cached]

    G = manager._build_nx_graph(allowed_names=allowed_names)
    if len(G.nodes) == 0:
        result: List[Set[str]] = []
        manager._cache_communities(cache_key, result)
        return result

    if method == "orphans":
        # Each isolated node (degree 0 in the filtered graph) is its own "community"
        result = [{node} for node in G.nodes if G.degree(node) == 0]
        manager._cache_communities(cache_key, result)
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

    manager._cache_communities(cache_key, communities)
    return [set(c) for c in communities]
