"""
Priority scoring algorithm based on Return on Investment (ROI).

Each node's priority is: P = eligibility * (TotalValue / PerceivedCost)
- TotalValue: intrinsic value + cascaded value from dependent nodes
- PerceivedCost: sub-linear combination of difficulty and time
- Eligibility: 1 if all hard prerequisites are Done, 0 otherwise

See README.md for full mathematical specification and hyperparameter profiles.
"""

import heapq
import math
import time
from collections import Counter
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


def intrinsic_value(node: Node, w_v: float, w_i: float,
                    value_exponent: float = 1.0) -> float:
    """Weighted sum of a node's Value and Interest.

    Returns 0 when `value_mode='inherited'`: the node is a pure structural
    conduit and shouldn't inject its own ratings as an IV bump into its
    descendants via the cascade. Mirrors the `time_mode='inherited'`
    short-circuit on `Node.time`.

    `value_exponent` raises ratings before weighting. This is a preference
    transform, not objective utility. With equal weights, 10/1 at exponent 2
    outweighs 7/7 (101 versus 98). Graph relationships represent downstream
    leverage separately from the node's own intrinsic benefit.

    Defaults to 1.0 (plain linear weighting) so direct callers that pass only
    the two weights keep the original behaviour.
    """
    if node.value_mode == 'inherited':
        return 0.0
    if value_exponent == 1.0:
        return (w_v * node.value) + (w_i * node.interest)
    return (w_v * (node.value ** value_exponent)) + (w_i * (node.interest ** value_exponent))


# Reference scales for the time term. `t` is divided by one of these before
# the beta exponent is applied, so beta is a pure *curvature* knob and w_t is
# the only *magnitude* knob. Under the older `w_t * t**beta` form the two were
# entangled: lowering beta silently shrank the whole time term (5.7x between
# beta 0.85 and 0.45 at the median node), which handed the denominator to
# difficulty instead of rebalancing toward value. See docs/scoring.md.
#
# Both MUST stay hardcoded constants. Deriving them from the live graph would
# make every node's cost depend on the whole graph, so long tasks would get
# quietly cheaper as work is completed, and the scoring cache keyed on
# _SCORING_RELEVANT_FIELDS would no longer be sound.
TIME_REF_HOURS = 40.0        # a typical substantial Learn node
GOAL_TIME_REF_HOURS = 1300.0  # median remaining hours in a Goal's hard subtree


def time_cost_term(t: float, w_t: float, beta: float,
                   ref: float = TIME_REF_HOURS) -> float:
    """The time contribution to a cost denominator: `w_t * (t / ref)**beta`.

    Shared by `perceived_cost` (leaf nodes, ref = TIME_REF_HOURS) and the Goal
    ranker in analyze_callbacks (whole subtrees, ref = GOAL_TIME_REF_HOURS).
    The two operate at ~33x different argument scales, so they need different
    references for `w_t` to mean the same thing in both places.
    """
    if t <= 0:
        return 0.0
    return w_t * ((t / ref) ** beta)


def perceived_cost(node: Node, w_e: float, w_t: float, beta: float,
                   time_override: float = None, effort_override: float = None) -> float:
    """Sub-linear cost combining Difficulty and PERT time.

    `time_override` substitutes for `node.time` when provided (used for
    `time_mode='inherited'` containers — see _compute_priority_score).
    `effort_override` substitutes for `node.difficulty` similarly when
    `value_mode='inherited'`, so a pure container contributes neither
    intrinsic value nor own-effort cost.

    Time enters as `w_t * (t / TIME_REF_HOURS)**beta`. Note the scale change
    from the pre-normalization form: a stored `w_t` from an older bundle must
    be multiplied by `TIME_REF_HOURS**beta` to mean the same thing
    (ConfigManager.get_hyperparams handles that migration).
    """
    t = time_override if time_override is not None else node.time
    e = effort_override if effort_override is not None else node.difficulty
    return 1.0 + (w_e * e) + time_cost_term(t, w_t, beta)


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


