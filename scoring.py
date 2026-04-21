"""
Priority scoring algorithm based on Return on Investment (ROI).

Each node's priority is: P = eligibility * (TotalValue / PerceivedCost)
- TotalValue: intrinsic value + cascaded value from dependent nodes
- PerceivedCost: sub-linear combination of difficulty and time
- Eligibility: 1 if all hard prerequisites are Done, 0 otherwise

See README.md for full mathematical specification and hyperparameter profiles.
"""

import time
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from typing import List, Dict, Tuple, Optional, Union


def build_adjacency(edges: List[Dict], node_names: set) -> Tuple[dict, dict, dict, dict]:
    """Build the four adjacency maps the scoring algorithm consumes.

    Returns (H_out, S_out, Syn, Hard_in) where:
      - H_out[n]   : nodes that depend on n via a hard prerequisite
      - S_out[n]   : nodes that depend on n via a soft prerequisite
      - Syn[n]     : nodes synergistic with n (symmetric set)
      - Hard_in[n] : the hard prerequisites of n (incoming)
    """
    H_out = {n: [] for n in node_names}
    S_out = {n: [] for n in node_names}
    Syn = {n: set() for n in node_names}
    Hard_in = {n: [] for n in node_names}

    for e in edges:
        src, trg, etype = e['source'], e['target'], e['type']
        if src not in node_names or trg not in node_names:
            continue

        if etype == EDGE_NEEDS_HARD:
            H_out[src].append(trg)
            Hard_in[trg].append(src)
        elif etype == EDGE_NEEDS_SOFT:
            S_out[src].append(trg)
        elif etype == EDGE_HELPS:
            Syn[src].add(trg)
            Syn[trg].add(src)

    return H_out, S_out, Syn, Hard_in


def intrinsic_value(node: Node, w_v: float, w_i: float) -> float:
    """Weighted sum of a node's Value and Interest."""
    return (w_v * node.value) + (w_i * node.interest)


def perceived_cost(node: Node, w_e: float, w_t: float, beta: float, time_override: float = None) -> float:
    """Sub-linear cost combining Difficulty and PERT time."""
    t = time_override if time_override is not None else node.time
    return 1.0 + (w_e * node.difficulty) + (w_t * (t ** beta))


def is_eligible(node_name: str, hard_in: dict, all_nodes: dict) -> bool:
    """True if all hard prerequisites are satisfied.

    All prereqs are satisfied when Done.
    """
    for req in hard_in.get(node_name, []):
        req_node = all_nodes.get(req)
        if not req_node:
            return False
        if req_node.status != "Done":
            return False
    return True


def _tv_dag(
    node_name: str, all_nodes: dict,
    H_out: dict, S_out: dict,
    w_v: float, w_i: float, d_H: float, d_S: float,
    memo: dict, computing: set,
) -> float:
    """DAG-cascade portion of Total Value. Fully memoized.

    Sums IV(n) + discounted children along Hard + Soft edges only. Because
    Hard + Soft form a DAG (enforced by `GraphManager.add_edge` cycle
    checks), diamonds collapse naturally under memoization and the
    algorithm is O(N + E_dag) amortized across all calls.

    The `computing` set is a belt-and-braces cycle guard: in the unlikely
    event a Hard/Soft cycle slips through, a node re-entered while being
    computed short-circuits to 0 rather than infinite-recursing.
    """
    if node_name in memo:
        return memo[node_name]
    if node_name in computing:
        return 0.0  # cycle safeguard (should be unreachable in valid DB)
    node = all_nodes.get(node_name)
    if not node:
        return 0.0

    computing.add(node_name)
    iv = intrinsic_value(node, w_v, w_i)
    nv = 0.0
    for x in H_out.get(node_name, []):
        nv += d_H * _tv_dag(x, all_nodes, H_out, S_out, w_v, w_i, d_H, d_S, memo, computing)
    for y in S_out.get(node_name, []):
        nv += d_S * _tv_dag(y, all_nodes, H_out, S_out, w_v, w_i, d_H, d_S, memo, computing)
    computing.discard(node_name)

    result = iv + nv
    memo[node_name] = result
    return result


def total_value(
    node_name: str, visited: set, all_nodes: dict,
    H_out: dict, S_out: dict, Syn: dict,
    w_v: float, w_i: float, d_H: float, d_S: float, d_Syn: float,
    memo: Optional[dict] = None,
) -> float:
    """Computes Total Value = DAG cascade + shallow Syn bonus.

    Two-part decomposition for speed:
    1. DAG cascade (`_tv_dag`): recursive sum over Hard + Soft edges,
       fully memoized across all calls. O(N + E) amortized.
    2. Syn bonus (this function): depth-1 additive bonus for each
       immediate Syn (Helps) neighbor of the starting node. Each
       Syn-neighbor z contributes `d_Syn * _tv_dag(z)`.

    Rationale: Hard + Soft are acyclic, so memoization is safe. Helps
    edges can form cycles (they're bidirectional), so we keep Syn shallow
    from the starting node to avoid path-dependent recursion.

    Semantic note: this gives slightly different scores than a fully
    recursive Syn walk would. In practice the "synergy boost" intent is
    preserved: a node's Syn neighbors still add discounted value. What's
    lost is transitive Syn chains (A synergy→B, B synergy→C no longer
    contributes to A). Tests confirm exact equivalence for pure-DAG
    graphs; the Syn semantics are a deliberate simplification.

    `visited` is still honored at the top level (legacy callers may pass
    a non-empty set). `memo` is the cross-call DAG cache.
    """
    if node_name in visited:
        return 0.0
    if memo is None:
        memo = {}
    computing: set = set()

    dag_val = _tv_dag(
        node_name, all_nodes, H_out, S_out,
        w_v, w_i, d_H, d_S, memo, computing,
    )

    # Shallow Syn bonus: each immediate synergy neighbor contributes its
    # DAG value discounted by d_Syn.
    syn_val = 0.0
    for z in Syn.get(node_name, set()):
        if z in visited or z == node_name:
            continue
        syn_val += d_Syn * _tv_dag(
            z, all_nodes, H_out, S_out,
            w_v, w_i, d_H, d_S, memo, computing,
        )

    return dag_val + syn_val


