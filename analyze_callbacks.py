"""
Callback definitions for the Analyze tab.
Computes and renders aggregate analytics about the graph.
"""

import dash
from dash import html, dcc, Input, Output, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from collections import defaultdict
from graph_manager import GraphManager
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from config import ConfigManager
from scoring import intrinsic_value

graph_manager = GraphManager()


# ---------------------------------------------------------------------------
# Adjacency helpers
# ---------------------------------------------------------------------------

def _build_adjacency(edges):
    """Build in-memory forward and reverse adjacency maps from edge list.

    Returns:
        hard_fwd:  source -> [targets]  for Needs_Hard edges
        hard_rev:  target -> [sources]  for Needs_Hard edges (prerequisites)
        all_fwd:   source -> [targets]  for all edge types
        all_rev:   target -> [sources]  for all edge types
    """
    hard_fwd = defaultdict(list)
    hard_rev = defaultdict(list)
    all_fwd = defaultdict(list)
    all_rev = defaultdict(list)
    for e in edges:
        s, t, etype = e['source'], e['target'], e['type']
        all_fwd[s].append(t)
        all_rev[t].append(s)
        if etype == EDGE_NEEDS_HARD:
            hard_fwd[s].append(t)
            hard_rev[t].append(s)
    return hard_fwd, hard_rev, all_fwd, all_rev


# ---------------------------------------------------------------------------
# Compute functions
# ---------------------------------------------------------------------------

def _compute_overview(nodes, edges):
    active = [n for n in nodes if n.status != 'Done']
    blocked = [n for n in active if n.status == 'Blocked']
    remaining_time = sum(n.time for n in nodes if n.status != 'Done')
    goals = [n for n in nodes if n.type == 'Goal']
    return {
        'active_count': len(active),
        'blocked_count': len(blocked),
        'blocked_pct': round(len(blocked) / len(active) * 100) if active else 0,
        'remaining_time': remaining_time,
        'goal_count': len(goals),
        'done_count': len([n for n in nodes if n.status == 'Done']),
        'total_count': len(nodes),
    }


def _compute_bottlenecks(nodes, hard_fwd, limits):
    """For each non-Done node, compute how many downstream nodes are reachable via hard edges."""
    non_done = {n.name for n in nodes if n.status != 'Done'}
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


def _compute_time_distribution(nodes, limits):
    active = [n for n in nodes if n.status != 'Done']
    total_time = sum(n.time for n in active)

    # By context
    by_context = defaultdict(lambda: {'count': 0, 'time': 0.0})
    for n in active:
        ctx = n.context or 'No Context'
        by_context[ctx]['count'] += 1
        by_context[ctx]['time'] += n.time
    ctx_rows = [
        {'context': ctx, 'count': d['count'], 'time': d['time'],
         'pct': round(d['time'] / total_time * 100) if total_time else 0}
        for ctx, d in sorted(by_context.items(), key=lambda x: x[1]['time'], reverse=True)
    ]

    # By type
    by_type = defaultdict(lambda: {'count': 0, 'time': 0.0})
    for n in active:
        by_type[n.type]['count'] += 1
        by_type[n.type]['time'] += n.time
    type_rows = [
        {'type': t, 'count': d['count'], 'time': d['time'],
         'pct': round(d['time'] / total_time * 100) if total_time else 0}
        for t, d in sorted(by_type.items(), key=lambda x: x[1]['time'], reverse=True)
    ]

    # Top 10 time sinks
    top_nodes = sorted(active, key=lambda n: n.time, reverse=True)[:limits.get('time_sinks', 10)]

    return ctx_rows, type_rows, top_nodes


def _get_limits():
    """Read analyze limits from user settings, with defaults."""
    return ConfigManager.get_analyze_limits()


