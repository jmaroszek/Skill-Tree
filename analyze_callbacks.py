"""
Callback definitions for the Analyze tab.
Computes and renders aggregate analytics about the graph.
"""

from dash import html, dcc, Input, Output, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from collections import defaultdict
from graph_manager import GraphManager
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from config import ConfigManager
from scoring import build_adjacency as _scoring_build_adjacency, total_value

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


def _compute_top_time_sinks(nodes, limits):
    active = [n for n in nodes if n.status != STATUS_DONE]
    return sorted(active, key=lambda n: n.time, reverse=True)[:limits.get('time_sinks', 10)]


def _get_limits():
    """Read analyze limits from user settings, with defaults."""
    return ConfigManager.get_analyze_limits()


def _rank_goals(goals, all_nodes, edges, priority_goals, hp):
    """Rank goals by the discounted value of their prerequisite subtree.

    Goals are sinks in the prereq DAG (work flows into them), so the
    scoring module's forward ``total_value`` (which cascades through
    outgoing Hard/Soft edges) collapses to a Goal's own intrinsic value.
    For the Analyze "Goals" chart the meaningful question is "how much
    work / value does this Goal subsume?" — so we invert Hard/Soft edges
    and apply the same ``total_value`` machinery against the flipped
    graph. The result is: IV(goal) + Σ d_H^depth * IV(prereq) over the
    Hard subtree (+ analogous Soft + Helps contributions).

    Boosted by the priority-rank multiplier (rank 1 gets the full
    ``goal_boost``, rank 2 gets 66% of the bump, rank 3 gets 33%).
    Returns goals sorted by rank score descending.
    """
    w_v = hp.get('w_v', 1.0)
    w_i = hp.get('w_i', 1.0)
    d_H = hp.get('d_H', 0.6)
    d_S = hp.get('d_S', 0.25)
    d_Syn_pair = hp.get('d_Syn_pair', 0.10)
    d_Syn_mul = hp.get('d_Syn_mul', 0.40)
    goal_boost = hp.get('goal_boost', 1.5)
    rank_multipliers = [
        goal_boost,
        1 + (goal_boost - 1) * 0.66,
        1 + (goal_boost - 1) * 0.33,
    ]

    # Invert Hard/Soft edges so the cascade walks upstream toward prereqs.
    # Helps is symmetric (bidirectional), so leave it alone.
    inverted = []
    for e in edges:
        if e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
            inverted.append({'source': e['target'], 'target': e['source'],
                             'type': e['type']})
        else:
            inverted.append(e)

    all_nodes_dict = {n.name: n for n in all_nodes}
    H_out, S_out, Syn, _ = _scoring_build_adjacency(
        inverted, set(all_nodes_dict.keys()))

    memo: dict = {}
    scored = []
    for g in goals:
        tv = total_value(
            g.name, set(), all_nodes_dict, H_out, S_out, Syn,
            w_v, w_i, d_H, d_S, d_Syn_pair, d_Syn_mul, memo,
        )
        if g.name in priority_goals:
            rank_idx = priority_goals.index(g.name)
            if rank_idx < 3:
                tv *= rank_multipliers[rank_idx]
        scored.append((g, tv))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [g for g, _ in scored]