def _get_goal_subtree_from_adjacency(goal_name: str, Hard_in: dict) -> set:
    """BFS over Hard_in to find all prerequisite descendants of a goal."""
    visited = set()
    queue = list(Hard_in.get(goal_name, []))
    while queue:
        node = queue.pop()
        if node in visited:
            continue
        visited.add(node)
        for prereq in Hard_in.get(node, []):
            if prereq not in visited:
                queue.append(prereq)
    return visited


def score_nodes(
    active_nodes: List[Node], all_nodes: List[Node],
    edges: List[Dict], hyperparams: dict,
    priority_goals: Optional[List[str]] = None,
    external_memo: Optional[Dict[str, float]] = None,
    time_phases: bool = False,
) -> Union[List[Node], Tuple[List[Node], Dict[str, float]]]:
    """Scores active nodes by priority (TV / Cost) and returns them sorted descending.

    When `time_phases` is True, also returns a dict of per-phase timings
    (adj_ms, goals_ms, score_ms, rank_ms, total_ms, n_nodes, n_edges). The
    node ordering and priority_score values are identical in both modes.
    """
    w_v = hyperparams.get('w_v', 1.0)
    w_i = hyperparams.get('w_i', 1.0)
    d_H = hyperparams.get('d_H', 0.6)
    d_S = hyperparams.get('d_S', 0.25)
    d_Syn = hyperparams.get('d_Syn', 0.35)
    w_e = hyperparams.get('w_e', 2.5)
    w_t = hyperparams.get('w_t', 1.0)
    beta = hyperparams.get('beta', 0.85)
    goal_boost = hyperparams.get('goal_boost', 1.5)

    all_nodes_dict = {n.name: n for n in all_nodes}

    t0 = time.perf_counter() if time_phases else 0.0
    H_out, S_out, Syn, Hard_in = build_adjacency(edges, set(all_nodes_dict.keys()))
    t1 = time.perf_counter() if time_phases else 0.0

    # Outer-call memo for total_value. When external_memo is supplied (by
    # GraphManager), reuse its cached values across score_nodes invocations
    # — safe because GraphManager invalidates on _graph_version / hyperparam
    # changes, which are the only inputs outer total_value depends on.
    # Direct callers (tests) without a memo get fresh per-call state.
    # Inner recursive calls are path-dependent on cycles and never cache.
    memo: Dict[str, float] = external_memo if external_memo is not None else {}

    # Pre-compute per-node boost from ranked priority goals
    # Index 0 = rank 1 (full boost), index 1 = rank 2 (66%), index 2 = rank 3 (33%)
    rank_multipliers = [
        goal_boost,
        1 + (goal_boost - 1) * 0.66,
        1 + (goal_boost - 1) * 0.33,
    ]
    node_to_boost = {}
    if priority_goals:
        for rank_idx, g in enumerate(priority_goals[:3]):
            multiplier = rank_multipliers[rank_idx]
            subtree = _get_goal_subtree_from_adjacency(g, Hard_in)
            for n in subtree:
                # Highest rank wins if node appears in multiple goal subtrees
                if n not in node_to_boost or multiplier > node_to_boost[n]:
                    node_to_boost[n] = multiplier

    t2 = time.perf_counter() if time_phases else 0.0

    scored_nodes = []
    for node in active_nodes:
        if node.type == 'Goal':
            node.priority_score = -1.0
            scored_nodes.append(node)
            continue

        if node.status in ("Done", "Blocked"):
            node.priority_score = -1.0
            scored_nodes.append(node)
            continue

        if not is_eligible(node.name, Hard_in, all_nodes_dict):
            node.priority_score = -1.0
            scored_nodes.append(node)
            continue

        # For inherited-time nodes, use minimal time to avoid double-counting
        # (their dependencies already carry their own time costs in scoring)
        t_override = 1.0 if node.time_mode == 'inherited' else None
        cost = perceived_cost(node, w_e, w_t, beta, time_override=t_override)
        tv = total_value(node.name, set(), all_nodes_dict, H_out, S_out, Syn, w_v, w_i, d_H, d_S, d_Syn, memo)
        score = round(tv / cost, 2)

        # Apply ranked priority goal boost (highest rank wins)
        if node.name in node_to_boost:
            score = round(score * node_to_boost[node.name], 2)

        node.priority_score = score
        scored_nodes.append(node)

    t3 = time.perf_counter() if time_phases else 0.0

    ranked = sorted(scored_nodes, key=lambda n: getattr(n, 'priority_score', -1.0), reverse=True)

    if not time_phases:
        return ranked

    t4 = time.perf_counter()
    timings = {
        'adj_ms': (t1 - t0) * 1000.0,
        'goals_ms': (t2 - t1) * 1000.0,
        'score_ms': (t3 - t2) * 1000.0,
        'rank_ms': (t4 - t3) * 1000.0,
        'total_ms': (t4 - t0) * 1000.0,
        'n_nodes': len(ranked),
        'n_edges': len(edges),
    }
    return ranked, timings
