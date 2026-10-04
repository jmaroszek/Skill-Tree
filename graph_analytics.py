"""Graph analytics data preparation; rendering belongs to the Analyze view."""
import math
import statistics
from collections import defaultdict
from datetime import date, timedelta
from config import ConfigManager
from graph_queries import summarize_completion
from models import (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN,
                    STATUS_BLOCKED, STATUS_DONE)
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


# Goals are containers and Milestones are checkpoints. Neither is work, so the
# structure charts walk through them without ranking or counting them.
_CONTAINER_TYPES = ('Goal', 'Milestone')
# Node types whose incoming edges count as a hub's inputs. A Resource linked to
# a topic is reading material for it, not a concept feeding into it.
_CONCEPT_TYPES = ('Learn', 'Action')


def _compute_bottlenecks(nodes, hard_fwd, limits):
    """Rank Open work nodes by the hours of unfinished work they gate, with
    each row's own estimated time beside it.

    Walks forward through hard edges from each Open node and sums the time of
    the work it reaches, stepping through Goals and Milestones without counting
    them. Blocked nodes are left out: the work a Blocked node gates already sits
    inside the row of an Open node upstream of it. Open nodes that gate exactly
    the same work share one row, since finishing any of them opens nothing the
    others don't."""
    node_map = {n.name: n for n in nodes}
    non_done = {n.name for n in nodes if n.status != STATUS_DONE}
    groups = defaultdict(list)

    for n in nodes:
        if n.status != STATUS_OPEN or n.type in _CONTAINER_TYPES:
            continue
        reached = set()
        queue = [t for t in hard_fwd.get(n.name, []) if t in non_done]
        while queue:
            current = queue.pop()
            if current in reached:
                continue
            reached.add(current)
            queue.extend(t for t in hard_fwd.get(current, [])
                         if t in non_done and t not in reached)
        work = frozenset(r for r in reached
                         if node_map[r].type not in _CONTAINER_TYPES)
        if work:
            groups[work].append(n.name)

    results = []
    for work, names in groups.items():
        names.sort(key=str.casefold)
        results.append({
            'names': names,
            'hours': sum(node_map[w].time for w in work),
            'count': len(work),
            # What clearing the gate costs. Nodes that share a row gate the
            # same work side by side, so all of them stand in its way.
            'own_hours': sum(node_map[name].time for name in names),
        })
    results.sort(key=lambda r: (-r['hours'], -r['count'], r['names'][0].casefold()))
    return results[:limits.get('bottlenecks', 15)]


def hub_scores(nodes, edges):
    """Every unfinished work node's hub score, keyed by name —
    ``sqrt(in_count * out_count) + 0.5 * helps_count`` over Hard + Soft
    prereq edges, with Helps edges counted as symmetric synergy partners.

    Only Learn and Action prerequisites count as inputs, and Goals and
    Milestones are not ranked. A Goal's incoming edges are its members, so
    every umbrella Goal used to top the list; a Resource's edge into a topic
    measures the length of its reading list, not how central the topic is.

    The geometric mean punishes asymmetry (a pure root or pure leaf scores
    0 on the first term), so hubs are exactly the nodes with traffic in
    both directions — concepts that absorb prereqs AND feed dependents.
    The Helps term gives synergy partners half-weight credit on top.

    The community labels use it to name a cluster after its most central
    nodes. Each value is a row with the score components. Nodes scoring 0
    are left out."""
    node_map = {n.name: n for n in nodes}
    candidates = {n.name for n in nodes
                  if n.status != STATUS_DONE and n.type not in _CONTAINER_TYPES}

    in_ct: dict = defaultdict(int)
    out_ct: dict = defaultdict(int)
    helps_ct: dict = defaultdict(int)

    for e in edges:
        s, t, etype = e['source'], e['target'], e['type']
        if etype in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
            out_ct[s] += 1
            if s in node_map and node_map[s].type in _CONCEPT_TYPES:
                in_ct[t] += 1
        elif etype == EDGE_HELPS:
            helps_ct[s] += 1
            helps_ct[t] += 1

    results = {}
    for name in candidates:
        i, o = in_ct[name], out_ct[name]
        h = helps_ct[name]
        score = math.sqrt(i * o) + 0.5 * h
        if score <= 0:
            continue
        n = node_map[name]
        results[name] = {
            'name': name,
            'score': score,
            'in_count': i,
            'out_count': o,
            'helps_count': h,
            'type': n.type,
            'status': n.status,
        }
    return results


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


_REFLECTION_MIN_N = 4  # min reflected nodes per context for the drift chart


def _compute_reflection_drift(nodes):
    """For each context with at least ``_REFLECTION_MIN_N`` reflected nodes,
    compute mean ``reflect_X - X`` across V/I/D. A null reflect_X is skipped
    for that metric only; nodes count toward the context's reflected total
    if any of the three reflection fields is populated.

    Only currently-Done nodes count. reflect_* columns persist when a node is
    un-marked Done (so re-completing restores the reflection), so without this
    gate a reverted node would keep skewing the drift chart."""
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