def _rank_goals(goals, priority_goals, hp):
    """Rank goals using intrinsic value from the scoring algorithm, boosted by priority rank.

    Returns goals sorted by rank score descending.
    """
    w_v = hp.get('w_v', 1.0)
    w_i = hp.get('w_i', 1.0)
    goal_boost = hp.get('goal_boost', 1.5)
    rank_multipliers = [
        goal_boost,
        1 + (goal_boost - 1) * 0.66,
        1 + (goal_boost - 1) * 0.33,
    ]

    scored = []
    for g in goals:
        iv = intrinsic_value(g, w_v, w_i)
        # Apply priority rank boost
        if g.name in priority_goals:
            rank_idx = priority_goals.index(g.name)
            if rank_idx < 3:
                iv *= rank_multipliers[rank_idx]
        scored.append((g, iv))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [g for g, _ in scored]


def _compute_goal_comparison(nodes, hard_rev, all_rev, limits):
    """Compute goal stats and pairwise overlap using in-memory adjacency.

    Ranks goals by intrinsic value (from scoring algorithm) boosted by priority rank,
    then caps to keep visualizations readable.
    """
    all_goals = [n for n in nodes if n.type == 'Goal']
    node_map = {n.name: n for n in nodes}
    priority_goals = ConfigManager.get_priority_goals()
    hp = ConfigManager.get_hyperparams()

    # Rank and cap
    ranked = _rank_goals(all_goals, priority_goals, hp)
    goals = ranked[:limits.get('goals', 75)]
    total_goal_count = len(all_goals)

    def _get_subtree(goal_name):
        """BFS backward through hard+soft prerequisite edges."""
        visited = set()
        queue = list(all_rev.get(goal_name, []))
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            for prev_node in all_rev.get(current, []):
                if prev_node not in visited:
                    queue.append(prev_node)
        return visited

    goal_rows = []
    subtrees = {}
    for g in goals:
        subtree = _get_subtree(g.name)
        subtrees[g.name] = subtree
        sub_nodes = [node_map[name] for name in subtree if name in node_map]
        total = len(sub_nodes)
        done = sum(1 for n in sub_nodes if n.status == 'Done')
        blocked = sum(1 for n in sub_nodes if n.status == 'Blocked')
        remaining = sum(n.time for n in sub_nodes if n.status != 'Done')
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
    goal_rows.sort(key=lambda r: r['pct'])

    # Pairwise overlap (only among top goals)
    overlap_rows = []
    goal_names = [g.name for g in goals]
    for i in range(len(goal_names)):
        for j in range(i + 1, len(goal_names)):
            a, b = goal_names[i], goal_names[j]
            sa, sb = subtrees.get(a, set()), subtrees.get(b, set())
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
    candidates = [
        n for n in nodes
        if n.status != 'Done' and n.time_o > 0 and n.time_p > 0
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
    active = [n for n in nodes if n.status != 'Done']
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
        results.append({
            'context': ctx,
            'count': c,
            'avg_value': round(sum(d['values']) / c, 1),
            'avg_interest': round(sum(d['interests']) / c, 1),
            'avg_difficulty': round(sum(d['difficulties']) / c, 1),
        })
    results.sort(key=lambda r: r['count'], reverse=True)
    return results


def _compute_context_coverage(nodes):
    """Compare configured contexts/subcontexts against actual node assignments."""
    configured_contexts = ConfigManager.get_contexts()
    configured_subcontexts = ConfigManager.get_subcontexts()
    active = [n for n in nodes if n.status != 'Done']

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
        })
    ctx_data.sort(key=lambda r: r['count'])

    # Subcontext coverage
    subctx_counts = defaultdict(lambda: {'count': 0, 'time': 0.0})
    for n in active:
        if n.subcontext:
            key = f"{n.context or '?'}: {n.subcontext}"
            subctx_counts[key]['count'] += 1
            subctx_counts[key]['time'] += n.time

    subctx_data = []
    for ctx, subs in configured_subcontexts.items():
        for sub in subs:
            key = f"{ctx}: {sub}"
            d = subctx_counts.get(key, {'count': 0, 'time': 0.0})
            subctx_data.append({
                'label': key,
                'count': d['count'],
                'time': d['time'],
            })
    subctx_data.sort(key=lambda r: r['count'])

    return ctx_data, subctx_data