def _strongest_routes(start, H_out, S_out, d_H, d_S, memo):
    """One strongest route per beneficiary; deterministic ties prefer fewer hops.

    Cache route maps separately from value and completion work. Invalid graphs
    fail closed at their cyclic portion rather than enumerating cyclic paths.
    """
    key = ('routes', start, d_H, d_S)
    if key in memo:
        return memo[key]
    routes = {start: (1.0, 0, 'Self')}
    order = _reachable_topo(start, H_out, S_out, {})
    preference = {'Self': 0, 'Hard': 1, 'Soft': 2}
    for name in order:
        if name not in routes:
            continue
        weight, depth, via = routes[name]
        for adjacency, discount, kind in ((H_out, d_H, 'Hard'), (S_out, d_S, 'Soft')):
            for target in adjacency.get(name, []):
                candidate = (weight * discount, depth + 1, kind if name == start else via)
                old = routes.get(target)
                if old is None or (-candidate[0], candidate[1], preference[candidate[2]]) < (-old[0], old[1], preference[old[2]]):
                    routes[target] = candidate
    memo[key] = routes
    return routes


def _remaining_hours(target, source, all_nodes, H_out, memo):
    """Unique unfinished hard closure, including target, excluding today's work."""
    if target == source:
        return 0.0
    if ('hard_in',) not in memo:
        incoming = {name: [] for name in all_nodes}
        for name, dependents in H_out.items():
            for dependent in dependents:
                incoming.setdefault(dependent, []).append(name)
        memo[('hard_in',)] = incoming
    key = ('work', target)
    if key not in memo:
        seen, stack = set(), [target]
        while stack:
            name = stack.pop()
            if name in seen:
                continue
            seen.add(name)
            stack.extend(memo[('hard_in',)].get(name, []))
        work = frozenset(name for name in seen if name in all_nodes
                         and all_nodes[name].status != STATUS_DONE
                         and not all_nodes[name].has_no_own_work)
        memo[key] = (work, math.fsum(all_nodes[name].time for name in work))
    work, hours = memo[key]
    return max(0.0, hours - (all_nodes[source].time if source in work else 0.0))


def _value_contributions(start, all_nodes, H_out, S_out, Syn, w_v, w_i,
                         d_H, d_S, d_Syn_pair, cross_context_mult=1.0,
                         value_exponent=1.0, memo=None,
                         future_work_half_credit_hours=0.0,
                         future_work_exponent=0.6):
    """Shared scoring/Explain attribution. Synergy is a separate additive channel."""
    memo = {} if memo is None else memo
    if start not in all_nodes:
        return []
    channels = [(start, 1.0, False)]
    context = all_nodes[start].context
    for partner in sorted(Syn.get(start, set()) - {start}):
        other = all_nodes.get(partner)
        if other is None:
            continue
        cross = cross_context_mult if context is not None and other.context is not None and context != other.context else 1.0
        if d_Syn_pair * cross:
            channels.append((partner, d_Syn_pair * cross, True))
    rows = {}
    for seed, coefficient, synergy in channels:
        for name, (route_weight, depth, via) in _strongest_routes(seed, H_out, S_out, d_H, d_S, memo).items():
            if name not in all_nodes:
                continue
            weight = coefficient * route_weight
            hours = _remaining_hours(name, start, all_nodes, H_out, memo) if future_work_half_credit_hours > 0 else 0.0
            discount = 1.0 / (1.0 + (hours / future_work_half_credit_hours) ** future_work_exponent) if future_work_half_credit_hours > 0 else 1.0
            iv = intrinsic_value(all_nodes[name], w_v, w_i, value_exponent)
            kind = 'Synergy' if synergy else via
            row = rows.setdefault(name, dict(name=name, depth=depth + int(synergy), via=kind,
                iv=iv, weight=0.0, remaining_hours=hours, future_discount=discount,
                contribution=0.0, channel_routes={}, channels={'Self': 0.0, 'Hard': 0.0, 'Soft': 0.0, 'Synergy': 0.0}))
            amount = weight * iv * discount
            row['weight'] += weight
            row['contribution'] += amount
            row['channels'][kind] += amount
            if amount > row['channel_routes'].get(kind, (-1, 0))[0]:
                row['channel_routes'][kind] = (amount, depth + int(synergy))
    for row in rows.values():
        # Mixed routes retain exact channel attribution; the bar uses the largest channel.
        row['via'] = max(row['channels'], key=row['channels'].get)
        row['depth'] = row.pop('channel_routes').get(row['via'], (0, row['depth']))[1]
    return list(rows.values())