def _compute_goal_comparison(nodes, edges, hard_rev, prereq_rev, limits):
    """Compute goal stats and pairwise overlap using in-memory adjacency.

    Ranks goals by total_value (intrinsic value + cascaded descendant value
    through Hard/Soft edges) boosted by priority rank, then caps to keep
    visualizations readable. Progress is computed over hard prerequisites
    only (those gate completion); pairwise overlap is computed over hard
    + soft prerequisites (the full body of prep work shared between goals).
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
    goal_rows.sort(key=lambda r: r['pct'])

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


def _compute_risk(nodes, limits):
    # Skip inherited-time containers: their `time` property short-circuits to 0
    # (models.py), so the expected-value marker would land outside the o→p band.
    candidates = [
        n for n in nodes
        if n.status != STATUS_DONE
        and n.time_o > 0 and n.time_p > 0
        and n.time_mode != 'inherited'
    ]
    results = []
    for n in candidates:
        spread = n.time_p - n.time_o
        ratio = round(n.time_p / n.time_o, 1) if n.time_o > 0 else 0
        results.append({
            'name': n.name,
            'type': n.type,
            'optimistic': n.time_o,
            'expected': n.time,
            'pessimistic': n.time_p,
            'spread': spread,
            'ratio': ratio,
        })
    results.sort(key=lambda r: r['spread'], reverse=True)
    return results[:limits.get('risk', 25)]


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
    """Compare configured contexts/subcontexts against actual node assignments."""
    configured_contexts = ConfigManager.get_contexts()
    configured_subcontexts = ConfigManager.get_subcontexts()
    weights = ConfigManager.get_context_weights()
    active = [n for n in nodes if n.status != STATUS_DONE]

    # Context coverage
    ctx_counts = defaultdict(lambda: {'count': 0, 'time': 0.0, 'avg_value': 0, 'avg_interest': 0, 'values': [], 'interests': []})
    for n in active:
        ctx = n.context or 'No Context'
        ctx_counts[ctx]['count'] += 1
        ctx_counts[ctx]['time'] += n.time
        ctx_counts[ctx]['values'].append(n.value)
        ctx_counts[ctx]['interests'].append(n.interest)

    ctx_data = []
    for ctx in configured_contexts:
        d = ctx_counts.get(ctx, {'count': 0, 'time': 0.0, 'values': [], 'interests': []})
        c = d['count']
        ctx_data.append({
            'context': ctx,
            'count': c,
            'time': d['time'],
            'avg_value': round(sum(d['values']) / c, 1) if c else 0,
            'avg_interest': round(sum(d['interests']) / c, 1) if c else 0,
            'weight': float(weights.get(ctx, 1.0)),
        })
    # Add "No Context" if any nodes lack one
    if 'No Context' in ctx_counts:
        d = ctx_counts['No Context']
        c = d['count']
        ctx_data.append({
            'context': 'No Context',
            'count': c,
            'time': d['time'],
            'avg_value': round(sum(d['values']) / c, 1) if c else 0,
            'avg_interest': round(sum(d['interests']) / c, 1) if c else 0,
            'weight': 1.0,
        })
    ctx_data.sort(key=lambda r: r['time'])

    # Subcontext coverage
    subctx_counts = defaultdict(lambda: {'count': 0, 'time': 0.0})
    for n in active:
        if n.subcontext:
            key = f"{n.context or '?'} > {n.subcontext}"
            subctx_counts[key]['count'] += 1
            subctx_counts[key]['time'] += n.time

    subctx_data = []
    for ctx, subs in configured_subcontexts.items():
        for sub in subs:
            key = f"{ctx} > {sub}"
            d = subctx_counts.get(key, {'count': 0, 'time': 0.0})
            subctx_data.append({
                'label': key,
                'count': d['count'],
                'time': d['time'],
            })
    subctx_data.sort(key=lambda r: r['time'])

    return ctx_data, subctx_data


def _compute_dependency_structure(nodes, hard_fwd, hard_rev, all_fwd, all_rev, edges, limits):
    non_done_names = {n.name for n in nodes if n.status != STATUS_DONE}
    all_names = {n.name for n in nodes}

    # --- Longest chain via DAG longest-path (topological order) ---
    # Only consider hard dependency edges among non-Done nodes
    in_degree = defaultdict(int)
    dag_fwd = defaultdict(list)
    for name in non_done_names:
        for tgt in hard_fwd.get(name, []):
            if tgt in non_done_names:
                dag_fwd[name].append(tgt)
                in_degree[tgt] += 1

    # Topological sort (Kahn's algorithm)
    queue = [n for n in non_done_names if in_degree[n] == 0]
    topo_order = []
    while queue:
        node = queue.pop(0)
        topo_order.append(node)
        for nxt in dag_fwd.get(node, []):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    # Longest path from each node
    dist = {n: 0 for n in non_done_names}
    parent = {n: None for n in non_done_names}
    for node in topo_order:
        for nxt in dag_fwd.get(node, []):
            if dist[node] + 1 > dist[nxt]:
                dist[nxt] = dist[node] + 1
                parent[nxt] = node

    # Reconstruct longest chain
    if dist:
        end_node = max(dist, key=dist.get)
        longest_length = dist[end_node]
        chain = []
        current = end_node
        while current is not None:
            chain.append(current)
            current = parent[current]
        chain.reverse()
    else:
        chain = []
        longest_length = 0

    # --- Deepest nodes (most hard prerequisites via BFS backward) ---
    depth_counts = []
    for name in non_done_names:
        visited = set()
        q = list(hard_rev.get(name, []))
        while q:
            cur = q.pop()
            if cur in visited:
                continue
            visited.add(cur)
            for prev_node in hard_rev.get(cur, []):
                if prev_node not in visited:
                    q.append(prev_node)
        # Only count non-Done prerequisites
        prereq_count = len(visited & non_done_names)
        if prereq_count > 0:
            depth_counts.append({'name': name, 'prereq_count': prereq_count})
    depth_counts.sort(key=lambda r: r['prereq_count'], reverse=True)

    # --- Most connected (total degree across all edge types) ---
    degree = defaultdict(int)
    for e in edges:
        degree[e['source']] += 1
        degree[e['target']] += 1
    connected = [
        {'name': name, 'degree': deg}
        for name, deg in degree.items() if name in all_names
    ]
    connected.sort(key=lambda r: r['degree'], reverse=True)

    return {
        'longest_chain': chain,
        'longest_length': longest_length,
        'deepest': depth_counts[:limits.get('deepest', 10)],
        'most_connected': connected[:limits.get('connected', 10)],
    }


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

_BG = '#1a1d21'
_CARD_BG = '#2b3035'
_BORDER = '#495057'
_STATUS_COLORS = {STATUS_OPEN: '#0d6efd', STATUS_BLOCKED: '#dc3545', STATUS_DONE: '#198754'}
_CHART_CFG = {"displayModeBar": False}


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


def _hbar_chart(names, values, colors=None, hover_texts=None, x_title=None, height=None, integer_x=False):
    """Create a standard horizontal bar chart figure.

    integer_x: when True, force integer-only x-axis ticks (for counts, not hours).
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
                "border": f"1px solid {_BORDER}", "backgroundColor": _CARD_BG,
                "textAlign": "center",
            }),
            style={"flex": "1 1 0", "minWidth": "0"},
        ))
    return html.Div(cols, style={
        "display": "flex", "gap": "1rem",
    }, className="mb-3")


