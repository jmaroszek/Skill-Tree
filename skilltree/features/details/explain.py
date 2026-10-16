"""The Explain modal: why a node scores what it does."""
from html import escape as _escape

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import html

from skilltree.store.settings import BADGE_PALETTE, ConfigManager
from skilltree.ui import tokens

# Maps the `via` field from scoring.explain_score to a bar color.
# Cool & quiet palette. Hard is a darker rugged blue (matches subtasks-
# table Hard and the HardRelPri badge in the node-info stack); Soft
# neutral slate; Synergy cyan-teal (categorically different — mutual,
# multiplicative reinforcement, not a weaker prereq). Self is a warm
# sand off the cool axis entirely so it can't be confused with Soft.
# Values come from config.BADGE_PALETTE so the chart, the subtasks-table
# relationship column and the node-info badges cannot drift apart.
_VIA_COLORS = {
    'Self':    BADGE_PALETTE['EdgeSelf'][0],     # warm sand — off the edge axis
    'Hard':    BADGE_PALETTE['EdgeHard'][0],     # darker rugged blue (must-have)
    'Soft':    BADGE_PALETTE['EdgeSoft'][0],     # neutral slate (should-have)
    'Synergy': BADGE_PALETTE['EdgeSynergy'][0],  # cyan-teal (mutual, multiplicative)
}


def _trunc(name: str, max_len: int = 25) -> str:
    """Truncate long names with an ellipsis; full name goes in hover."""
    return name if len(name) <= max_len else name[:max_len - 1] + '\u2026'


def _format_share(pct: float) -> str:
    """A share of total value: whole percents from 10% up, one decimal below."""
    if pct >= 9.95:
        return f"{pct:.0f}%"
    if pct >= 0.05:
        return f"{pct:.1f}%"
    return "<0.1%" if pct > 0 else "0%"


def _format_effect(multiplier: float) -> str:
    """The change a score multiplier makes, as a signed percent: 0.487 -> '−51%'."""
    change = (multiplier - 1.0) * 100.0
    size = abs(change)
    text = f"{size:.0f}%" if size >= 9.95 else f"{size:.1f}%"
    return ("+" if change > 0 else "−") + text


def _format_rating(rating) -> str:
    """A 1-10 rating without a trailing '.0'."""
    return f"{rating:g}" if isinstance(rating, (int, float)) else str(rating)


