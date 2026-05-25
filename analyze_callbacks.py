"""
Callback definitions for the Analyze tab.
Computes and renders aggregate analytics about the graph.
"""

import math
from dataclasses import replace
from dash import html, dcc, Input, Output, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from collections import defaultdict
from graph_manager import GraphManager
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from config import ConfigManager, BADGE_PALETTE
from scoring import (
    build_adjacency as _scoring_build_adjacency, total_value, explain_score,
)

graph_manager = GraphManager()


def _trunc(name, max_len=25):
    """Truncate a name for chart labels, preserving full name in hover."""
    return name if len(name) <= max_len else name[:max_len - 1] + '\u2026'


def _label_axis(full_names):
    """Axis-dict fragment that displays truncated labels for full categorical names.

    Plotly treats duplicate categorical axis values as a single category and overlays
    their bars; passing full (unique) names as the axis values and using tickvals /
    ticktext to override the displayed labels keeps each entry distinct while still
    showing a truncated label.
    """
    return dict(
        tickmode='array',
        tickvals=list(full_names),
        ticktext=[_trunc(n) for n in full_names],
    )


# ---------------------------------------------------------------------------
# Adjacency helpers
# ---------------------------------------------------------------------------

def _build_adjacency(edges):
    """Build in-memory forward and reverse adjacency maps from edge list.

    Returns:
        hard_fwd:    source -> [targets]  for Needs_Hard edges
        hard_rev:    target -> [sources]  for Needs_Hard edges (hard prerequisites)
        prereq_rev:  target -> [sources]  for Needs_Hard + Needs_Soft edges (all prerequisites)
        all_fwd:     source -> [targets]  for all edge types
        all_rev:     target -> [sources]  for all edge types
    """
    hard_fwd = defaultdict(list)
    hard_rev = defaultdict(list)
    prereq_rev = defaultdict(list)
    all_fwd = defaultdict(list)
    all_rev = defaultdict(list)
    for e in edges:
        s, t, etype = e['source'], e['target'], e['type']
        all_fwd[s].append(t)
        all_rev[t].append(s)
        if etype == EDGE_NEEDS_HARD:
            hard_fwd[s].append(t)
            hard_rev[t].append(s)
            prereq_rev[t].append(s)
        elif etype == EDGE_NEEDS_SOFT:
            prereq_rev[t].append(s)
    return hard_fwd, hard_rev, prereq_rev, all_fwd, all_rev


# ---------------------------------------------------------------------------
# Compute functions
# ---------------------------------------------------------------------------

def _compute_overview(nodes, edges):
    active = [n for n in nodes if n.status != STATUS_DONE]
    blocked = [n for n in active if n.status == STATUS_BLOCKED]
    goals = [n for n in nodes if n.type == 'Goal']
    milestones = [n for n in nodes if n.type == 'Milestone']
    return {
        'active_count': len(active),
        'blocked_count': len(blocked),
        'blocked_pct': round(len(blocked) / len(active) * 100) if active else 0,
        'goal_count': len(goals),
        'milestone_count': len(milestones),
        'done_count': len([n for n in nodes if n.status == STATUS_DONE]),
        'total_count': len(nodes),
    }


def _compute_bottlenecks(nodes, hard_fwd, limits):
    """For each non-Done node, compute how many downstream nodes are reachable via hard edges."""
    non_done = {n.name for n in nodes if n.status != STATUS_DONE}
    node_map = {n.name: n for n in nodes}
    results = []

    for name in non_done:
        if name not in hard_fwd:
            continue
        # BFS forward through hard edges counting non-Done reachable nodes
        direct = set(hard_fwd.get(name, []))
        direct_non_done = direct & non_done
        # Cascade: full BFS
        visited = set()
        queue = list(direct_non_done)
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            for nxt in hard_fwd.get(current, []):
                if nxt not in visited and nxt in non_done:
                    queue.append(nxt)

        node = node_map[name]
        results.append({
            'name': name,
            'status': node.status,
            'type': node.type,
            'time': node.time,
            'direct_unlocks': len(direct_non_done),
            'cascade': len(visited),
        })

    results.sort(key=lambda r: (r['cascade'], r['direct_unlocks']), reverse=True)
    return results[:limits.get('bottlenecks', 25)]


def _compute_hub_score(nodes, edges, limits):
    """For each non-Done node, compute its hub score —
    ``sqrt(in_count * out_count) + 0.5 * helps_count`` over Hard + Soft
    prereq edges, with Helps edges counted as symmetric synergy partners.

    The geometric mean punishes asymmetry (a pure root or pure leaf scores
    0 on the first term), so hubs are exactly the nodes with traffic in
    both directions — concepts that absorb prereqs AND feed dependents.
    The Helps term gives synergy partners half-weight credit on top.

    Returns the top N (capped by ``limits['bottlenecks']``, since the
    Graph Structure section's gear controls both charts) sorted by score
    descending. Each row also carries the score components and the count
    of distinct contexts among the node's neighbors, for tooltip display."""
    node_map = {n.name: n for n in nodes}
    non_done = {n.name for n in nodes if n.status != STATUS_DONE}

    in_ct: dict = defaultdict(int)
    out_ct: dict = defaultdict(int)
    helps_ct: dict = defaultdict(int)
    neighbor_ctx: dict = defaultdict(set)

    for e in edges:
        s, t, etype = e['source'], e['target'], e['type']
        if etype in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
            out_ct[s] += 1
            in_ct[t] += 1
        elif etype == EDGE_HELPS:
            helps_ct[s] += 1
            helps_ct[t] += 1
        s_ctx = node_map[s].context if s in node_map else None
        t_ctx = node_map[t].context if t in node_map else None
        if s_ctx:
            neighbor_ctx[t].add(s_ctx)
        if t_ctx:
            neighbor_ctx[s].add(t_ctx)

    results = []
    for name in non_done:
        i, o = in_ct[name], out_ct[name]
        h = helps_ct[name]
        score = math.sqrt(i * o) + 0.5 * h
        if score <= 0:
            continue
        n = node_map[name]
        results.append({
            'name': name,
            'score': score,
            'in_count': i,
            'out_count': o,
            'helps_count': h,
            'distinct_contexts': len(neighbor_ctx[name]),
            'type': n.type,
            'status': n.status,
            'context': n.context,
        })

    results.sort(key=lambda r: r['score'], reverse=True)
    return results[:limits.get('bottlenecks', 25)]


def _compute_estimation_accuracy(nodes):
    """Pair each completed node's forecast estimate against its captured
    actual time. Both figures run through the same `blend_time_estimate`
    blend so they are directly comparable. Nodes with no actual-time data,
    or with no own estimate (inherited-time Goals), are skipped."""
    from models import blend_time_estimate
    rows = []
    for n in nodes:
        if n.status != STATUS_DONE:
            continue
        lo, mid, hi = n.actual_time_lower, n.actual_time_point, n.actual_time_upper
        if lo is None and mid is None and hi is None:
            continue
        estimate = n.time
        if estimate <= 0:
            continue
        actual = blend_time_estimate(lo, mid, hi)
        rows.append({
            'name': n.name,
            'type': n.type,
            'context': n.context,
            'estimate': estimate,
            'actual': actual,
        })
    return rows


_REFLECTION_MIN_N = 2  # min reflected nodes per context for the drift heatmap


def _compute_reflection_drift(nodes):
    """For each context with at least ``_REFLECTION_MIN_N`` reflected nodes,
    compute mean ``reflect_X - X`` across V/I/D. A null reflect_X is skipped
    for that metric only; nodes count toward the context's reflected total
    if any of the three reflection fields is populated."""
    by_ctx = defaultdict(lambda: {'dv': [], 'di': [], 'dd': [], 'count': 0})
    for n in nodes:
        if (n.reflect_value is None
                and n.reflect_interest is None
                and n.reflect_difficulty is None):
            continue
        ctx = n.context or 'No Context'
        d = by_ctx[ctx]
        d['count'] += 1
        if n.reflect_value is not None:
            d['dv'].append(n.reflect_value - n.value)
        if n.reflect_interest is not None:
            d['di'].append(n.reflect_interest - n.interest)
        if n.reflect_difficulty is not None:
            d['dd'].append(n.reflect_difficulty - n.difficulty)

    def _mean(xs):
        return round(sum(xs) / len(xs), 2) if xs else None

    results = []
    for ctx, d in by_ctx.items():
        if d['count'] < _REFLECTION_MIN_N:
            continue
        results.append({
            'context': ctx, 'count': d['count'],
            'd_value': _mean(d['dv']),
            'd_interest': _mean(d['di']),
            'd_difficulty': _mean(d['dd']),
        })
    results.sort(key=lambda r: r['count'], reverse=True)
    return results


