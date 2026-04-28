"""
Priority scoring algorithm based on Return on Investment (ROI).

Each node's priority is: P = eligibility * (TotalValue / PerceivedCost)
- TotalValue: intrinsic value + cascaded value from dependent nodes
- PerceivedCost: sub-linear combination of difficulty and time
- Eligibility: 1 if all hard prerequisites are Done, 0 otherwise

See README.md for full mathematical specification and hyperparameter profiles.
"""

import math
import time
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
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
    """Weighted sum of a node's Value and Interest.

    Returns 0 when `value_mode='inherited'`: the node is a pure structural
    conduit and shouldn't inject its own ratings as an IV bump into its
    descendants via the cascade. Mirrors the `time_mode='inherited'`
    short-circuit on `Node.time`.
    """
    if node.value_mode == 'inherited':
        return 0.0
    return (w_v * node.value) + (w_i * node.interest)


def perceived_cost(node: Node, w_e: float, w_t: float, beta: float,
                   time_override: float = None, effort_override: float = None) -> float:
    """Sub-linear cost combining Difficulty and PERT time.

    `time_override` substitutes for `node.time` when provided (used for
    `time_mode='inherited'` containers — see _compute_priority_score).
    `effort_override` substitutes for `node.difficulty` similarly when
    `value_mode='inherited'`, so a pure container contributes neither
    intrinsic value nor own-effort cost.
    """
    t = time_override if time_override is not None else node.time
    e = effort_override if effort_override is not None else node.difficulty
    return 1.0 + (w_e * e) + (w_t * (t ** beta))


def is_eligible(node_name: str, hard_in: dict, all_nodes: dict) -> bool:
    """True if all hard prerequisites are satisfied.

    All prereqs are satisfied when Done.
    """
    for req in hard_in.get(node_name, []):
        req_node = all_nodes.get(req)
        if not req_node:
            return False
        if req_node.status != STATUS_DONE:
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
    w_v: float, w_i: float, d_H: float, d_S: float,
    d_Syn_pair: float, d_Syn_mul: float,
    memo: Optional[dict] = None,
) -> float:
    """Computes Total Value = scaled intrinsic + DAG cascade + Syn pair bonus.

    M3 hybrid synergy model:
    1. DAG cascade (`_tv_dag`): recursive sum over Hard + Soft edges,
       fully memoized across all calls. O(N + E) amortized.
    2. Syn pair bonus (additive, partner-state-blind): each immediate
       Syn (Helps) neighbor z contributes `d_Syn_pair * _tv_dag(z)`.
       Co-promotes synergy pairs into joint consideration before any
       work has started.
    3. Syn completion multiplier on intrinsic: `iv * (1 + d_Syn_mul *
       count_done_partners)`. Captures the "doing both > sum of parts"
       intent — kicks in only once partners are Done. Multiplier
       applies to *intrinsic value only*, not to cascade or pair bonus.

    Rationale: Hard + Soft are acyclic, so memoization is safe. Helps
    edges can form cycles (they're bidirectional), so Syn stays shallow
    (depth-1 only) from the starting node — synergies do not chain.

    `visited` is still honored at the top level (legacy callers may pass
    a non-empty set). `memo` is the cross-call DAG cache.
    """
    if node_name in visited:
        return 0.0
    if memo is None:
        memo = {}
    computing: set = set()

    node = all_nodes.get(node_name)
    if not node:
        return 0.0

    full_dag = _tv_dag(
        node_name, all_nodes, H_out, S_out,
        w_v, w_i, d_H, d_S, memo, computing,
    )
    iv = intrinsic_value(node, w_v, w_i)
    cascade = full_dag - iv  # cascade-only portion (Hard + Soft contributions)

    syn_additive = 0.0
    done_syn = 0
    for z in Syn.get(node_name, set()):
        if z in visited or z == node_name:
            continue
        syn_additive += d_Syn_pair * _tv_dag(
            z, all_nodes, H_out, S_out,
            w_v, w_i, d_H, d_S, memo, computing,
        )
        z_node = all_nodes.get(z)
        if z_node is not None and z_node.status == STATUS_DONE:
            done_syn += 1

    # Sub-linear (sqrt) accumulation so dense synergy hubs don't run away —
    # 4 Done partners give 2× the kick of 1, not 4×, and a node with 16 Done
    # partners caps near 4× rather than 16×. Keeps "more partners = more
    # boost" without unbounded inflation in heavily-synergy-linked graphs.
    syn_multiplier = 1.0 + d_Syn_mul * math.sqrt(done_syn)
    return iv * syn_multiplier + cascade + syn_additive


