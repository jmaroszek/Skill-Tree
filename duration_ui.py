"""Shared estimate guidance and compact duration forecast explanations."""
from dash import html
import dash_bootstrap_components as dbc

from config import TOOLTIP_SHOW_DELAY_MS, TOOLTIP_HIDE_DELAY_MS

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