def _compute_throughput(nodes, granularity='quarter',
                        start_date=None, end_date=None):
    """Bucket Done nodes with ``done_date`` into calendar buckets, segmented
    by context. ``granularity`` is 'month' | 'quarter' | 'year'; empty
    buckets between min and max are still emitted so the timeline reads
    continuously. ``start_date`` / ``end_date`` are ISO strings that
    optionally clip the range; None means "auto" (use the available data's
    natural extent). Per-node hours use captured actual time when present,
    otherwise the forecast estimate; each segment carries its ``nodes``
    list (``(name, hours)`` tuples, hours-descending) for tooltips."""
    from models import blend_time_estimate

    if granularity not in ('month', 'quarter', 'year'):
        granularity = 'quarter'

    def _hours(n):
        actual = blend_time_estimate(
            n.actual_time_lower, n.actual_time_point, n.actual_time_upper)
        if actual > 0 and (n.actual_time_lower is not None
                           or n.actual_time_point is not None
                           or n.actual_time_upper is not None):
            return actual
        return n.time

    def _bucket_key(y, m):
        if granularity == 'month':
            return (y, m)
        if granularity == 'year':
            return (y,)
        # quarter
        return (y, (m - 1) // 3 + 1)

    def _bucket_label(key):
        if granularity == 'year':
            return str(key[0])
        if granularity == 'month':
            return f'{_MONTH_ABBR[key[1] - 1]} {key[0]}'
        return f'{key[0]} Q{key[1]}'

    def _next_key(key):
        if granularity == 'year':
            return (key[0] + 1,)
        if granularity == 'month':
            y, m = key
            return (y + 1, 1) if m == 12 else (y, m + 1)
        # quarter
        y, q = key
        return (y + 1, 1) if q == 4 else (y, q + 1)

    buckets = defaultdict(lambda: defaultdict(list))
    for n in nodes:
        if not n.done_date:
            continue
        try:
            y_str, m_str, _ = n.done_date.split('-')
            y, m = int(y_str), int(m_str)
        except (ValueError, AttributeError):
            continue
        if start_date and n.done_date < start_date:
            continue
        if end_date and n.done_date > end_date:
            continue
        ctx = n.context or 'No Context'
        buckets[_bucket_key(y, m)][ctx].append((n.name, _hours(n)))

    if not buckets:
        return []

    keys_sorted = sorted(buckets.keys())
    cur, last = keys_sorted[0], keys_sorted[-1]
    full_keys = []
    # Cap the synthesised fill so a wide date range at month granularity
    # can't run away with the chart (e.g. 5 years * 12 = 60 bars max).
    while cur <= last and len(full_keys) < 120:
        full_keys.append(cur)
        cur = _next_key(cur)

    rows = []
    for k in full_keys:
        ctxs = buckets.get(k, {})
        segments = []
        for ctx, items in ctxs.items():
            items.sort(key=lambda x: x[1], reverse=True)
            segments.append({
                'context': ctx,
                'hours': sum(h for _, h in items),
                'nodes': items,
            })
        segments.sort(key=lambda s: s['hours'], reverse=True)
        rows.append({
            'label': _bucket_label(k),
            'segments': segments,
            'total_hours': sum(s['hours'] for s in segments),
        })
    return rows


_MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _get_limits():
    """Read analyze limits from user settings, with defaults."""
    return ConfigManager.get_analyze_limits()


def _milestones_as_transparent_checkpoints(nodes):
    """Return a scoring view where Milestones carry no own value or time.

    Goal ranking answers "what body of work is worth pursuing?" Milestones
    are checkpoints inside that body of work, so they should let prerequisite
    value flow through without adding their own ratings to the ROI numerator.
    """
    return [
        replace(n, value_mode='inherited', time_mode='inherited')
        if n.type == 'Milestone' else n
        for n in nodes
    ]


def _rank_goals(goals, all_nodes, edges, priority_goals, hp,
                with_scores=False, with_components=False):
    """Rank goals by ROI — prerequisite-subtree value per unit of time,
    scaled by priority-rank boost and context weight.

    Goals are sinks in the prereq DAG (work flows into them), so the
    scoring module's forward ``total_value`` collapses to a Goal's own
    intrinsic value. We invert Hard/Soft edges and run the same
    ``total_value`` machinery on the flipped graph instead, yielding
    IV(goal) + Σ d_H^depth * IV(prereq) over the prereq subtree.

    That raw value is extensive — it grows with subtree size — so alone
    it just ranks goals by how big they are. Dividing by the goal's
    aggregate cost turns it into a priority signal. Cost is the
    beta-compressed sum of remaining hard-prereq time, mirroring the
    time term of ``perceived_cost`` (effort is omitted — a 1-10 rating
    has no meaningful subtree aggregate). Final score:

        TV / cost * rank_boost * context_weight * density_mult

    where density_mult = 1 / max(1, |B_goals|)^alpha_goal damps Goals
    sharing a (context, subcontext) bucket with other open Goals — the
    Goal-level analogue of the leaf-node ``alpha`` density correction.
    Bucket counts use Goal headcount only (not scored nodes) and exclude
    Done goals. alpha_goal=0 disables the correction.

    rank_boost gives priority rank 1 the full ``goal_boost``, rank 2 66%
    of the bump, rank 3 33%. Returns goals sorted by score descending;
    with ``with_scores`` returns ``(goal, score)`` tuples instead.
    """
    w_v = hp.get('w_v', 1.0)
    w_i = hp.get('w_i', 1.0)
    d_H = hp.get('d_H', 0.6)
    d_S = hp.get('d_S', 0.40)
    d_Syn_pair = hp.get('d_Syn_pair', 0.10)
    d_Syn_mul = hp.get('d_Syn_mul', 0.40)
    cross_context_mult = hp.get('cross_context_mult', 1.0)
    w_t = hp.get('w_t', 1.0)
    beta = hp.get('beta', 0.85)
    goal_boost = hp.get('goal_boost', 1.5)
    alpha_goal = hp.get('alpha_goal', 0.20)
    rank_multipliers = [
        goal_boost,
        1 + (goal_boost - 1) * 0.66,
        1 + (goal_boost - 1) * 0.33,
    ]
    context_weights = ConfigManager.get_context_weights() or {}

    # Goal-only bucket counts for the density correction. Done Goals are
    # excluded — they're not competing for sidebar attention. Null-context
    # Goals (rare) keep their own bucket via the None key, mirroring how
    # scored-node bucketing treats (None, None) below.
    goal_bucket_counts: dict = defaultdict(int)
    for g in all_nodes:
        if g.type != 'Goal' or g.status == STATUS_DONE:
            continue
        goal_bucket_counts[(g.context, g.subcontext)] += 1

    # Invert Hard/Soft edges so the cascade walks upstream toward prereqs.
    # Helps is symmetric (bidirectional), so leave it alone.
    inverted = []
    for e in edges:
        if e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
            inverted.append({'source': e['target'], 'target': e['source'],
                             'type': e['type']})
        else:
            inverted.append(e)

    rank_nodes = _milestones_as_transparent_checkpoints(all_nodes)
    all_nodes_dict = {n.name: n for n in rank_nodes}
    H_out, S_out, Syn, _ = _scoring_build_adjacency(
        inverted, set(all_nodes_dict.keys()))

    def _hard_subtree_remaining(goal_name):
        """Sum of remaining (non-Done) time over the hard-prereq subtree.
        Inverted H_out walks goal -> prereqs, so this is the whole body
        of hard work still owed before the goal can complete."""
        visited = set()
        queue = list(H_out.get(goal_name, []))
        while queue:
            cur = queue.pop()
            if cur in visited:
                continue
            visited.add(cur)
            for nxt in H_out.get(cur, []):
                if nxt not in visited:
                    queue.append(nxt)
        total = 0.0
        for name in visited:
            n = all_nodes_dict.get(name)
            if n is not None and n.status != STATUS_DONE:
                total += n.time
        return total

    memo: dict = {}
    scored = []
    for g in goals:
        tv = total_value(
            g.name, set(), all_nodes_dict, H_out, S_out, Syn,
            w_v, w_i, d_H, d_S, d_Syn_pair, d_Syn_mul, memo,
            cross_context_mult=cross_context_mult,
        )
        remaining_time = _hard_subtree_remaining(g.name)
        cost = 1.0 + w_t * (remaining_time ** beta)
        raw = tv / cost
        rank_mult = 1.0
        rank_idx = None
        if g.name in priority_goals:
            ri = priority_goals.index(g.name)
            if ri < 3:
                rank_mult = rank_multipliers[ri]
                rank_idx = ri
        context_weight = context_weights.get(g.context, 1.0) if g.context else 1.0
        bucket_count = goal_bucket_counts.get((g.context, g.subcontext), 1)
        # Done Goals are excluded from the bucket count, so they would key to
        # 0 (defaultdict default) if requested directly — but Done Goals also
        # rarely flow into _rank_goals callers. Floor at 1 to mirror the
        # max(1, ...) guard in scoring.score_nodes.
        bucket_count = max(1, bucket_count)
        density_mult = 1.0 / (bucket_count ** alpha_goal) if alpha_goal > 0 else 1.0
        score = raw * rank_mult * context_weight * density_mult
        scored.append((g, score, {
            'score': score, 'raw': raw, 'tv': tv, 'cost': cost,
            'remaining_time': remaining_time, 'rank_mult': rank_mult,
            'rank_idx': rank_idx, 'context_weight': context_weight,
            'bucket_count': bucket_count, 'alpha_goal': alpha_goal,
            'density_mult': density_mult,
        }))

    scored.sort(key=lambda x: x[1], reverse=True)
    if with_components:
        return [(g, comp) for g, _, comp in scored]
    if with_scores:
        return [(g, s) for g, s, _ in scored]
    return [g for g, _, _ in scored]


def explain_goal(goal_name, all_nodes, edges, hp, priority_goals):
    """Explain-modal breakdown for a Goal node.

    ``scoring.explain_score`` walks the prereq DAG *forward*, summing what a
    node unlocks. Goals are sinks (work flows into them, nothing flows out),
    so that forward cascade collapses to the Goal's own intrinsic value and
    explain_score correctly reports them as not-ranked. The meaningful
    question for a Goal is the inverse: how much prerequisite value/work
    does it subsume, and what is that worth per unit of remaining time —
    exactly what ``_rank_goals`` scores.

    This stitches the two correct halves together:

      * value composition + contributors — ``explain_score`` run on the
        Hard/Soft-*inverted* edge set, so its forward cascade now walks the
        prerequisite subtree. Helps edges are symmetric and left alone.
      * headline score + cost — taken straight from ``_rank_goals`` so the
        modal's number matches the Goals sidebar and Analyze tab exactly.

    Fields that have no meaning for a Goal are neutralised rather than left
    showing stale forward-graph values: eligibility is forced True (Goals
    *are* ranked, just on the inverted graph). The density adjustment is
    populated from ``_rank_goals`` (Goal-only bucket count + ``alpha_goal``),
    not from ``score_nodes`` (which excludes Goals from leaf-level buckets).

    Returns ``(breakdown, normalized)``; ``normalized`` is the 0-100 score
    against the top-ranked Goal. Returns ``None`` if ``goal_name`` is not a
    Goal in ``all_nodes``.
    """
    node = next((n for n in all_nodes if n.name == goal_name), None)
    if node is None or node.type != 'Goal':
        return None

    goals = [n for n in all_nodes if n.type == 'Goal']
    comps = {g.name: c for g, c in _rank_goals(
        goals, all_nodes, edges, priority_goals, hp, with_components=True)}
    me = comps.get(goal_name)
    if me is None:
        return None

    valid = [c['score'] for c in comps.values() if c['score'] >= 0]
    top = max(valid) if valid else 0.0
    normalized = round(me['score'] / top * 100) if top > 0 else None

    # Invert Hard/Soft so explain_score's forward cascade walks prereqs.
    inverted = []
    for e in edges:
        if e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
            inverted.append({'source': e['target'], 'target': e['source'],
                             'type': e['type']})
        else:
            inverted.append(e)

    explain_nodes = _milestones_as_transparent_checkpoints(all_nodes)
    bd = explain_score(goal_name, explain_nodes, inverted, hp, priority_goals)
    if bd is None:
        return None

    bd['is_goal'] = True
    bd['eligible'] = True
    bd['block_reason'] = None
    bd['score'] = round(me['score'], 2)
    bd['raw_score'] = me['raw']
    bd['cost'] = {
        'goal': True,
        'remaining_time': me['remaining_time'],
        'cost': me['cost'],
        'time_overridden': False,
    }
    if me['rank_idx'] is not None:
        bd['goal_boost'] = {
            'multiplier': me['rank_mult'],
            'goal': goal_name,
            'rank': me['rank_idx'] + 1,
        }
    else:
        bd['goal_boost'] = None
    bd['context_adjustment'] = {
        'weight': me['context_weight'],
        'n_bucket': me['bucket_count'],
        'alpha': me['alpha_goal'],
        'density_mult': me['density_mult'],
        'combined_multiplier': me['context_weight'] * me['density_mult'],
    }
    return bd, normalized


def _compute_goal_comparison(nodes, edges, hard_rev, prereq_rev, limits):
    """Compute goal stats and pairwise overlap using in-memory adjacency.

    Ranks goals via _rank_goals (prereq-subtree value per unit of remaining
    time, boosted by priority rank and context weight), then caps to the top
    N to keep visualizations readable. Progress is computed over hard
    prerequisites only (those gate completion); pairwise overlap is computed
    over hard + soft prerequisites (the full body of prep work shared between
    goals).
    """
    all_goals = [n for n in nodes if n.type == 'Goal']
    node_map = {n.name: n for n in nodes}
    priority_goals = ConfigManager.get_priority_goals()
    hp = ConfigManager.get_hyperparams()

    # Rank and cap
    ranked = _rank_goals(all_goals, nodes, edges, priority_goals, hp)
    goals = ranked[:limits.get('goals', 75)]
    total_goal_count = len(all_goals)

    def _walk_back(goal_name, adjacency):
        """BFS backward through the given reverse adjacency map."""
        visited = set()
        queue = list(adjacency.get(goal_name, []))
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            for prev_node in adjacency.get(current, []):
                if prev_node not in visited:
                    queue.append(prev_node)
        return visited

    goal_rows = []
    prereq_subtrees = {}
    for g in goals:
        # Hard subtree drives completion stats (hard prereqs gate the goal).
        hard_subtree = _walk_back(g.name, hard_rev)
        sub_nodes = [node_map[name] for name in hard_subtree if name in node_map]
        total = len(sub_nodes)
        done = sum(1 for n in sub_nodes if n.status == STATUS_DONE)
        blocked = sum(1 for n in sub_nodes if n.status == STATUS_BLOCKED)
        remaining = sum(n.time for n in sub_nodes if n.status != STATUS_DONE)
        pct = round(done / total * 100) if total else 0
        priority_rank = (priority_goals.index(g.name) + 1) if g.name in priority_goals else None
        goal_rows.append({
            'name': g.name,
            'pct': pct,
            'done': done,
            'total': total,
            'remaining': remaining,
            'blocked': blocked,
            'priority_rank': priority_rank,
        })
        # Hard + soft subtree drives shared-prerequisite overlap.
        prereq_subtrees[g.name] = _walk_back(g.name, prereq_rev)
    # goal_rows stays in _rank_goals ROI order (highest priority first) — both
    # the completion chart and the overlap heatmap render in that order.

    # Pairwise overlap (only among top goals) — uses combined hard + soft prereqs
    overlap_rows = []
    goal_names = [g.name for g in goals]
    for i in range(len(goal_names)):
        for j in range(i + 1, len(goal_names)):
            a, b = goal_names[i], goal_names[j]
            sa, sb = prereq_subtrees.get(a, set()), prereq_subtrees.get(b, set())
            shared = sa & sb
            union = sa | sb
            if shared:
                overlap_rows.append({
                    'goal_a': a,
                    'goal_b': b,
                    'shared': len(shared),
                    'jaccard': round(len(shared) / len(union) * 100) if union else 0,
                })
    overlap_rows.sort(key=lambda r: r['shared'], reverse=True)

    return goal_rows, overlap_rows, total_goal_count


def _compute_ratings(nodes):
    """Compute average value, interest, difficulty per context for non-Done nodes."""
    all_by_ctx = defaultdict(lambda: {'total': 0, 'done': 0})
    active = [n for n in nodes if n.status != STATUS_DONE]
    for n in nodes:
        ctx = n.context or 'No Context'
        all_by_ctx[ctx]['total'] += 1
        if n.status == STATUS_DONE:
            all_by_ctx[ctx]['done'] += 1

    by_ctx = defaultdict(lambda: {'values': [], 'interests': [], 'difficulties': [], 'count': 0})
    for n in active:
        ctx = n.context or 'No Context'
        by_ctx[ctx]['values'].append(n.value)
        by_ctx[ctx]['interests'].append(n.interest)
        by_ctx[ctx]['difficulties'].append(n.difficulty)
        by_ctx[ctx]['count'] += 1

    results = []
    for ctx, d in by_ctx.items():
        c = d['count']
        totals = all_by_ctx[ctx]
        completion = round(totals['done'] / totals['total'] * 100) if totals['total'] else 0
        results.append({
            'context': ctx, 'count': c,
            'avg_value': round(sum(d['values']) / c, 1),
            'avg_interest': round(sum(d['interests']) / c, 1),
            'avg_difficulty': round(sum(d['difficulties']) / c, 1),
            'completion_pct': completion,
        })
    results.sort(key=lambda r: r['count'], reverse=True)
    return results


def _compute_context_coverage(nodes):
    """Per-context active-node count and time, with a subcontext breakdown.

    Each ctx_data row carries a ``segments`` list partitioning that context's
    active nodes by subcontext; nodes with no subcontext form a
    ``"(No subcontext)"`` segment. Segment times sum exactly to the row's
    ``time``, so a stacked bar of the segments matches the context total.
    """
    configured_contexts = ConfigManager.get_contexts()
    weights = ConfigManager.get_context_weights()
    active = [n for n in nodes if n.status != STATUS_DONE]

    ctx_counts = defaultdict(lambda: {
        'count': 0, 'time': 0.0,
        'segments': defaultdict(lambda: {'count': 0, 'time': 0.0}),
    })
    for n in active:
        ctx = n.context or 'No Context'
        d = ctx_counts[ctx]
        d['count'] += 1
        d['time'] += n.time
        seg = n.subcontext or '(No subcontext)'
        d['segments'][seg]['count'] += 1
        d['segments'][seg]['time'] += n.time

    def _row(ctx, weight):
        d = ctx_counts.get(ctx)
        if d is None:
            return {'context': ctx, 'count': 0, 'time': 0.0,
                    'weight': weight, 'segments': []}
        # Named subcontexts (largest time first), then "(No subcontext)".
        named = sorted(
            (kv for kv in d['segments'].items() if kv[0] != '(No subcontext)'),
            key=lambda kv: kv[1]['time'], reverse=True)
        ordered = list(named)
        rest = d['segments'].get('(No subcontext)')
        if rest is not None:
            ordered.append(('(No subcontext)', rest))
        return {
            'context': ctx,
            'count': d['count'],
            'time': d['time'],
            'weight': weight,
            'segments': [{'name': name, 'count': s['count'], 'time': s['time']}
                         for name, s in ordered],
        }

    ctx_data = [_row(ctx, float(weights.get(ctx, 1.0)))
                for ctx in configured_contexts]
    if 'No Context' in ctx_counts:
        ctx_data.append(_row('No Context', 1.0))
    ctx_data.sort(key=lambda r: r['time'])
    return ctx_data


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

_BG = '#1a1d21'
_CARD_BG = '#2b3035'
_BORDER = '#495057'
_STATUS_COLORS = {STATUS_OPEN: '#0d6efd', STATUS_BLOCKED: '#dc3545', STATUS_DONE: '#198754'}
_CHART_CFG = {"displayModeBar": False}

# Bar-fill overrides for node types whose BADGE_PALETTE colour is tuned for
# small badge areas and overpowers when applied to large bar fills. Goal's
# canvas yellow is engineered to read at a glance on the graph; in a long
# horizontal bar it dominates the row. Falls through to BADGE_PALETTE for
# any type not listed here.
_CHART_BAR_FILLS = {
    'Goal': '#a89a2c',  # muted olive-yellow; same hue family, lower chroma
}


def _chart_bar_color(node_type):
    if node_type in _CHART_BAR_FILLS:
        return _CHART_BAR_FILLS[node_type]
    return BADGE_PALETTE.get(node_type, ('#6c757d', '#fff'))[0]


def _base_layout(**overrides):
    """Return a Plotly layout dict with consistent dark theme styling."""
    layout = dict(
        template="plotly_dark",
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        font=dict(size=12),
    )
    layout.update(overrides)
    return layout


def _card(children):
    """Wrap a visual in the standard Analyze card — a subtly raised panel
    with a soft border and rounded corners, matching the overview tiles."""
    return html.Div(children, style={
        "backgroundColor": _BG,
        "borderRadius": "6px",
        "padding": "12px 16px",
    })


def _integer_dtick(max_val):
    """Pick a nice integer tick step aiming for ~5-8 ticks on an axis."""
    if max_val <= 5:
        return 1
    if max_val <= 10:
        return 2
    if max_val <= 25:
        return 5
    if max_val <= 50:
        return 10
    if max_val <= 100:
        return 20
    if max_val <= 250:
        return 50
    if max_val <= 500:
        return 100
    return max(1, round(max_val / 6))


def _friendly_xticks(max_val: float) -> tuple[list, list]:
    """Return (tickvals, ticktext) for an hours-valued axis with friendly labels.

    Picks a step that scales with the user's productivity settings — years for
    very large ranges, then months, weeks, hours — and labels each tick via
    ``ConfigManager.format_time_friendly`` so the axis reads "1y" / "2m" /
    "3w" / "8h" instead of raw hour counts.
    """
    if max_val <= 0:
        return [0], ["0h"]
    settings = ConfigManager.get_time_settings()
    hw = max(1, settings.get('hours_per_week', 40))
    hm = max(1, settings.get('hours_per_month', 160))
    hy = ConfigManager.HOURS_PER_YEAR_MULT * hm

    # Pick a step that gives roughly 4-7 ticks for the visible range.
    if max_val >= 4 * hy:
        step = hy
    elif max_val >= 1.5 * hy:
        step = hy / 2
    elif max_val >= 4 * hm:
        step = hm
    elif max_val >= 1.5 * hm:
        step = hm / 2
    elif max_val >= 4 * hw:
        step = hw
    elif max_val >= 1.5 * hw:
        step = hw / 2
    elif max_val >= 20:
        step = 5
    elif max_val >= 10:
        step = 2
    else:
        step = 1

    tickvals = [0]
    v = step
    while v <= max_val * 1.05:
        tickvals.append(round(v, 4))
        v += step
    ticktext = [ConfigManager.format_time_friendly(t) for t in tickvals]
    return tickvals, ticktext


def _log_time_ticks(min_val: float, max_val: float) -> tuple[list, list]:
    """Return (tickvals, ticktext) for a log-scaled hours axis, placing ticks
    at 1-2-5 ×10^k values within range and labelling each via
    ``ConfigManager.format_time_friendly``."""
    import math as _math
    if max_val <= 0:
        return [1.0], [ConfigManager.format_time_friendly(1.0)]
    lo = max(0.5, min_val)
    vals = []
    k = _math.floor(_math.log10(lo))
    while True:
        for base in (1, 2, 5):
            # 10.0 ** k keeps v a float — format_time_friendly rounds with
            # ndigits, which leaves ints unchanged, and int.is_integer()
            # only exists on Python 3.12+.
            v = base * (10.0 ** k)
            if v < lo / 1.5:
                continue
            if v > max_val * 1.5:
                return vals, [ConfigManager.format_time_friendly(x) for x in vals]
            vals.append(v)
        k += 1


def _hbar_chart(names, values, colors=None, hover_texts=None, x_title=None,
                height=None, integer_x=False, friendly_x=False):
    """Create a standard horizontal bar chart figure.

    integer_x: force integer-only x-axis ticks (for counts, not hours).
    friendly_x: when the x values are hours, render ticks via
        ConfigManager.format_time_friendly (e.g. "1y", "2m") instead of raw
        hour counts. Mutually exclusive with integer_x.
    """
    if not names:
        return None
    color = colors if colors else '#0d6efd'
    # Reverse so largest is at top (Plotly draws bottom-up)
    names = list(reversed(names))
    values = list(reversed(values))
    if isinstance(color, list):
        color = list(reversed(color))
    if hover_texts:
        hover_texts = list(reversed(hover_texts))

    if height is None:
        height = max(180, len(names) * 28 + 60)

    fig = go.Figure(go.Bar(
        y=names, x=values, orientation='h',
        marker_color=color, opacity=0.9,
        hovertext=hover_texts,
        hoverinfo='text' if hover_texts else 'x+y',
    ))
    xaxis = dict(title=x_title) if x_title else {}
    if integer_x and values:
        xaxis['tickmode'] = 'linear'
        xaxis['tick0'] = 0
        xaxis['dtick'] = _integer_dtick(max(values))
        xaxis['tickformat'] = 'd'
    elif friendly_x and values:
        tickvals, ticktext = _friendly_xticks(max(values))
        xaxis['tickmode'] = 'array'
        xaxis['tickvals'] = tickvals
        xaxis['ticktext'] = ticktext
    fig.update_layout(**_base_layout(
        height=height,
        margin=dict(l=10, r=20, t=10, b=30),
        yaxis=dict(automargin=True, ticklabelstandoff=8, **_label_axis(names)),
        xaxis=xaxis,
    ))
    return fig


# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------

def _render_overview(metrics):
    cards = [
        ('Goals', str(metrics['goal_count']), '#ffc107'),
        ('Milestones', str(metrics['milestone_count']), '#0dcaf0'),
        ('Active Nodes', str(metrics['active_count']), '#0d6efd'),
        (STATUS_DONE, str(metrics['done_count']), '#198754'),
        (STATUS_BLOCKED, f"{metrics['blocked_pct']}%", '#dc3545'),
    ]
    cols = []
    for label, value, color in cards:
        cols.append(html.Div(
            html.Div([
                html.Div(value, style={
                    "fontSize": "1.8rem", "fontWeight": "700", "color": color,
                }),
                html.Div(label, className="text-muted small"),
            ], style={
                "padding": "14px 18px", "borderRadius": "6px",
                "backgroundColor": _CARD_BG,
                "textAlign": "center",
            }),
            style={"flex": "1 1 0", "minWidth": "0"},
        ))
    return html.Div(cols, style={
        "display": "flex", "gap": "1rem",
    }, className="mb-3")


def _render_bottleneck_chart(data, height=None):
    title = html.H6("Bottleneck Analysis", className="text-muted mb-1")
    if not data:
        return _card([title, html.P("No bottleneck nodes found.",
                                    className="text-muted small")])

    fmt = ConfigManager.format_time_friendly
    names = [d['name'] for d in data]
    values = [d['cascade'] for d in data]
    # Blocked nodes flag red; open nodes take the bar-fill palette colour
    # for their type (muted variant of the badge colour where defined).
    colors = [
        _STATUS_COLORS[STATUS_BLOCKED] if d['status'] == STATUS_BLOCKED
        else _chart_bar_color(d['type'])
        for d in data
    ]
    hover = [
        f"<b>{d['name']}</b><br>"
        f"Cascade: {d['cascade']}<br>"
        f"Direct unlocks: {d['direct_unlocks']}<br>"
        f"Type: {d['type']}<br>"
        f"Time: {fmt(d['time'])}"
        for d in data
    ]

    fig = _hbar_chart(names, values, colors=colors, hover_texts=hover,
                      x_title="Downstream nodes reached", integer_x=True,
                      height=height)
    return _card([title, dcc.Graph(figure=fig, config=_CHART_CFG)])


def _render_hub_chart(data, height=None):
    """Companion to the bottleneck chart. Bottleneck asks 'what unlocks the
    most downstream?'; Hub asks 'what is most integrated into the user's
    thinking?'. Same horizontal-bar treatment so the comparison reads as
    intentional."""
    title = html.H6("Hub Nodes", className="text-muted mb-1")
    if not data:
        return _card([title, html.P(
            "No hub nodes found — nodes need edges flowing in AND out to "
            "qualify.", className="text-muted small")])

    names = [d['name'] for d in data]
    values = [round(d['score'], 2) for d in data]
    colors = [
        _STATUS_COLORS[STATUS_BLOCKED] if d['status'] == STATUS_BLOCKED
        else _chart_bar_color(d['type'])
        for d in data
    ]

    def _plural(n, word):
        return f"{n} {word}{'s' if n != 1 else ''}"

    hover = [
        f"<b>{d['name']}</b><br>"
        f"Hub score: {d['score']:.2f}<br>"
        f"  ↑ {_plural(d['in_count'], 'prereq')} feeding in<br>"
        f"  ↓ {_plural(d['out_count'], 'dependent')} flowing out<br>"
        f"  ⟷ {_plural(d['helps_count'], 'synergy partner')}<br>"
        f"  Spans {_plural(d['distinct_contexts'], 'context')}<br>"
        f"Type: {d['type']}"
        for d in data
    ]

    fig = _hbar_chart(names, values, colors=colors, hover_texts=hover,
                      x_title="Hub score", height=height)
    return _card([title, dcc.Graph(figure=fig, config=_CHART_CFG)])


def _render_goal_comparison(goal_rows, overlap_rows, goal_names_ordered):
    fmt = ConfigManager.format_time_friendly

    if not goal_rows:
        return _card(html.P("No goals defined.", className="text-muted small"))

    sections_left = []
    sections_right = []

    # --- Shared y-axis order (used by both charts) ---
    # goal_rows is in ROI order (highest priority first); both charts place
    # the highest-priority goal at the top.
    y_order = [g['name'] for g in goal_rows]
    n_goals = len(y_order)
    shared_height = max(300, n_goals * 32 + 80)
    shared_margin = dict(l=10, r=20, t=30, b=30)

    # --- Completion bar chart (stacked: done + remaining) ---
    sorted_goals = list(reversed(goal_rows))  # reversed for Plotly bottom-up drawing
    bar_names = [g['name'] for g in sorted_goals]
    done_pcts = [g['pct'] for g in sorted_goals]
    remaining_pcts = [100 - g['pct'] for g in sorted_goals]
    hover_done = [
        f"<b>{g['name']}</b><br>"
        f"Done: {g['done']} / {g['total']} hard ({g['pct']}%)<br>"
        f"Remaining: {fmt(g['remaining'])}<br>"
        f"Blocked: {g['blocked']}"
        + (f"<br>Priority #{g['priority_rank']}" if g['priority_rank'] else "")
        for g in sorted_goals
    ]
    hover_remaining = [
        f"<b>{g['name']}</b><br>Remaining: {100 - g['pct']}%"
        for g in sorted_goals
    ]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=bar_names, x=done_pcts, orientation='h',
        marker_color='#198754', opacity=0.9, name=STATUS_DONE,
        hovertext=hover_done, hoverinfo='text',
    ))
    # Faint remaining track: keeps a common 100% baseline and a hover target
    # for zero-progress goals (whose Done segment is zero-width).
    fig.add_trace(go.Bar(
        y=bar_names, x=remaining_pcts, orientation='h',
        marker_color='#495057', opacity=0.15, name='Remaining',
        hovertext=hover_remaining, hoverinfo='text',
    ))
    fig.update_layout(**_base_layout(
        barmode='stack', height=shared_height,
        margin=shared_margin,
        yaxis=dict(automargin=True, ticklabelstandoff=8,
                   categoryorder='array', categoryarray=bar_names,
                   **_label_axis(bar_names)),
        xaxis=dict(title="Completion %", range=[0, 100], showgrid=False),
    ))
    sections_left.append(html.H6("Completion", className="text-muted mb-1"))
    sections_left.append(html.Small(
        "Hard prerequisites only",
        className="text-muted d-block mb-2",
        style={"fontSize": "0.75rem"},
    ))
    sections_left.append(dcc.Graph(figure=fig, config=_CHART_CFG))

    # --- Shared Prerequisites Heatmap ---
    if overlap_rows and len(goal_names_ordered) > 1:
        gnames = goal_names_ordered
        n = len(gnames)
        idx = {name: i for i, name in enumerate(gnames)}
        # Build symmetric matrix
        matrix = [[0] * n for _ in range(n)]
        for o in overlap_rows:
            i, j = idx.get(o['goal_a']), idx.get(o['goal_b'])
            if i is not None and j is not None:
                matrix[i][j] = o['shared']
                matrix[j][i] = o['shared']

        hover_matrix = [['' for _ in range(n)] for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i == j:
                    hover_matrix[i][j] = f"<b>{gnames[i]}</b>"
                else:
                    hover_matrix[i][j] = (
                        f"<b>{gnames[i]}</b> & <b>{gnames[j]}</b><br>"
                        f"Shared: {matrix[i][j]} nodes"
                    )

        # Use y_order (ROI order) for BOTH axes so the diagonal aligns
        # top-left to bottom-right; mask the upper-right triangle since the
        # matrix is symmetric. Plotly renders None cells as transparent.
        ordered_matrix = []
        ordered_hover = []
        for i, name_i in enumerate(y_order):
            src_i = idx.get(name_i)
            row, hover_row = [], []
            for j, name_j in enumerate(y_order):
                src_j = idx.get(name_j)
                if src_i is None or src_j is None or i < j:
                    row.append(None)
                    hover_row.append('')
                else:
                    row.append(matrix[src_i][src_j])
                    hover_row.append(hover_matrix[src_i][src_j])
            ordered_matrix.append(row)
            ordered_hover.append(hover_row)

        hm_fig = go.Figure(go.Heatmap(
            z=ordered_matrix, x=y_order, y=y_order,
            colorscale=[[0, _BG], [0.25, '#162d50'], [0.5, '#1a5276'], [0.75, '#2185d0'], [1, '#54b8ff']],
            hovertext=ordered_hover, hoverinfo='text',
            showscale=False,
        ))
        hm_fig.update_layout(**_base_layout(
            height=shared_height,
            margin=shared_margin,
            xaxis=dict(automargin=True, tickangle=-45, side='bottom',
                       showgrid=False, zeroline=False,
                       categoryorder='array', categoryarray=y_order,
                       **_label_axis(y_order)),
            yaxis=dict(automargin=True, ticklabelstandoff=8,
                       showgrid=False, zeroline=False,
                       autorange='reversed',
                       categoryorder='array', categoryarray=y_order,
                       **_label_axis(y_order)),
        ))

        sections_right.append(html.H6("Shared Prerequisites", className="text-muted mb-1"))
        sections_right.append(html.Small(
            "Hard + soft prerequisites",
            className="text-muted d-block mb-2",
            style={"fontSize": "0.75rem"},
        ))
        sections_right.append(dcc.Graph(figure=hm_fig, config=_CHART_CFG))

    # If no overlap data, show a message in the right column
    if not sections_right:
        sections_right.append(html.H6("Shared Prerequisites", className="text-muted mb-1"))
        sections_right.append(html.Small(
            "Hard + soft prerequisites",
            className="text-muted d-block mb-2",
            style={"fontSize": "0.75rem"},
        ))
        sections_right.append(html.P("No shared prerequisites between goals.", className="text-muted small"))

    return dbc.Row([
        dbc.Col(_card(sections_left), width=6),
        dbc.Col(_card(sections_right), width=6),
    ], className="g-3")


def _render_estimation_accuracy(rows):
    """Scatter of estimated vs. actual time for completed nodes, with a y=x
    reference line. Points above the line overran the estimate."""
    title = html.H6("By Node", className="text-muted mb-1")
    if not rows:
        return _card([title, html.P(
            "No completed nodes have actual-time data yet. Mark nodes Done "
            "with Reflection enabled to populate this chart.",
            className="text-muted small")])

    fmt = ConfigManager.format_time_friendly
    colors = ConfigManager.get_node_colors()

    all_vals = [r['estimate'] for r in rows] + [r['actual'] for r in rows]
    lo = min(v for v in all_vals if v > 0) * 0.7
    hi = max(all_vals) * 1.4

    fig = go.Figure()
    # y = x reference line \u2014 perfect estimation.
    fig.add_trace(go.Scatter(
        x=[lo, hi], y=[lo, hi], mode='lines',
        line=dict(color='#6c757d', dash='dash', width=1),
        hoverinfo='skip', showlegend=False,
    ))
    # One marker trace per node type so the legend doubles as a colour key.
    by_type = defaultdict(list)
    for r in rows:
        by_type[r['type']].append(r)
    for ntype, trows in sorted(by_type.items()):
        hover = []
        for r in trows:
            ratio = r['actual'] / r['estimate']
            hover.append(
                f"<b>{r['name']}</b><br>"
                f"Estimated: {fmt(r['estimate'])}<br>"
                f"Actual: {fmt(r['actual'])}<br>"
                f"{ratio:.1f}\u00d7 estimate"
            )
        fig.add_trace(go.Scatter(
            x=[r['estimate'] for r in trows],
            y=[r['actual'] for r in trows],
            mode='markers', name=ntype,
            marker=dict(size=9, color=colors.get(ntype, '#0d6efd'),
                        line=dict(width=1, color=_BG)),
            hovertext=hover, hoverinfo='text',
        ))

    tickvals, ticktext = _log_time_ticks(lo, hi)
    axis = dict(type='log', range=[math.log10(lo), math.log10(hi)],
                tickvals=tickvals, ticktext=ticktext,
                gridcolor='#343a40', automargin=True)
    fig.update_layout(**_base_layout(
        height=420, showlegend=True,
        margin=dict(l=50, r=20, t=10, b=45),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0),
        xaxis=dict(title="Estimated", **axis),
        yaxis=dict(title="Actual", **axis),
    ))
    return _card([
        title,
        dcc.Graph(figure=fig, config=_CHART_CFG),
    ])


