"""The Nodes tab's layout."""
from dash import html
from skilltree.store import settings
from skilltree.store.settings import DEFAULT_GRAPH_LAYOUT
from skilltree.ui import tokens
from skilltree.ui.canvas.settings_panel import build_graph_settings_panel
from skilltree.ui.canvas.settings_panel import freeze_indicator
from skilltree.ui.kit import Tooltip
from skilltree.ui.kit import filter_chip
from skilltree.ui.styles import LOADING_SPINNER_STYLE
from skilltree.ui.styles import stylesheet
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto


def empty_canvas_detail(hidden):
    """The line under "No nodes match your filters", from `hidden_by_status`.

    When Done or Dormant nodes are the reason, it says how many matching nodes
    they hide. Otherwise it says what else can be done.
    """
    total, done, dormant = hidden['hidden'], hidden['done'], hidden['dormant']
    if not total:
        return "Widen the filters, or clear them."
    noun = "matching node" if total == 1 else "matching nodes"
    verb = "is" if total == 1 else "are"
    if done and dormant:
        return f"{total} {noun} {verb} hidden: {done} Done, {dormant} Dormant."
    return f"{total} {noun} {verb} {'Done' if done else 'Dormant'} and hidden."


def create_graph_view():
    """Create the Cytoscape graph canvas with fullscreen toggle button.

    It starts empty. The canvas gets its elements on its first visit."""
    gl = settings.GRAPH_LAYOUT_DEFAULTS.get()
    return html.Div([
        html.Div([
            cyto.Cytoscape(
                id='cytoscape-graph',
                # Filter changes re-run this layout, so it describes a
                # transition: keep the current positions, and animate to match
                # the Animate switch, which starts on. The graph-settings
                # callback only rewrites this prop once a control is touched,
                # so until then Animate read on but ran off. The cold start
                # from nodes stacked at the origin is the exception, adjusted
                # by assets/canvas/canvas_first_paint.js.
                layout={
                    'name': 'fcose', 'quality': 'proof',
                    'fit': True, 'animate': True, 'animationDuration': 1000,
                    'padding': 30, 'numIter': 2500, 'randomize': False,
                    'idealEdgeLength': gl.get('edge_length', DEFAULT_GRAPH_LAYOUT['edge_length']),
                    'nodeRepulsion': gl.get('repulsion', DEFAULT_GRAPH_LAYOUT['repulsion']),
                    'gravity': gl.get('gravity', DEFAULT_GRAPH_LAYOUT['gravity']),
                },
                style={'width': '100%', 'height': '100%',
                       'backgroundColor': tokens.BG_CANVAS, 'borderRadius': '8px'},
                elements=[],
                stylesheet=stylesheet,
                userZoomingEnabled=False,
                boxSelectionEnabled=True,
                userPanningEnabled=False,
                autoungrabify=False
            ),
            dbc.Button(html.I(className="bi bi-gear"),
                       id="btn-graph-settings",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right"),
            Tooltip("Graph layout", target="btn-graph-settings", placement="left"),
            freeze_indicator("freeze-indicator"),
            build_graph_settings_panel(
                "graph-settings",
                defaults_getter=settings.GRAPH_LAYOUT_DEFAULTS.get,
            ),
            dbc.Button(html.I(className="bi bi-arrows-fullscreen"),
                       id="btn-fullscreen",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right-mid"),
            Tooltip("Toggle fullscreen", target="btn-fullscreen", placement="left"),
            html.Div(id="canvas-node-count", className="canvas-stats-overlay"),
            filter_chip("nodes-filter-chip", "filter-chip-overlay"),
            # Shown over an empty canvas (callbacks.register_engine_callbacks fills it
            # in and opens it): what the filters hid, and the way back.
            html.Div([
                html.Div("No nodes match your filters", className="canvas-empty-title"),
                html.Div(id="canvas-empty-detail", className="canvas-empty-detail"),
                html.Div([
                    dbc.Button("Show Done", id="btn-empty-show-done",
                               color="secondary", size="sm"),
                    dbc.Button("Show Dormant", id="btn-empty-show-dormant",
                               color="secondary", size="sm"),
                    dbc.Button("Clear filters", id="btn-empty-clear",
                               color="secondary", size="sm"),
                ], id="canvas-empty-actions", className="canvas-empty-actions"),
            ], id="canvas-empty-state", className="canvas-empty-state",
                role="status", **{"aria-live": "polite"}),  # type: ignore[reportArgumentType]
            # First-paint cover. This canvas mounts inside the hidden Nodes
            # tab, where Cytoscape stacks every node at the origin until its
            # layout runs and `fit` is a no-op at 0x0 — so opening the tab
            # early used to show the graph piled into the top-left corner and
            # then jump. It starts opaque and is lifted by
            # assets/canvas/canvas_first_paint.js once the graph is laid out and
            # framed. Last child so it covers the overlays above it too.
            html.Div(
                html.Div([
                    dbc.Spinner(spinner_style=LOADING_SPINNER_STYLE),
                    html.Div("Preparing the graph…", className="canvas-cover-label"),
                ], className="canvas-cover-inner"),
                id="canvas-first-paint-cover",
                className="canvas-cover",
                role="status",
                **{"aria-live": "polite"},  # type: ignore[reportArgumentType]
            ),
        ], id="canvas-container", className="canvas-container h-100", style={"overflow": "hidden", "borderRadius": "8px"}),
    ], className="h-100", style={"overflow": "hidden"})