def _render_bottleneck_chart(data, height=None):
    if not data:
        return html.P("No bottleneck nodes found.", className="text-muted small")

    fmt = ConfigManager.format_time_friendly
    names = [d['name'] for d in data]
    values = [d['cascade'] for d in data]
    colors = [_STATUS_COLORS.get(d['status'], '#6c757d') for d in data]
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
    return dcc.Graph(figure=fig, config=_CHART_CFG)


def _render_time_distribution(ctx_chart, subctx_chart, top_nodes, risk_data, row_height=None):
    fmt = ConfigManager.format_time_friendly
    sections = []

    # Row 1: Hours by Context (coverage chart) + Longest Projects side by side
    top_cols = []
    if ctx_chart is not None:
        top_cols.append(dbc.Col([ctx_chart], width=6))
    else:
        top_cols.append(dbc.Col(
            html.P("No data.", className="text-muted small"), width=6))

    if top_nodes:
        names = [n.name for n in top_nodes]
        values = [n.time for n in top_nodes]
        hover = [
            f"<b>{n.name}</b><br>"
            f"{fmt(n.time)}<br>"
            f"Type: {n.type}<br>"
            f"Context: {n.context or '—'}"
            for n in top_nodes
        ]
        fig = _hbar_chart(names, values, colors='#6f42c1', hover_texts=hover,
                          x_title="Hours", height=row_height)
        top_cols.append(dbc.Col([
            html.H6("Longest Projects", className="text-muted mb-1"),
            dcc.Graph(figure=fig, config=_CHART_CFG),
        ], width=6))
    else:
        top_cols.append(dbc.Col(
            html.P("No data.", className="text-muted small"), width=6))

    sections.append(dbc.Row(top_cols, className="g-3"))

    # Row 2: By Subcontext (vertical, full width)
    if subctx_chart is not None:
        sections.append(subctx_chart)

    # Row 3: Uncertainty (full width)
    if risk_data:
        risk_content = _render_risk_chart(risk_data)
        sections.append(html.Div([
            html.H6("Uncertainty", className="text-muted mb-1 mt-4"),
            risk_content,
        ]))
    else:
        sections.append(html.Div([
            html.H6("Uncertainty", className="text-muted mb-1 mt-4"),
            html.P("No nodes with sufficient time estimate data.", className="text-muted small"),
        ]))

    return html.Div(sections)


