"""The Analyze tab's charts and tables, drawn from data.py's numbers.

Plotly reads computed values and can't resolve a CSS variable, so the chart
colours here are literals; test_style_tokens pins them to their tokens."""
import math
from collections import defaultdict

import plotly.graph_objects as go
from dash import dcc, html

from skilltree.domain.models import STATUS_BLOCKED, STATUS_DONE, STATUS_OPEN
from skilltree.domain.time import DAYS_PER_WEEK, HOURS_PER_YEAR_MULT
from skilltree.features.analyze.data import RECENT_DAYS, REFLECTION_MIN_N, TYPE_ORDER
from skilltree.store import settings
from skilltree.store.settings import DEFAULT_ANALYZE_LIMITS
from skilltree.ui import kit as ui_kit
from skilltree.ui import tokens
from skilltree.ui.components.duration import format_time_friendly
from skilltree.ui.styles import BADGE_PALETTE, badge_style


def _trunc(name, max_len=25):
    """Truncate a name for chart labels, preserving full name in hover."""
    return name if len(name) <= max_len else name[:max_len - 1] + '\u2026'


# Plotly reads computed values, not CSS variables, so these chart-only
# constants stay literal. Keep them equal to the matching tokens in
# assets/css/tokens.css (--st-bg-canvas, --st-bg-raised).
_BG = '#1a1d21'


_CARD_BG = '#2b3035'


_TEXT = '#dee2e6'  # --st-text-primary


_SOFT = '#adb5bd'  # --st-text-soft: tick labels and axis titles


_GRID = '#2b3035'  # --st-bg-raised: gridlines, a step above the canvas


# Lato is loaded by assets/vendor/lato; Plotly's default stack would not use it.
_FONT = "Lato, -apple-system, 'Segoe UI', sans-serif"


_CHART_CFG = {"displayModeBar": False}


def _graph(fig, zoom=False):
    """A Graph that re-measures its width when the Analyze tab opens. Its
    hover text is shown by assets/analyze/rating_dist.js in the Plan charts' tooltip:
    each mark's ``customdata`` is the text, first line in bold.

    The tab usually renders while hidden, where Plotly falls back to a 700 px
    width, and a non-responsive graph keeps it. A responsive one sizes itself
    to its container instead, height included, so the container carries the
    figure's height.

    Drag-to-zoom is off unless ``zoom`` is set. On bars and the heatmap it
    only crops, and the crosshair cursor and a stray drag got in the way of
    hovering. The Time Estimation Accuracy charts keep it: their points crowd
    together at the low end of a log axis."""
    if not zoom:
        fig.update_layout(dragmode=False)
        fig.update_xaxes(fixedrange=True)
        fig.update_yaxes(fixedrange=True)
    extra = {'style': {'height': f'{fig.layout.height}px'}} if fig.layout.height else {}
    return dcc.Graph(figure=fig, config=_CHART_CFG, responsive=True,
                     className="analyze-plot", **extra)


def _base_layout(**overrides):
    """Return a Plotly layout dict that sits beside the HTML charts: the
    app's font, soft tick labels and no axis lines. The legend is HTML, and
    hover boxes are off (``hoverinfo='none'`` on each trace, which still fires
    the events assets/analyze/rating_dist.js shows the shared tooltip on)."""
    layout = dict(
        template="plotly_dark",
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        font=dict(family=_FONT, size=12, color=_TEXT),
    )
    for name in ('xaxis', 'yaxis'):
        axis = dict(tickfont=dict(size=12, color=_SOFT), automargin=True,
                    gridcolor=_GRID, zerolinecolor=_GRID, showline=False)
        given = dict(overrides.pop(name, {}))
        if 'title' in given:
            # The x title sits a little below the tick labels, not against them.
            given['title'] = dict(text=given['title'], font=dict(size=14, color=_SOFT),
                                  standoff=16 if name == 'xaxis' else 8)
        layout[name] = {**axis, **given}
    layout.update(overrides)
    return layout


