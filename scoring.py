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


def _reachable_topo(start: str, H_out: dict, S_out: dict, Syn: dict) -> List[str]:
    """Topological order of H/S nodes reachable from `start` plus its Syn seeds.

    Used by explain_score to propagate contribution weights in an order
    that guarantees each node is processed only after all its H/S
    predecessors — the DAG property of Hard+Soft makes this well-defined.
    """
    seeds = {start} | (Syn.get(start, set()) - {start})
    reachable = set()
    stack = list(seeds)
    while stack:
        n = stack.pop()
        if n in reachable:
            continue
        reachable.add(n)
        for c in H_out.get(n, []):
            if c not in reachable:
                stack.append(c)
        for c in S_out.get(n, []):
            if c not in reachable:
                stack.append(c)

    in_degree = {n: 0 for n in reachable}
    for n in reachable:
        for c in H_out.get(n, []):
            if c in reachable:
                in_degree[c] += 1
        for c in S_out.get(n, []):
            if c in reachable:
                in_degree[c] += 1

    queue = [n for n in reachable if in_degree[n] == 0]
    topo = []
    while queue:
        n = queue.pop(0)
        topo.append(n)
        for c in H_out.get(n, []):
            if c in reachable:
                in_degree[c] -= 1
                if in_degree[c] == 0:
                    queue.append(c)
        for c in S_out.get(n, []):
            if c in reachable:
                in_degree[c] -= 1
                if in_degree[c] == 0:
                    queue.append(c)
    return topo


def _contribution_weights(
    start: str, H_out: dict, S_out: dict, Syn: dict,
    d_H: float, d_S: float, d_Syn: float,
) -> Dict[str, float]:
    """Forward-propagate discount weights from `start`.

    Returns {name: W(name)} where W(D) is the sum over all paths
    (H/S from start, plus syn-seeded + H/S from each syn neighbor)
    of the product of edge discounts. By linearity of the TV formula,
    `contribution(D) = W(D) * IV(D)` and the contributions sum to TV(start).
    """
    topo = _reachable_topo(start, H_out, S_out, Syn)
    W: Dict[str, float] = {start: 1.0}
    for z in Syn.get(start, set()):
        if z != start:
            W[z] = W.get(z, 0.0) + d_Syn

    for n in topo:
        w = W.get(n, 0.0)
        if w == 0.0:
            continue
        for c in H_out.get(n, []):
            W[c] = W.get(c, 0.0) + w * d_H
        for c in S_out.get(n, []):
            W[c] = W.get(c, 0.0) + w * d_S
    return W


def _depth_and_via(start: str, H_out: dict, S_out: dict, Syn: dict,
                   W: Dict[str, float]) -> Tuple[Dict[str, int], Dict[str, str]]:
    """BFS over reachable W-keys to assign shortest depth + first-hop type.

    `via` categorizes the first edge taken out of `start` on the shortest
    path to each node: one of 'Self', 'Hard', 'Soft', 'Synergy'. Ties at
    equal depth break Hard > Soft > Synergy for display consistency.
    """
    reachable = set(W.keys())
    depth: Dict[str, int] = {start: 0}
    via: Dict[str, str] = {start: 'Self'}

    # Depth-1 seeds with explicit first-hop type
    priority = {'Hard': 3, 'Soft': 2, 'Synergy': 1, 'Self': 0}

    def consider(name: str, d: int, v: str) -> None:
        if name not in depth or d < depth[name]:
            depth[name] = d
            via[name] = v
        elif d == depth[name] and priority[v] > priority.get(via[name], 0):
            via[name] = v

    for c in H_out.get(start, []):
        if c in reachable:
            consider(c, 1, 'Hard')
    for c in S_out.get(start, []):
        if c in reachable:
            consider(c, 1, 'Soft')
    for c in Syn.get(start, set()):
        if c in reachable and c != start:
            consider(c, 1, 'Synergy')

    # BFS onward, propagating `via` from parent
    queue = [n for n in depth if depth[n] == 1]
    while queue:
        n = queue.pop(0)
        d_next = depth[n] + 1
        v = via[n]
        for edge_list in (H_out.get(n, []), S_out.get(n, [])):
            for c in edge_list:
                if c not in reachable:
                    continue
                if c not in depth or d_next < depth[c]:
                    depth[c] = d_next
                    via[c] = v
                    queue.append(c)
                elif d_next == depth[c] and priority[v] > priority.get(via[c], 0):
                    via[c] = v
    return depth, via


