"""Shared estimate guidance and the Time Simulation forecast chart."""
from dash import html
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from config import ConfigManager, TOOLTIP_SHOW_DELAY_MS, TOOLTIP_HIDE_DELAY_MS

_BRACKET_HINTS = {
    "Lower": "10% chance of finishing sooner than this.",
    "Expected": "A 50/50 estimate.",
    "Upper": "10% chance of taking longer than this.",
}


def bracket_label(kind, label_id, className="small text-muted mb-0"):
    """A Lower/Expected/Upper input label with a hover tooltip on the word itself."""
    return [
        dbc.Label(kind, id=label_id, className=className),
        dbc.Tooltip(_BRACKET_HINTS[kind], target=label_id, placement="top",
                    delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
    ]


def estimate_guidance(id_prefix):
    """Info icon explaining how a bracket (or a lone Expected value) becomes a mean."""
    info_id = f"{id_prefix}-time-info"
    return html.Span([
        html.I(className="bi bi-info-circle", id=info_id,
               style={"color": "#6c757d", "cursor": "pointer", "fontSize": "0.9rem"}),
        dbc.Tooltip(
            "With only Expected filled in, that number is used directly as the mean. "
            "With a bracket, the mean work hours are calculated from all supplied values.",
            target=info_id, placement="right",
            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
    ], className="ms-1")


_UNIT_TITLES = {"y": "Years", "m": "Months", "w": "Weeks", "h": "Hours"}

_PERCENTILE_LINES = (("P10", "p10", "#198754"),
                     ("P50", "p50", "#ffc107"),
                     ("P90", "p90", "#dc3545"))


def _chance(fraction):
    """A cumulative share of simulation runs, read as a chance of finishing.

    The ends print as "Under 1%" and "Over 99%". The longest simulated run
    doesn't promise that nothing could take longer, so no bar claims a certain
    finish. Words rather than `<` and `>` also keep Plotly from reading the
    text as a tag.
    """
    if fraction < 0.005:
        return "Under 1%"
    if fraction >= 0.995:
        return "Over 99%"
    return f"{fraction * 100:.0f}%"


def simulation_figure(summary, time_settings=None, requested_trials=None):
    """The Time Simulation histogram for one `SimulationService.summarize` result.

    Every value on the chart is drawn in one unit: whichever fits the median,
    so a multi-year Goal reads in years and a short task in hours. The axis,
    the P lines and the bar tooltips all share it.

    Hovering a bar gives the chance of finishing by its right edge. Hover
    answers only over a bar itself, and dragging doesn't zoom. The chart is a
    high-level view, so it shows no exact values that would suggest false
    precision.
    """
    stats, counts = summary["stats"], summary["counts"]
    size, suffix = ConfigManager.time_unit(stats["p50"], time_settings=time_settings)
    centers = [center / size for center in summary["centers"]]
    width = summary["width"] / size

    # Enough decimals that neighbouring bars never print the same time.
    decimals = 1
    while decimals < 3 and width <= 10 ** -decimals:
        decimals += 1

    trials = sum(counts)
    finished = 0
    hover = []
    for count, center in zip(counts, centers):
        finished += count
        hover.append(f"{_chance(finished / trials)} chance within "
                     f"{center + width / 2:.{decimals}f}{suffix}")

    fig = go.Figure(go.Bar(
        x=centers, y=counts, width=width,
        marker_color="#0d6efd", opacity=0.85,
        customdata=hover,
        hovertemplate="%{customdata}<extra></extra>",
    ))
    for label, key, color in _PERCENTILE_LINES:
        fig.add_vline(
            x=stats[key] / size, line_dash="dash", line_color=color, line_width=2,
            annotation_text=f"{label}: {stats[key] / size:.1f}{suffix}",
            annotation_position="top",
            annotation_font_color=color,
        )

    fig.update_layout(
        meta={"trials": summary["trials"], "requested_trials": requested_trials,
              "chain_size": summary["chain_size"]},
        template="plotly_dark",
        paper_bgcolor="#1a1d21",
        plot_bgcolor="#1a1d21",
        margin=dict(l=40, r=20, t=20, b=40),
        xaxis_title=_UNIT_TITLES[suffix],
        yaxis_title="Frequency",
        xaxis=dict(showgrid=False, fixedrange=True),
        yaxis=dict(showgrid=False, fixedrange=True),
        dragmode=False,
        showlegend=False,
        # 'closest' answers only with the pointer inside a bar, and unlike 'x'
        # it pins no raw value to the axis.
        hovermode="closest",
        hoverlabel=dict(bgcolor="#2b3035", bordercolor="#495057",
                        font=dict(color="#dee2e6", size=13)),
        bargap=0,
    )
    return fig