def _compute_dependency_structure(nodes, hard_fwd, hard_rev, all_fwd, all_rev, edges, limits):
    non_done_names = {n.name for n in nodes if n.status != 'Done'}
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
_STATUS_COLORS = {'Open': '#0d6efd', 'Blocked': '#dc3545', 'Done': '#198754'}
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


def _hbar_chart(names, values, colors=None, hover_texts=None, x_title=None, height=None):
    """Create a standard horizontal bar chart figure."""
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
    fig.update_layout(**_base_layout(
        height=height,
        margin=dict(l=10, r=20, t=10, b=30),
        yaxis=dict(automargin=True),
        xaxis=dict(title=x_title) if x_title else {},
    ))
    return fig


# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------

def _render_overview(metrics):
    fmt = ConfigManager.format_time_friendly
    cards = [
        ('Goals', str(metrics['goal_count']), '#ffc107'),
        ('Active Nodes', str(metrics['active_count']), '#0d6efd'),
        ('Blocked', f"{metrics['blocked_pct']}%", '#dc3545'),
        ('Remaining Time', fmt(metrics['remaining_time']), '#0dcaf0'),
    ]
    cols = []
    for label, value, color in cards:
        cols.append(dbc.Col(
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
            width=3,
        ))
    return dbc.Row(cols, className="mb-3 g-3")


def _render_bottleneck_chart(data):
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
                      x_title="Downstream nodes reached")
    return dcc.Graph(figure=fig, config=_CHART_CFG)


def _render_time_distribution(ctx_rows, type_rows, top_nodes):
    fmt = ConfigManager.format_time_friendly

    # --- By Context + By Type side by side ---
    top_row = []
    for label, rows, key, color in [
        ("By Context", ctx_rows, 'context', '#0dcaf0'),
        ("By Type", type_rows, 'type', '#ffc107'),
    ]:
        if rows:
            names = [r[key] for r in rows]
            values = [r['time'] for r in rows]
            hover = [
                f"<b>{r[key]}</b><br>"
                f"{fmt(r['time'])} ({r['pct']}%)<br>"
                f"{r['count']} nodes"
                for r in rows
            ]
            fig = _hbar_chart(names, values, colors=color, hover_texts=hover,
                              x_title="Hours")
            top_row.append(dbc.Col([
                html.H6(label, className="text-muted mb-1"),
                dcc.Graph(figure=fig, config=_CHART_CFG),
            ], width=6))
        else:
            top_row.append(dbc.Col(
                html.P("No data.", className="text-muted small"), width=6))

    sections = [dbc.Row(top_row, className="g-3")]

    # --- Top 10 Time Sinks below ---
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
                          x_title="Hours")
        sections.append(html.H6("Top 10 Time Sinks", className="text-muted mb-1 mt-3"))
        sections.append(dcc.Graph(figure=fig, config=_CHART_CFG))

    return html.Div(sections)