def explain_score(
    node_name: str,
    all_nodes: List[Node],
    edges: List[Dict],
    hyperparams: dict,
    priority_goals: Optional[List[str]] = None,
) -> Optional[Dict]:
    """Decomposes a node's priority score into its constituent parts.

    Returns a dict describing intrinsic value, perceived cost, the
    breakdown of TotalValue by edge type (hard/soft/synergy cascades), a
    goal-boost entry if applicable, and a list of top contributors —
    every descendant whose IV propagates into this node's TV, sorted by
    contribution.

    Handles ineligible, Done, Blocked, and Goal nodes gracefully: the
    breakdown is still computed but `eligible=False` and `block_reason`
    is set.

    Returns None if the node is not in `all_nodes`.
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
    node = all_nodes_dict.get(node_name)
    if node is None:
        return None

    H_out, S_out, Syn, Hard_in = build_adjacency(edges, set(all_nodes_dict.keys()))

    iv = intrinsic_value(node, w_v, w_i)
    time_overridden = (node.time_mode == 'inherited')
    t_override = 1.0 if time_overridden else None
    cost = perceived_cost(node, w_e, w_t, beta, time_override=t_override)

    # Contribution weights + per-node metadata
    W = _contribution_weights(node_name, H_out, S_out, Syn, d_H, d_S, d_Syn)
    depth, via = _depth_and_via(node_name, H_out, S_out, Syn, W)

    contributors = []
    hard_cascade = 0.0
    soft_cascade = 0.0
    synergy_cascade = 0.0
    total_value_sum = 0.0
    for name, weight in W.items():
        other = all_nodes_dict.get(name)
        if other is None:
            continue
        iv_n = intrinsic_value(other, w_v, w_i)
        contribution = weight * iv_n
        total_value_sum += contribution
        v = via.get(name, 'Self')
        if name == node_name:
            pass  # intrinsic, tracked separately
        elif v == 'Hard':
            hard_cascade += contribution
        elif v == 'Soft':
            soft_cascade += contribution
        elif v == 'Synergy':
            synergy_cascade += contribution
        contributors.append({
            'name': name,
            'depth': depth.get(name, 0),
            'via': v,
            'iv': iv_n,
            'weight': weight,
            'contribution': contribution,
        })

    # Percentages (guard against TV=0)
    tv_for_pct = total_value_sum if total_value_sum > 0 else 1.0
    for c in contributors:
        c['pct_of_tv'] = 100.0 * c['contribution'] / tv_for_pct

    contributors.sort(key=lambda c: c['contribution'], reverse=True)

    # Goal boost
    goal_boost_info = None
    if priority_goals:
        rank_multipliers = [
            goal_boost,
            1 + (goal_boost - 1) * 0.66,
            1 + (goal_boost - 1) * 0.33,
        ]
        best = None  # (multiplier, goal_name, rank)
        for rank_idx, g in enumerate(priority_goals[:3]):
            multiplier = rank_multipliers[rank_idx]
            subtree = _get_goal_subtree_from_adjacency(g, Hard_in)
            if node_name in subtree and (best is None or multiplier > best[0]):
                best = (multiplier, g, rank_idx + 1)
        if best is not None:
            goal_boost_info = {
                'multiplier': best[0], 'goal': best[1], 'rank': best[2],
            }

    # Eligibility / block reason
    eligible = True
    block_reason: Optional[str] = None
    if node.type == 'Goal':
        eligible = False
        block_reason = "Goals are not ranked"
    elif node.status == 'Done':
        eligible = False
        block_reason = "Done"
    elif node.status == 'Blocked':
        eligible = False
        block_reason = "Blocked"
    else:
        missing = [
            req for req in Hard_in.get(node_name, [])
            if all_nodes_dict.get(req) is None
            or all_nodes_dict[req].status != 'Done'
        ]
        if missing:
            eligible = False
            block_reason = "Missing prereqs: " + ", ".join(sorted(missing))

    raw_score = total_value_sum / cost if cost > 0 else 0.0
    if eligible:
        score = round(raw_score, 2)
        if goal_boost_info is not None:
            score = round(score * goal_boost_info['multiplier'], 2)
    else:
        score = -1.0

    return {
        'node': node_name,
        'score': score,
        'raw_score': raw_score,
        'eligible': eligible,
        'block_reason': block_reason,
        'hyperparams': {
            'w_v': w_v, 'w_i': w_i, 'w_e': w_e, 'w_t': w_t, 'beta': beta,
            'd_H': d_H, 'd_S': d_S, 'd_Syn': d_Syn, 'goal_boost': goal_boost,
        },
        'intrinsic': {
            'value': node.value,
            'interest': node.interest,
            'iv': iv,
        },
        'cost': {
            'difficulty': node.difficulty,
            'time': 1.0 if time_overridden else node.time,
            'time_overridden': time_overridden,
            'cost': cost,
        },
        'composition': {
            'iv': iv,
            'hard_cascade': hard_cascade,
            'soft_cascade': soft_cascade,
            'synergy': synergy_cascade,
            'total_value': total_value_sum,
        },
        'goal_boost': goal_boost_info,
        'contributors': contributors,
    }