def _render_goal_comparison(goal_rows, overlap_rows, goal_names_ordered):
    fmt = ConfigManager.format_time_friendly

    if not goal_rows:
        return html.P("No goals defined.", className="text-muted small")

    sections_left = []
    sections_right = []

    # --- Shared y-axis order (used by both charts) ---
    # goal_rows is sorted by pct ascending; we want least complete at top
    y_order = [g['name'] for g in goal_rows]  # bottom-to-top in Plotly
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
    hover_rem = [f"Remaining: {100 - g['pct']}%" for g in sorted_goals]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=bar_names, x=done_pcts, orientation='h',
        marker_color='#198754', opacity=0.9, name=STATUS_DONE,
        hovertext=hover_done, hoverinfo='text',
    ))
    fig.add_trace(go.Bar(
        y=bar_names, x=remaining_pcts, orientation='h',
        marker_color='#495057', opacity=0.6, name='Remaining',
        hovertext=hover_rem, hoverinfo='text',
    ))
    fig.update_layout(**_base_layout(
        barmode='stack', height=shared_height,
        margin=shared_margin,
        yaxis=dict(automargin=True, ticklabelstandoff=8,
                   categoryorder='array', categoryarray=bar_names,
                   **_label_axis(bar_names)),
        xaxis=dict(title="Completion %", range=[0, 100]),
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

        # Use y_order (pct ascending) for BOTH axes so the diagonal aligns
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
        dbc.Col(sections_left, width=6),
        dbc.Col(sections_right, width=6),
    ], className="g-3")


def _render_risk_chart(data):
    if not data:
        return html.P("No nodes with sufficient time estimate data.", className="text-muted small")

    fmt = ConfigManager.format_time_friendly
    # Keep sorted by spread descending (largest spread on left)
    full_names = [d['name'] for d in data]
    optimistic = [d['optimistic'] for d in data]
    spreads = [d['pessimistic'] - d['optimistic'] for d in data]
    expected = [d['expected'] for d in data]

    hover = [
        f"<b>{d['name']}</b><br>"
        f"Optimistic: {fmt(d['optimistic'])}<br>"
        f"Expected: {fmt(d['expected'])}<br>"
        f"Pessimistic: {fmt(d['pessimistic'])}<br>"
        f"Spread: {fmt(d['spread'])} ({d['ratio']}x)"
        for d in data
    ]

    fig = go.Figure()
    # Invisible base bar (pushes the visible bar up)
    fig.add_trace(go.Bar(
        x=full_names, y=optimistic, orientation='v',
        marker_color='rgba(0,0,0,0)', marker_line_width=0, showlegend=False,
        hoverinfo='skip',
    ))
    # Visible range bar (optimistic to pessimistic)
    fig.add_trace(go.Bar(
        x=full_names, y=spreads, orientation='v',
        marker_color='#dc3545', opacity=0.7,
        hovertext=hover, hoverinfo='text',
    ))
    # Expected value markers
    fig.add_trace(go.Scatter(
        x=full_names, y=expected, mode='markers',
        marker=dict(color='#ffc107', size=8, symbol='diamond'),
        hoverinfo='skip',
    ))
    fig.update_layout(**_base_layout(
        barmode='stack', height=350,
        margin=dict(l=40, r=10, t=10, b=10),
        xaxis=dict(automargin=True, tickangle=-45,
                   categoryorder='array', categoryarray=full_names,
                   **_label_axis(full_names)),
        yaxis=dict(title="Hours", automargin=True, ticklabelstandoff=8),
    ))
    # Add a legend note
    return html.Div([
        dcc.Graph(figure=fig, config=_CHART_CFG),
        html.Div([
            html.Span("\u25c6 ", style={"color": "#ffc107"}),
            html.Span("Expected", className="text-muted small me-3"),
            html.Span("\u2588 ", style={"color": "#dc3545", "opacity": "0.7"}),
            html.Span("Optimistic \u2192 Pessimistic range", className="text-muted small"),
        ], className="mt-1"),
    ])