_CTX_ACCURACY_MIN_N = 3  # min completed nodes for a context to get a box


def _render_context_accuracy_boxplot(rows):
    """Per-context box plots of the actual/estimate ratio. One box per context
    with at least `_CTX_ACCURACY_MIN_N` completed nodes; the dashed line marks
    a perfect 1× estimate. The ratio axis is log-scaled so 2× over and 0.5×
    under read as symmetric distances from centre."""
    import statistics
    by_ctx = defaultdict(list)
    for r in rows:
        if r.get('context'):
            by_ctx[r['context']].append(r)
    qualifying = {c: v for c, v in by_ctx.items()
                  if len(v) >= _CTX_ACCURACY_MIN_N}
    hidden = len(by_ctx) - len(qualifying)
    title = html.H6("By Context", className="text-muted mb-1")
    if not qualifying:
        return _card([title, html.P(
            f"Not enough completed nodes per context yet — a context needs "
            f"at least {_CTX_ACCURACY_MIN_N} with captured actual time.",
            className="text-muted small")])

    def _ratio(r):
        return r['actual'] / r['estimate']

    # Descending median order: the context that most chronically blows
    # past its estimate lands at the top, mirroring the Contexts row's
    # "biggest at top" convention. (Plotly horizontal box traces stack
    # first-added-at-top.)
    ordered = sorted(
        qualifying.items(),
        key=lambda kv: statistics.median([_ratio(r) for r in kv[1]]),
        reverse=True)

    # Soft filled boxes in a single blue; the 1× reference line conveys
    # over- vs. under-estimation by position.
    line_c = '#4f9ed9'
    fill_c = 'rgba(79,158,217,0.22)'

    fig = go.Figure()
    for ctx, ctx_rows in ordered:
        ratios = [_ratio(r) for r in ctx_rows]
        fig.add_trace(go.Box(
            x=ratios, name=ctx, orientation='h',
            boxpoints='all', jitter=0.4, pointpos=0, whiskerwidth=0.5,
            marker=dict(color=line_c, size=4, opacity=0.45),
            line=dict(color=line_c, width=1.5), fillcolor=fill_c,
            hoveron='points', customdata=[r['name'] for r in ctx_rows],
            hovertemplate=('<b>%{customdata}</b><br>'
                           '%{x:.2f}× estimate<extra></extra>'),
        ))

    all_ratios = [_ratio(r) for _, ctx_rows in ordered for r in ctx_rows]
    rmin, rmax = min(all_ratios), max(all_ratios)
    ticks = [t for t in (0.0625, 0.125, 0.25, 0.5, 1, 2, 4, 8, 16)
             if rmin / 1.3 <= t <= rmax * 1.3]
    if 1 not in ticks:
        ticks = sorted(ticks + [1])

    # Aim near the scatter's 420px so the two charts sit level side-by-side,
    # growing only when there are many contexts.
    height = max(420, len(ordered) * 42 + 80)
    fig.update_layout(**_base_layout(
        height=height, showlegend=False,
        margin=dict(l=10, r=20, t=10, b=40),
        xaxis=dict(type='log', title="Actual ÷ Estimated",
                   tickvals=ticks, ticktext=[f"{t:g}×" for t in ticks],
                   gridcolor='#343a40', automargin=True),
        yaxis=dict(automargin=True),
    ))
    fig.add_vline(x=1, line=dict(color='#6c757d', dash='dash', width=1))

    children = [
        title,
        dcc.Graph(figure=fig, config=_CHART_CFG),
    ]
    if hidden:
        children.append(html.P(
            f"{hidden} context(s) hidden — fewer than "
            f"{_CTX_ACCURACY_MIN_N} completed nodes.",
            className="text-muted small mt-1"))
    return _card(children)


