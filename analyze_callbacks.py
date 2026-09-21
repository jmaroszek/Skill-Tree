"""
Callback definitions for the Analyze tab.
Computes and renders aggregate analytics about the graph.
"""

from graph_analytics import (
    _build_adjacency,
    _compute_overview,
    _compute_bottlenecks,
    _compute_hub_score,
    _compute_estimation_accuracy,
    _REFLECTION_MIN_N,
    _compute_reflection_drift,
    _compute_throughput,
    _compute_goal_comparison,
    _compute_ratings,
    _compute_context_coverage,
)

import logging
import math
import uuid
from datetime import date
from dash import html, dcc, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from collections import defaultdict
from graph_manager import GraphManager
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from config import ConfigManager, BADGE_PALETTE
from scoring import (
    build_adjacency as _scoring_build_adjacency, total_value, explain_score,
    time_cost_term, GOAL_TIME_REF_HOURS,
)
import style_tokens as tokens

graph_manager = GraphManager()
logger = logging.getLogger(__name__)

# Distinguishes this server process from an earlier one, whose version
# counters restarted from zero, in a signature a page is still holding.
_PROCESS_EPOCH = uuid.uuid4().hex


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


# ---------------------------------------------------------------------------
# Compute functions
# ---------------------------------------------------------------------------


def _get_limits():
    """Read analyze limits from user settings, with defaults."""
    return ConfigManager.get_analyze_limits()


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

# Plotly reads computed values, not CSS variables, so these chart-only
# constants stay literal. Keep them equal to the matching tokens in
# assets/tokens.css (--st-bg-canvas, --st-bg-raised, --st-border-panel).
_BG = '#1a1d21'
_CARD_BG = '#2b3035'
_BORDER = '#495057'
# Was a fourth, independent status palette that painted Blocked in stock
# Bootstrap red (#dc3545) while the rest of the app used #9e3838. Now sourced
# from BADGE_PALETTE so a status means one color everywhere.
_STATUS_COLORS = {
    STATUS_OPEN:    BADGE_PALETTE[STATUS_OPEN][0],
    STATUS_BLOCKED: BADGE_PALETTE[STATUS_BLOCKED][0],
    STATUS_DONE:    BADGE_PALETTE[STATUS_DONE][0],
}
_CHART_CFG = {"displayModeBar": False}