def _tv_dag(node_name, all_nodes, H_out, S_out, w_v, w_i, d_H, d_S,
            memo, computing, value_exponent=1.0):
    """Undiscounted completion-work value over unique strongest DAG routes."""
    if node_name in computing:
        return 0.0
    value = math.fsum(weight * intrinsic_value(all_nodes[name], w_v, w_i, value_exponent)
        for name, (weight, _, _) in _strongest_routes(node_name, H_out, S_out, d_H, d_S, memo).items()
        if name in all_nodes)
    return value


def total_value(node_name, visited, all_nodes, H_out, S_out, Syn,
                w_v, w_i, d_H, d_S, d_Syn_pair, d_Syn_mul, memo=None,
                cross_context_mult=1.0, value_exponent=1.0,
                future_work_half_credit_hours=0.0, future_work_exponent=0.6):
    """Strongest-path value, completion-work discount, and distinct synergy bonuses.

    Direct callers may disable the future-work discount with a zero half-credit
    scale. Profiles supply a positive scale; Goal ranking explicitly disables it.
    """
    if node_name in visited or node_name not in all_nodes:
        return 0.0
    partners = {node_name: Syn.get(node_name, set()) - visited}
    rows = _value_contributions(node_name, all_nodes, H_out, S_out, partners,
        w_v, w_i, d_H, d_S, d_Syn_pair, cross_context_mult, value_exponent, memo,
        future_work_half_credit_hours, future_work_exponent)
    done = sum(all_nodes[z].status == STATUS_DONE for z in partners[node_name]
               if z != node_name and z in all_nodes)
    kick = intrinsic_value(all_nodes[node_name], w_v, w_i, value_exponent) * d_Syn_mul * math.sqrt(done)
    return math.fsum(row['contribution'] for row in rows) + kick


def _compute_priority_score(
    node: Node,
    *,
    all_nodes_dict: dict,
    H_out: dict, S_out: dict, Syn: dict,
    hyperparams: dict,
    node_to_boost: Dict[str, float],
    memo: Optional[dict] = None,
) -> Tuple[float, float, float]:
    """Single source of truth for the per-node ROI formula.

    Used by batch ranking. Explain shares _value_contributions and perceived_cost
    and reconstructs the same adjustments for display. Callers handle
    ineligibility / Goal / Done / Blocked filtering before calling this.

    Returns (rounded priority score, raw total_value, exact priority score).
    The rounded figure is what the UI displays and what callers store on the
    node; the exact one exists purely so `score_nodes` can order nodes that
    round to the same 2dp value. Both apply the identical boost, context
    weight multipliers — they differ only in rounding.
    """
    w_v = hyperparams.get('w_v', 1.0)
    w_i = hyperparams.get('w_i', 1.0)
    d_H = hyperparams.get('d_H', 0.6)
    d_S = hyperparams.get('d_S', 0.40)
    d_Syn_pair = hyperparams.get('d_Syn_pair', 0.10)
    d_Syn_mul = hyperparams.get('d_Syn_mul', 0.40)
    cross_context_mult = hyperparams.get('cross_context_mult', 1.0)
    value_exponent = hyperparams.get('value_exponent', 1.0)
    w_e = hyperparams.get('w_e', 2.5)
    w_t = hyperparams.get('w_t', 1.0)
    beta = hyperparams.get('beta', 0.85)
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
        cross_context_mult=cross_context_mult,
        value_exponent=value_exponent,
        future_work_half_credit_hours=hyperparams.get('future_work_half_credit_hours', 0.0),
        future_work_exponent=hyperparams.get('future_work_exponent', 0.6),
    )
    ratio = (tv / cost) if cost > 0 else 0.0
    score = round(ratio, 2)
    exact = ratio

    if node.name in node_to_boost:
        boost = node_to_boost[node.name]
        score = round(score * boost, 2)
        exact *= boost

    weight = context_weights.get(node.context, 1.0) if node.context else 1.0
    if weight != 1.0:
        score = round(score * weight, 2)
        exact *= weight

    return score, tv, exact


