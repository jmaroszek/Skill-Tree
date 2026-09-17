"""Graph analytics data preparation; rendering belongs to the Analyze view."""
import math
from datetime import date
from collections import defaultdict
from config import ConfigManager
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from goal_ranking import _rank_goals

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
    actual time. Both figures run through the same `expected_time_estimate`
    blend so they are directly comparable. Nodes with no actual-time data,
    or with no own estimate (inherited-time Goals), are skipped."""
    from models import expected_time_estimate
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
        actual = expected_time_estimate(lo, mid, hi)
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
    if any of the three reflection fields is populated.

    Only currently-Done nodes count. reflect_* columns persist when a node is
    un-marked Done (so re-completing restores the reflection), so without this
    gate a reverted node would keep skewing the drift heatmap."""
    by_ctx = defaultdict(lambda: {'dv': [], 'di': [], 'dd': [], 'count': 0})
    for n in nodes:
        if n.status != STATUS_DONE:
            continue
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
    """Bucket currently-Done nodes with ``done_date`` into calendar buckets,
    segmented by context. The status gate matters because ``done_date`` can
    linger on a node that was completed and later reverted to Open (older
    reverts predate the auto-clear on un-Done); requiring status Done keeps
    such a node out of the timeline. ``granularity`` is 'month' | 'quarter' |
    'year'; empty
    buckets between min and max are still emitted so the timeline reads
    continuously. ``start_date`` / ``end_date`` are ISO strings that
    optionally clip the range; None means "auto" (use the available data's
    natural extent). Per-node hours use captured actual time when present,
    otherwise the forecast estimate; each segment carries its ``nodes``
    list (``(name, hours)`` tuples, hours-descending) for tooltips."""
    from models import expected_time_estimate

    if granularity not in ('month', 'quarter', 'year'):
        granularity = 'quarter'

    def _hours(n):
        actual = expected_time_estimate(
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
        if n.status != STATUS_DONE:
            continue
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