def _explain_summary_table(breakdown: dict, normalized):
    """Grouped table: Value / Cost / Adjustments / Score, in the reader's terms.

    The scorer's internal quantities never appear. Intrinsic and total value
    have no unit, and their size moves with the scoring profile, so a figure
    like 181 tells the reader nothing. Value is shown as shares of the node's
    total value instead, which always sum to 100%. Cost is shown as the time
    and effort it is built from. Each adjustment is shown as the change it
    makes to the score. The only score printed is the 0-100 priority every
    other surface shows.

    Rows carry a short muted detail (the ratings, the context, the goal)
    rather than the parameter values behind them. Value sources with no share
    are left out, as is the Adjustments section when nothing adjusts the score.

    Goal breakdowns (`is_goal`, produced by goal_ranking.explain_goal) are
    scored by the average worth of the work left beneath the Goal. Their
    value splits into the tasks' own ratings and the credit the tasks earn
    for this Goal and for other Goals, and their cost is that work.
    """
    comp = breakdown['composition']
    cost_info = breakdown['cost']
    intrinsic = breakdown.get('intrinsic') or {}
    boost = breakdown['goal_boost']
    is_goal = breakdown.get('is_goal', False)

    header_style = {
        "fontWeight": "700",
        "letterSpacing": "0.06em",
        "textTransform": "uppercase",
        "fontSize": tokens.FS_LG,
        "color": "#fff",  # literal: on a coloured tile
        "backgroundColor": tokens.BG_PANEL,
        "borderTop": f"1px solid {tokens.BORDER_PANEL}",
        "paddingTop": "10px",
        "paddingBottom": "8px",
    }
    total_style = {"fontWeight": "600", "borderTop": f"1px solid {tokens.BORDER_PANEL}"}
    num_style = {"textAlign": "right", "fontVariantNumeric": "tabular-nums",
                 "whiteSpace": "nowrap"}
    detail_style = {"color": tokens.TEXT_SOFT, "fontSize": tokens.FS_MD, "marginLeft": "8px"}

    rows = []

    def header(text):
        rows.append(html.Tr([html.Td(text, colSpan=2, style=header_style)]))

    def row(label, figure, detail=None, style=None):
        label_cell = [html.Span(label)]
        if detail:
            label_cell.append(html.Span(detail, style=detail_style))
        rows.append(html.Tr([
            html.Td(label_cell, style=style),
            html.Td(figure, style={**num_style, **(style or {})}),
        ]))

    # --- Value: where the total comes from ------------------------------
    header("Value")
    total = comp['total_value']

    def share(amount):
        return _format_share(100.0 * amount / total) if total > 1e-9 else "—"

    if intrinsic.get('value_overridden'):
        own_detail = "none of its own"
    elif intrinsic.get('value') is not None:
        own_detail = (f"Value {_format_rating(intrinsic['value'])} · "
                      f"Interest {_format_rating(intrinsic['interest'])}")
    else:
        own_detail = None
    if is_goal:
        row("Ratings of the work left", share(comp['iv']))
        row("Credit for this goal", share(comp.get('goal_credit', 0.0)), own_detail)
        if comp.get('other_goal_credit', 0.0) > 1e-9:
            row("Credit for other goals", share(comp['other_goal_credit']))
    else:
        row("Own ratings", share(comp['iv']), own_detail)
    for label, amount in (
        ("Prerequisites" if is_goal else "Unlocks", comp['hard_cascade']),
        ("Prepares you for", comp['soft_cascade']),
        ("Synergy partners", comp['synergy']),
    ):
        if amount > 1e-9:
            row(label, share(amount))

    # --- Cost: the time and effort it is built from ---------------------
    header("Cost")

    def duration(hours):
        return ConfigManager.format_time_friendly(hours) if hours > 0 else "None"

    if is_goal:
        count = cost_info.get('n_tasks', 0)
        row("Work left", duration(cost_info.get('remaining_time', 0.0)),
            f"{count} task{'' if count == 1 else 's'}")
    else:
        row("Time", "None of its own" if cost_info['time_overridden']
            else duration(cost_info['time']))
        row("Effort", "None of its own" if cost_info.get('effort_overridden')
            else f"{_format_rating(cost_info['difficulty'])} of 10")

    # --- Adjustments: each as the change it makes to the score ----------
    adjustments = []
    if boost is not None:
        adjustments.append(("Priority goal", f"{boost['goal']} (#{boost['rank']})",
                            boost['multiplier']))
    ctx_adj = breakdown.get('context_adjustment') or {}
    context = breakdown.get('context')
    if abs(ctx_adj.get('weight', 1.0) - 1.0) > 1e-9:
        adjustments.append(("Context weight", context, ctx_adj['weight']))
    if abs(ctx_adj.get('density_mult', 1.0) - 1.0) > 1e-9:
        # Goal-only: unfinished Goals sharing this one's context/subcontext.
        area = " · ".join(p for p in (context, breakdown.get('subcontext')) if p)
        count = ctx_adj.get('n_bucket', 1)
        adjustments.append(("Crowding", f"{count} goals in {area}" if area
                            else f"{count} goals", ctx_adj['density_mult']))
    variety = breakdown.get('variety') or {}
    if variety.get('divisor') and abs(variety['divisor'] - 1.0) > 1e-9:
        # What the node gives up for being the nth recommendation from its
        # context; the scorer divides by it, so it is shown as a reduction.
        where = [f"{_ordinal(variety['context_rank'])} from {variety['context']}"]
        if variety.get('subcontext'):
            where.append(f"{_ordinal(variety['subcontext_rank'])} from {variety['subcontext']}")
        adjustments.append(("Variety", ", ".join(where), 1.0 / variety['divisor']))

    if adjustments:
        header("Adjustments")
        combined = 1.0
        for label, detail, multiplier in adjustments:
            row(label, _format_effect(multiplier), detail)
            combined *= multiplier
        if len(adjustments) > 1:
            row("Together", _format_effect(combined), style=total_style)

    # --- Score: the 0-100 priority shown everywhere else ----------------
    header("Score")
    if breakdown['eligible']:
        row("Priority", f"{normalized} of 100" if normalized is not None else "—")
    else:
        row("Not ranked", "—", breakdown['block_reason'])

    return dbc.Table(
        [html.Tbody(rows)],
        borderless=True, size="sm",
        className="mb-0",
        style={"color": tokens.TEXT_PRIMARY, "marginTop": "4px"},
    )