def _render_goal_comparison(goal_rows, overlap_rows, goal_names_ordered):
    fmt = ConfigManager.format_time_friendly

    if not goal_rows:
        return html.P("No goals defined.", className="text-muted small")

    sections = []

    # --- Completion bar chart (stacked: done + remaining) ---
    # Sort by completion ascending for the chart (least complete at top)
    sorted_goals = list(reversed(goal_rows))  # goal_rows already sorted by pct asc
    names = [g['name'] for g in sorted_goals]
    done_pcts = [g['pct'] for g in sorted_goals]
    remaining_pcts = [100 - g['pct'] for g in sorted_goals]
    hover_done = [
        f"<b>{g['name']}</b><br>"
        f"Done: {g['done']} / {g['total']} ({g['pct']}%)<br>"
        f"Remaining: {fmt(g['remaining'])}<br>"
        f"Blocked: {g['blocked']}"
        + (f"<br>Priority #{g['priority_rank']}" if g['priority_rank'] else "")
        for g in sorted_goals
    ]
    hover_rem = [f"Remaining: {100 - g['pct']}%" for g in sorted_goals]

    height = max(200, len(names) * 32 + 60)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=names, x=done_pcts, orientation='h',
        marker_color='#198754', opacity=0.9, name='Done',
        hovertext=hover_done, hoverinfo='text',
    ))
    fig.add_trace(go.Bar(
        y=names, x=remaining_pcts, orientation='h',
        marker_color='#495057', opacity=0.6, name='Remaining',
        hovertext=hover_rem, hoverinfo='text',
    ))
    fig.update_layout(**_base_layout(
        barmode='stack', height=height,
        margin=dict(l=10, r=20, t=10, b=30),
        yaxis=dict(automargin=True),
        xaxis=dict(title="Completion %", range=[0, 100]),
    ))
    sections.append(dcc.Graph(figure=fig, config=_CHART_CFG))

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

        hm_size = max(300, n * 40 + 80)
        hm_fig = go.Figure(go.Heatmap(
            z=matrix, x=gnames, y=gnames,
            colorscale=[[0, _BG], [0.01, '#1a3a5c'], [0.5, '#0d6efd'], [1, '#60a5fa']],
            hovertext=hover_matrix, hoverinfo='text',
            showscale=False,
        ))
        hm_fig.update_layout(**_base_layout(
            height=hm_size,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(automargin=True, tickangle=-45, side='bottom'),
            yaxis=dict(automargin=True, autorange='reversed'),
        ))

        sections.append(html.H6("Shared Prerequisites", className="text-muted mb-1 mt-3"))
        sections.append(html.P(
            "Goals sharing subtasks. Brighter = more overlap.",
            className="text-muted small"))
        sections.append(dcc.Graph(figure=hm_fig, config=_CHART_CFG))

    return html.Div(sections)