def _render_reflection_drift_chart(rows, height=None, context_order=None):
    """Per-context mean drift (``reflect_X - X``) for V/I/D as a diverging
    heatmap. Red cells mean the user overrated initially (reflection is
    lower); blue cells mean the user underrated initially. Symmetric scale
    around 0 so cell colour reads as direction × magnitude at a glance.

    ``context_order`` (ascending — same as the Hours-by-Context bar chart)
    forces the row order to match the row's other panels; contexts below
    ``_REFLECTION_MIN_N`` appear as blank (NaN) rows so all panels line up."""
    title = html.H6("Reflection Drift by Context", className="text-muted mb-1")
    if not rows and not context_order:
        return _card([title, html.P(
            f"Not enough reflected nodes per context yet — a context "
            f"needs at least {_REFLECTION_MIN_N} re-rated nodes.",
            className="text-muted small")])

    by_ctx = {r['context']: r for r in rows}
    metric_keys = [('d_value', 'Value'), ('d_interest', 'Interest'),
                   ('d_difficulty', 'Difficulty')]

    contexts = context_order if context_order else [r['context'] for r in rows]

    z, hover = [], []
    for ctx in contexts:
        r = by_ctx.get(ctx)
        z_row, hover_row = [], []
        for attr, label in metric_keys:
            if r is None:
                z_row.append(None)
                hover_row.append(
                    f"<b>{ctx}</b><br>{label}: fewer than "
                    f"{_REFLECTION_MIN_N} reflected nodes")
                continue
            v = r[attr]
            z_row.append(v if v is not None else None)
            if v is None:
                hover_row.append(f"<b>{ctx}</b><br>{label}: no data")
            else:
                sign = '+' if v > 0 else ''
                hover_row.append(
                    f"<b>{ctx}</b><br>"
                    f"{label} drift: {sign}{v}<br>"
                    f"{r['count']} reflected node{'s' if r['count'] != 1 else ''}"
                )
        z.append(z_row)
        hover.append(hover_row)

    # Symmetric range so 0 maps to the colorscale midpoint. Cap at +/-3 to
    # keep colour resolution useful for the typical drift range; larger
    # magnitudes still saturate cleanly to the endpoints.
    drift_vals = [r[a] for r in rows for a, _ in metric_keys if r[a] is not None]
    abs_max = max((abs(v) for v in drift_vals), default=1)
    rng = max(1.0, min(3.0, round(abs_max + 0.5)))

    if height is None:
        height = max(200, len(contexts) * 32 + 80)

    fig = go.Figure(go.Heatmap(
        z=z, x=[label for _, label in metric_keys], y=contexts,
        colorscale=[[0, '#c0392b'], [0.5, _BG], [1, '#2185d0']],
        hovertext=hover, hoverinfo='text',
        showscale=True,
        colorbar=dict(title="Δ", len=0.5),
        zmin=-rng, zmax=rng, zmid=0,
    ))
    fig.update_layout(**_base_layout(
        height=height,
        margin=dict(l=10, r=20, t=10, b=30),
        # Plotly heatmap default is first-y-at-top, so callers pass
        # ``context_order`` already in the desired top-to-bottom sequence.
        yaxis=dict(automargin=True, ticklabelstandoff=8,
                   categoryorder='array', categoryarray=contexts,
                   **_label_axis(contexts)),
        xaxis=dict(side='bottom'),
    ))
    return _card([title, dcc.Graph(figure=fig, config=_CHART_CFG)])