def _card(children, fill=False, class_name=None):
    """Wrap a visual in the standard Analyze card — a subtly raised panel
    with a soft border and rounded corners, matching the overview tiles.
    ``fill`` stretches it to its column's height, so two cards side by side
    end level however tall their contents are."""
    return html.Div(children, className=class_name, style={
        "backgroundColor": _BG,
        "borderRadius": "6px",
        "padding": "12px 16px",
        **({"height": "100%"} if fill else {}),
    })


def _friendly_xticks(max_val: float) -> tuple[list, list]:
    """Return (tickvals, ticktext) for an hours-valued axis with friendly labels.

    Picks a step that scales with the user's productivity settings — years for
    very large ranges, then months, weeks, days, hours — and labels each tick via
    ``format_time_friendly`` so the axis reads "1y" / "2m" /
    "3w" / "8h" instead of raw hour counts.
    """
    if max_val <= 0:
        return [0], ["0h"]
    time_settings = settings.TIME_SETTINGS.get()
    hw = max(1, time_settings['hours_per_week'])
    hm = max(1, time_settings['hours_per_month'])
    hy = HOURS_PER_YEAR_MULT * hm
    hd = hw / DAYS_PER_WEEK

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
    ticktext = [format_time_friendly(t) for t in tickvals]
    return tickvals, ticktext


def _log_time_ticks(min_val: float, max_val: float) -> tuple[list, list]:
    """Return (tickvals, ticktext) for a log-scaled hours axis, placing ticks
    at 1-2-5 ×10^k values within range and labelling each via
    ``format_time_friendly``."""
    if max_val <= 0:
        return [1.0], [format_time_friendly(1.0)]
    lo = max(0.5, min_val)
    vals = []
    k = math.floor(math.log10(lo))
    while True:
        for base in (1, 2, 5):
            # 10.0 ** k keeps v a float — format_time_friendly rounds with
            # ndigits, which leaves ints unchanged, and int.is_integer()
            # only exists on Python 3.12+.
            v = base * (10.0 ** k)
            if v < lo / 1.5:
                continue
            if v > max_val * 1.5:
                return vals, [format_time_friendly(x) for x in vals]
            vals.append(v)
        k += 1


def render_overview(metrics):
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


def _bottleneck_label(names):
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} + {names[1]}"
    return f"{names[0]} + {len(names) - 1} more"


def render_bottleneck_chart(data):
    """Open nodes ranked by the unfinished work they gate. Each bar starts
    with a gray stub for the node's own time, so a cheap gate and an
    expensive one with the same reach read differently. The number at the
    end is the work unlocked. Built from the same rows as the Goals chart,
    so the two share their type, spacing and tooltip. The section header
    names the chart, so the card has no title of its own."""
    if not data:
        return _card([html.P("No open node gates any unfinished work.",
                             className="text-muted small mb-0")])

    fmt = format_time_friendly
    widest = max(d['own_hours'] + d['hours'] for d in data) or 1
    body = []
    for d in data:
        nodes = f"{d['count']} node{'s' if d['count'] != 1 else ''}"
        if len(d['names']) == 1:
            tip = (f"{d['names'][0]}\nTakes {fmt(d['own_hours'])}"
                   f"\nUnlocks {fmt(d['hours'])} across {nodes}")
        else:
            tip = ("\n".join(d['names'])
                   + f"\nTake {fmt(d['own_hours'])} together"
                   + f"\nEach unlocks the same {nodes} ({fmt(d['hours'])})")
        segments = [html.Div(className=cls, style={'width': f"max({100 * h / widest:.2f}%, 2px)"})
                    for cls, h in (("bn-own", d['own_hours']), ("bn-unlocks", d['hours']))
                    if h > 0]
        label = _bottleneck_label(d['names'])
        body.append(html.Div([
            html.Div(html.Span(label, className="gp-name-text", title=" + ".join(d['names'])),
                     className="gp-name"),
            html.Div(html.Div(segments, className="gp-track"), className="gp-bar",
                     **{'data-tip': tip}),
            html.Div(fmt(d['hours']), className="gp-pct"),
        ], className="gp-row"))
    legend = html.Div([
        html.Span([html.I(className="gp-swatch bn-own"), "Own time"]),
        html.Span([html.I(className="gp-swatch bn-unlocks"), "Work unlocked"]),
    ], className="gp-legend")
    return _card([html.Div([html.Div(body), legend],
                           className="goal-progress bottlenecks")])


