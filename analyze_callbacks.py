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
from scoring import intrinsic_value, total_value, build_adjacency as build_scoring_adjacency

graph_manager = GraphManager()


def _trunc(name, max_len=25):
    """Truncate a name for chart labels, preserving full name in hover."""
    return name if len(name) <= max_len else name[:max_len - 1] + '\u2026'


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


def _compute_top_time_sinks(nodes, limits):
    active = [n for n in nodes if n.status != 'Done']
    return sorted(active, key=lambda n: n.time, reverse=True)[:limits.get('time_sinks', 10)]


def _compute_most_valuable_chain(nodes, edges):
    """Compute the top 5 most valuable non-Done nodes using the scoring algorithm's total_value."""
    hp = ConfigManager.get_hyperparams()
    w_v, w_i = hp.get('w_v', 1.0), hp.get('w_i', 1.0)
    d_H, d_S, d_Syn = hp.get('d_H', 0.6), hp.get('d_S', 0.25), hp.get('d_Syn', 0.35)

    all_nodes_dict = {n.name: n for n in nodes}
    node_names = set(all_nodes_dict.keys())
    H_out, S_out, Syn, Hard_in = build_scoring_adjacency(edges, node_names)

    non_done = [n for n in nodes if n.status != 'Done']
    scored = []
    for n in non_done:
        tv = total_value(n.name, set(), all_nodes_dict, H_out, S_out, Syn, w_v, w_i, d_H, d_S, d_Syn)
        scored.append({'name': n.name, 'type': n.type, 'total_value': round(tv, 1)})

    scored.sort(key=lambda x: x['total_value'], reverse=True)
    return scored[:5]


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
    all_by_ctx = defaultdict(lambda: {'total': 0, 'done': 0})
    active = [n for n in nodes if n.status != 'Done']
    for n in nodes:
        ctx = n.context or 'No Context'
        all_by_ctx[ctx]['total'] += 1
        if n.status == 'Done':
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
    # Truncate names for display, keep originals for hover
    display_names = [_trunc(n) for n in names]
    # Reverse so largest is at top (Plotly draws bottom-up)
    names = list(reversed(names))
    display_names = list(reversed(display_names))
    values = list(reversed(values))
    if isinstance(color, list):
        color = list(reversed(color))
    if hover_texts:
        hover_texts = list(reversed(hover_texts))

    if height is None:
        height = max(180, len(names) * 28 + 60)

    fig = go.Figure(go.Bar(
        y=display_names, x=values, orientation='h',
        marker_color=color, opacity=0.9,
        hovertext=hover_texts,
        hoverinfo='text' if hover_texts else 'x+y',
    ))
    fig.update_layout(**_base_layout(
        height=height,
        margin=dict(l=10, r=20, t=10, b=30),
        yaxis=dict(automargin=True, ticksuffix="  "),
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
        ('Done', str(metrics['done_count']), '#198754'),
        ('Blocked', f"{metrics['blocked_pct']}%", '#dc3545'),
        ('Remaining Time', fmt(metrics['remaining_time']), '#0dcaf0'),
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
    display_y_order = [_trunc(n) for n in y_order]
    n_goals = len(y_order)
    shared_height = max(300, n_goals * 32 + 80)
    shared_margin = dict(l=10, r=20, t=30, b=30)

    # --- Completion bar chart (stacked: done + remaining) ---
    sorted_goals = list(reversed(goal_rows))  # reversed for Plotly bottom-up drawing
    display_names = [_trunc(g['name']) for g in sorted_goals]
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

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=display_names, x=done_pcts, orientation='h',
        marker_color='#198754', opacity=0.9, name='Done',
        hovertext=hover_done, hoverinfo='text',
    ))
    fig.add_trace(go.Bar(
        y=display_names, x=remaining_pcts, orientation='h',
        marker_color='#495057', opacity=0.6, name='Remaining',
        hovertext=hover_rem, hoverinfo='text',
    ))
    fig.update_layout(**_base_layout(
        barmode='stack', height=shared_height,
        margin=shared_margin,
        yaxis=dict(automargin=True, ticksuffix="  ",
                   categoryorder='array', categoryarray=display_y_order),
        xaxis=dict(title="Completion %", range=[0, 100]),
    ))
    sections_left.append(html.H6("Completion", className="text-muted mb-1"))
    sections_left.append(dcc.Graph(figure=fig, config=_CHART_CFG))

    # --- Shared Prerequisites Heatmap ---
    if overlap_rows and len(goal_names_ordered) > 1:
        gnames = goal_names_ordered
        display_gnames = [_trunc(n) for n in gnames]
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

        # Reorder matrix rows to match bar chart y-axis (y_order = pct ascending)
        reorder_idx = [gnames.index(name) if name in gnames else -1 for name in y_order]
        reordered_matrix = []
        reordered_hover = []
        for ri in reorder_idx:
            if ri >= 0:
                reordered_matrix.append(matrix[ri])
                reordered_hover.append(hover_matrix[ri])
            else:
                reordered_matrix.append([0] * n)
                reordered_hover.append([''] * n)

        hm_fig = go.Figure(go.Heatmap(
            z=reordered_matrix, x=display_gnames, y=display_y_order,
            colorscale=[[0, _BG], [0.25, '#162d50'], [0.5, '#1a5276'], [0.75, '#2185d0'], [1, '#54b8ff']],
            hovertext=reordered_hover, hoverinfo='text',
            showscale=False,
        ))
        hm_fig.update_layout(**_base_layout(
            height=shared_height,
            margin=shared_margin,
            xaxis=dict(automargin=True, tickangle=-45, side='bottom'),
            yaxis=dict(automargin=True, ticksuffix="  ",
                       categoryorder='array', categoryarray=display_y_order),
        ))

        sections_right.append(html.H6("Shared Prerequisites", className="text-muted mb-1"))
        sections_right.append(dcc.Graph(figure=hm_fig, config=_CHART_CFG))

    # If no overlap data, show a message in the right column
    if not sections_right:
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
    names = [d['name'] for d in data]
    display_names = [_trunc(d['name']) for d in data]
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
        x=display_names, y=optimistic, orientation='v',
        marker_color='rgba(0,0,0,0)', marker_line_width=0, showlegend=False,
        hoverinfo='skip',
    ))
    # Visible range bar (optimistic to pessimistic)
    fig.add_trace(go.Bar(
        x=display_names, y=spreads, orientation='v',
        marker_color='#dc3545', opacity=0.7,
        hovertext=hover, hoverinfo='text',
    ))
    # Expected value markers
    fig.add_trace(go.Scatter(
        x=display_names, y=expected, mode='markers',
        marker=dict(color='#ffc107', size=8, symbol='diamond'),
        hoverinfo='skip',
    ))
    fig.update_layout(**_base_layout(
        barmode='stack', height=350,
        margin=dict(l=40, r=10, t=10, b=10),
        xaxis=dict(automargin=True, tickangle=-45),
        yaxis=dict(title="Hours"),
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

    If total_height is given, each chart gets roughly half to align with the bottleneck column.
    """
    deepest = dep_data['deepest']
    most_connected = dep_data['most_connected']
    half_h = (total_height - 120) // 2 if total_height else None  # subtract titles + margins + gap

    sections = []
    chart_data = [
        ("Deepest Nodes", deepest, 'prereq_count', '#0dcaf0'),
        ("Most Connected", most_connected, 'degree', '#6f42c1'),
    ]
    for idx, (label, items, key, color) in enumerate(chart_data):
        mt = "mt-3" if idx > 0 else ""
        if items:
            names = [d['name'] for d in items]
            values = [d[key] for d in items]
            fig = _hbar_chart(names, values, colors=color,
                              x_title="Hard needs" if key == 'prereq_count' else "Connections",
                              height=half_h)
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


def _render_most_valuable_chain(mvc_data):
    """Render top 5 most valuable nodes as pill-and-arrow display with value scores."""
    if not mvc_data:
        return html.P("No non-Done nodes found.", className="text-muted small")

    chain_items = []
    for i, d in enumerate(mvc_data):
        chain_items.append(html.Span(d['name'], style={
            "padding": "2px 8px", "borderRadius": "4px",
            "backgroundColor": _CARD_BG, "border": f"1px solid {_BORDER}",
            "fontSize": "0.82rem", "whiteSpace": "nowrap",
        }))
        if i < len(mvc_data) - 1:
            chain_items.append(html.Span(" \u2192 ", className="text-muted",
                                         style={"fontSize": "0.82rem"}))
    return html.Div(chain_items, style={
        "padding": "8px 12px", "overflowX": "auto",
        "whiteSpace": "nowrap", "display": "flex",
        "alignItems": "center", "gap": "2px",
        "justifyContent": "flex-start",
    })


def _render_ratings_chart(data):
    if not data:
        return html.P("No active nodes.", className="text-muted small")

    # Sort so largest context is at top (data is already sorted by count desc)
    contexts = [d['context'] for d in data]
    display_contexts = [_trunc(d['context']) for d in data]
    metrics = ['avg_difficulty', 'avg_interest', 'avg_value']
    metric_labels = ['Difficulty', 'Interest', 'Value']

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
        y=display_contexts,
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
        yaxis=dict(automargin=True, ticksuffix="  "),
        xaxis=dict(side='bottom'),
    ))
    return html.Div([
        html.H6("Ratings", className="text-muted mb-1"),
        dcc.Graph(figure=fig, config=_CHART_CFG),
    ])


def _coverage_color_hours(time):
    """Return a color based on total hours: gray for empty, red for sparse, yellow for moderate, green for rich."""
    if time == 0:
        return '#495057'   # empty -- dark gray
    elif time < 50:
        return '#dc3545'   # sparse -- red
    elif time < 200:
        return '#ffc107'   # moderate -- yellow
    else:
        return '#198754'   # rich -- green


def _render_context_coverage(ctx_data, subctx_data, chart_height=None):
    """Returns a tuple: (ctx_chart for column, subctx_chart for full-width row)."""
    fmt = ConfigManager.format_time_friendly
    sections_ctx = []
    sections_sub = []

    if ctx_data:
        names = [d['context'] for d in ctx_data]
        hours = [d['time'] for d in ctx_data]
        colors = [_coverage_color_hours(d['time']) for d in ctx_data]
        hover = [
            f"<b>{d['context']}</b><br>"
            f"Time: {fmt(d['time'])}<br>"
            f"Nodes: {d['count']}<br>"
            f"Avg value: {d['avg_value']}<br>"
            f"Avg interest: {d['avg_interest']}"
            if d['count'] > 0 else
            f"<b>{d['context']}</b><br>No nodes assigned"
            for d in ctx_data
        ]
        height = chart_height or max(180, len(names) * 28 + 60)
        fig = _hbar_chart(names, hours, colors=colors, hover_texts=hover,
                          x_title="Hours", height=height)
        # Override the reversal -- data is already sorted ascending (sparsest at top)
        display_names = [_trunc(n) for n in names]
        fig.data[0].y = display_names
        fig.data[0].x = hours
        fig.data[0].marker.color = colors
        fig.data[0].hovertext = hover

        sections_ctx.append(html.H6("Hours by Context", className="text-muted mb-1"))
        sections_ctx.append(dcc.Graph(figure=fig, config=_CHART_CFG))

    if subctx_data:
        # Sort descending for vertical display (largest on left)
        sorted_sub = sorted(subctx_data, key=lambda d: d['time'], reverse=True)
        names = [d['label'] for d in sorted_sub]
        display_names = [_trunc(n) for n in names]
        hours = [d['time'] for d in sorted_sub]
        colors = [_coverage_color_hours(d['time']) for d in sorted_sub]
        hover = [
            f"<b>{d['label']}</b><br>"
            f"Time: {fmt(d['time'])}<br>"
            f"Nodes: {d['count']}"
            if d['count'] > 0 else
            f"<b>{d['label']}</b><br>No nodes assigned"
            for d in sorted_sub
        ]
        fig = go.Figure(go.Bar(
            x=display_names, y=hours, orientation='v',
            marker_color=colors, opacity=0.9,
            hovertext=hover, hoverinfo='text',
        ))
        fig.update_layout(**_base_layout(
            height=350,
            margin=dict(l=40, r=10, t=10, b=10),
            xaxis=dict(automargin=True, tickangle=-45),
            yaxis=dict(title="Hours"),
        ))

        sections_sub.append(html.H6("By Subcontext", className="text-muted mb-1 mt-3"))
        sections_sub.append(dcc.Graph(figure=fig, config=_CHART_CFG))

    # Legend (add to whichever has content, prefer subctx since it's below)
    legend = html.Div([
        html.Span("\u2588 ", style={"color": "#dc3545"}),
        html.Span("< 50h", className="text-muted small me-3"),
        html.Span("\u2588 ", style={"color": "#ffc107"}),
        html.Span("50\u2013199h", className="text-muted small me-3"),
        html.Span("\u2588 ", style={"color": "#198754"}),
        html.Span("200h+", className="text-muted small me-3"),
        html.Span("\u2588 ", style={"color": "#495057"}),
        html.Span("Empty", className="text-muted small"),
    ], className="mt-1")

    if sections_sub:
        sections_sub.append(legend)
    elif sections_ctx:
        sections_ctx.append(legend)

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
        top_nodes = _compute_top_time_sinks(nodes, limits)
        ratings_data = _compute_ratings(nodes)
        goal_rows, overlap_rows, total_goal_count = _compute_goal_comparison(nodes, hard_rev, all_rev, limits)
        risk_data = _compute_risk(nodes, limits)
        dep_data = _compute_dependency_structure(nodes, hard_fwd, hard_rev, all_fwd, all_rev, edges, limits)
        ctx_coverage, subctx_coverage = _compute_context_coverage(nodes)
        # Shared height for Hours by Context + Longest Projects row
        time_row_height = max(
            max(180, len(ctx_coverage) * 28 + 60),
            max(180, len(top_nodes) * 28 + 60),
        )
        ctx_chart, subctx_chart = _render_context_coverage(ctx_coverage, subctx_coverage, chart_height=time_row_height)

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
            html.P("Where remaining time is concentrated and where estimates are uncertain.",
                   className="text-muted small"),
            _render_time_distribution(ctx_chart, subctx_chart, top_nodes, risk_data, row_height=time_row_height),
            html.Hr(className="my-3"),

            # -- Graph Structure --
            html.H5("Graph Structure", className="mb-1"),
            html.P("Structural patterns in the graph.",
                   className="text-muted small"),
            # Row 1: Bottleneck + Deepest/Connected (matched heights)
            dbc.Row([
                dbc.Col([html.H6("Bottleneck Analysis", className="text-muted mb-1"),
                         _render_bottleneck_chart(bottlenecks)], width=6),
                dbc.Col([_render_dep_charts(dep_data,
                         total_height=max(200, len(bottlenecks) * 28 + 60))], width=6),
            ], className="g-3"),
            # Row 2: Longest Prerequisite Chain
            html.H6("Longest Prerequisite Chain", className="text-muted mb-1 mt-3"),
            _render_longest_chain(dep_data),
            html.Hr(className="my-3"),

            # -- Contexts --
            html.H5("Contexts", className="mb-1"),
            html.P("Average ratings by context.",
                   className="text-muted small"),
            html.Div([_render_ratings_chart(ratings_data)], style={"maxWidth": "600px"}),
        ]