def _render_dep_charts(dep_data, total_height=None):
    """Render deepest nodes + most connected bar charts stacked vertically.

    If total_height is given, each chart gets roughly half so the combined
    column matches the bottleneck column on the left. The 40px subtracted
    accounts for one extra H6 (≈24px, mb-1) and the mt-3 gap (≈16px) the
    right column carries vs. the left.
    """
    deepest = dep_data['deepest']
    most_connected = dep_data['most_connected']
    half_h = (total_height - 40) // 2 if total_height else None

    sections = []
    chart_data = [
        ("Deepest Nodes", deepest, 'prereq_count', '#6f42c1'),
        ("Most Connected", most_connected, 'degree', '#6f42c1'),
    ]
    for idx, (label, items, key, color) in enumerate(chart_data):
        mt = "mt-3" if idx > 0 else ""
        if items:
            names = [d['name'] for d in items]
            values = [d[key] for d in items]
            fig = _hbar_chart(names, values, colors=color,
                              x_title="Hard needs" if key == 'prereq_count' else "Connections",
                              height=half_h, integer_x=True)
            sections.append(html.H6(label, className=f"text-muted mb-1 {mt}"))
            sections.append(dcc.Graph(figure=fig, config=_CHART_CFG))
        else:
            sections.append(html.H6(label, className=f"text-muted mb-1 {mt}"))
            sections.append(html.P("No data.", className="text-muted small"))

    return html.Div(sections)


def _render_longest_chain(dep_data):
    """Render the longest prerequisite chain as pill-and-arrow display."""
    chain = dep_data['longest_chain']
    length = dep_data['longest_length']

    if chain and length > 0:
        chain_items = []
        for i, name in enumerate(chain):
            chain_items.append(html.Span(name, style={
                "padding": "2px 8px", "borderRadius": "4px",
                "backgroundColor": _CARD_BG, "border": f"1px solid {_BORDER}",
                "fontSize": "0.82rem", "whiteSpace": "nowrap",
            }))
            if i < len(chain) - 1:
                chain_items.append(html.Span(" \u2192 ", className="text-muted",
                                             style={"fontSize": "0.82rem"}))
        return html.Div(chain_items, style={
            "padding": "8px 12px", "overflowX": "auto",
            "whiteSpace": "nowrap", "display": "flex",
            "alignItems": "center", "gap": "2px",
            "justifyContent": "flex-start",
        })
    else:
        return html.P("No dependency chains found.", className="text-muted small")


def _render_ratings_chart(data):
    if not data:
        return html.P("No active nodes.", className="text-muted small")

    # Sort so largest context is at top (data is already sorted by count desc)
    contexts = [d['context'] for d in data]

    # Build z-matrix: rows = contexts, cols = metrics
    z = []
    hover = []
    for d in data:
        z.append([d['avg_value'], d['avg_interest'], d['avg_difficulty']])
        row_hover = []
        for attr, label in [('avg_value', 'Value'), ('avg_interest', 'Interest'), ('avg_difficulty', 'Difficulty')]:
            row_hover.append(
                f"<b>{d['context']}</b><br>"
                f"{label}: {d[attr]}<br>"
                f"{d['count']} active nodes<br>"
                f"Completion: {d['completion_pct']}%"
            )
        hover.append(row_hover)

    height = max(200, len(contexts) * 32 + 80)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=['Value', 'Interest', 'Difficulty'],
        y=contexts,
        colorscale=[[0, '#1a1d21'], [0.25, '#162d50'], [0.5, '#1a5276'],
                    [0.75, '#2185d0'], [1.0, '#54b8ff']],
        hovertext=hover, hoverinfo='text',
        showscale=True,
        colorbar=dict(title="Avg", len=0.5),
        zmin=1, zmax=10,
    ))
    fig.update_layout(**_base_layout(
        height=height,
        margin=dict(l=10, r=20, t=10, b=30),
        yaxis=dict(automargin=True, ticklabelstandoff=8, **_label_axis(contexts)),
        xaxis=dict(side='bottom'),
    ))
    return html.Div([
        html.H6("Ratings", className="text-muted mb-1"),
        dcc.Graph(figure=fig, config=_CHART_CFG),
    ])