def _progress_label(row):
    """A Goals row's percent. Only a Goal whose every node is Done reads
    100%; one whose last open node holds no hours of its own reads 99.9%."""
    if row['pct'] == 100:
        return "100%"
    return _share_label(min(row['share'], 0.999))


def render_goal_progress(rows):
    """One row per top Goal: a bar of the share of its estimated work that is
    Done, the brighter part finished in the last six months, then the
    percent. HTML rather than Plotly, like the Contexts table, so each name
    sits on its bar's line and the priority badge can follow the name."""
    if not rows:
        return _card(html.P("No goals defined.", className="text-muted small mb-0"))

    fmt = format_time_friendly
    months = round(RECENT_DAYS / 30.4)
    body = []
    for r in rows:
        total = r['total_time']
        if total > 0:
            recent = r['recent_time'] / total
            earlier = r['done_time'] / total - recent
        else:
            recent, earlier = 0.0, r['share']
        segments = [html.Div(className=cls, style={'width': f"max({100 * w:.2f}%, 2px)"})
                    for cls, w in (("gp-earlier", earlier), ("gp-recent", recent))
                    if w > 0]
        if total <= 0:
            done_line = f"{r['done']} of {r['total']} nodes done"
        elif r['done_time'] > 0:
            done_line = f"{fmt(r['done_time'])} of {fmt(total)} done"
        else:
            done_line = f"None of its {fmt(total)} done yet"
        n = r['recent_count']
        recent_line = (f"{fmt(r['recent_time'])} of it in the last {months} months, "
                       f"across {n} node{'s' if n != 1 else ''}"
                       if r['recent_time'] else
                       f"Nothing finished in the last {months} months")
        name = [html.Span(r['name'], className="gp-name-text", title=r['name'])]
        if r['priority_rank']:
            name.append(html.Span(str(r['priority_rank']), className="badge gp-rank",
                                  title=f"Priority {r['priority_rank']}",
                                  style=badge_style("PriorityRank", font_size=tokens.FS_XS)))
        body.append(html.Div([
            html.Div(name, className="gp-name"),
            html.Div(html.Div(segments, className="gp-track"), className="gp-bar",
                     **{'data-tip': f"{r['name']}\n{done_line}\n{recent_line}"}),
            html.Div(_progress_label(r), className="gp-pct"),
        ], className="gp-row"))
    legend = html.Div([
        html.Span([html.I(className="gp-swatch gp-earlier"), "Done earlier"]),
        html.Span([html.I(className="gp-swatch gp-recent"), f"Last {months} months"]),
    ], className="gp-legend")
    return _card([html.Div([html.Div(body), legend], className="goal-progress")])


def render_estimation_accuracy(rows):
    """Scatter of estimated vs. actual time for completed nodes, with a y=x
    reference line. Points above the line overran the estimate."""
    if not rows:
        return _card([html.P(
            "No completed nodes have actual-time data yet. Mark nodes Done "
            "with Reflection enabled to populate this chart.",
            className="text-muted small")])

    fmt = format_time_friendly
    colors = settings.NODE_COLORS.get()

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
                f"{r['name']}\n"
                f"Estimated: {fmt(r['estimate'])}\n"
                f"Actual: {fmt(r['actual'])}\n"
                f"{ratio:.1f}\u00d7 estimate"
            )
        fig.add_trace(go.Scatter(
            x=[r['estimate'] for r in trows],
            y=[r['actual'] for r in trows],
            mode='markers', name=ntype,
            marker=dict(size=9, color=colors.get(ntype, '#0d6efd'),
                        line=dict(width=1, color=_BG)),
            customdata=hover, hoverinfo='none',
        ))

    tickvals, ticktext = _log_time_ticks(lo, hi)
    axis = dict(type='log', range=[math.log10(lo), math.log10(hi)],
                tickvals=tickvals, ticktext=ticktext)
    fig.update_layout(**_base_layout(
        height=420,
        margin=dict(l=50, r=20, t=10, b=45),
        xaxis=dict(title="Estimated work time", **axis),
        yaxis=dict(title="Actual work time", **axis),
    ))
    legend = html.Div([
        html.Span([html.I(className="gp-swatch dot",
                          style={'backgroundColor': colors.get(t, '#0d6efd')}), t],
                  className="gp-legend-item", role="button", tabIndex=0,
                  title=f"Show or hide {t}",
                  **{'data-trace': t, 'aria-pressed': 'true'})
        for t in sorted(by_type)], className="gp-legend")
    return _card([_graph(fig, zoom=True), legend], fill=True)