# The order a Throughput chart colored by node type stacks its segments,
# bottom up: study, reading, then practice.
_TYPE_ORDER = ('Learn', 'Resource', 'Action', 'Goal', 'Milestone')


def _bucket_span(key, granularity):
    """The first and last day of a calendar bucket."""
    if granularity == 'year':
        first, after = date(key[0], 1, 1), date(key[0] + 1, 1, 1)
    elif granularity == 'month':
        y, m = key
        first = date(y, m, 1)
        after = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    else:
        y, q = key
        first = date(y, 3 * q - 2, 1)
        after = date(y + 1, 1, 1) if q == 4 else date(y, 3 * q + 1, 1)
    return first, after - timedelta(days=1)


def _compute_throughput(nodes, granularity='quarter',
                        start_date=None, end_date=None, by='context',
                        today=None):
    """Bucket currently-Done nodes with ``done_date`` into calendar buckets,
    segmented by context, or by node type when ``by`` is 'type'. The status
    gate matters because ``done_date`` can linger on a node that was
    completed and later reverted to Open (older reverts predate the
    auto-clear on un-Done); requiring status Done keeps such a node out of
    the timeline. ``granularity`` is 'month' | 'quarter' | 'year'.
    ``start_date`` / ``end_date`` are ISO strings that optionally clip the
    range; None means "auto". Per-node hours use captured actual time when
    present, otherwise the forecast estimate; each segment carries its
    ``nodes`` list (``(name, hours)`` tuples, hours-descending) for tooltips.

    Each bucket also carries ``capacity``: the time settings' hours a week,
    spread over the bucket's days. Empty buckets between the first completion
    and today (or the end date) are still emitted, so a quiet month shows as
    an empty bar under the capacity line rather than dropping off the end.
    The bucket under way counts only the days so far, and a start or end
    date trims the capacity of the bucket it falls in."""
    if granularity not in ('month', 'quarter', 'year'):
        granularity = 'quarter'
    today = today or date.today()
    _hours = _completed_hours

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

    def _parse(iso):
        try:
            return date.fromisoformat(iso) if iso else None
        except ValueError:
            return None

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
        group = n.type if by == 'type' else (n.context or 'No Context')
        buckets[_bucket_key(y, m)][group].append((n.name, _hours(n)))

    if not buckets:
        return []

    first_day = _parse(start_date)
    last_day = min(d for d in (_parse(end_date), today) if d is not None)
    keys_sorted = sorted(buckets.keys())
    cur = keys_sorted[0]
    if first_day is not None:
        cur = min(cur, _bucket_key(first_day.year, first_day.month))
    last = max(keys_sorted[-1], _bucket_key(last_day.year, last_day.month))
    full_keys = []
    # Every bucket is emitted. The chart shows only the latest few, so
    # capping here would drop the recent end of a long range.
    while cur <= last:
        full_keys.append(cur)
        cur = _next_key(cur)

    per_week = ConfigManager.get_time_settings().get('hours_per_week', 40)
    rows = []
    for k in full_keys:
        groups = buckets.get(k, {})
        segments = []
        for group, items in groups.items():
            items.sort(key=lambda x: x[1], reverse=True)
            segments.append({
                'key': group,
                'hours': sum(h for _, h in items),
                'nodes': items,
            })
        if by == 'type':
            segments.sort(key=lambda s: (_TYPE_ORDER.index(s['key'])
                                         if s['key'] in _TYPE_ORDER else 99))
        else:
            segments.sort(key=lambda s: s['hours'], reverse=True)
        span_first, span_last = _bucket_span(k, granularity)
        if first_day is not None:
            span_first = max(span_first, first_day)
        span_last = min(span_last, last_day)
        days = max(0, (span_last - span_first).days + 1)
        rows.append({
            'label': _bucket_label(k),
            'segments': segments,
            'total_hours': sum(s['hours'] for s in segments),
            'capacity': per_week * days / 7,
        })
    return rows


def _completed_hours(n):
    """Hours a finished node took: its captured actual time when there is
    one, otherwise its forecast estimate."""
    from models import expected_time_estimate
    captured = (n.actual_time_lower, n.actual_time_point, n.actual_time_upper)
    actual = expected_time_estimate(*captured)
    if actual > 0 and any(v is not None for v in captured):
        return actual
    return n.time


_MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# How far back the Completion rows' brighter "recent" segment reaches.
_RECENT_DAYS = 182


def _walk_back(name, adjacency):
    """Everything upstream of ``name`` through a reverse adjacency map."""
    visited = set()
    queue = list(adjacency.get(name, []))
    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(p for p in adjacency.get(current, []) if p not in visited)
    return visited