def _tercile_colors(values):
    """Color each value by tercile of the non-zero distribution.

    Linear-interpolated 1/3 and 2/3 quantiles of the non-zero subset; zero
    values fall in the bottom tercile naturally. Returns a per-value color
    list. With <2 non-zero values the distribution is degenerate, so all
    bars get the neutral chart color (purple).
    """
    nonzero = sorted(v for v in values if v > 0)
    n = len(nonzero)
    if n < 2:
        return ['#6f42c1'] * len(values)

    def _q(q):
        pos = q * (n - 1)
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        frac = pos - lo
        return nonzero[lo] * (1 - frac) + nonzero[hi] * frac

    low_t, high_t = _q(1/3), _q(2/3)

    def _color(v):
        if v < low_t:
            return '#dc3545'   # red \u2014 bottom tercile
        if v < high_t:
            return '#ffc107'   # yellow \u2014 middle tercile
        return '#198754'       # green \u2014 top tercile

    return [_color(v) for v in values]


def _render_context_coverage(ctx_data, subctx_data, chart_height=None):
    """Returns a tuple: (ctx_chart for column, subctx_chart for full-width row)."""
    fmt = ConfigManager.format_time_friendly
    sections_ctx = []
    sections_sub = []

    if ctx_data:
        names = [d['context'] for d in ctx_data]
        hours = [d['time'] for d in ctx_data]
        colors = ['#6f42c1'] * len(ctx_data)
        hover = [
            f"<b>{d['context']}</b><br>"
            f"Weight: \u00d7{d['weight']:.2f}<br>"
            f"Time: {fmt(d['time'])}<br>"
            f"Nodes: {d['count']}<br>"
            f"Avg value: {d['avg_value']}<br>"
            f"Avg interest: {d['avg_interest']}"
            if d['count'] > 0 else
            f"<b>{d['context']}</b><br>"
            f"Weight: \u00d7{d['weight']:.2f}<br>"
            f"No nodes assigned"
            for d in ctx_data
        ]
        height = chart_height or max(180, len(names) * 28 + 60)
        fig = _hbar_chart(names, hours, colors=colors, hover_texts=hover,
                          x_title="Hours", height=height)
        # Override the reversal -- data is already sorted ascending (sparsest at top).
        # Plotly trace attribute types are stricter than runtime; the ignores below are false positives.
        fig.data[0].y = names  # pyright: ignore[reportOptionalMemberAccess]
        fig.data[0].x = hours  # pyright: ignore[reportOptionalMemberAccess]
        fig.data[0].marker.color = colors  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]
        fig.data[0].hovertext = hover  # pyright: ignore[reportOptionalMemberAccess]
        fig.update_yaxes(**_label_axis(names))

        sections_ctx.append(html.H6("Hours by Context", className="text-muted mb-1"))
        sections_ctx.append(dcc.Graph(figure=fig, config=_CHART_CFG))

    if subctx_data:
        # Sort descending for vertical display (largest on left)
        sorted_sub = sorted(subctx_data, key=lambda d: d['time'], reverse=True)
        names = [d['label'] for d in sorted_sub]
        hours = [d['time'] for d in sorted_sub]
        colors = _tercile_colors(hours)
        hover = [
            f"<b>{d['label']}</b><br>"
            f"Time: {fmt(d['time'])}<br>"
            f"Nodes: {d['count']}"
            if d['count'] > 0 else
            f"<b>{d['label']}</b><br>No nodes assigned"
            for d in sorted_sub
        ]
        fig = go.Figure(go.Bar(
            x=names, y=hours, orientation='v',
            marker_color=colors, opacity=0.9,
            hovertext=hover, hoverinfo='text',
        ))
        fig.update_layout(**_base_layout(
            height=350,
            margin=dict(l=40, r=10, t=10, b=10),
            xaxis=dict(automargin=True, tickangle=-45,
                       categoryorder='array', categoryarray=names,
                       **_label_axis(names)),
            yaxis=dict(title="Hours", automargin=True, ticklabelstandoff=8),
        ))

        sections_sub.append(html.H6("By Subcontext", className="text-muted mb-1 mt-3"))
        sections_sub.append(dcc.Graph(figure=fig, config=_CHART_CFG))
        sections_sub.append(html.Div([
            html.Span("\u2588 ", style={"color": "#dc3545"}),
            html.Span("Low", className="text-muted small me-3"),
            html.Span("\u2588 ", style={"color": "#ffc107"}),
            html.Span("Mid", className="text-muted small me-3"),
            html.Span("\u2588 ", style={"color": "#198754"}),
            html.Span("High", className="text-muted small"),
        ], className="mt-1"))

    ctx_chart = html.Div(sections_ctx) if sections_ctx else html.P("No contexts configured.", className="text-muted small")
    subctx_chart = html.Div(sections_sub) if sections_sub else html.Div()

    return ctx_chart, subctx_chart


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------