_CTX_ACCURACY_MIN_N = 3  # min completed nodes for a context to get a box


def render_context_accuracy_boxplot(rows):
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
    if not qualifying:
        return _card([html.P(
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
    for context, context_rows in ordered:
        ratios = [_ratio(r) for r in context_rows]
        fig.add_trace(go.Box(
            x=ratios, name=context, orientation='h',
            boxpoints='all', jitter=0.4, pointpos=0, whiskerwidth=0.5,
            # Light dots with a background-colored halo so each observation
            # reads as a distinct point on top of the box rather than
            # dissolving into the same-blue fill.
            marker=dict(color='#dee2e6', size=7, opacity=0.9,
                        line=dict(color=_BG, width=1)),
            line=dict(color=line_c, width=1.5), fillcolor=fill_c,
            hoveron='points', hoverinfo='none',
            customdata=[f"{r['name']}\n{_ratio(r):.2f}× estimate"
                        for r in context_rows],
        ))

    all_ratios = [_ratio(r) for _, context_rows in ordered for r in context_rows]
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
                   range=xrange),
        yaxis=dict(tickfont=dict(size=12, color=_TEXT)),
    ))
    fig.add_vline(x=1, line=dict(color='#6c757d', dash='dash', width=1))

    # No footnote for contexts below the minimum: it made this card taller
    # than the scatter beside it.
    return _card(_graph(fig, zoom=True), fill=True)


_DRIFT_UNDER = '#c0392b'  # overrated going in: the reflection came in lower


_DRIFT_OVER = '#2185d0'   # underrated going in


def render_reflection_drift_chart(rows):
    """Per-context mean drift (``reflect_X - X``) for V/I/D as three
    diverging bar panels on one shared scale. A bar left of zero (red) means
    the user overrated the work going in; right of zero (blue), underrated.
    Length carries the size, which a colour cell near zero could not.
    Only contexts with at least ``REFLECTION_MIN_N`` reflected nodes get a
    row, most-reflected first, with the count after the name.

    HTML rather than Plotly, like Goals: each context's name sits on its
    bars' line and the tooltip is the one the Plan charts use."""
    if not rows:
        return _card([html.P(
            f"Not enough reflected nodes per context yet — a context "
            f"needs at least {REFLECTION_MIN_N} re-rated nodes.",
            className="text-muted small")])

    metric_keys = [('d_value', 'Value'), ('d_interest', 'Interest'),
                   ('d_difficulty', 'Effort')]

    drift_vals = [r[a] for r in rows for a, _ in metric_keys if r[a] is not None]
    rng = max(1, math.ceil(max((abs(v) for v in drift_vals), default=1)))
    # Each track runs a little past +-rng, so the longest bar stops short of
    # the end. ``unit`` is a rating point as a percent of the track.
    unit = 100 / (2.3 * rng)
    tick_at = 50 - rng * unit

    def _cell(r, attr, label):
        v = r[attr]
        n = r['count']
        if v is None:
            tip = f"{r['context']}\n{label}: no data"
            bar = []
        else:
            sign = '+' if v > 0 else ''
            tip = (f"{r['context']}\n{label} drift: {sign}{v}\n"
                   f"{n} reflected node{'s' if n != 1 else ''}")
            bar = [html.Div(className="dr-bar " + ("under" if v < 0 else "over"),
                            style={'width': f"{abs(v) * unit:.2f}%"})] if v else []
        return html.Div(html.Div(bar + [html.Div(className="dr-zero")],
                                 className="dr-track"),
                        className="dr-cell", **{'data-tip': tip})

    def _axis():
        return html.Div([
            html.Span(text, style={'left': f"{left:.2f}%"})
            for text, left in ((f"−{rng}", tick_at), ("0", 50), (f"+{rng}", 100 - tick_at))
        ], className="dr-axis")

    body = [html.Div([html.Div()] + [html.Div(label, className="dr-title")
                                     for _, label in metric_keys],
                     className="gp-row dr-row dr-head")]
    for r in rows:
        body.append(html.Div([
            html.Div([html.Span(r['context'], className="gp-name-text", title=r['context']),
                      html.Span(f"({r['count']})", className="dr-n")],
                     className="gp-name"),
            *[_cell(r, attr, label) for attr, label in metric_keys],
        ], className="gp-row dr-row"))
    body.append(html.Div([html.Div()] + [_axis() for _ in metric_keys],
                         className="gp-row dr-row dr-foot"))
    legend = html.Div([
        html.Span([html.I(className="gp-swatch", style={'backgroundColor': c}), text])
        for c, text in ((_DRIFT_UNDER, "Overrated going in"),
                        (_DRIFT_OVER, "Underrated going in"))
    ], className="gp-legend")
    # In a .hist-fit wrapper: it scrolls, with a fade, once taller than Throughput.
    return _card([html.Div(body, className="drift-chart hist-chart"), legend],
                 class_name="scroll-fade-bottom")