def _graph(fig):
    """A Graph that re-measures its width when the Analyze tab opens.

    The tab usually renders while hidden, where Plotly falls back to a 700 px
    width, and a non-responsive graph keeps it. A responsive one sizes itself
    to its container instead, height included, so the container carries the
    figure's height."""
    extra = {'style': {'height': f'{fig.layout.height}px'}} if fig.layout.height else {}
    return dcc.Graph(figure=fig, config=_CHART_CFG, responsive=True, **extra)

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
    very large ranges, then months, weeks, days, hours — and labels each tick via
    ``ConfigManager.format_time_friendly`` so the axis reads "1y" / "2m" /
    "3w" / "8h" instead of raw hour counts.
    """
    if max_val <= 0:
        return [0], ["0h"]
    settings = ConfigManager.get_time_settings()
    hw = max(1, settings.get('hours_per_week', 40))
    hm = max(1, settings.get('hours_per_month', 160))
    hy = ConfigManager.HOURS_PER_YEAR_MULT * hm
    hd = hw / ConfigManager.DAYS_PER_WEEK

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
    elif max_val >= 4 * hd:
        step = hd
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
    # Tile colors come from BADGE_PALETTE so an Analyze headline and the badge
    # for the same concept elsewhere in the app are the same color. These were
    # stock Bootstrap hues, which made Done and Blocked here visibly different
    # from Done and Blocked on every node.
    cards = [
        ('Goals', str(metrics['goal_count']), BADGE_PALETTE['Goal'][0]),
        ('Milestones', str(metrics['milestone_count']), BADGE_PALETTE['Milestone'][0]),
        ('Active Nodes', str(metrics['active_count']), BADGE_PALETTE[STATUS_OPEN][0]),
        (STATUS_DONE, str(metrics['done_count']), BADGE_PALETTE[STATUS_DONE][0]),
        (STATUS_BLOCKED, f"{metrics['blocked_pct']}%", BADGE_PALETTE[STATUS_BLOCKED][0]),
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
    return _card([title, _graph(fig)])


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
    return _card([title, _graph(fig)])


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
    sections_left.append(_graph(fig))

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
        sections_right.append(_graph(hm_fig))

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
        _graph(fig),
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
            # Light dots with a background-colored halo so each observation
            # reads as a distinct point on top of the box rather than
            # dissolving into the same-blue fill.
            marker=dict(color='#dee2e6', size=7, opacity=0.9,
                        line=dict(color=_BG, width=1)),
            line=dict(color=line_c, width=1.5), fillcolor=fill_c,
            hoveron='points', customdata=[r['name'] for r in ctx_rows],
            hovertemplate=('<b>%{customdata}</b><br>'
                           '%{x:.2f}× estimate<extra></extra>'),
        ))

    all_ratios = [_ratio(r) for _, ctx_rows in ordered for r in ctx_rows]
    rmin, rmax = min(all_ratios), max(all_ratios)
    ladder = (0.0625, 0.125, 0.25, 0.5, 1, 2, 4, 8, 16)
    # Ticks inside a padded data window, *plus* the ladder steps immediately
    # below rmin and above rmax. Without the bracketing steps, a narrow band
    # that falls entirely between two ladder rungs (e.g. all ratios in
    # 0.5-1x) loses its lower reference and floats left of a lone 1x line.
    ticks = [t for t in ladder if rmin / 1.3 <= t <= rmax * 1.3]
    below = [t for t in ladder if t <= rmin]
    above = [t for t in ladder if t >= rmax]
    if below:
        ticks.append(below[-1])
    if above:
        ticks.append(above[0])
    if 1 not in ticks:
        ticks.append(1)
    ticks = sorted(set(ticks))

    # Pin the (log) axis range to the bracketing ticks so both framing
    # references stay on-screen. Autorange would hug the data and clip the
    # lower tick — e.g. a 0.5-1x band would lose its 0.5x line and float
    # left of a lone 1x. The brackets always enclose the data and the 1x
    # line, so this never hides a point. Range is in log10 units.
    import math
    pad = 0.06
    xrange = [math.log10(min(ticks)) - pad, math.log10(max(ticks)) + pad]

    # Aim near the scatter's 420px so the two charts sit level side-by-side,
    # growing only when there are many contexts.
    height = max(420, len(ordered) * 42 + 80)
    fig.update_layout(**_base_layout(
        height=height, showlegend=False,
        margin=dict(l=10, r=20, t=10, b=40),
        xaxis=dict(type='log', title="Actual ÷ Estimated",
                   tickvals=ticks, ticktext=[f"{t:g}×" for t in ticks],
                   range=xrange, gridcolor='#343a40', automargin=True),
        yaxis=dict(automargin=True),
    ))
    fig.add_vline(x=1, line=dict(color='#6c757d', dash='dash', width=1))

    # No footnote for contexts below the minimum: it made this card taller
    # than the scatter beside it.
    return _card([title, _graph(fig)])


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
                   ('d_difficulty', 'Effort')]

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
    return _card([title, _graph(fig)])


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
    return _card([title, _graph(fig)])


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
                   ('avg_difficulty', 'Effort')]

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
        _graph(fig),
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
_SLATE = '#4a6480'  # the palette entry closest to the grey above


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

    # Colours are assigned per bar, stepping through the palette in stack
    # order, so neighbouring segments always differ. A global per-subcontext
    # colour wrapped past the palette's end and put repeats side by side.
    seg_color = {}
    for ctx in ctx_names:
        shown = [n for n in seg_order
                 if (seg_by_ctx[ctx].get(n) or {}).get('time', 0) > 0]
        named_shown = [n for n in shown if n != '(No subcontext)']
        for k, name in enumerate(named_shown):
            seg_color[ctx, name] = _SUBCONTEXT_PALETTE[k % len(_SUBCONTEXT_PALETTE)]
        # The slate entry reads as the neutral grey, so it can't sit last
        # before a "(No subcontext)" segment. The next entry differs from both
        # neighbours: the grey, and the entry before slate.
        if (named_shown and '(No subcontext)' in shown
                and seg_color[ctx, named_shown[-1]] == _SLATE):
            seg_color[ctx, named_shown[-1]] = _SUBCONTEXT_PALETTE[
                (len(named_shown)) % len(_SUBCONTEXT_PALETTE)]
        seg_color[ctx, '(No subcontext)'] = _NO_SUBCONTEXT_COLOR

    fig = go.Figure()
    for seg_name in seg_order:
        xs, hovers, colors = [], [], []
        for ctx in ctx_names:
            s = seg_by_ctx[ctx].get(seg_name)
            colors.append(seg_color.get((ctx, seg_name), _NO_SUBCONTEXT_COLOR))
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
            marker_color=colors, marker_line=dict(color=_BG, width=1),
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
        _graph(fig),
    ])


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------

def register_analyze_callbacks(app, services=None):
    graph_manager = services.graph if services is not None else globals()['graph_manager']

    # Arrival gate. Listening to `main-tabs.active_tab` directly meant every
    # tab switch anywhere in the app posted a request to the server just to
    # have refresh_analyze_tab answer no_update six times — a round-trip that
    # queued behind the real work the user was waiting on. This clientside
    # filter only bumps the store when Analyze is the tab being opened, so
    # switching to Details or Next now costs nothing here.
    app.clientside_callback(
        """
        function(active_tab) {
            if (active_tab !== 'tab-analyze') {
                return window.dash_clientside.no_update;
            }
            return Date.now();
        }
        """,
        Output("analyze-active-store", "data"),
        Input("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )

    # Background prewarm: render the hidden Analyze tab as soon as the core
    # engine's first payload lands, so the first visit finds it ready. Waiting
    # for the payload keeps this compute from competing with the core engine
    # for the server. Starting then, rather than once the browser has gone
    # idle, lets it run while the browser spends most of a second ingesting
    # that payload. The startup cover waits for this render, so the idle wait
    # used to make startup about half a second longer. See
    # assets/startup_cover.js.
    app.clientside_callback(
        """
        function(elements, prewarmed) {
            if (prewarmed || !elements || !elements.length) {
                return window.dash_clientside.no_update;
            }
            return Date.now();
        }
        """,
        Output("analyze-prewarm-store", "data"),
        Input("elements-pending-store", "data"),
        State("analyze-prewarm-store", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("analyze-overview-content", "children"),
        Output("analyze-goals-content", "children"),
        Output("analyze-time-content", "children"),
        Output("analyze-graph-content", "children"),
        Output("analyze-contexts-content", "children"),
        Output("analyze-throughput-content", "children"),
        Output("analyze-sections", "hidden"),
        Output("analyze-loading-cover", "hidden"),
        Output("analyze-rendered-store", "data"),
        Input("analyze-active-store", "data"),
        Input("analyze-prewarm-store", "data"),
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
        # Read as State now that arrival is signalled by analyze-active-store.
        # Still needed: the settings and save-output Inputs fire from any tab.
        State("main-tabs", "active_tab"),
        State("analyze-rendered-store", "data"),
        prevent_initial_call=True,
    )
    def refresh_analyze_tab(_arrived, _prewarm, bottlenecks, goals,
                            thru_gran, thru_start, thru_end, _save_output,
                            active_tab, rendered_signature):
        skip = (no_update,) * 9
        signature = _analyze_signature()
        if ctx.triggered_id in ("analyze-active-store", "analyze-prewarm-store"):
            # Arrivals and the prewarm render only what's out of date. Every
            # write the charts depend on bumps the graph version.
            if rendered_signature == signature:
                return skip
        elif active_tab != "tab-analyze":
            return skip

        try:
            sections = _render_analyze_sections(
                bottlenecks, goals, thru_gran, thru_start, thru_end)
        except Exception:
            # Never strand the tab behind its cover. Leaving the signature
            # unset retries the render on the next visit.
            logger.exception("Analyze render failed")
            error = html.P("The analysis couldn't be computed. "
                           "See the app log for details.",
                           className="text-danger small")
            return error, "", "", "", "", "", False, True, None
        return (*sections, False, True, signature)


def _analyze_signature():
    """What the Analyze charts are computed from, cheaply. The graph version
    covers nodes, edges, and the scoring and time settings. Contexts are
    listed on their own because adding an empty one bumps nothing, and the
    date because the charts are dated."""
    return [_PROCESS_EPOCH, GraphManager._graph_version,
            ConfigManager.get_contexts(), date.today().isoformat()]


def _render_analyze_sections(bottlenecks, goals, thru_gran, thru_start,
                             thru_end):
    """The six section bodies of the Analyze tab, in output order."""
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