def _compute_priority_score(
    node: Node,
    *,
    all_nodes_dict: dict,
    H_out: dict, S_out: dict, Syn: dict,
    hyperparams: dict,
    node_to_boost: Dict[str, float],
    n_active_map: Dict[Tuple[Optional[str], Optional[str]], int],
    memo: Optional[Dict[str, float]] = None,
) -> float:
    """Single source of truth for the per-node ROI formula.

    Used by both ``score_nodes`` (batch ranking) and ``explain_score``
    (per-node breakdown) so the two paths can never drift on the order or
    composition of cost / TV / boost / density / weight. Returns the final
    rounded priority score; callers handle ineligibility / Goal / Done /
    Blocked filtering before calling this.
    """
    w_v = hyperparams.get('w_v', 1.0)
    w_i = hyperparams.get('w_i', 1.0)
    d_H = hyperparams.get('d_H', 0.6)
    d_S = hyperparams.get('d_S', 0.25)
    d_Syn_pair = hyperparams.get('d_Syn_pair', 0.10)
    d_Syn_mul = hyperparams.get('d_Syn_mul', 0.40)
    w_e = hyperparams.get('w_e', 2.5)
    w_t = hyperparams.get('w_t', 1.0)
    beta = hyperparams.get('beta', 0.85)
    alpha = hyperparams.get('alpha', 0.0)
    context_weights = hyperparams.get('context_weights', {}) or {}

    # Inherited-time containers carry no marginal time cost; inherited-value
    # containers also carry no marginal effort cost (the node is a pure
    # structural conduit). The base `1.0 +` keeps the denominator positive
    # in both cases.
    t_override = 0.0 if node.time_mode == 'inherited' else None
    e_override = 0.0 if node.value_mode == 'inherited' else None
    cost = perceived_cost(node, w_e, w_t, beta,
                          time_override=t_override, effort_override=e_override)
    tv = total_value(
        node.name, set(), all_nodes_dict, H_out, S_out, Syn,
        w_v, w_i, d_H, d_S, d_Syn_pair, d_Syn_mul, memo,
    )
    score = round(tv / cost, 2) if cost > 0 else 0.0

    if node.name in node_to_boost:
        score = round(score * node_to_boost[node.name], 2)

    weight = context_weights.get(node.context, 1.0) if node.context else 1.0
    n_bucket = max(1, n_active_map.get((node.context, node.subcontext), 1))
    density_mult = (1.0 / (n_bucket ** alpha)) if alpha > 0 else 1.0
    if weight != 1.0 or density_mult != 1.0:
        score = round(score * weight * density_mult, 2)

    return score


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
    d_Syn_pair = hyperparams.get('d_Syn_pair', 0.10)
    d_Syn_mul = hyperparams.get('d_Syn_mul', 0.40)
    w_e = hyperparams.get('w_e', 2.5)
    w_t = hyperparams.get('w_t', 1.0)
    beta = hyperparams.get('beta', 0.85)
    goal_boost = hyperparams.get('goal_boost', 1.5)
    alpha = hyperparams.get('alpha', 0.0)
    context_weights = hyperparams.get('context_weights', {}) or {}

    all_nodes_dict = {n.name: n for n in all_nodes}

    t0 = time.perf_counter() if time_phases else 0.0
    H_out, S_out, Syn, Hard_in = build_adjacency(edges, set(all_nodes_dict.keys()))
    t1 = time.perf_counter() if time_phases else 0.0

    # Per-bucket active counts for density normalization. Goal/Done/Blocked
    # nodes don't compete for top-N slots, so they don't dilute the budget.
    # (context, None) IS a meaningful bucket — it means "broad area, not a
    # specific subarea" — so subcontext being None doesn't disqualify.
    # context=None is rejected at add_node; defensively skip if any legacy
    # row slipped through.
    n_active_map: Dict[Tuple[Optional[str], Optional[str]], int] = {}
    for n in active_nodes:
        if n.type == 'Goal' or n.status in (STATUS_DONE, STATUS_BLOCKED):
            continue
        if n.context is None:
            continue
        key = (n.context, n.subcontext)
        n_active_map[key] = n_active_map.get(key, 0) + 1

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

        if node.status in (STATUS_DONE, STATUS_BLOCKED):
            node.priority_score = -1.0
            scored_nodes.append(node)
            continue

        if not is_eligible(node.name, Hard_in, all_nodes_dict):
            node.priority_score = -1.0
            scored_nodes.append(node)
            continue

        node.priority_score = _compute_priority_score(
            node,
            all_nodes_dict=all_nodes_dict,
            H_out=H_out, S_out=S_out, Syn=Syn,
            hyperparams=hyperparams,
            node_to_boost=node_to_boost,
            n_active_map=n_active_map,
            memo=memo,
        )
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
    d_H: float, d_S: float, d_Syn_pair: float,
) -> Dict[str, float]:
    """Forward-propagate discount weights from `start`.

    Returns {name: W(name)} where W(D) is the sum over all paths
    (H/S from start, plus syn-seeded + H/S from each syn neighbor)
    of the product of edge discounts. By linearity of the additive
    portion of TV, `contribution(D) = W(D) * IV(D)` and the contributions
    sum to (intrinsic + cascade + syn_additive). The synergy multiplier
    on intrinsic is a node-level scalar, applied separately by callers.
    """
    topo = _reachable_topo(start, H_out, S_out, Syn)
    W: Dict[str, float] = {start: 1.0}
    for z in Syn.get(start, set()):
        if z != start:
            W[z] = W.get(z, 0.0) + d_Syn_pair

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
    d_Syn_pair = hyperparams.get('d_Syn_pair', 0.10)
    d_Syn_mul = hyperparams.get('d_Syn_mul', 0.40)
    w_e = hyperparams.get('w_e', 2.5)
    w_t = hyperparams.get('w_t', 1.0)
    beta = hyperparams.get('beta', 0.85)
    goal_boost = hyperparams.get('goal_boost', 1.5)
    alpha = hyperparams.get('alpha', 0.0)
    context_weights = hyperparams.get('context_weights', {}) or {}

    all_nodes_dict = {n.name: n for n in all_nodes}
    node = all_nodes_dict.get(node_name)
    if node is None:
        return None

    H_out, S_out, Syn, Hard_in = build_adjacency(edges, set(all_nodes_dict.keys()))

    # Bucket counts match score_nodes: exclude Goal/Done/Blocked AND
    # uncategorized (context=None) from density. See score_nodes for rationale.
    n_active_map: Dict[Tuple[Optional[str], Optional[str]], int] = {}
    for n_ in all_nodes:
        if n_.type == 'Goal' or n_.status in (STATUS_DONE, STATUS_BLOCKED):
            continue
        if n_.context is None:
            continue
        key = (n_.context, n_.subcontext)
        n_active_map[key] = n_active_map.get(key, 0) + 1

    iv = intrinsic_value(node, w_v, w_i)
    time_overridden = (node.time_mode == 'inherited')
    value_overridden = (node.value_mode == 'inherited')
    t_override = 0.0 if time_overridden else None
    e_override = 0.0 if value_overridden else None
    cost = perceived_cost(node, w_e, w_t, beta,
                          time_override=t_override, effort_override=e_override)

    # Contribution weights + per-node metadata
    W = _contribution_weights(node_name, H_out, S_out, Syn, d_H, d_S, d_Syn_pair)
    depth, via = _depth_and_via(node_name, H_out, S_out, Syn, W)

    # Synergy multiplier on intrinsic: kicks in when partners are Done.
    # This is a node-level scalar, not a per-contributor weight, so it
    # lives outside the W loop.
    done_syn_count = sum(
        1 for z in Syn.get(node_name, set())
        if z != node_name and (other := all_nodes_dict.get(z)) is not None
        and other.status == STATUS_DONE
    )
    # Sub-linear (sqrt) so dense synergy hubs don't run away. Matches the
    # formula in `total_value` exactly so explain_score's reported multiplier
    # never drifts from the actual scoring multiplier.
    iv_multiplier = 1.0 + d_Syn_mul * math.sqrt(done_syn_count)
    iv_multiplier_contribution = iv * (iv_multiplier - 1.0)

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

    # Percentages (guard against TV=0). Use the *full* TV including the
    # multiplicative kick so contributor percentages reflect the actual
    # ranking signal — otherwise pct rows wouldn't add up sensibly when a
    # synergy multiplier is active.
    tv_full = total_value_sum + iv_multiplier_contribution
    tv_for_pct = tv_full if tv_full > 0 else 1.0
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
    elif node.status == STATUS_DONE:
        eligible = False
        block_reason = STATUS_DONE
    elif node.status == STATUS_BLOCKED:
        eligible = False
        block_reason = STATUS_BLOCKED
    else:
        missing = [
            req for req in Hard_in.get(node_name, [])
            if all_nodes_dict.get(req) is None
            or all_nodes_dict[req].status != STATUS_DONE
        ]
        if missing:
            eligible = False
            block_reason = "Missing prereqs: " + ", ".join(sorted(missing))

    raw_score = tv_full / cost if cost > 0 else 0.0

    # Context-aware adjustments (mirrors score_nodes).
    ctx_weight = context_weights.get(node.context, 1.0) if node.context else 1.0
    n_bucket = max(1, n_active_map.get((node.context, node.subcontext), 1))
    density_mult = (1.0 / (n_bucket ** alpha)) if alpha > 0 else 1.0
    combined_ctx_mult = ctx_weight * density_mult

    if eligible:
        score = round(raw_score, 2)
        if goal_boost_info is not None:
            score = round(score * goal_boost_info['multiplier'], 2)
        if combined_ctx_mult != 1.0:
            score = round(score * combined_ctx_mult, 2)
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
            'd_H': d_H, 'd_S': d_S,
            'd_Syn_pair': d_Syn_pair, 'd_Syn_mul': d_Syn_mul,
            'goal_boost': goal_boost,
            'alpha': alpha,
        },
        'intrinsic': {
            'value': node.value,
            'interest': node.interest,
            'iv': iv,
        },
        'cost': {
            'difficulty': node.difficulty,
            'time': 0.0 if time_overridden else node.time,
            'time_overridden': time_overridden,
            'cost': cost,
        },
        'composition': {
            'iv': iv,
            'iv_multiplier': iv_multiplier,
            'iv_multiplier_contribution': iv_multiplier_contribution,
            'done_synergy_count': done_syn_count,
            'hard_cascade': hard_cascade,
            'soft_cascade': soft_cascade,
            'synergy': synergy_cascade,
            'total_value': total_value_sum + iv_multiplier_contribution,
        },
        'goal_boost': goal_boost_info,
        'context_adjustment': {
            'weight': ctx_weight,
            'n_bucket': n_bucket,
            'alpha': alpha,
            'density_mult': density_mult,
            'combined_multiplier': combined_ctx_mult,
        },
        'contributors': contributors,
    }


