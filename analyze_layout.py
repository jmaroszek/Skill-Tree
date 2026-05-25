"""
Layout definition for the Analyze tab.

The section headers, their display-limit gear buttons, and the gear popovers
are all static here — only the chart bodies are injected by analyze_callbacks.
Keeping each gear and its popover static (and co-located) is what lets the
popover's click trigger bind reliably.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc
from config import ConfigManager

_GEAR_STYLE = {
    "background": "none", "border": "none", "padding": "0",
    "color": "#6c757d", "cursor": "pointer",
    "fontSize": "0.8rem", "lineHeight": "1",
    "position": "relative", "top": "2px",
}


def _plain_header(text):
    return html.H5(text, className="mb-1")


def _gear_header(text, gear_id, popover_id, label, input_id, lo, hi, value):
    """A section header with a small gear that opens a display-limit popover."""
    return _gear_header_custom(text, gear_id, popover_id, [
        dbc.Label(label, className="mb-1 d-block"),
        dbc.Input(id=input_id, type="number", min=lo, max=hi, step=5,
                  debounce=True, value=value, size="sm",
                  style={"width": "88px"}),
    ])


def _gear_header_custom(text, gear_id, popover_id, popover_body,
                        popover_style=None):
    """Generic gear header — caller supplies the popover body. Used when the
    section's settings are more than a single integer input. ``popover_style``
    is merged into the Popover's style dict (e.g. to constrain its width)."""
    popover_kwargs = dict(
        id=popover_id, target=gear_id, trigger="legacy", placement="bottom",
    )
    if popover_style:
        popover_kwargs['style'] = popover_style
    return html.Div([
        html.Div([
            html.H5(text, className="mb-0 me-2"),
            html.Button(html.I(className="bi bi-gear"), id=gear_id,
                        style=_GEAR_STYLE),
        ], className="d-flex align-items-center"),
        dbc.Popover(
            dbc.PopoverBody(popover_body),
            **popover_kwargs,
        ),
    ], className="mb-1")


def build_analyze_tab_content():
    """Static shell for the Analyze tab. Chart bodies are injected by callback."""
    al = ConfigManager.get_analyze_limits()
    return html.Div([
        html.Div(id="analyze-overview-content"),
        html.Hr(className="my-3"),

        _gear_header("Goals", "btn-analyze-goals-limit", "popover-analyze-goals",
                     "Goals shown", "setting-analyze-goals",
                     5, 200, al.get('goals', 75)),
        html.Div(id="analyze-goals-content"),
        html.Hr(className="my-3"),

        _plain_header("Contexts"),
        html.Div(id="analyze-contexts-content"),
        html.Hr(className="my-3"),

        _plain_header("Time Estimation Accuracy"),
        html.Div(id="analyze-time-content"),
        html.Hr(className="my-3"),

        _gear_header_custom(
            "Throughput",
            "btn-analyze-throughput-gear", "popover-analyze-throughput",
            [
                dbc.Label("Granularity", className="mb-1 d-block"),
                dbc.Select(
                    id="setting-analyze-throughput-granularity",
                    options=[{'label': 'Months', 'value': 'month'},
                             {'label': 'Quarters', 'value': 'quarter'},
                             {'label': 'Years', 'value': 'year'}],
                    value=al.get('throughput_granularity', 'quarter'),
                    size='sm', className="mb-2",
                    style={'width': '140px'},
                ),
                dbc.Label("Start date", className="mb-1 d-block"),
                dbc.Input(id="setting-analyze-throughput-start", type='date',
                          debounce=True, size='sm',
                          value=al.get('throughput_start') or '',
                          style={'width': '140px', 'marginBottom': '8px'}),
                dbc.Label("End date", className="mb-1 d-block"),
                dbc.Input(id="setting-analyze-throughput-end", type='date',
                          debounce=True, size='sm',
                          value=al.get('throughput_end') or '',
                          style={'width': '140px'}),
            ],
            popover_style={'maxWidth': '200px', 'minWidth': '180px'},
        ),
        html.Div(id="analyze-throughput-content"),
        html.Hr(className="my-3"),

        _gear_header("Graph Structure", "btn-analyze-bottlenecks-limit",
                     "popover-analyze-bottlenecks", "Nodes shown",
                     "setting-analyze-bottlenecks", 5, 100, al.get('bottlenecks', 25)),
        html.Div(id="analyze-graph-content"),
    ], className="px-4 pt-3 pb-4")
