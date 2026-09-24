"""
Layout definition for the Analyze tab.

The section headers, their display-limit gear buttons, and the gear popovers
are all static here — only the chart bodies are injected by analyze_callbacks.
Keeping each gear and its popover static (and co-located) is what lets the
popover's click trigger bind reliably.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc
from config import ConfigManager, LOADING_SPINNER_STYLE
import style_tokens as tokens

_GEAR_STYLE = {
    "background": "none", "border": "none", "padding": "0",
    "color": tokens.TEXT_DIM, "cursor": "pointer",
    "fontSize": tokens.FS_CAP, "lineHeight": "1",
    "position": "relative", "top": "2px",
}


def _plain_header(text):
    return html.H5(text, className="mt-2 mb-1")


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
    """Static shell for the Analyze tab. Chart bodies are injected by callback.

    The sections start hidden behind a loading cover, so a visit before the
    first render shows a spinner rather than a column of empty headers. The
    render callback swaps the two on its first return."""
    return html.Div([
        html.Div([
            dbc.Spinner(spinner_style=LOADING_SPINNER_STYLE),
            html.Div("Preparing the analysis…", className="canvas-cover-label"),
        ], id="analyze-loading-cover", className="loading-cover",
            role="status", **{"aria-live": "polite"}),  # type: ignore[reportArgumentType]
        html.Div(_analyze_sections(), id="analyze-sections", hidden=True),
    ], className="h-100")


def _analyze_sections():
    """Overview strip, then three subtabs. Plan reads the unfinished graph,
    so it is complete from day one. History reads Done nodes and their
    reflections, so it fills in over time. Structure is graph shape. Every
    pane renders together; a subtab switch only shows and hides them."""
    al = ConfigManager.get_analyze_limits()
    return html.Div([
        html.Div(id="analyze-overview-content"),
        dbc.Tabs(
            id="analyze-subtabs", active_tab="analyze-plan",
            persistence=True, persistence_type="local",
            children=[
                dbc.Tab(label="Plan", tab_id="analyze-plan"),
                dbc.Tab(label="History", tab_id="analyze-history"),
                dbc.Tab(label="Structure", tab_id="analyze-structure"),
            ],
            className="analyze-subtabs mb-3",
        ),
        _pane("analyze-pane-plan", _plan_sections(al), shown=True),
        _pane("analyze-pane-history", _history_sections(al)),
        _pane("analyze-pane-structure", _structure_sections(al)),
    ], className="px-4 pt-3 pb-4")


def _pane(pane_id, sections, shown=False):
    # The class is how assets/analyze_first_paint.js recognises a pane
    # being revealed.
    return html.Div(sections, id=pane_id, className="analyze-subpane",
                    style={"display": "block" if shown else "none"})


def _plan_sections(al):
    return [
        _gear_header("Goals", "btn-analyze-goals-limit", "popover-analyze-goals",
                     "Goals shown", "setting-analyze-goals",
                     5, 200, al.get('goals', 75)),
        html.Div(id="analyze-goals-content"),
        html.Hr(className="my-3"),

        _plain_header("Contexts"),
        html.Div(id="analyze-contexts-content"),
    ]


def _history_sections(al):
    return [
        _plain_header("Time Estimation Accuracy"),
        html.Div(id="analyze-time-content"),
        html.Hr(className="my-3"),

        _plain_header("Rating Accuracy"),
        html.Div(id="analyze-drift-content"),
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

        _plain_header("Plan vs. Actual"),
        html.Div(id="analyze-plan-actual-content"),
    ]


def _structure_sections(al):
    return [
        _gear_header("Graph Structure", "btn-analyze-bottlenecks-limit",
                     "popover-analyze-bottlenecks", "Nodes shown",
                     "setting-analyze-bottlenecks", 5, 100, al.get('bottlenecks', 10)),
        html.Div(id="analyze-graph-content"),
    ]