def render_throughput_chart(quarter_rows,
                             granularity=DEFAULT_ANALYZE_LIMITS['throughput_granularity'],
                             by=DEFAULT_ANALYZE_LIMITS['throughput_color']):
    """Stacked vertical bars of hours completed per calendar bucket
    (month/quarter/year), segmented by context or by node type. Contexts get
    no legend: their name and a top-N list of completed nodes (with hours)
    come up on hover. Node types have one, in the badge colors, since there
    are only a few.

    HTML rather than Plotly, like the Plan charts, with the same tooltip.
    There is no capacity line: a part-way month's prorated capacity made it
    drop sharply at the end. The tooltip still gives the share of capacity.
    A long run of buckets turns the labels on their side so they never
    overlap."""
    fmt = format_time_friendly
    if not quarter_rows or all(not r['segments'] for r in quarter_rows):
        return _card([html.P(
            "No nodes with a completion date yet. Mark nodes Done to "
            "populate this chart.", className="text-muted small")])

    total_per_key = defaultdict(float)
    for r in quarter_rows:
        for seg in r['segments']:
            total_per_key[seg['key']] += seg['hours']
    # A Done Milestone holds no hours, and would only add an empty legend entry.
    total_per_key = {k: h for k, h in total_per_key.items() if h > 0}
    if by == 'type':
        keys = sorted(total_per_key, key=lambda t: (TYPE_ORDER.index(t)
                                                    if t in TYPE_ORDER else 99))
        color = {t: BADGE_PALETTE.get(t, (_NO_SUBCONTEXT_COLOR,))[0] for t in keys}
    else:
        # Stable per-context colour, ordered by total throughput so the
        # largest context gets the first palette colour and the stacking
        # order is consistent across bars.
        keys = sorted(total_per_key, key=lambda c: total_per_key[c], reverse=True)
        color = {
            c: (_NO_SUBCONTEXT_COLOR if c == 'No Context'
                else _SUBCONTEXT_PALETTE[i % len(_SUBCONTEXT_PALETTE)])
            for i, c in enumerate(keys)
        }

    def _against_capacity(r):
        cap = r['capacity']
        if not cap:
            return f"{fmt(r['total_hours'])} done"
        return (f"{fmt(r['total_hours'])} done of {fmt(cap)} capacity "
                f"({r['total_hours'] / cap:.0%})")

    def _tooltip(r, key, seg):
        n_nodes = len(seg['nodes'])
        lines = [
            f"{r['label']} · {key}",
            f"{fmt(seg['hours'])} across {n_nodes} node"
            f"{'s' if n_nodes != 1 else ''}",
        ]
        for name, h in seg['nodes'][:5]:
            nm = name if len(name) <= 30 else name[:29] + '…'
            lines.append(f"• {nm} ({fmt(h)})")
        if n_nodes > 5:
            lines.append(f"… and {n_nodes - 5} more")
        lines.append(_against_capacity(r))
        return '\n'.join(lines)

    top = max(r['total_hours'] for r in quarter_rows)
    tickvals, ticktext = _friendly_xticks(top)
    ymax = max(top, max(tickvals)) or 1

    def _pct(hours):
        return f"{100 * hours / ymax:.3f}%"

    slots = []
    for r in quarter_rows:
        segments = []
        for key in keys:
            seg = next((s for s in r['segments'] if s['key'] == key), None)
            if seg and seg['hours'] > 0:
                segments.append(html.Div(className="tp-seg", style={
                    'height': f"{100 * seg['hours'] / r['total_hours']:.3f}%",
                    'backgroundColor': color[key],
                }, **{'data-tip': _tooltip(r, key, seg)}))
        slots.append(html.Div(html.Div(segments, className="tp-col",
                                       style={'height': _pct(r['total_hours'])}),
                              className="tp-slot"))

    # Labels about 7 characters wide fit a slot while ten or so share the
    # chart; past that they stand on end.
    longest = max(len(r['label']) for r in quarter_rows)
    rotated = " tp-rotated" if len(quarter_rows) * longest > 72 else ""
    plot = html.Div([
        html.Div([html.Span(text, style={'bottom': _pct(v)})
                  for v, text in zip(tickvals, ticktext)], className="tp-y"),
        html.Div([html.Div(className="tp-grid", style={'bottom': _pct(v)})
                  for v in tickvals if v > 0]
                 + [html.Div(slots, className="tp-slots")], className="tp-plot"),
        html.Div(),
        html.Div([html.Span(r['label']) for r in quarter_rows],
                 className="tp-x"),
    ], className="tp-body" + rotated)
    children = [html.Div(plot, className="throughput-chart hist-chart")]
    if by == 'type':
        children.append(html.Div([
            html.Span([html.I(className="gp-swatch", style={'backgroundColor': color[k]}), k])
            for k in keys], className="gp-legend"))
    return _card(children)