def _render_risk_chart(data):
    if not data:
        return html.P("No nodes with sufficient time estimate data.", className="text-muted small")

    fmt = ConfigManager.format_time_friendly
    # Reverse for bottom-up display (largest spread at top)
    data = list(reversed(data))
    names = [d['name'] for d in data]
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

    height = max(200, len(names) * 28 + 60)
    fig = go.Figure()
    # Invisible base bar (pushes the visible bar right)
    fig.add_trace(go.Bar(
        y=names, x=optimistic, orientation='h',
        marker_color='rgba(0,0,0,0)', showlegend=False,
        hoverinfo='skip',
    ))
    # Visible range bar (optimistic to pessimistic)
    fig.add_trace(go.Bar(
        y=names, x=spreads, orientation='h',
        marker_color='#dc3545', opacity=0.7,
        hovertext=hover, hoverinfo='text',
    ))
    # Expected value markers
    fig.add_trace(go.Scatter(
        y=names, x=expected, mode='markers',
        marker=dict(color='#ffc107', size=8, symbol='diamond'),
        hoverinfo='skip',
    ))
    fig.update_layout(**_base_layout(
        barmode='stack', height=height,
        margin=dict(l=10, r=20, t=10, b=30),
        yaxis=dict(automargin=True),
        xaxis=dict(title="Hours"),
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


def _render_dependency_structure(dep_data):
    chain = dep_data['longest_chain']
    length = dep_data['longest_length']
    deepest = dep_data['deepest']
    most_connected = dep_data['most_connected']

    sections = []

    # Longest chain
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
        sections.append(html.Div([
            html.H6("Longest Prerequisite Chain", className="text-muted mb-1"),
            html.Div(chain_items, style={
                "padding": "8px 12px", "overflowX": "auto",
                "whiteSpace": "nowrap", "display": "flex",
                "alignItems": "center", "gap": "2px",
                "justifyContent": "flex-start",
            }),
        ]))
    else:
        sections.append(html.Div([
            html.H6("Longest Prerequisite Chain", className="text-muted mb-1"),
            html.P("No dependency chains found.", className="text-muted small"),
        ]))

    # Deepest + Most Connected side by side as bar charts
    charts_row = []
    for label, items, key, color in [
        ("Deepest Nodes", deepest, 'prereq_count', '#0dcaf0'),
        ("Most Connected", most_connected, 'degree', '#6f42c1'),
    ]:
        if items:
            names = [d['name'] for d in items]
            values = [d[key] for d in items]
            fig = _hbar_chart(names, values, colors=color,
                              x_title="Hard prereqs" if key == 'prereq_count' else "Connections")
            charts_row.append(dbc.Col([
                html.H6(label, className="text-muted mb-1"),
                dcc.Graph(figure=fig, config=_CHART_CFG),
            ], width=6))
        else:
            charts_row.append(dbc.Col(
                html.P("No data.", className="text-muted small"), width=6))

    if charts_row:
        sections.append(dbc.Row(charts_row, className="g-3 mt-2"))

    return html.Div(sections)


def _render_ratings_chart(data):
    if not data:
        return html.P("No active nodes.", className="text-muted small")

    # Reverse so largest context is at top (Plotly draws bottom-up)
    data = list(reversed(data))
    contexts = [d['context'] for d in data]
    height = max(200, len(contexts) * 32 + 80)

    fig = go.Figure()
    for attr, label, color in [
        ('avg_value', 'Value', '#0d6efd'),
        ('avg_interest', 'Interest', '#ffc107'),
        ('avg_difficulty', 'Difficulty', '#dc3545'),
    ]:
        values = [d[attr] for d in data]
        hover = [
            f"<b>{d['context']}</b><br>"
            f"{label}: {d[attr]}<br>"
            f"{d['count']} nodes"
            for d in data
        ]
        fig.add_trace(go.Bar(
            y=contexts, x=values, orientation='h',
            name=label, marker_color=color, opacity=0.85,
            hovertext=hover, hoverinfo='text',
        ))

    fig.update_layout(**_base_layout(
        barmode='group', height=height,
        margin=dict(l=10, r=20, t=10, b=30),
        yaxis=dict(automargin=True),
        xaxis=dict(title="Average Rating", range=[0, 10]),
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
    ))
    return dcc.Graph(figure=fig, config=_CHART_CFG)


def _coverage_color(count):
    """Return a color based on node count: red for sparse, yellow for moderate, green for rich."""
    if count == 0:
        return '#495057'   # empty — dark gray
    elif count < 5:
        return '#dc3545'   # sparse — red
    elif count < 15:
        return '#ffc107'   # moderate — yellow
    else:
        return '#198754'   # rich — green


def _render_context_coverage(ctx_data, subctx_data):
    fmt = ConfigManager.format_time_friendly
    sections = []

    if ctx_data:
        names = [d['context'] for d in ctx_data]
        counts = [d['count'] for d in ctx_data]
        colors = [_coverage_color(d['count']) for d in ctx_data]
        hover = [
            f"<b>{d['context']}</b><br>"
            f"Nodes: {d['count']}<br>"
            f"Time: {fmt(d['time'])}<br>"
            f"Avg value: {d['avg_value']}<br>"
            f"Avg interest: {d['avg_interest']}"
            if d['count'] > 0 else
            f"<b>{d['context']}</b><br>No nodes assigned"
            for d in ctx_data
        ]
        height = max(180, len(names) * 28 + 60)
        fig = _hbar_chart(names, counts, colors=colors, hover_texts=hover,
                          x_title="Node count")
        # Override the reversal — data is already sorted ascending (sparsest at top)
        fig.data[0].y = names
        fig.data[0].x = counts
        fig.data[0].marker.color = colors
        fig.data[0].hovertext = hover
        fig.update_layout(height=height)

        sections.append(html.H6("By Context", className="text-muted mb-1"))
        sections.append(dcc.Graph(figure=fig, config=_CHART_CFG))

    if subctx_data:
        names = [d['label'] for d in subctx_data]
        counts = [d['count'] for d in subctx_data]
        colors = [_coverage_color(d['count']) for d in subctx_data]
        hover = [
            f"<b>{d['label']}</b><br>"
            f"Nodes: {d['count']}<br>"
            f"Time: {fmt(d['time'])}"
            if d['count'] > 0 else
            f"<b>{d['label']}</b><br>No nodes assigned"
            for d in subctx_data
        ]
        height = max(180, len(names) * 28 + 60)
        fig = _hbar_chart(names, counts, colors=colors, hover_texts=hover,
                          x_title="Node count")
        fig.data[0].y = names
        fig.data[0].x = counts
        fig.data[0].marker.color = colors
        fig.data[0].hovertext = hover
        fig.update_layout(height=height)

        sections.append(html.H6("By Subcontext", className="text-muted mb-1 mt-3"))
        sections.append(dcc.Graph(figure=fig, config=_CHART_CFG))

    if not sections:
        return html.P("No contexts configured.", className="text-muted small")

    # Legend
    sections.append(html.Div([
        html.Span("\u2588 ", style={"color": "#dc3545"}),
        html.Span("< 5 nodes", className="text-muted small me-3"),
        html.Span("\u2588 ", style={"color": "#ffc107"}),
        html.Span("5\u201314 nodes", className="text-muted small me-3"),
        html.Span("\u2588 ", style={"color": "#198754"}),
        html.Span("15+ nodes", className="text-muted small me-3"),
        html.Span("\u2588 ", style={"color": "#495057"}),
        html.Span("Empty", className="text-muted small"),
    ], className="mt-1"))

    return html.Div(sections)


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
        node_map = {n.name: n for n in nodes}

        if not nodes:
            return html.Div([
                html.H5("Analyze", className="text-muted"),
                html.P("No nodes in the graph yet.", className="text-muted small"),
            ], style={"textAlign": "center", "marginTop": "20%"})

        hard_fwd, hard_rev, all_fwd, all_rev = _build_adjacency(edges)

        # Compute all sections
        limits = _get_limits()
        overview = _compute_overview(nodes, edges)
        bottlenecks = _compute_bottlenecks(nodes, hard_fwd, limits)
        ctx_rows, type_rows, top_nodes = _compute_time_distribution(nodes, limits)
        ratings_data = _compute_ratings(nodes)
        goal_rows, overlap_rows, total_goal_count = _compute_goal_comparison(nodes, hard_rev, all_rev, limits)
        risk_data = _compute_risk(nodes, limits)
        dep_data = _compute_dependency_structure(nodes, hard_fwd, hard_rev, all_fwd, all_rev, edges, limits)
        ctx_coverage, subctx_coverage = _compute_context_coverage(nodes)

        # Goal names for heatmap axis ordering
        goal_names_ordered = [g['name'] for g in goal_rows]

        # Render all sections
        return [
            _render_overview(overview),
            html.Hr(className="my-3"),

            html.H5("Bottleneck Analysis", className="mb-1"),
            html.P("Nodes whose completion would unblock the most downstream work.",
                   className="text-muted small"),
            _render_bottleneck_chart(bottlenecks),
            html.Hr(className="my-3"),

            html.H5("Time Distribution", className="mb-1"),
            html.P("Where remaining time is concentrated across your graph.",
                   className="text-muted small"),
            _render_time_distribution(ctx_rows, type_rows, top_nodes),
            html.Hr(className="my-3"),

            html.H5("Node Ratings", className="mb-1"),
            html.P("Average value, interest, and difficulty by context.",
                   className="text-muted small"),
            _render_ratings_chart(ratings_data),
            html.Hr(className="my-3"),

            html.H5("Goal Comparison", className="mb-1"),
            html.P(
                f"Top {len(goal_rows)} of {total_goal_count} goals, ranked by scoring algorithm."
                if total_goal_count > len(goal_rows)
                else "Side-by-side progress and overlap for all goals.",
                className="text-muted small"),
            _render_goal_comparison(goal_rows, overlap_rows, goal_names_ordered),
            html.Hr(className="my-3"),

            html.H5("Risk & Uncertainty", className="mb-1"),
            html.P("Nodes with the widest gap between optimistic and pessimistic time estimates.",
                   className="text-muted small"),
            _render_risk_chart(risk_data),
            html.Hr(className="my-3"),

            html.H5("Dependency Structure", className="mb-1"),
            html.P("Structural patterns in the prerequisite graph.",
                   className="text-muted small"),
            _render_dependency_structure(dep_data),
            html.Hr(className="my-3"),

            html.H5("Context Coverage", className="mb-1"),
            html.P("Contexts and subcontexts with few or no assigned nodes may represent blind spots.",
                   className="text-muted small"),
            _render_context_coverage(ctx_coverage, subctx_coverage),
        ]