def _render_throughput_chart(quarter_rows, granularity='quarter'):
    """Stacked vertical bar of hours completed per calendar bucket
    (month/quarter/year), segmented by context. No legend — context name
    plus a top-N list of completed nodes (with hours) is revealed via hover."""
    fmt = ConfigManager.format_time_friendly
    title_word = {'month': 'Month', 'quarter': 'Quarter',
                  'year': 'Year'}.get(granularity, 'Quarter')
    title = html.H6(f"Hours Completed by {title_word}",
                    className="text-muted mb-1")
    if not quarter_rows or all(not r['segments'] for r in quarter_rows):
        return _card([title, html.P(
            "No nodes with a completion date yet. Mark nodes Done to "
            "populate this chart.", className="text-muted small")])

    # Stable per-context colour, ordered by total throughput so the largest
    # context gets the first palette colour and the stacking order is
    # consistent across bars.
    total_per_ctx = defaultdict(float)
    for r in quarter_rows:
        for s in r['segments']:
            total_per_ctx[s['context']] += s['hours']
    ctx_order = sorted(total_per_ctx.keys(),
                       key=lambda c: total_per_ctx[c], reverse=True)
    ctx_color = {
        c: (_NO_SUBCONTEXT_COLOR if c == 'No Context'
            else _SUBCONTEXT_PALETTE[i % len(_SUBCONTEXT_PALETTE)])
        for i, c in enumerate(ctx_order)
    }

    q_labels = [r['label'] for r in quarter_rows]

    def _tooltip(label, ctx, seg):
        n_nodes = len(seg['nodes'])
        lines = [
            f"<b>{label} · {ctx}</b>",
            f"{fmt(seg['hours'])} across {n_nodes} node"
            f"{'s' if n_nodes != 1 else ''}",
        ]
        for name, h in seg['nodes'][:5]:
            nm = name if len(name) <= 30 else name[:29] + '…'
            lines.append(f"  • {nm} ({fmt(h)})")
        if n_nodes > 5:
            lines.append(f"  … and {n_nodes - 5} more")
        return '<br>'.join(lines)

    fig = go.Figure()
    for ctx in ctx_order:
        ys, hovers = [], []
        for r in quarter_rows:
            seg = next((s for s in r['segments'] if s['context'] == ctx), None)
            if seg and seg['hours'] > 0:
                ys.append(seg['hours'])
                hovers.append(_tooltip(r['label'], ctx, seg))
            else:
                ys.append(0)
                hovers.append('')
        fig.add_trace(go.Bar(
            x=q_labels, y=ys, name=ctx,
            marker_color=ctx_color[ctx], marker_line=dict(color=_BG, width=1),
            opacity=0.9, hovertext=hovers, hoverinfo='text',
        ))

    max_total = max((r['total_hours'] for r in quarter_rows), default=0)
    tickvals, ticktext = _friendly_xticks(max_total)
    fig.update_layout(**_base_layout(
        barmode='stack', height=360,
        margin=dict(l=10, r=20, t=10, b=40),
        xaxis=dict(automargin=True, categoryorder='array',
                   categoryarray=q_labels),
        yaxis=dict(tickmode='array', tickvals=tickvals, ticktext=ticktext,
                   automargin=True),
    ))
    return _card([title, dcc.Graph(figure=fig, config=_CHART_CFG)])