# Categorical palette for the Throughput chart's context segments. Tuned to
# the muted, deeper register of styles.BADGE_PALETTE (see STYLE_GUIDE.md) so
# it sits with the DARKLY theme rather than reading as bright/pastel. Distinct
# hues, ordered to alternate warm/cool so adjacent stacked segments stay
# legible.
_SUBCONTEXT_PALETTE = [
    '#3a6ba6', '#b06a2c', '#2f8f93', '#7e4f9c', '#4f8a52',
    '#b0a335', '#a85070', '#4a6480', '#56539c', '#3f8388',
]


_NO_SUBCONTEXT_COLOR = '#495057'


_RATING_METRICS = (('value', 'Value'), ('interest', 'Interest'),
                   ('effort', 'Effort'))


def _heat_mix(share):
    """How much heat colour a cell holding ``share`` of its row's nodes gets,
    as a percentage. 40% of the row or more is full strength; the curve lifts
    small shares so a single node still shows."""
    return round(10 + 90 * min(1.0, share / 0.4) ** 0.85)


# Bars shorter than this many rating points are left out: a 0.1 gap drew a
# few-pixel speck at the tick rather than a bar. The tooltip still gives the
# exact difference.
_GAP_BAR_MIN = 0.25


def _strip_left(value, width):
    """CSS ``left`` that centres a ``width``-px mark on ``value`` (1-10) in a
    strip of ten equal cells with 2px gaps. Cell k's centre sits at
    (k - 0.5)(W + 2)/10 - 1px, and a fractional value lands between cells."""
    return f"calc({value - 0.5:.3f} * (100% + 2px) / 10 - {1 + width / 2:g}px)"