def variety_exponents(hyperparams: dict) -> Tuple[float, float]:
    """The (a, b) repetition exponents from the configured premiums.

    Settings store percentages of extra merit a node must carry to earn a
    second recommendation in a context (`suggestion_context_premium`) or in
    a subcontext (`suggestion_subcontext_premium`). The subcontext figure is
    the *total*, so it is clamped to at least the context figure and `b`
    carries only the difference between them. Both zero disables variety.
    """
    def premium(key, default):
        try:
            value = float(hyperparams.get(key, default))
            return max(0.0, min(100.0, value)) if math.isfinite(value) else default
        except (TypeError, ValueError):
            return default

    context = premium('suggestion_context_premium', 5.0)
    subcontext = max(context, premium('suggestion_subcontext_premium', 15.0))
    a = math.log2(1 + context / 100)
    b = math.log2((1 + subcontext / 100) / (1 + context / 100))
    return a, b


def variety_divisors(pool: List[Tuple[str, Optional[str], Optional[str], float]],
                     hyperparams: dict) -> Dict[str, dict]:
    """Hierarchical-variety divisors for an entire pool of scorable nodes.

    Variety is part of a node's score rather than a re-ordering applied to a
    finished list: the Next tab prints the number it sorts on, so anything
    that moves a row has to move its number too. Computing the divisors over
    the whole pool — every scorable non-Now node in the graph — is what makes
    the number a property of the node instead of a property of one list. A
    filter then narrows which rows appear without altering any of them.

    The walk itself is the original greedy: repeatedly take the node with the
    best merit-after-divisor, then charge its context and subcontext one more
    repetition. Merit ties break toward the higher raw merit, then the
    alphabetically earlier name. Because a divisor only ever grows, a heap
    entry can be revalidated lazily — a stale key is always too optimistic,
    so it is re-pushed rather than trusted.

    `pool` is (name, context, subcontext, exact merit). Returns name -> dict
    with the divisor and the 1-based repetition ranks behind it, which the
    Explain modal reports, in the order the walk selected them. Empty when
    both premiums are zero, which restores plain merit ordering.
    """
    a, b = variety_exponents(hyperparams)
    if a <= 0.0 and b <= 0.0:
        return {}

    contexts: Counter = Counter()
    pairs: Counter = Counter()

    def divisor_for(context, subcontext) -> float:
        if context is None:
            return 1.0
        return ((1 + contexts[context]) ** a
                * (1 + pairs[context, subcontext]) ** b)

    # Every node starts on an empty board, so its first key uses divisor 1.0.
    heap = [(-merit, -merit, name, context, subcontext, 1.0)
            for name, context, subcontext, merit in pool]
    heapq.heapify(heap)

    out: Dict[str, dict] = {}
    while heap:
        _, neg_merit, name, context, subcontext, charged = heapq.heappop(heap)
        current = divisor_for(context, subcontext)
        if current != charged:
            heapq.heappush(heap, (neg_merit / current, neg_merit, name,
                                  context, subcontext, current))
            continue
        out[name] = {
            'divisor': current,
            'context': context,
            'subcontext': subcontext,
            'context_rank': contexts[context] + 1,
            'subcontext_rank': pairs[context, subcontext] + 1,
        }
        if context is not None:
            contexts[context] += 1
            pairs[context, subcontext] += 1
    return out


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
    nodes_to_score: List[Node], all_nodes: List[Node],
    edges: List[Dict], hyperparams: dict,
    priority_goals: Optional[List[str]] = None,
    external_memo: Optional[dict] = None,
    time_phases: bool = False,
) -> Union[List[Node], Tuple[List[Node], Dict[str, float]]]:
    """Scores nodes by priority (TV / Cost) and returns them sorted descending.

    When `time_phases` is True, also returns a dict of per-phase timings
    (adj_ms, goals_ms, score_ms, rank_ms, total_ms, n_nodes, n_edges). The
    node ordering and priority_score values are identical in both modes.
    """
    w_v = hyperparams.get('w_v', 1.0)
    w_i = hyperparams.get('w_i', 1.0)
    d_H = hyperparams.get('d_H', 0.6)
    d_S = hyperparams.get('d_S', 0.40)
    d_Syn_pair = hyperparams.get('d_Syn_pair', 0.10)
    d_Syn_mul = hyperparams.get('d_Syn_mul', 0.40)
    cross_context_mult = hyperparams.get('cross_context_mult', 1.0)
    value_exponent = hyperparams.get('value_exponent', 1.0)
    w_e = hyperparams.get('w_e', 2.5)
    w_t = hyperparams.get('w_t', 1.0)
    beta = hyperparams.get('beta', 0.85)
    goal_boost = hyperparams.get('goal_boost', 1.5)
    context_weights = hyperparams.get('context_weights', {}) or {}

    all_nodes_dict = {n.name: n for n in all_nodes}

    t0 = time.perf_counter() if time_phases else 0.0
    H_out, S_out, Syn, Hard_in = build_adjacency(edges, set(all_nodes_dict.keys()))
    t1 = time.perf_counter() if time_phases else 0.0

    # Outer-call memo for total_value. When external_memo is supplied (by
    # GraphManager), reuse its cached values across score_nodes invocations
    # — safe because GraphManager invalidates on _graph_version / hyperparam
    # changes, which are the only inputs outer total_value depends on.
    # Direct callers (tests) without a memo get fresh per-call state.
    # Maps contain unique beneficiaries and required hard work, not scalar subtree sums.
    memo: dict = external_memo if external_memo is not None else {}

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

    def _tv_for(name: str) -> float:
        return total_value(
            name, set(), all_nodes_dict, H_out, S_out, Syn,
            w_v, w_i, d_H, d_S, d_Syn_pair, d_Syn_mul, memo,
            cross_context_mult=cross_context_mult,
            value_exponent=value_exponent,
            future_work_half_credit_hours=hyperparams.get('future_work_half_credit_hours', 0.0),
            future_work_exponent=hyperparams.get('future_work_exponent', 0.6),
        )

    def _is_scorable(node: Node) -> bool:
        """Whether the ROI formula applies to this node at all.

        Everything else carries a flat -1.0. The one non-obvious exclusion is
        `has_no_own_work`: such a node's cost carries no time term, so it
        undercuts the pool on price while still collecting the full cascade in
        the numerator — on a real graph it lands in the top five the moment it
        unblocks, despite having nothing left to do. `time_mode='inherited'`
        draws time from the hard prerequisites that eligibility already
        requires to be Done, so by the time it ranks, its inherited hours are
        spent. See Node.has_no_own_work. Their prerequisites competed on their
        own hours; cascade still flows through these nodes untouched.
        """
        return (node.type not in ('Goal', 'Milestone')
                and not node.has_no_own_work
                and node.status not in (STATUS_DONE, STATUS_BLOCKED)
                and is_eligible(node.name, Hard_in, all_nodes_dict))

    # Merit is computed for the whole graph, not just the caller's slice,
    # because the variety divisor below ranks a node against every peer it
    # could be recommended alongside. A caller's own objects win over the
    # graph's copy of the same name: they may carry edits not yet written
    # back, and scoring them as they are is what the old per-node pass did.
    merit_inputs = {n.name: n for n in all_nodes}
    merit_inputs.update({n.name: n for n in nodes_to_score})
    merits = {
        name: _compute_priority_score(
            node,
            all_nodes_dict=all_nodes_dict,
            H_out=H_out, S_out=S_out, Syn=Syn,
            hyperparams=hyperparams,
            node_to_boost=node_to_boost,
            memo=memo,
        )
        for name, node in merit_inputs.items() if _is_scorable(node)
    }

    # Now nodes are pulled out of the suggestion list entirely (see
    # next_callbacks.get_suggestions), so they neither earn a divisor nor
    # spend a repetition against their context.
    variety = variety_divisors(
        [(name, merit_inputs[name].context, merit_inputs[name].subcontext,
          merits[name][2])
         for name in merits if not getattr(merit_inputs[name], 'now', 0)],
        hyperparams,
    )

    scored_nodes = []
    # name -> unrounded priority, used only for ordering (see the sort below).
    exact_scores: Dict[str, float] = {}
    for node in nodes_to_score:
        if node.name not in merits:
            node.priority_score = -1.0
            node.total_value = _tv_for(node.name)
            scored_nodes.append(node)
            continue

        score, node.total_value, exact = merits[node.name]
        adjustment = variety.get(node.name)
        node.variety = adjustment
        if adjustment is not None and adjustment['divisor'] != 1.0:
            score = round(score / adjustment['divisor'], 2)
            exact /= adjustment['divisor']
        node.priority_score = score
        node.priority_score_exact = exact_scores[node.name] = exact
        scored_nodes.append(node)

    t3 = time.perf_counter() if time_phases else 0.0

    # Sort on the unrounded ratio, falling back to the rounded score for nodes
    # that never went through _compute_priority_score (Goals, Milestones, Done,
    # Blocked and ineligible nodes all carry a flat -1.0).
    #
    # `priority_score` is rounded to 2dp for display, which collapses ~440
    # distinct scores into ~170 on a real graph: past about rank 30 the large
    # majority of nodes share a score with a neighbour, and the tie then breaks
    # on list order, which carries no meaning. Ordering on the exact value
    # keeps the displayed number stable while making the sequence meaningful.
    #
    # Remaining ties break toward the higher pre-variety merit and then the
    # earlier name, matching the order the variety walk itself resolved them
    # in. Without that, two nodes whose adjusted scores coincide could rank
    # here in a different order than the divisors were assigned in.
    ranked = sorted(
        scored_nodes,
        key=lambda n: (-exact_scores.get(n.name, getattr(n, 'priority_score', -1.0)),
                       -merits.get(n.name, (0.0, 0.0, -1.0))[2],
                       n.name),
    )

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
    all_nodes_dict: Optional[Dict] = None,
    cross_context_mult: float = 1.0,
) -> Dict[str, float]:
    """Structural weights: strongest DAG route plus distinct synergy channels.

    Completion-work discount is applied by _value_contributions, which supplies
    the exact attribution used by both scoring and Explain.
    """
    memo = {}
    W = {name: route[0] for name, route in _strongest_routes(start, H_out, S_out, d_H, d_S, memo).items()}
    for partner in Syn.get(start, set()) - {start}:
        cross = 1.0
        if all_nodes_dict and start in all_nodes_dict and partner in all_nodes_dict:
            a, b = all_nodes_dict[start].context, all_nodes_dict[partner].context
            if a is not None and b is not None and a != b:
                cross = cross_context_mult
        for name, route in _strongest_routes(partner, H_out, S_out, d_H, d_S, memo).items():
            W[name] = W.get(name, 0.0) + d_Syn_pair * cross * route[0]
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
    variety: Optional[dict] = None,
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

    `variety` is the node's entry from `variety_divisors` — the repetition
    adjustment already folded into its ranked score. It is passed in rather
    than recomputed because it depends on the whole pool: the caller has the
    ranked list to hand, and reproducing it here would mean scoring the graph
    a second time and risking a number that disagrees with the ranking.

    Returns None if the node is not in `all_nodes`.
    """
    w_v = hyperparams.get('w_v', 1.0)
    w_i = hyperparams.get('w_i', 1.0)
    d_H = hyperparams.get('d_H', 0.6)
    d_S = hyperparams.get('d_S', 0.40)
    d_Syn_pair = hyperparams.get('d_Syn_pair', 0.10)
    d_Syn_mul = hyperparams.get('d_Syn_mul', 0.40)
    cross_context_mult = hyperparams.get('cross_context_mult', 1.0)
    value_exponent = hyperparams.get('value_exponent', 1.0)
    w_e = hyperparams.get('w_e', 2.5)
    w_t = hyperparams.get('w_t', 1.0)
    beta = hyperparams.get('beta', 0.85)
    goal_boost = hyperparams.get('goal_boost', 1.5)
    context_weights = hyperparams.get('context_weights', {}) or {}

    all_nodes_dict = {n.name: n for n in all_nodes}
    node = all_nodes_dict.get(node_name)
    if node is None:
        return None

    H_out, S_out, Syn, Hard_in = build_adjacency(edges, set(all_nodes_dict.keys()))

    iv = intrinsic_value(node, w_v, w_i, value_exponent)
    time_overridden = (node.time_mode == 'inherited')
    value_overridden = (node.value_mode == 'inherited')
    t_override = 0.0 if time_overridden else None
    e_override = 0.0 if value_overridden else None
    cost = perceived_cost(node, w_e, w_t, beta,
                          time_override=t_override, effort_override=e_override)

    contributors = _value_contributions(node_name, all_nodes_dict, H_out, S_out, Syn,
        w_v, w_i, d_H, d_S, d_Syn_pair, cross_context_mult, value_exponent,
        future_work_half_credit_hours=hyperparams.get('future_work_half_credit_hours', 0.0),
        future_work_exponent=hyperparams.get('future_work_exponent', 0.6))

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

    hard_cascade = math.fsum(c['channels']['Hard'] for c in contributors)
    soft_cascade = math.fsum(c['channels']['Soft'] for c in contributors)
    synergy_cascade = math.fsum(c['channels']['Synergy'] for c in contributors)
    total_value_sum = math.fsum(c['contribution'] for c in contributors)

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
    if node.type in ('Goal', 'Milestone'):
        eligible = False
        block_reason = f"{node.type}s are not ranked"
    elif node.has_no_own_work:
        eligible = False
        block_reason = "Container — children are recommended instead"
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
    combined_ctx_mult = ctx_weight

    variety_divisor = (variety or {}).get('divisor', 1.0)

    if eligible:
        score = round(raw_score, 2)
        if goal_boost_info is not None:
            score = round(score * goal_boost_info['multiplier'], 2)
        if combined_ctx_mult != 1.0:
            score = round(score * combined_ctx_mult, 2)
        if variety_divisor != 1.0:
            score = round(score / variety_divisor, 2)
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
            'cross_context_mult': cross_context_mult,
            'goal_boost': goal_boost,
            'alpha': 0.0,  # Compatibility for older Explain consumers.
            'value_exponent': value_exponent,
            'future_work_half_credit_hours': hyperparams.get('future_work_half_credit_hours', 0.0),
            'future_work_exponent': hyperparams.get('future_work_exponent', 0.6),
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
        'variety': variety,
        'context_adjustment': {
            'weight': ctx_weight,
            'n_bucket': 1,
            'alpha': 0.0,  # Compatibility for older Explain consumers.
            'density_mult': 1.0,
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