def _compute_goal_progress(nodes, edges, hard_rev, limits, today=None):
    """The Completion rows: the top Goals and how far along each one is.

    Ranks goals via _rank_goals (average worth of the work left in the hard
    subtree, boosted by priority rank and context weight), then caps to the
    top N. Progress is `summarize_completion` over the hard subtree, the
    prerequisites that gate the Goal: the share of its estimated hours that
    are Done. ``recent_time`` is the part of that finished in the last six
    months, so a stalled Goal reads differently from a moving one.

    Returns ``(rows, total_goal_count)``, rows in ranked order.
    """
    all_goals = [n for n in nodes if n.type == 'Goal']
    node_map = {n.name: n for n in nodes}
    priority_goals = ConfigManager.get_priority_goals()
    hp = ConfigManager.get_hyperparams()
    ranked = _rank_goals(all_goals, nodes, edges, priority_goals, hp)
    cutoff = ((today or date.today()) - timedelta(days=_RECENT_DAYS)).isoformat()

    rows = []
    for g in ranked[:limits.get('goals', 20)]:
        members = [node_map[name] for name in _walk_back(g.name, hard_rev)
                   if name in node_map]
        recent = [n for n in members
                  if n.status == STATUS_DONE and n.time > 0
                  and n.done_date and n.done_date >= cutoff]
        rows.append({
            'name': g.name,
            'priority_rank': (priority_goals.index(g.name) + 1
                              if g.name in priority_goals else None),
            **summarize_completion(members),
            'recent_time': sum(n.time for n in recent),
            'recent_count': len(recent),
        })
    return rows, len(all_goals)


_RATING_KEYS = (('value', 'value'), ('interest', 'interest'),
                ('effort', 'difficulty'))


def _compute_rating_distribution(nodes):
    """How the open nodes' Value, Interest and Effort ratings spread from 1
    to 10, for the whole graph, each context and each subcontext.

    Milestones and nodes in inherited ratings mode are left out, since their
    stored ratings don't score. Contexts run in descending open time,
    matching the Work left column, with nodes that have no context in a last
    "No Context" group. Within a context, subcontexts run the same way and
    "No subcontext" closes the group. A context whose nodes all lack a
    subcontext gets no subcontext rows, since its one row would repeat the
    context's. Contexts without a rated node are skipped.

    Returns ``{'all': row, 'groups': [{'row': row, 'subs': [row, ...]}]}``.
    A row is ``{'context', 'subcontext', 'count'}`` plus, per rating key,
    ``{'counts': [n at 1, ..., n at 10], 'mean'}``. ``subcontext`` is None on
    a context's own row, and both are None on the whole-graph row.

    Each row also carries ``time``, the area's remaining work, and ``share``,
    that time over the whole graph's. Time counts every open node, Milestones
    and inherited nodes included, since they are still work to do; the
    ratings leave those out. ``time_by_type`` splits ``time`` by node type.
    ``median_time`` is the median estimate of the nodes the row counts,
    less those whose time comes from their children (they hold none of
    their own), or None when there are none.
    """
    rated = [n for n in nodes
             if n.status != STATUS_DONE and n.type != 'Milestone'
             and n.value_mode != 'inherited']
    groups = defaultdict(lambda: defaultdict(list))
    for n in rated:
        groups[n.context or 'No Context'][n.subcontext or 'No subcontext'].append(n)
    hours = defaultdict(float)
    by_type = defaultdict(lambda: defaultdict(float))
    for n in nodes:
        if n.status != STATUS_DONE:
            ctx = n.context or 'No Context'
            for area in (None, ctx, (ctx, n.subcontext or 'No subcontext')):
                hours[area] += n.time
                by_type[area][n.type] += n.time
    total_hours = hours[None]

    def _row(ctx, sub, members):
        area = None if ctx is None else ctx if sub is None else (ctx, sub)
        time = hours[area]
        sizes = [n.time for n in members if n.time > 0]
        row = {'context': ctx, 'subcontext': sub, 'count': len(members),
               'time': time, 'share': time / total_hours if total_hours else 0.0,
               'time_by_type': {t: h for t, h in by_type[area].items() if h > 0},
               'median_time': statistics.median(sizes) if sizes else None}
        for key, attr in _RATING_KEYS:
            ratings = [min(10, max(1, int(getattr(n, attr)))) for n in members]
            counts = [0] * 10
            for r in ratings:
                counts[r - 1] += 1
            row[key] = {'counts': counts,
                        'mean': sum(ratings) / len(ratings) if ratings else None}
        return row

    contexts = sorted((c for c in groups if c != 'No Context'),
                      key=lambda c: -hours[c])
    if 'No Context' in groups:
        contexts.append('No Context')

    result = {'all': _row(None, None, rated), 'groups': []}
    for ctx in contexts:
        subs = groups[ctx]
        group = {'row': _row(ctx, None, [n for m in subs.values() for n in m]),
                 'subs': []}
        if list(subs) != ['No subcontext']:
            ordered = sorted(subs, key=lambda s: (s == 'No subcontext',
                                                  -hours[ctx, s]))
            group['subs'] = [_row(ctx, s, subs[s]) for s in ordered]
        result['groups'].append(group)
    return result