def _render_ratings_chart(data, height=None, context_order=None):
    """``context_order`` (ascending — same as the Hours-by-Context bar chart)
    forces the row order to match the row's other panels; contexts absent
    from ``data`` (e.g. all nodes Done) appear as blank rows so the panels
    stay row-aligned."""
    if not data and not context_order:
        return _card([
            html.H6("Ratings by Context", className="text-muted mb-1"),
            html.P("No active nodes.", className="text-muted small"),
        ])

    by_ctx = {d['context']: d for d in data}
    contexts = context_order if context_order else [d['context'] for d in data]
    metric_keys = [('avg_value', 'Value'), ('avg_interest', 'Interest'),
                   ('avg_difficulty', 'Difficulty')]

    z, hover = [], []
    for ctx in contexts:
        d = by_ctx.get(ctx)
        if d is None:
            z.append([None, None, None])
            hover.append([f"<b>{ctx}</b><br>No active nodes"] * 3)
            continue
        z.append([d['avg_value'], d['avg_interest'], d['avg_difficulty']])
        row_hover = []
        for attr, label in metric_keys:
            row_hover.append(
                f"<b>{ctx}</b><br>"
                f"{label}: {d[attr]}<br>"
                f"{d['count']} active nodes"
            )
        hover.append(row_hover)

    if height is None:
        height = max(200, len(contexts) * 32 + 80)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[label for _, label in metric_keys],
        y=contexts,
        colorscale=[[0, _BG], [0.25, '#162d50'], [0.5, '#1a5276'],
                    [0.75, '#2185d0'], [1.0, '#54b8ff']],
        hovertext=hover, hoverinfo='text',
        showscale=True,
        colorbar=dict(title="Avg", len=0.5),
        zmin=1, zmax=10,
    ))
    fig.update_layout(**_base_layout(
        height=height,
        margin=dict(l=10, r=20, t=10, b=30),
        # Plotly heatmap default is first-y-at-top, so callers pass
        # ``context_order`` already in the desired top-to-bottom sequence.
        yaxis=dict(automargin=True, ticklabelstandoff=8,
                   categoryorder='array', categoryarray=contexts,
                   **_label_axis(contexts)),
        xaxis=dict(side='bottom'),
    ))
    return _card([
        html.H6("Ratings by Context", className="text-muted mb-1"),
        dcc.Graph(figure=fig, config=_CHART_CFG),
    ])