def _share_label(share):
    """A share as a percent. Below 1% and just short of 100% keep a decimal,
    so a sliver never reads 0% and a near-whole never reads 100%."""
    v = 100 * share
    if 0 < v < 1 or 99.5 <= v < 100:
        return f"{min(max(v, 0.1), 99.9):.1f}%"
    return f"{v:.0f}%"


def _type_split(time_by_type):
    """'Learn 54% · Resource 42% · Action 4%', in the stacking order."""
    total = sum(time_by_type.values())
    if not total:
        return ""
    return " · ".join(f"{t} {_share_label(time_by_type[t] / total)}"
                      for t in TYPE_ORDER if time_by_type.get(t))


def _work_left_cell(row, area, scale):
    """The last column: the area's remaining work as a bar and a time. Bars
    share one scale, the largest context's share, so the biggest context
    fills its track and a subcontext reads against it. The bar is split by
    node type in the badge colors. ``scale`` is None on the All nodes row,
    which shows its total without a bar.

    The tooltip leaves out the total, which ends the bar already. It gives
    the area's share of all remaining work, the exact type mix and the
    median node time; the row's count, at its start, is the median's
    sample, less any node whose time comes from its children."""
    fmt = format_time_friendly
    by_type = row.get('time_by_type') or {}
    track = []
    if scale:
        width = min(100.0, 100 * row['share'] / scale)
        segments = [
            html.Div(className="rd-work-seg", style={
                'width': f"max({width * by_type[t] / row['time']:.2f}%, 2px)",
                'backgroundColor': BADGE_PALETTE.get(t, (_NO_SUBCONTEXT_COLOR,))[0],
            })
            for t in TYPE_ORDER if by_type.get(t) and row['time']
        ]
        track = [html.Div(segments, className="rd-work-track")]
    lines = [area]
    if scale:
        lines.append(f"{_share_label(row['share'])} of all remaining work")
    lines.append(_type_split(by_type))
    if row.get('median_time'):
        lines.append(f"Median node time: {fmt(row['median_time'])}")
    return html.Div(track + [html.Span(fmt(row['time']), className="rd-work-time")],
                    className="rd-work",
                    **{'data-tip': "\n".join(line for line in lines if line)})


def _rating_dist_row(row, label, kind, defs, chevron=False, element=html.Div,
                     guide=None, work_scale=None):
    """One grid row: the area label, then a 1-10 strip and the mean for each
    rating. A context's row is an ``html.Summary``, so it carries a chevron;
    a context with nothing to open keeps the chevron's space, hidden.

    Each cell carries its tooltip in ``data-tip``, which
    assets/analyze/rating_dist.js shows on hover: the area, then a sentence
    with the count, then the rating's definition. The sentence keeps the
    count and the rating apart with words; "Interest 8: 8 of 32" ran two
    unrelated numbers together. The row total is in both places on purpose.
    The label's tells you how far to trust the row; the tooltip's gives the
    cell its share, read far from the label.

    ``guide`` is the All nodes row. Every other row draws a faint line at its
    mean, so a row's tick reads as left or right of the whole graph by how
    far. A threshold-based highlight flagged nearly half the means, most of
    them deliberate calibration choices, so distance carries it instead."""
    area = ('All nodes' if row['context'] is None
            else row['context'] if row['subcontext'] is None
            else f"{row['context']} > {row['subcontext']}")
    total = row['count']
    head = [html.Span(className="editor-chevron on-dark")] if chevron else []
    children = [html.Div(head + [
        html.Span(label, className="rd-name", title=label),
        html.Span(str(row['count']), className="rd-count"),
    ], className="rd-label")]
    nodes_word = 'node' if total == 1 else 'nodes'
    for i, (key, name) in enumerate(_RATING_METRICS):
        dist = row[key]
        cells = []
        for x, n in enumerate(dist['counts'], start=1):
            definition = (defs.get(x) or {}).get(key, '')
            verb = 'has' if n == 1 else 'have'
            tip = (f"{area}\n{n} of {total} {nodes_word} {verb} {name} {x}"
                   f"\n{definition}")
            cells.append(html.Div(
                className="rd-cell has" if n else "rd-cell",
                style={'--mix': f"{_heat_mix(n / total)}%"} if n else None,
                **{'data-tip': tip}))
        mean = dist['mean']
        tip = f"{area}\nMean {name}: {mean:.1f}"
        if guide is not None:
            overall = guide[key]['mean']
            cells.append(html.Div(className="rd-guide",
                                  style={'left': _strip_left(overall, 2)}))
            diff = mean - overall
            # A bar from the guide to the tick: the distance, drawn. Orange
            # above, violet below; not red/green, which read as good/bad
            # (Effort above the mean is not good) and blur for deutans.
            if abs(diff) >= 0.05:
                if abs(diff) >= _GAP_BAR_MIN:
                    cells.append(html.Div(
                        className="rd-gap " + ("above" if diff > 0 else "below"),
                        style={'left': _strip_left(min(mean, overall), 0),
                               'width': f"calc({abs(diff):.3f} * (100% + 2px) / 10)"}))
                tip += (f"\n{abs(diff):.1f} {'above' if diff > 0 else 'below'}"
                        f" all nodes ({overall:.1f})")
            else:
                tip += f"\nSame as all nodes ({overall:.1f})"
        # The tick names itself on hover, so the description needn't.
        cells.append(html.Div(className="rd-mean",
                              style={'left': _strip_left(mean, 2)},
                              **{'data-tip': tip}))
        later = " rd-later" if i else ""
        children.append(html.Div(cells, className="rd-strip" + later))
        children.append(html.Div(f"{mean:.1f}", className="rd-stat"))
    children.append(_work_left_cell(row, area, work_scale))
    return element(children, className=f"rd-row {kind}")


