"""Shared estimate guidance and the Time Simulation forecast chart."""
from dash import html
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from config import ConfigManager
from ui_kit import Tooltip, info_button
import style_tokens as tokens

_BRACKET_HINTS = {
    "Lower": "10% chance of finishing sooner than this.",
    "Expected": "A 50/50 estimate.",
    "Upper": "10% chance of taking longer than this.",
}


def bracket_label(kind, label_id, className="small text-muted mb-0"):
    """A Lower/Expected/Upper input label with a hover tooltip on the word itself."""
    return [
        dbc.Label(kind, id=label_id, className=className),
        Tooltip(_BRACKET_HINTS[kind], target=label_id, placement="top"),
    ]


def estimate_guidance(id_prefix):
    """Info icon explaining how a bracket (or a lone Expected value) becomes a mean."""
    info_id = f"{id_prefix}-time-info"
    # A bare <i> is not focusable, so this one help affordance was unreachable
    # by keyboard while the other four were buttons. ui_kit.info_button gives
    # them all the same element and the same hit target.
    return info_button(
        info_id,
        "With only Expected filled in, that number is used directly as the mean. "
        "With a bracket, the mean work hours are calculated from all supplied values.",
        placement="right")


# --- Unit selects -----------------------------------------------------------
# One builder for every "per what?" select in the app. These used to be typed
# out by hand at nine call sites, which is how the Reflection modal's copy
# ended up missing "Years" while ConfigManager.hours_to_friendly_unit could
# still hand it that value, and how four of them picked up a 100px width the
# others never got.

#: Elapsed-time units. Anything measuring how long work takes.
TIME_UNITS = ("hours", "days", "weeks", "months", "years")

#: Calendar-duration units. Habit windows and activation delays, which are
#: counted in days rather than worked hours.
DURATION_UNITS = ("days", "weeks", "months", "years")


def unit_options(units):
    """Option dicts for a unit select, labelled in title case."""
    return [{"label": u.capitalize(), "value": u} for u in units]


def unit_select(select_id, units=TIME_UNITS, value=None, compact=False, **kwargs):
    """A unit select.

    ``compact=True`` gives the narrow inline variant that sits beside a number
    input on one row; the default fills its column.
    """
    if compact:
        kwargs.setdefault("size", "sm")
        kwargs.setdefault("style", {"width": "100px"})
    return dbc.Select(id=select_id, options=unit_options(units), value=value,
                      **kwargs)


# --- Calendar-duration formatting -------------------------------------------
# The output half of the DURATION_UNITS widget above. This arithmetic used to
# exist as four hand-written copies -- two forward, two inverse -- and the two
# inverses disagreed. The edit form knew about years and the dormant table did
# not, so a one-year delay round-tripped as "365 days". Both inverses now share
# _largest_exact_unit, so the form and the display cannot drift apart again.
#
# ConfigManager.format_time_friendly / time_unit are deliberately NOT reused
# here. Those measure worked hours against the user's hours-per-week setting;
# a delay is plain calendar days with fixed constants.

#: Largest first. The inverse walks this in order and takes the first exact fit.
_DURATION_UNIT_DAYS = (("years", 365), ("months", 30), ("weeks", 7), ("days", 1))


def duration_to_days(value, unit) -> int:
    """Convert a (value, unit) duration pair to whole days."""
    try:
        count = int(value or 0)
    except (TypeError, ValueError):
        return 0
    for name, size in _DURATION_UNIT_DAYS:
        if unit == name:
            return count * size
    return count


def _largest_exact_unit(days: int) -> tuple[int, str]:
    """The biggest unit that divides `days` exactly, as (count, unit).

    Exact division only, so 730 reads as "2 years" while 700 stays "100 weeks"
    rather than becoming an approximate "1 year 4 months". The form holds one
    number and one select, so a single unit is all it can carry.
    """
    for name, size in _DURATION_UNIT_DAYS:
        if size > 1 and days >= size and days % size == 0:
            return days // size, name
    return days, "days"


def days_to_duration(days) -> tuple[int, str]:
    """Invert `duration_to_days` back to the (value, unit) pair a form holds."""
    days = int(days or 0)
    if days <= 0:
        return 0, "days"
    return _largest_exact_unit(days)


def format_duration_days(days, zero="None") -> str:
    """Render a day count as display text. 0 becomes `zero`, 365 becomes "1 year"."""
    days = int(days or 0)
    if days <= 0:
        return zero
    count, unit = _largest_exact_unit(days)
    return f"{count} {unit[:-1] if count == 1 else unit}"


_UNIT_TITLES = {"y": "Years", "m": "Months", "w": "Weeks", "d": "Days", "h": "Hours"}

# literal: Plotly shape colours -- read as computed values, not CSS.
_PERCENTILE_LINES = (("P10", "p10", "#198754"),  # literal: Plotly
                     ("P50", "p50", "#ffc107"),  # literal: Plotly
                     ("P90", "p90", "#dc3545"))  # literal: Plotly


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
        marker_color="#0d6efd", opacity=0.85,  # literal: Plotly
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
        paper_bgcolor="#1a1d21",  # literal: Plotly
        plot_bgcolor="#1a1d21",  # literal: Plotly
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
        hoverlabel=dict(bgcolor="#2b3035", bordercolor="#495057",  # literal: Plotly
                        font=dict(color="#dee2e6", size=13)),  # literal: Plotly
        bargap=0,
    )
    return fig