# Categorical palette for subcontext segments. Tuned to the muted, deeper
# register of config.BADGE_PALETTE (see STYLE_GUIDE.md) so it sits with the
# DARKLY theme rather than reading as bright/pastel. Distinct hues, ordered
# to alternate warm/cool so adjacent stacked segments stay legible.
_SUBCONTEXT_PALETTE = [
    '#3a6ba6', '#b06a2c', '#2f8f93', '#7e4f9c', '#4f8a52',
    '#b0a335', '#a85070', '#4a6480', '#56539c', '#3f8388',
]
_NO_SUBCONTEXT_COLOR = '#495057'


def _render_hours_by_context(ctx_data, height=None):
    """Single stacked horizontal bar: one bar per context, segmented by
    subcontext. No legend \u2014 each segment's name, node count, and hours
    surface on hover. Segment times sum to the context total, so a bar's
    length is that context's total active time.
    """
    fmt = ConfigManager.format_time_friendly
    if not ctx_data:
        return _card([
            html.H6("Hours by Context", className="text-muted mb-1"),
            html.P("No contexts configured.", className="text-muted small"),
        ])

    ctx_names = [d['context'] for d in ctx_data]
    seg_by_ctx = {d['context']: {s['name']: s for s in d['segments']}
                  for d in ctx_data}

    # Global stack order: total time descending, "(No subcontext)" last.
    totals = defaultdict(float)
    for d in ctx_data:
        for s in d['segments']:
            totals[s['name']] += s['time']
    named = sorted((n for n in totals if n != '(No subcontext)'),
                   key=lambda n: totals[n], reverse=True)
    seg_order = named + (['(No subcontext)'] if '(No subcontext)' in totals else [])

    fig = go.Figure()
    for i, seg_name in enumerate(seg_order):
        color = (_NO_SUBCONTEXT_COLOR if seg_name == '(No subcontext)'
                 else _SUBCONTEXT_PALETTE[i % len(_SUBCONTEXT_PALETTE)])
        xs, hovers = [], []
        for ctx in ctx_names:
            s = seg_by_ctx[ctx].get(seg_name)
            if s and s['time'] > 0:
                xs.append(s['time'])
                hovers.append(
                    f"<b>{seg_name}</b><br>"
                    f"Context: {ctx}<br>"
                    f"Nodes: {s['count']}<br>"
                    f"Time: {fmt(s['time'])}"
                )
            else:
                xs.append(0)
                hovers.append('')
        fig.add_trace(go.Bar(
            y=ctx_names, x=xs, orientation='h',
            marker_color=color, marker_line=dict(color=_BG, width=1),
            opacity=0.9, hovertext=hovers, hoverinfo='text',
        ))

    tickvals, ticktext = _friendly_xticks(
        max((d['time'] for d in ctx_data), default=0))
    if height is None:
        height = max(180, len(ctx_names) * 28 + 60)
    fig.update_layout(**_base_layout(
        barmode='stack', height=height,
        margin=dict(l=10, r=20, t=10, b=30),
        yaxis=dict(automargin=True, ticklabelstandoff=8,
                   categoryorder='array', categoryarray=ctx_names,
                   **_label_axis(ctx_names)),
        xaxis=dict(tickmode='array', tickvals=tickvals, ticktext=ticktext),
    ))
    return _card([
        html.H6("Hours by Context", className="text-muted mb-1"),
        dcc.Graph(figure=fig, config=_CHART_CFG),
    ])


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------