def shortest_paths_focus_data(
    source: str,
    ranked_targets: List[Tuple[int, str]],
    all_nodes: List[Node],
    edges: List[Dict],
) -> Dict:
    """Shortest Hard/Soft paths from `source` to each target, for focus highlighting.

    Mirrors the edge set used by `explain_score`'s contribution graph:
    BFS over Hard + Soft edges with a depth-1 Synergy seed from source.

    `ranked_targets` is a list of (rank, target_name) in rank-ascending
    order (smallest rank = most valuable). Paths are reconstructed per
    target by walking parent pointers; for nodes and edges that lie on
    multiple paths, the smallest rank wins (so Path 1's color dominates
    shared segments).

    Returns a dict with:
      - 'subtree':       list of node names on any path (sorted for determinism)
      - 'node_rank':     {name: min_rank}  including source
      - 'edge_rank':     {(source_name, target_name, edge_type): min_rank}
      - 'target_labels': {name: '#<rank>'} for each reachable target only
    """
    all_nodes_dict = {n.name: n for n in all_nodes}
    if source not in all_nodes_dict:
        return {'subtree': [], 'node_rank': {}, 'edge_rank': {},
                'target_labels': {}}

    H_out, S_out, Syn, _ = build_adjacency(edges, set(all_nodes_dict.keys()))

    # BFS with parent pointers. parent[child] = (parent_name, edge_type).
    # source has parent=None (sentinel for "stop walking").
    parent: Dict[str, Optional[Tuple[str, str]]] = {source: None}
    queue: List[str] = [source]
    # Depth-1 synergy seeds — matches explain_score's single-hop Syn bonus.
    for z in Syn.get(source, set()):
        if z == source or z in parent:
            continue
        parent[z] = (source, EDGE_HELPS)
        queue.append(z)
    # BFS over H + S.
    head = 0
    while head < len(queue):
        n = queue[head]
        head += 1
        for c in H_out.get(n, []):
            if c in parent:
                continue
            parent[c] = (n, EDGE_NEEDS_HARD)
            queue.append(c)
        for c in S_out.get(n, []):
            if c in parent:
                continue
            parent[c] = (n, EDGE_NEEDS_SOFT)
            queue.append(c)

    node_rank: Dict[str, int] = {}
    edge_rank: Dict[Tuple[str, str, str], int] = {}
    target_labels: Dict[str, str] = {}

    # Reconstruct each path. Iterate rank-ascending so min rank wins on
    # shared segments (Path 1 claims before Path 2, etc.).
    for rank, target in ranked_targets:
        if target not in parent:
            continue  # unreachable target — silently skipped
        target_labels[target] = f"#{rank}"
        cur: Optional[str] = target
        while cur is not None:
            if cur not in node_rank or rank < node_rank[cur]:
                node_rank[cur] = rank
            step = parent[cur]
            if step is None:
                break
            parent_name, etype = step
            key = (parent_name, cur, etype)
            if key not in edge_rank or rank < edge_rank[key]:
                edge_rank[key] = rank
            cur = parent_name

    # No targets reachable: still include source so the canvas dims
    # everything else but leaves the starting node lit.
    if source not in node_rank:
        node_rank[source] = 1

    subtree = sorted(node_rank.keys())
    return {
        'subtree': subtree,
        'node_rank': node_rank,
        'edge_rank': edge_rank,
        'target_labels': target_labels,
    }