def register_analyze_callbacks(app):

    @app.callback(
        Output("analyze-content-container", "children"),
        Input("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def refresh_analyze_tab(active_tab):
        if active_tab != "tab-analyze":
            return no_update

        nodes = graph_manager.get_all_nodes(include_dormant=False)
        edges = graph_manager.get_edges()

        if not nodes:
            return html.Div([
                html.H5("Analyze", className="text-muted"),
                html.P("No nodes in the graph yet.", className="text-muted small"),
            ], style={"textAlign": "center", "marginTop": "20%"})

        hard_fwd, hard_rev, prereq_rev, all_fwd, all_rev = _build_adjacency(edges)

        # Compute all sections
        limits = _get_limits()
        overview = _compute_overview(nodes, edges)
        bottlenecks = _compute_bottlenecks(nodes, hard_fwd, limits)
        top_nodes = _compute_top_time_sinks(nodes, limits)
        ratings_data = _compute_ratings(nodes)
        goal_rows, overlap_rows, total_goal_count = _compute_goal_comparison(nodes, edges, hard_rev, prereq_rev, limits)
        risk_data = _compute_risk(nodes, limits)
        dep_data = _compute_dependency_structure(nodes, hard_fwd, hard_rev, all_fwd, all_rev, edges, limits)
        ctx_coverage, subctx_coverage = _compute_context_coverage(nodes)
        # Shared height for Hours by Context + Longest Projects row
        time_row_height = max(
            max(180, len(ctx_coverage) * 28 + 60),
            max(180, len(top_nodes) * 28 + 60),
        )
        ctx_chart, subctx_chart = _render_context_coverage(ctx_coverage, subctx_coverage, chart_height=time_row_height)
        # Shared height for the Bottleneck row so left + right columns match
        bottleneck_row_height = max(180, len(bottlenecks) * 28 + 60)

        # Goal names for heatmap axis ordering
        goal_names_ordered = [g['name'] for g in goal_rows]

        # Render all sections
        return [
            _render_overview(overview),
            html.Hr(className="my-3"),

            # -- Goals --
            html.H5("Goals", className="mb-1"),
            html.P(
                f"Top {len(goal_rows)} of {total_goal_count} goals, ranked by scoring algorithm."
                if total_goal_count > len(goal_rows)
                else "Side-by-side progress and overlap for all goals.",
                className="text-muted small"),
            _render_goal_comparison(goal_rows, overlap_rows, goal_names_ordered),
            html.Hr(className="my-3"),

            # -- Time --
            html.H5("Time", className="mb-1"),
            _render_time_distribution(ctx_chart, subctx_chart, top_nodes, risk_data, row_height=time_row_height),
            html.Hr(className="my-3"),

            # -- Graph Structure --
            html.H5("Graph Structure", className="mb-1"),
            # Row 1: Bottleneck + Deepest/Connected (matched heights via
            # shared bottleneck_row_height computed above).
            dbc.Row([
                dbc.Col([html.H6("Bottleneck Analysis", className="text-muted mb-1"),
                         _render_bottleneck_chart(bottlenecks, height=bottleneck_row_height)], width=6),
                dbc.Col([_render_dep_charts(dep_data, total_height=bottleneck_row_height)], width=6),
            ], className="g-3"),
            html.Hr(className="my-3"),

            # -- Contexts --
            html.H5("Contexts", className="mb-1"),
            html.Div([_render_ratings_chart(ratings_data)], style={"maxWidth": "600px"}),
        ]