def register_analyze_callbacks(app):

    @app.callback(
        Output("analyze-overview-content", "children"),
        Output("analyze-goals-content", "children"),
        Output("analyze-time-content", "children"),
        Output("analyze-graph-content", "children"),
        Output("analyze-contexts-content", "children"),
        Output("analyze-throughput-content", "children"),
        Input("main-tabs", "active_tab"),
        Input("setting-analyze-bottlenecks", "value"),
        Input("setting-analyze-goals", "value"),
        Input("setting-analyze-throughput-granularity", "value"),
        Input("setting-analyze-throughput-start", "value"),
        Input("setting-analyze-throughput-end", "value"),
        # save-output is the global "something was saved" channel. Reflection
        # edits via the hub modal don't regenerate Cytoscape elements, so
        # graph-version-store doesn't bump and the usual graph-change signal
        # misses them. Listening to save-output picks them up; the active_tab
        # guard below short-circuits when the user is not on this tab.
        Input("save-output", "children"),
        prevent_initial_call=True,
    )
    def refresh_analyze_tab(active_tab, bottlenecks, goals,
                            thru_gran, thru_start, thru_end, _save_output):
        if active_tab != "tab-analyze":
            return (no_update,) * 6

        # Persist any limit changes made via the gear popovers before rendering.
        al = ConfigManager.get_analyze_limits()
        if bottlenecks is not None:
            al['bottlenecks'] = int(bottlenecks)
        if goals is not None:
            al['goals'] = int(goals)
        if thru_gran in ('month', 'quarter', 'year'):
            al['throughput_granularity'] = thru_gran
        # Empty-string date inputs persist as None (auto-extent).
        al['throughput_start'] = thru_start or None
        al['throughput_end'] = thru_end or None
        ConfigManager.set_analyze_limits(al)

        nodes = graph_manager.get_all_nodes(include_dormant=False)
        edges = graph_manager.get_edges()

        if not nodes:
            empty = html.P("No nodes in the graph yet.", className="text-muted small")
            return empty, "", "", "", "", ""

        hard_fwd, hard_rev, prereq_rev, _, _ = _build_adjacency(edges)

        # Compute all sections
        limits = _get_limits()
        overview = _compute_overview(nodes, edges)
        bottlenecks = _compute_bottlenecks(nodes, hard_fwd, limits)
        ratings_data = _compute_ratings(nodes)
        goal_rows, overlap_rows, total_goal_count = _compute_goal_comparison(nodes, edges, hard_rev, prereq_rev, limits)
        est_accuracy = _compute_estimation_accuracy(nodes)
        ctx_coverage = _compute_context_coverage(nodes)
        drift_rows = _compute_reflection_drift(nodes)
        throughput_rows = _compute_throughput(
            nodes,
            granularity=al.get('throughput_granularity', 'quarter'),
            start_date=al.get('throughput_start'),
            end_date=al.get('throughput_end'),
        )
        hub_data = _compute_hub_score(nodes, edges, limits)

        # Goal names for heatmap axis ordering
        goal_names_ordered = [g['name'] for g in goal_rows]

        overview_content = _render_overview(overview)

        goals_content = [
            html.P(
                f"Top {len(goal_rows)} of {total_goal_count} goals, ranked by scoring algorithm."
                if total_goal_count > len(goal_rows)
                else "Side-by-side progress and overlap for all goals.",
                className="text-muted small"),
            _render_goal_comparison(goal_rows, overlap_rows, goal_names_ordered),
        ]

        time_content = [
            html.P(
                "On the By Node scatter, points above the dashed line took "
                "longer than estimated; points below were finished faster. "
                "On the By Context box plots, boxes right of the 1× line ran "
                "over estimate; left, came in under.",
                className="text-muted small"),
            dbc.Row([
                dbc.Col(_render_estimation_accuracy(est_accuracy), width=6),
                dbc.Col(_render_context_accuracy_boxplot(est_accuracy), width=6),
            ], className="g-3"),
        ]

        # Bottleneck and Hub share the gear's "nodes shown" limit and render
        # at the same height (max of the two list lengths) so the row reads
        # as a paired comparison.
        gs_count = max(len(bottlenecks), len(hub_data), 1)
        gs_height = max(180, gs_count * 28 + 60)
        graph_content = [
            html.P("Bottleneck: nodes whose completion would unlock the "
                   "largest downstream cascade. Hub: nodes most integrated "
                   "into the graph — traffic flowing in AND out.",
                   className="text-muted small"),
            dbc.Row([
                dbc.Col(_render_bottleneck_chart(bottlenecks,
                                                 height=gs_height), width=6),
                dbc.Col(_render_hub_chart(hub_data,
                                          height=gs_height), width=6),
            ], className="g-3"),
        ]

        ctx_height = max(180, len(ctx_coverage) * 28 + 60)
        # Bar chart: ctx_coverage is ascending by hours; plotly's horizontal
        # bar default puts the LAST y at the top, so the largest context
        # renders at the top.
        # Heatmaps: plotly heatmap default puts the FIRST y at the top, so
        # we pass the same contexts in reversed (descending) order to land
        # the largest context at the top — matching the bar chart's order.
        ctx_order_heatmap = list(reversed([c['context'] for c in ctx_coverage]))
        contexts_content = [
            html.P("Where your active time is allocated, the average "
                   "ratings behind it, and how those ratings have drifted "
                   "post-reflection.",
                   className="text-muted small"),
            dbc.Row([
                dbc.Col(_render_hours_by_context(ctx_coverage,
                                                 height=ctx_height), width=6),
                dbc.Col(_render_ratings_chart(ratings_data,
                                              height=ctx_height,
                                              context_order=ctx_order_heatmap), width=3),
                dbc.Col(_render_reflection_drift_chart(drift_rows,
                                                       height=ctx_height,
                                                       context_order=ctx_order_heatmap), width=3),
            ], className="g-3"),
        ]

        gran = al.get('throughput_granularity', 'quarter')
        gran_label = {'month': 'month', 'quarter': 'quarter',
                      'year': 'year'}[gran]
        throughput_content = [
            html.P(f"Hours of completed work per calendar {gran_label}, "
                   "stacked by context. Hover a segment for the node "
                   "list.",
                   className="text-muted small"),
            _render_throughput_chart(throughput_rows, granularity=gran),
        ]

        return (overview_content, goals_content, time_content, graph_content,
                contexts_content, throughput_content)