def render_rating_distribution(dist):
    """Where each area's open nodes fall on the 1-10 Value, Interest and
    Effort scales. A cell's shade is its share of the row's nodes and the
    tick is the mean. Contexts start collapsed and open into their
    subcontexts. The native details element does the folding, so it needs
    no callback.

    It has no title of its own: it is the Contexts section's only chart, and
    the section heading names it."""
    if not dist['all']['count']:
        return _card([html.P("No open rated nodes.",
                             className="text-muted small mb-0")])

    defs = {d['rating']: d for d in settings.RATINGS_DEFINITIONS.get()}
    header = [html.Div()]
    for i, (_, name) in enumerate(_RATING_METRICS):
        header.append(html.Div([
            html.Div(name, className="rd-metric"),
            html.Div([html.Span(str(x)) for x in range(1, 11)],
                     className="rd-ticks"),
        ], className="rd-later" if i else None))
        header.append(html.Div("Mean", className="rd-colh"))
    header.append(html.Div("Work left", className="rd-colh rd-work-head"))
    scale = max((g['row']['share'] for g in dist['groups']), default=0)

    body = [html.Div(header, className="rd-row rd-head"),
            _rating_dist_row(dist['all'], "All nodes", "rd-all", defs)]
    for group in dist['groups']:
        ctx_row = group['row']
        if group['subs']:
            body.append(html.Details([
                _rating_dist_row(ctx_row, ctx_row['context'], "rd-ctx", defs,
                                 chevron=True, element=html.Summary,
                                 guide=dist['all'], work_scale=scale),
                *[_rating_dist_row(sub, sub['subcontext'], "rd-sub", defs,
                                   guide=dist['all'], work_scale=scale)
                  for sub in group['subs']],
            ], className="rd-group"))
        else:
            body.append(html.Div(_rating_dist_row(
                ctx_row, ctx_row['context'], "rd-ctx rd-leaf", defs,
                chevron=True, guide=dist['all'], work_scale=scale),
                className="rd-group"))
    # assets/analyze/rating_dist.js handles all three buttons in the browser; the
    # guide toggle remembers its state per viewer. No callbacks. The toggle
    # goes last: it is used less than the pair that folds the rows.
    head = html.Div([
        ui_kit.disclosure_all_button("rating-dist-expand-all", True),
        ui_kit.disclosure_all_button("rating-dist-collapse-all", False),
        ui_kit.guide_toggle_button("rating-dist-guide-toggle"),
    ], className="rd-tools d-flex gap-1")
    return _card([html.Div([head, *body], className="rating-dist")])