def _contributor_hover(row: dict) -> str:
    """Short hover text for one bar of the contributors chart.

    Kept short: the name, its type and ratings, how the node is reached, and
    how much of its value reaches the explained node. The bar's own label
    already carries its share of total value.
    """
    lines = [f"<b>{_escape(row['name'])}</b>"]
    facts = [_escape(row['type'])] if row.get('type') else []
    if row.get('iv', 0.0) > 1e-9 and row.get('value') is not None:
        facts += [f"Value {_format_rating(row['value'])}",
                  f"Interest {_format_rating(row['interest'])}"]
    if facts:
        lines.append(" · ".join(facts))
    via = row.get('via')
    if via != 'Self':
        steps = row.get('depth', 0)
        through = {'Hard': "hard prerequisite", 'Soft': "soft prerequisite",
                   'Synergy': "synergy partner"}.get(via, "relationship")
        lines.append(f"{steps} step{'' if steps == 1 else 's'} away via {through}")
        # A Goal's work counts in full, so there is no share to report.
        if row.get('iv', 0.0) > 1e-9 and not row.get('goal_work'):
            # Route discounts and the required-work discount, combined.
            channels = row.get('channels')
            ordinary = (sum(channels.get(k, 0.0) for k in ('Self', 'Hard', 'Soft'))
                        if channels is not None else row.get('contribution', 0.0))
            if ordinary > 0:
                passed_on = 100.0 * ordinary / row['iv']
                lines.append(f"Passes on {_format_share(passed_on)} of its value")
    synergy = row.get('synergy_detail')
    if synergy:
        state = 'Finished partner' if synergy['done'] else 'Unfinished partner'
        lines.append(f"{state} · Reinforces this project")
    return "<br>".join(lines)


def _explain_bar_chart(contributors: list, top_n: int):
    """Horizontal Plotly bar of top-N contributors, colored by `via`.

    Bars measure each contributor's share of total value, the unit the Value
    rows of the calculation details use. Long node names are truncated for
    the y-axis tick labels (full name preserved in hover); `ticksuffix` adds
    breathing room between labels and bar starts — both patterns lifted from
    analyze_callbacks._trunc.
    """
    rows = list(reversed(contributors[:top_n]))  # Plotly stacks bottom-up
    shares = [r.get('pct_of_tv', 0.0) for r in rows]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=shares, y=[_trunc(r['name']) for r in rows],
        orientation='h',
        marker_color=[_VIA_COLORS.get(r['via'], BADGE_PALETTE['SoftRelPri'][0]) for r in rows],
        text=[_format_share(s) for s in shares],
        textposition='outside',
        cliponaxis=False,
        customdata=[_contributor_hover(r) for r in rows],
        hovertemplate="%{customdata}<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='#1a1d21',  # literal: Plotly cannot resolve var()
        plot_bgcolor='#1a1d21',  # literal: Plotly cannot resolve var()
        margin=dict(l=10, r=40, t=10, b=40),
        xaxis=dict(title="Share of total value", ticksuffix="%"),
        yaxis=dict(automargin=True, ticksuffix="  "),
        showlegend=False,
        height=max(260, 30 * len(rows) + 80),
    )
    return fig


def build_explain_summary(breakdown: dict, normalized=None):
    """Dash component for the Value/Cost/Score summary table.

    `breakdown` is the dict from scoring.explain_score. `normalized` is
    the integer 0–100 score the Home tab would show, or None to render
    as '—'. Returns a single component; the caller slots it into the
    static modal body in details_layout.
    """
    if breakdown is None:
        return html.Div("Node not found.", className="text-muted",
                        style={"padding": "16px"})
    return _explain_summary_table(breakdown, normalized)


def _ordinal(n: int) -> str:
    """1 -> '1st', 2 -> '2nd', 11 -> '11th'."""
    if 10 <= (n % 100) <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def format_value_rank(total_value, peer_values, noun="projects"):
    """Where a node sits among comparable nodes, as a plain rank.

    Deliberately reports only the position. Total value itself is an internal
    quantity: it has no units, and its magnitude moves with the scoring profile,
    so printing the number invites the reader to interpret a figure that means
    nothing on its own. The rank carries everything useful about it.

    `peer_values` is every comparable node's total value and must include this
    node's own. Goals are ranked against Goals: their figure is the average
    worth of the work left beneath them, which is not an ordinary node's
    total value, so mixing
    them with ordinary nodes would rank every Goal near the top.

    Returns '' when there is nothing to compare against, so the caller can drop
    the line rather than render a lone "1st of 1".
    """
    if total_value is None:
        return ""
    peers = [v for v in (peer_values or []) if v is not None]
    if len(peers) < 2:
        return ""
    rank = sum(1 for v in peers if v > total_value) + 1
    return f"Ranks {_ordinal(rank)} of {len(peers)} {noun}"


def format_priority_rank(position, total, in_now=False):
    """A node's place in the Next ranking, as the Home tab orders it.

    `position` is 1-based among `total` ranked nodes. Home never lists a Now
    node, so for one the position is where it would sit if it weren't in Now.
    """
    if in_now:
        return f"Would rank {_ordinal(position)} of {total} projects if it weren't in Now"
    return f"Ranks {_ordinal(position)} of {total} projects"


def build_explain_chart(contributors, top_n: int = 10):
    """Plotly figure for the Top Contributors bar chart.

    `contributors` is the sorted list from scoring.explain_score (or the
    serialized copy stored in dcc.Store). Returns a go.Figure; the
    callback assigns it to the static dcc.Graph's figure prop.
    """
    return _explain_bar_chart(contributors or [], top_n)
