"""
Layout definitions for the Skill Tree Dash application.
Contains all UI component definitions and the Cytoscape stylesheet.
"""

from dash import html, dcc
import dash_cytoscape as cyto
import dash_bootstrap_components as dbc
from config import (
    ConfigManager,
    CANVAS_HEIGHT,
    TOOLTIP_SHOW_DELAY_MS,
    TOOLTIP_HIDE_DELAY_MS,
    TOOLTIP_NODE_HIDE_DELAY_MS,
)
from events_layout import build_events_tab_content, build_events_sidebar_content
from details_layout import build_details_tab_content, _freeze_indicator
from settings_layout import build_settings_tab_content
from analyze_layout import build_analyze_tab_content
from styles import stylesheet

# These are only used for the initial render; core_engine refreshes them dynamically.
NODE_TYPES = ConfigManager.get_node_types()
CONTEXTS = ConfigManager.get_contexts()
_TED = ConfigManager.get_time_estimate_defaults()

# --- Sidebar (Node Editor) ---
sidebar_content = html.Div(
    [
        html.Div([
            html.H4("Node Editor"),
            html.Span("×", id="btn-close-editor", className="fs-3 text-white float-end", style={"cursor": "pointer"})
        ], className="d-flex justify-content-between align-items-center mb-3 mt-2"),
        dbc.Form([
            html.Div(id="node-priority-badge", children=[],
                     className="d-flex gap-1 flex-wrap mb-2",
                     style={"display": "none"}),
            html.H5("Search", className="mt-2 mb-1"),
            html.Div([
                html.Div(dcc.Dropdown(
                    id="search-node",
                    options=[],  # Populated dynamically by core_engine callback
                    value=None,
                    searchable=True,
                    clearable=True,
                ), className="text-dark", style={"flex": 1}),
                dbc.Button(html.I(className="bi bi-crosshair"),
                           id="btn-locate-node", color="light", size="sm",
                           className="ms-1 px-2", disabled=True),
            ], className="d-flex"),
            dbc.Tooltip("Locate node on graph",
                        target="btn-locate-node", placement="right",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            html.Div(id="locate-message", className="text-warning small mt-1"),
            dcc.Interval(id='locate-clear-interval', interval=4000, n_intervals=0, disabled=True),
            dcc.Store(id='locate-animate-trigger', data=None),

            html.H5("General", className="mt-3 mb-1"),
            dbc.Label("Name", className="mt-2"),
            html.Div([
                dbc.Input(id="node-name", type="text", style={'flex': 1}),
                dbc.Button("▾", id="btn-aliases-toggle", color="light", className="ms-1 px-2"),
            ], className="d-flex"),
            html.Div(id="node-name-duplicate-warning", children="",
                     style={"display": "none"}, className="mt-1"),
            dbc.Collapse(
                html.Div([
                    html.Div([
                        dbc.Label("Aliases", className="mb-0"),
                        dbc.Button("+", id="btn-alias-add", color="link",
                                   className="p-0 ms-2 text-decoration-none text-muted",
                                   title="Add alias",
                                   style={"fontSize": "1.2rem", "lineHeight": "1"}),
                    ], className="d-flex align-items-center mt-1 mb-1"),
                    html.Div(id='aliases-container'),
                ]),
                id="collapse-aliases",
                is_open=False,
            ),
            dcc.Store(id='aliases-store', data=['']),

            dbc.Label("Type", className="mt-2"),
            dbc.Select(id="node-type", options=[{"label": t, "value": t} for t in NODE_TYPES]),

            dbc.Label("Context", className="mt-2"),
            html.Div([
                dbc.Select(id="node-context", options=[{"label": "None", "value": ""}] + [{"label": c, "value": c} for c in CONTEXTS], value="", style={'flex': 1}),  # type: ignore[reportArgumentType]
                dbc.Button("▾", id="btn-subcontext-toggle", color="light", className="ms-1 px-2")
            ], className="d-flex"),
            dbc.Collapse(dbc.Select(id="node-subcontext", options=[], className="mt-1"), id="collapse-subcontext", is_open=False),

            dbc.Label("Description", className="mt-2"),
            dbc.Textarea(id="node-desc", style={"height": "120px", "resize": "vertical"}),

            html.Div([
                dbc.Label("Competence", className="mb-0"),
                html.Button(
                    html.I(className="bi bi-info-circle"),
                    id="btn-competence-info",
                    style={
                        "background": "none", "border": "none", "padding": "0 0 0 6px",
                        "color": "#6c757d", "cursor": "pointer", "fontSize": "0.8rem",
                        "lineHeight": "1", "position": "relative", "top": "1px"
                    }
                ),
                dbc.Tooltip("Competence reference", target="btn-competence-info", placement="right",
                            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            ], className="d-flex align-items-center mt-2"),
            dbc.Select(
                id="node-competence",
                options=[
                    {"label": "\u2014", "value": ""},
                    {"label": "Outsider", "value": "outsider"},
                    {"label": "Reciter", "value": "reciter"},
                    {"label": "Processor", "value": "processor"},
                    {"label": "Thinker", "value": "thinker"},
                    {"label": "Creator", "value": "creator"},
                    {"label": "Master", "value": "master"},
                    {"label": "Innovator", "value": "innovator"},
                ],
                value="",
            ),

            html.Div(id="section-priority-rank", style={"display": "none"}, children=[
                dbc.Label("Priority Rank", className="mt-2"),
                dbc.Select(
                    id="node-priority-rank",
                    options=[
                        {"label": "\u2014", "value": "none"},
                        {"label": "#1 Priority", "value": "1"},
                        {"label": "#2 Priority", "value": "2"},
                        {"label": "#3 Priority", "value": "3"},
                    ],
                    value="none",
                ),
            ]),

            html.Div(id="auto-status-display", className="d-none"),

            # --- Section: Done toggle + Time Estimates (Learn, Goal, Resource) ---
            html.Div(id="section-done-time", children=[
                html.Div([
                    dbc.Checklist(
                        options=[{"label": "Done", "value": "Done"}],
                        value=[],
                        id="node-status-done",
                        switch=True,
                    ),
                ], className="d-flex justify-content-start mt-3"),
            ]),

            # Numeric inputs (shared by all types)
            html.Hr(className="my-2"),
            html.Div([
                html.H5("Ratings", className="mb-0"),
                html.Button(
                    html.I(className="bi bi-info-circle"),
                    id="btn-ratings-info",
                    style={
                        "background": "none", "border": "none", "padding": "0 0 0 6px",
                        "color": "#6c757d", "cursor": "pointer", "fontSize": "0.95rem",
                        "lineHeight": "1", "position": "relative", "top": "3px"
                    }
                ),
                dbc.Tooltip("Ratings reference", target="btn-ratings-info", placement="right",
                            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            ], className="d-flex align-items-center mt-2 mb-1"),
            dbc.Label("Value", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-value"),

            dbc.Label("Interest", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-interest"),

            dbc.Label("Effort", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-difficulty"),

            dbc.Checklist(
                options=[{"label": "Override", "value": "on"}],
                value=[],
                id="override-toggle",
                switch=True,
                className="mt-3 mb-1",
            ),
            dbc.Popover(
                [
                    dbc.PopoverHeader("Override Mode"),
                    dbc.PopoverBody([
                        dbc.RadioItems(
                            id="override-mode-radio",
                            options=[
                                {"label": "Node Only", "value": "node_only"},
                                {"label": "Node + Hard Dependencies", "value": "hard"},
                                {"label": "Node + Soft Dependencies", "value": "soft"},
                                {"label": "Node + All Dependencies", "value": "all"},
                            ],
                            value="hard",
                            className="mb-2",
                        ),
                        dbc.Button("Apply", id="btn-override-apply", color="primary",
                                   size="sm", className="w-100"),
                    ]),
                ],
                id="popover-override-mode",
                target="override-toggle",
                is_open=False,
                placement="bottom",
            ),

            # --- Section: Time Estimates ---
            html.Div(id="section-time-estimates", children=[
                html.Hr(className="my-2"),
                html.H5("Time Estimates", className="mt-2 mb-2"),
                html.Div([
                    dbc.Checklist(
                        options=[{"label": "Inherit", "value": "inherited"}],
                        value=[],
                        id="node-time-mode",
                        switch=True,
                        className="mb-0 flex-grow-1",
                    ),
                    dbc.Select(id="node-time-unit", options=[
                        {"label": "Hours", "value": "hours"},
                        {"label": "Weeks", "value": "weeks"},
                        {"label": "Months", "value": "months"},
                    ], value=_TED.get('unit', 'weeks'), size="sm", style={"width": "100px"}),
                ], className="d-flex align-items-center mb-2"),
                html.Div(id="section-time-omp", children=[
                    dbc.Row([
                        dbc.Col([dbc.Label("Optimistic", className="small text-muted mb-0"), dbc.Input(id="node-time-o", type="number", min=0)]),
                        dbc.Col([dbc.Label("Expected", className="small text-muted mb-0"), dbc.Input(id="node-time-m", type="number", min=0)]),
                        dbc.Col([dbc.Label("Pessimistic", className="small text-muted mb-0"), dbc.Input(id="node-time-p", type="number", min=0)]),
                    ]),
                    html.Div(id="time-validation-error", children="",
                             style={"display": "none", "color": "#dc3545", "fontSize": "0.85rem"},
                             className="mt-1"),
                ]),
            ]),
            
            html.Hr(className="my-2"),
            html.H5("Relationships", className="mt-2 mb-1"),
            dbc.Label("Needs", className="mt-2"),
            html.Div([
                dcc.Dropdown(id="edge-needs-hard", multi=True, placeholder="Hard..."),
                dcc.Dropdown(id="edge-needs-soft", multi=True, placeholder="Soft...", className="mt-1"),
            ], className="text-dark"),

            dbc.Label("Supports", className="mt-2"),
            html.Div([
                dcc.Dropdown(id="edge-supports-hard", multi=True, placeholder="Hard..."),
                dcc.Dropdown(id="edge-supports-soft", multi=True, placeholder="Soft...", className="mt-1"),
            ], className="text-dark"),

            dbc.Label("Helps", className="mt-2"),
            html.Div(dcc.Dropdown(id="edge-helps", multi=True, placeholder="Synergies..."), className="text-dark"),

            dcc.Store(id='edge-resources', data=[]),

            html.Hr(className="my-2"),
            html.H5("External Resources", className="mt-2 mb-1"),

            # Stores hold JSON arrays of links for each resource type
            dcc.Store(id='obsidian-links-store', data=['']),
            dcc.Store(id='drive-links-store', data=['']),
            dcc.Store(id='website-links-store', data=['']),

            html.Div([
                dbc.Label("Obsidian", className="mb-0"),
                dbc.Button("+", id="btn-obsidian-add", color="link", className="p-0 ms-2 text-decoration-none text-muted", title="Add Obsidian link", style={"fontSize": "1.2rem", "lineHeight": "1"})
            ], className="d-flex align-items-center mt-2 mb-1"),
            html.Div(id='obsidian-links-container'),

            html.Div([
                dbc.Label("Google Drive", className="mb-0"),
                dbc.Button("+", id="btn-drive-add", color="link", className="p-0 ms-2 text-decoration-none text-muted", title="Add Google Drive link", style={"fontSize": "1.2rem", "lineHeight": "1"})
            ], className="d-flex align-items-center mt-3 mb-1"),
            html.Div(id='drive-links-container'),

            html.Div([
                dbc.Label("Website", className="mb-0"),
                dbc.Button("+", id="btn-website-add", color="link", className="p-0 ms-2 text-decoration-none text-muted", title="Add Website link", style={"fontSize": "1.2rem", "lineHeight": "1"})
            ], className="d-flex align-items-center mt-3 mb-1"),
            html.Div(id='website-links-container'),
            
            html.Hr(className="my-2"),
            html.Div([
                dbc.Button("Delete", id="btn-delete", color="danger", className="flex-fill me-2", style={"backgroundColor": ConfigManager.get_danger_color(), "borderColor": ConfigManager.get_danger_color(), "padding": "6px 0"}),
                dbc.Button("Cancel", id="btn-revert", className="flex-fill me-2", style={"padding": "6px 0", "backgroundColor": "#6c757d", "borderColor": "#6c757d", "color": "#fff"}),
                dbc.Button("Save", id="btn-save", color="primary", className="flex-fill me-2", style={"padding": "6px 0"}),
                dbc.Button("Save & Close", id="btn-save-close", color="success", className="flex-fill", style={"padding": "6px 0"})
            ], className="d-flex mt-4"),
            dbc.Button("New Node", id="btn-new-node", color="secondary", className="w-100 mt-2",
                       style={"padding": "8px 0"}),
            dbc.Tooltip("Discard unsaved changes and revert this node to its last saved state", target="btn-revert", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Tooltip("Save changes", target="btn-save", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Tooltip("Save changes and close the node editor", target="btn-save-close", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Tooltip("Delete this node", target="btn-delete", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Tooltip("Create a new node", target="btn-new-node", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            html.Div(id="save-output", className="text-success fw-bold text-end mt-2 mb-5"),
            dcc.Interval(id='clear-interval', interval=3000, n_intervals=0, disabled=True),
            dcc.Store(id='node-time-unit-prev', data='weeks'),
            dcc.Store(id='node-original-name', data=None)
        ])
    ],
    className="ps-3 pe-4 pb-2 pt-0",
    style={"width": "380px", "minWidth": "380px"}
)


# --- Graph View (Canvas only) ---

def _build_graph_settings_panel(prefix="graph-settings"):
    """Build the graph settings panel controls.

    Args:
        prefix: ID prefix — 'graph-settings' for main canvas,
                'details-graph-settings' for details canvas.
    """
    gl = ConfigManager.get_graph_layout_defaults()
    reset_btn_id = f"btn-reset-{prefix}"
    return html.Div([
        html.Div([
            html.Span("Graph Settings", style={"fontWeight": "300", "fontSize": "1.05rem"}),
            dbc.Button("\u21ba", id=reset_btn_id, color="link", size="sm",
                       className="ms-2 p-0",
                       style={"fontSize": "1.1rem", "lineHeight": "1",
                              "color": "#adb5bd", "position": "relative",
                              "top": "0px", "textDecoration": "none"}),
            dbc.Tooltip("Restore defaults", target=reset_btn_id, placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
        ], className="d-flex align-items-center",
           style={"marginBottom": "12px"}),
        html.Div("Max Depth", className="settings-label"),
        dcc.Slider(
            id=f"{prefix}-max-depth",
            min=0, max=5, step=1, value=0,
            marks={0: "All", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5"},
            updatemode="mouseup",
        ),

        html.Div([
            dbc.Switch(
                id=f"{prefix}-neighbor-links",
                label="Neighbors",
                value=True,
                style={"fontSize": "0.82rem"},
            ),
            dbc.Switch(
                id=f"{prefix}-animate",
                label="Smooth",
                value=True,
                style={"fontSize": "0.82rem"},
            ),
            dbc.Switch(
                id=f"{prefix}-freeze-rerender",
                label="Freeze",
                value=False,
                style={"fontSize": "0.82rem"},
            ),
        ], className="d-flex gap-2 mt-3"),
        dbc.Tooltip("Pause graph updates on save. Use Re-layout to refresh manually.",
                    target=f"{prefix}-freeze-rerender", placement="left",
                    delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),

        html.Hr(style={"borderColor": "#495057", "margin": "12px 0"}),

        html.Div("Edge Length", className="settings-label"),
        dcc.Slider(
            id=f"{prefix}-edge-length",
            min=50, max=300, step=10, value=gl.get('edge_length', 100),
            marks={50: "50", 100: "100", 150: "150", 200: "200", 250: "250", 300: "300"},
            updatemode="mouseup",
        ),

        html.Div("Gravity", className="settings-label"),
        dcc.Slider(
            id=f"{prefix}-gravity",
            min=0, max=5, step=0.25, value=gl.get('gravity', 0.25),
            marks={0: "0", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5"},
            updatemode="mouseup",
        ),

        html.Div("Repulsion", className="settings-label"),
        dcc.Slider(
            id=f"{prefix}-repulsion",
            min=500, max=100000, step=500, value=gl.get('repulsion', 4500),
            marks={500: "500", 25000: "25k", 50000: "50k", 75000: "75k", 100000: "100k"},
            updatemode="mouseup",
        ),

        html.Hr(style={"borderColor": "#495057", "margin": "12px 0"}),

        dbc.Button("Settle", id=f"{prefix}-relayout",
                   color="secondary", size="sm", className="w-100 mt-2"),
        dbc.Tooltip("Re-run layout physics to untangle nodes",
                    target=f"{prefix}-relayout", placement="top",
                    delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
    ], id=f"{prefix}-panel", className="graph-settings-panel",
       style={"display": "none"})


def create_graph_view(initial_elements):
    """Create the Cytoscape graph canvas with fullscreen toggle button."""
    gl = ConfigManager.get_graph_layout_defaults()
    return html.Div([
        html.Div([
            cyto.Cytoscape(
                id='cytoscape-graph',
                layout={
                    'name': 'cose-bilkent', 'fit': True, 'animate': False,
                    'padding': 30, 'numIter': 2500, 'randomize': True,
                    'idealEdgeLength': gl.get('edge_length', 100),
                    'nodeRepulsion': gl.get('repulsion', 4500),
                    'gravity': gl.get('gravity', 0.25),
                },
                style={'width': '100%', 'height': '100%',
                       'backgroundColor': '#1a1d21', 'borderRadius': '8px'},
                elements=initial_elements,
                stylesheet=stylesheet,
                userZoomingEnabled=False,
                boxSelectionEnabled=True,
                userPanningEnabled=False,
                autoungrabify=False
            ),
            dbc.Button(html.I(className="bi bi-gear"),
                       id="btn-graph-settings",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right-mid"),
            dbc.Tooltip("Graph settings", target="btn-graph-settings", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            _freeze_indicator("freeze-indicator"),
            _build_graph_settings_panel("graph-settings"),
            dbc.Button(html.I(className="bi bi-arrows-fullscreen"),
                       id="btn-fullscreen",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right"),
            dbc.Tooltip("Toggle fullscreen", target="btn-fullscreen", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
        ], id="canvas-container", className="canvas-container h-100", style={"overflow": "hidden", "borderRadius": "8px"}),
    ], className="h-100", style={"overflow": "hidden"})



# --- Filters Section ---

filters_content = html.Div([
    html.Div([
        html.H4("Filters"),
        html.Span("×", id="btn-close-filters", className="fs-3 text-white float-end", style={"cursor": "pointer"})
    ], className="d-flex justify-content-between align-items-center mb-1 mt-2"),

    html.Div(id="filter-node-count", className="text-muted small mb-2"),

    html.H5("General", className="mt-2 mb-1"),
    dbc.Label("Node Type", className="mt-2"),
    dcc.Dropdown(
        id="filter-node-type",
        options=[{"label": t, "value": t} for t in NODE_TYPES],
        value=[],
        multi=True,
        placeholder="All",
        style={"color": "#212529"},
    ),

    dbc.Label("Context", className="mt-2"),
    dcc.Dropdown(
        id="filter-context",
        options=[{"label": c, "value": c} for c in CONTEXTS],
        value=[],
        multi=True,
        placeholder="All",
        style={"color": "#212529"},
    ),

    dbc.Label("Subcontext", className="mt-2"),
    dcc.Dropdown(
        id="filter-subcontext",
        options=[],
        value=[],
        multi=True,
        placeholder="All",
        style={"color": "#212529"},
    ),

    dbc.Label("Goal", className="mt-2"),
    dcc.Dropdown(
        id="filter-goal",
        options=[],
        value=[],
        multi=True,
        placeholder="All",
        style={"color": "#212529"},
    ),

    html.Hr(className="my-3"),

    html.H5("Communities", className="mt-2 mb-1"),
    dbc.Label("Detection Method", className="mt-2"),
    dbc.Select(id="community-method", options=[
        {"label": "Islands", "value": "components"},
        {"label": "Clusters", "value": "louvain"},
        {"label": "Orphans", "value": "orphans"},
    ], value="components"),

    dbc.Label("Community", className="mt-3"),
    dbc.Select(id="filter-community", options=[{"label": "All", "value": "All"}], value="All"),

    html.Hr(className="my-3"),

    html.H5("Ratings", className="mt-2 mb-1"),
    dbc.Label("Min Value", className="mt-2"),
    dcc.Slider(min=1, max=10, step=1, value=1, id="filter-value",
               marks={i: str(i) for i in range(1, 11)}),

    dbc.Label("Min Interest", className="mt-2"),
    dcc.Slider(min=1, max=10, step=1, value=1, id="filter-interest",
               marks={i: str(i) for i in range(1, 11)}),

    dbc.Label("Max Effort", className="mt-3"),
    dcc.Slider(min=1, max=10, step=1, value=10, id="filter-difficulty",
               marks={i: str(i) for i in range(1, 11)}),

    dbc.Label("Max Time in Hours", className="mt-2"),
    dbc.Input(id="filter-time", type="number", min=0.1, placeholder="No limit"),

    html.Hr(className="my-3"),

    dbc.Checklist(
        options=[{"label": "Hide Completed Tasks", "value": "hide_done"}],
        value=["hide_done"],  # Default ON
        id="filter-done",
        switch=True,
    ),

    html.Hr(className="my-3"),
    html.Div([
        dbc.Button("Clear Filters", id="btn-clear-filters", color="secondary", size="sm", className="flex-fill"),
        dbc.Button("Re-layout", id="btn-sidebar-relayout", color="secondary", size="sm", className="flex-fill"),
    ], className="d-flex gap-2 mb-3"),
], className="px-3 pb-2 pt-0", style={"width": "320px", "minWidth": "320px"})


_section_title_style = {"fontSize": "1.3rem", "fontWeight": "600"}
_formula_hint_style = {"fontSize": "0.8rem", "fontFamily": "monospace", "color": "#6c757d", "marginBottom": "0.25rem"}

# --- Info Panels ---

relationships_view = html.Div([
    html.H6("Relationships", className="text-muted mb-2", style=_section_title_style),
    html.Div([
        html.Div([
            html.H6("Hard Dependencies", className="text-muted mb-2", style={"fontSize": "0.95rem"}),
            html.Div(id="traversal-chains-hard")
        ], style={"marginRight": "2rem", "flex": "0 1 auto", "minWidth": 0, "overflow": "hidden"}),
        html.Div([
            html.H6("Soft Dependencies", className="text-muted mb-2", style={"fontSize": "0.95rem"}),
            html.Div(id="traversal-chains-soft")
        ], style={"marginRight": "2rem", "flex": "0 1 auto", "minWidth": 0, "overflow": "hidden"}),
        html.Div([
            html.H6("Synergies", className="text-muted mb-2", style={"fontSize": "0.95rem"}),
            html.Div(id="synergies-list")
        ], style={"flex": "0 1 auto", "minWidth": 0, "overflow": "hidden"}),
    ], style={"display": "flex", "alignItems": "flex-start"})
], style={"flex": "0 0 auto", "maxWidth": "80%", "minWidth": 0})

description_view = html.Div([
    html.H6("Description", className="text-muted mb-2", style=_section_title_style),
    html.Div(id="node-info-description", style={"color": "#dee2e6", "whiteSpace": "pre-wrap", "fontSize": "0.95rem"})
], style={"flex": "1", "marginLeft": "3rem", "minWidth": 0})

# --- Next View ---

next_view = html.Div([
    dcc.Store(id='suggestion-count-store', data=10),
    html.Div([
        html.H6("Suggestions", className="text-muted mb-0", style=_section_title_style),
        dbc.ButtonGroup([
            dbc.Button("−", id="btn-sugg-minus", color="secondary", size="sm",
                       style={"fontSize": "1rem", "lineHeight": "1", "padding": "2px 8px"}),
            html.Span(id="suggestion-count-display", children="10",
                       className="align-self-center mx-2",
                       style={"fontSize": "0.95rem", "fontWeight": "bold", "minWidth": "18px",
                              "textAlign": "center"}),
            dbc.Button("+", id="btn-sugg-plus", color="secondary", size="sm",
                       style={"fontSize": "1rem", "lineHeight": "1", "padding": "2px 8px"}),
        ], className="align-middle"),
    ], className="d-flex align-items-center mb-2", style={"gap": "12px"}),
    dcc.Store(id='selected-suggestion-store', data=None),
    dcc.Store(id='focus-goal-store', data=None),
    html.Div(id="suggestions-table", children=[
        html.P("Loading suggestions...", className="text-muted mt-3")
    ]),
])






# --- Migration Modal ---

def build_migration_content(orphans_by_field, new_values_by_field, subcontexts_by_context=None):
    """Build dynamic migration modal body from orphan data.

    Type orphans: one dropdown per node, grouped by old value (migration-dropdown IDs).
    Context orphans: one dropdown per old context value (migration-ctx-group-dropdown IDs).
    Subcontext orphans: one dropdown per old subcontext value (migration-sub-group-dropdown IDs).

    This grouped design avoids the cross-node state bug (one node's selection affecting
    another's) and naturally supports bulk renaming (e.g. all "STEM" → "Science").

    Args:
        orphans_by_field: {'context': {'OldCtx': [Node, ...]}, 'type': {...}, 'subcontext': {...}}
        new_values_by_field: {'context': [...], 'type': [...], 'subcontext': [...]}
        subcontexts_by_context: unused, kept for signature compatibility

    Returns:
        Tuple of (children list for modal body, mapping dict).
        Mapping: {
            "type": [{"field": "type", "old_value": ..., "node_name": ...}, ...],
            "ctx_groups": [{"old_value": ..., "node_names": [...]}, ...],
            "sub_groups": [{"old_value": ..., "node_names": [...]}, ...],
        }
    """
    children = []
    type_mapping = []
    ctx_groups = []
    sub_groups = []
    type_idx = 0

    # --- Type changes (one dropdown per node, grouped by old value) ---
    type_orphans = orphans_by_field.get('type', {})
    if type_orphans:
        new_vals = new_values_by_field.get('type', [])
        children.append(html.H5("Type Changes", className="mt-3 mb-2"))
        for old_val, nodes in type_orphans.items():
            options = [{"label": v, "value": v} for v in new_vals]
            default_val = new_vals[0] if new_vals else None
            children.append(dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.Strong(old_val),
                        html.Span(f" — {len(nodes)} node{'s' if len(nodes) != 1 else ''} affected",
                                  className="text-muted ms-1"),
                    ], className="mb-2"),
                    *[
                        dbc.Row([
                            dbc.Col(html.Span(n.name, className="small",
                                              style={"lineHeight": "38px"}), width=5),
                            dbc.Col(dbc.Select(
                                id={"type": "migration-dropdown", "index": type_idx + i},
                                options=options,  # type: ignore[reportArgumentType]
                                value=default_val,
                                placeholder="Reassign to...",
                                size="sm",
                            ), width=7),
                        ], className="mb-1")
                        for i, n in enumerate(nodes)
                    ],
                ])
            ], className="mb-2"))
            for n in nodes:
                type_mapping.append({"field": "type", "old_value": old_val, "node_name": n.name})
                type_idx += 1

    new_ctx_vals = new_values_by_field.get('context', [])
    subcontexts_map = subcontexts_by_context or {}

    ctx_options = [{"label": v, "value": v} for v in new_ctx_vals]
    ctx_options += [{"label": "Keep existing", "value": "__keep__"}, {"label": "Clear (set to none)", "value": "__clear__"}]

    def _sub_options_for(ctx_val):
        if ctx_val and ctx_val not in ('__keep__', '__clear__'):
            subs = subcontexts_map.get(ctx_val, [])
        else:
            subs = [s for ss in subcontexts_map.values() for s in ss]
        opts = [{"label": s, "value": s} for s in subs]
        opts += [{"label": "Keep existing", "value": "__keep__"}, {"label": "Clear (set to none)", "value": "__clear__"}]
        return opts, (subs[0] if subs else "__keep__")

    def _group_rows(orphans, group_list, ctx_dd_type, sub_dd_type, ctx_required):
        """Build group rows for context or subcontext orphan section."""
        rows = []
        for group_i, (old_val, nodes) in enumerate(orphans.items()):
            node_names = [n.name for n in nodes]
            preview = ", ".join(node_names[:8]) + (f" +{len(node_names) - 8} more" if len(node_names) > 8 else "")
            default_ctx = new_ctx_vals[0] if (ctx_required and new_ctx_vals) else "__keep__"
            init_sub_opts, default_sub = _sub_options_for(default_ctx)
            if not ctx_required:
                default_sub = "__keep__"
                init_sub_opts, _ = _sub_options_for("__keep__")
            rows.append(dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Strong(old_val),
                        html.Span(f" — {len(nodes)} node{'s' if len(nodes) != 1 else ''}",
                                   className="text-muted ms-1 small"),
                    ]),
                    html.Div(preview, className="text-muted mt-1", style={"fontSize": "0.78rem"}),
                ], width=4),
                dbc.Col(dbc.Select(
                    id={"type": ctx_dd_type, "index": group_i},
                    options=ctx_options,  # type: ignore[reportArgumentType]
                    value=default_ctx,
                    size="sm",
                ), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Select(
                    id={"type": sub_dd_type, "index": group_i},
                    options=init_sub_opts,  # type: ignore[reportArgumentType]
                    value=default_sub,
                    size="sm",
                ), width=4, className="d-flex align-items-center"),
            ], className="mb-2"))
            group_list.append({"old_value": old_val, "node_names": node_names})
        return rows

    header_row = dbc.Row([
        dbc.Col(html.Small("", className="text-muted fw-bold"), width=4),
        dbc.Col(html.Small("Context", className="text-muted fw-bold"), width=4),
        dbc.Col(html.Small("Subcontext", className="text-muted fw-bold"), width=4),
    ], className="mb-1 px-1")

    # --- Context changes ---
    ctx_orphans = orphans_by_field.get('context', {})
    if ctx_orphans:
        children.append(html.H5("Context Changes", className="mt-3 mb-2"))
        rows = _group_rows(ctx_orphans, ctx_groups, "migration-cgc", "migration-cgs", ctx_required=True)
        children.append(dbc.Card([dbc.CardBody([header_row] + rows)], className="mb-2"))

    # --- Subcontext changes ---
    sub_orphans = orphans_by_field.get('subcontext', {})
    if sub_orphans:
        children.append(html.H5("Subcontext Changes", className="mt-3 mb-2"))
        rows = _group_rows(sub_orphans, sub_groups, "migration-sgc", "migration-sgs", ctx_required=False)
        children.append(dbc.Card([dbc.CardBody([header_row] + rows)], className="mb-2"))

    return children, {"type": type_mapping, "ctx_groups": ctx_groups, "sub_groups": sub_groups}


migration_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Migration Required")),
    dbc.ModalBody(id="migration-modal-body"),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-migration-cancel", color="secondary", className="me-auto"),
        dbc.Button("Skip (keep old values)", id="btn-migration-skip", color="secondary", className="me-2"),
        dbc.Button("Apply Migrations", id="btn-migration-apply", color="primary"),
    ])
], id="modal-migration", size="lg", is_open=False, centered=True, backdrop="static")


error_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Validation Error", className="text-danger")),
    dbc.ModalBody(id="error-modal-body", style={"color": "#dee2e6"}),
    dbc.ModalFooter(dbc.Button("Close", id="btn-close-error", color="secondary"))
], id="modal-error", size="sm", is_open=False, centered=True)


unsaved_changes_modal = dbc.Modal([
    # close_button=False removes the header X so the modal can only be resolved
    # via one of the three footer actions. backdrop="static" + keyboard=False
    # block backdrop-click and Esc dismissals; Bootstrap auto-plays its built-in
    # "shake" animation on the modal when the static backdrop is clicked.
    dbc.ModalHeader(dbc.ModalTitle("Unsaved Changes"), close_button=False),
    dbc.ModalBody("You have unsaved changes. Please choose an action to continue."),
    dbc.ModalFooter([
        dbc.Button("Discard", id="btn-unsaved-discard", color="danger", className="flex-fill me-2"),
        dbc.Button("Edit", id="btn-unsaved-cancel", color="secondary", className="flex-fill me-2"),
        dbc.Button("Save", id="btn-unsaved-save", color="success", className="flex-fill"),
    ], className="d-flex flex-nowrap"),
], id="modal-unsaved-changes", size="sm", is_open=False, centered=True,
   backdrop="static", keyboard=False)


delete_confirm_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Confirm Delete")),
    dbc.ModalBody("Are you sure you want to delete this node? This action cannot be undone."),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-node-delete-cancel", color="secondary", className="flex-fill me-2"),
        dbc.Button("Delete", id="btn-node-delete-confirm", color="danger", className="flex-fill",
                   style={"backgroundColor": ConfigManager.get_danger_color(),
                          "borderColor": ConfigManager.get_danger_color()}),
    ], className="d-flex"),
], id="modal-node-delete-confirm", size="sm", is_open=False, centered=True)


# Used by the canvas context menu and Delete-key hotkey — handles one or many
# nodes. Distinct from the node-editor delete flow above, which always targets
# the single node currently open in the editor.
group_delete_confirm_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Confirm Delete")),
    dbc.ModalBody(id="group-delete-confirm-body"),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-group-delete-cancel", color="secondary", className="flex-fill me-2"),
        dbc.Button("Delete", id="btn-group-delete-confirm", color="danger", className="flex-fill",
                   style={"backgroundColor": ConfigManager.get_danger_color(),
                          "borderColor": ConfigManager.get_danger_color()}),
    ], className="d-flex"),
], id="modal-group-delete-confirm", size="sm", is_open=False, centered=True)


override_conflict_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Override Conflict")),
    dbc.ModalBody([
        html.Div(id="override-conflict-body"),
        html.Div(id="override-conflict-mode-wrapper", children=[
            html.Hr(className="my-2"),
            dbc.RadioItems(
                id="override-conflict-mode-radio",
                options=[
                    {"label": "Node Only", "value": "node_only"},
                    {"label": "Node + Hard Dependencies", "value": "hard"},
                    {"label": "Node + Soft Dependencies", "value": "soft"},
                    {"label": "Node + All Dependencies", "value": "all"},
                ],
                value="hard",
            ),
        ]),
    ]),
    dbc.ModalFooter([
        dbc.Button("Keep Current", id="btn-override-keep", color="secondary", className="flex-fill me-2"),
        dbc.Button("Apply to New", id="btn-override-replace", color="primary", className="flex-fill"),
    ], className="d-flex"),
], id="modal-override-conflict", is_open=False, centered=True)


override_untoggle_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Override Active")),
    dbc.ModalBody(id="override-untoggle-body"),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-override-untoggle-cancel", color="secondary", className="flex-fill me-2"),
        dbc.Button("Untoggle All", id="btn-override-untoggle-all", color="danger", className="flex-fill me-2",
                   style={"backgroundColor": ConfigManager.get_danger_color(),
                          "borderColor": ConfigManager.get_danger_color()}),
        dbc.Button("Hard Only", id="btn-override-untoggle-hard", color="primary", className="flex-fill me-2"),
        dbc.Button("Soft Only", id="btn-override-untoggle-soft", color="info", className="flex-fill"),
    ], className="d-flex"),
], id="modal-override-untoggle", size="md", is_open=False, centered=True)


# --- Bottom Panel (Relationships + Description) ---

bottom_panel = html.Div([
    html.Div([
        relationships_view,
        description_view
    ], className="d-flex")
], className="p-3")


# --- Floating Tooltip ---

hover_tooltip = html.Div(
    id="hover-tooltip",
    className="border rounded shadow p-2",
    style={
        "position": "fixed",
        "zIndex": 9999,
        "display": "none",
        "pointerEvents": "none",
        "maxWidth": "280px",
        "fontSize": "0.85rem",
        "lineHeight": "1.5",
        "backgroundColor": "#2b3035",
        "color": "#dee2e6",
        "borderColor": "#495057"
    }
)


_cell_style = {
    "padding": "6px 8px",
    "verticalAlign": "top",
    "borderBottom": "1px solid #343a40",
    "lineHeight": "1.4",
}
_header_cell_style = {
    **_cell_style,
    "fontWeight": "700",
    "backgroundColor": "#2b3035",
    "borderBottom": "2px solid #495057",
    "position": "sticky",
    "top": "0",
}


def build_popup_table_rows(defs):
    """Build the ratings popup table rows from a list of definition dicts."""
    return [
        html.Tr([
            html.Td(str(d['rating']), style={
                **_cell_style, "fontWeight": "700", "color": "#adb5bd",
                "backgroundColor": "#1a1d21" if i % 2 == 0 else "transparent",
            }),
            html.Td(d['value'], style={
                **_cell_style, "backgroundColor": "#1a1d21" if i % 2 == 0 else "transparent",
            }),
            html.Td(d['interest'], style={
                **_cell_style, "backgroundColor": "#1a1d21" if i % 2 == 0 else "transparent",
            }),
            html.Td(d['effort'], style={
                **_cell_style, "backgroundColor": "#1a1d21" if i % 2 == 0 else "transparent",
            }),
        ])
        for i, d in enumerate(defs)
    ]


def build_editor_table(defs):
    """Build the full editor table (with header) for the ratings editor modal."""
    return html.Table([
        html.Thead(html.Tr([
            html.Th("#", style={**_header_cell_style, "width": "36px"}),
            html.Th("Value", style=_header_cell_style),
            html.Th("Interest", style=_header_cell_style),
            html.Th("Effort", style=_header_cell_style),
        ])),
        html.Tbody(build_editor_rows(defs)),
    ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.8rem", "color": "#dee2e6"})


def build_editor_rows(defs):
    """Build the editor modal rows (textareas) from a list of definition dicts."""
    from dash import dcc
    rows = []
    for d in defs:
        i = d['rating'] - 1
        rows.append(html.Tr([
            html.Td(str(d['rating']), style={
                **_cell_style, "fontWeight": "700", "color": "#adb5bd",
                "width": "36px", "textAlign": "center",
            }),
            html.Td(dcc.Textarea(
                id={"type": "ratings-edit-value", "index": i},
                value=d['value'],
                style={"width": "100%", "height": "72px", "resize": "vertical",
                       "backgroundColor": "#2b3035", "color": "#dee2e6",
                       "border": "1px solid #495057", "borderRadius": "4px",
                       "padding": "4px", "fontSize": "0.8rem"},
            ), style=_cell_style),
            html.Td(dcc.Textarea(
                id={"type": "ratings-edit-interest", "index": i},
                value=d['interest'],
                style={"width": "100%", "height": "72px", "resize": "vertical",
                       "backgroundColor": "#2b3035", "color": "#dee2e6",
                       "border": "1px solid #495057", "borderRadius": "4px",
                       "padding": "4px", "fontSize": "0.8rem"},
            ), style=_cell_style),
            html.Td(dcc.Textarea(
                id={"type": "ratings-edit-effort", "index": i},
                value=d['effort'],
                style={"width": "100%", "height": "72px", "resize": "vertical",
                       "backgroundColor": "#2b3035", "color": "#dee2e6",
                       "border": "1px solid #495057", "borderRadius": "4px",
                       "padding": "4px", "fontSize": "0.8rem"},
            ), style=_cell_style),
        ]))
    return rows


ratings_popup = html.Div([
    # Draggable header
    html.Div([
        html.Span("Ratings Reference", style={"fontWeight": "600", "fontSize": "0.9rem"}),
        html.Button(html.I(className="bi bi-pencil"), id="btn-ratings-edit", style={
            "background": "none", "border": "none", "color": "#adb5bd",
            "fontSize": "0.85rem", "lineHeight": "1", "cursor": "pointer",
            "padding": "0 6px", "marginLeft": "8px",
        }, title="Edit definitions"),
        html.Button("×", id="btn-ratings-close", style={
            "background": "none", "border": "none", "color": "#adb5bd",
            "fontSize": "1.2rem", "lineHeight": "1", "cursor": "pointer",
            "padding": "0", "marginLeft": "auto",
        }),
    ], id="ratings-popup-header", className="d-flex align-items-center", style={
        "cursor": "move",
        "padding": "8px 10px",
        "backgroundColor": "#2b3035",
        "borderBottom": "1px solid #495057",
        "borderRadius": "6px 6px 0 0",
        "flexShrink": "0",
        "userSelect": "none",
    }),
    # Scrollable body
    html.Div([
        html.Table([
            html.Thead(html.Tr([
                html.Th("#", style={**_header_cell_style, "width": "36px"}),
                html.Th("Value", style=_header_cell_style),
                html.Th("Interest", style=_header_cell_style),
                html.Th("Effort", style=_header_cell_style),
            ])),
            html.Tbody(
                id="ratings-popup-table-body",
                children=build_popup_table_rows(ConfigManager.get_ratings_definitions()),
            ),
        ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.8rem", "color": "#dee2e6"}),
    ], style={"overflow": "auto", "flex": "1", "padding": "4px"}),
], id="ratings-popup", style={
    "display": "none",
    "flexDirection": "column",
    "position": "fixed",
    "top": "120px",
    "left": "420px",
    "width": "960px",
    "height": "710px",
    "minWidth": "400px",
    "minHeight": "200px",
    "zIndex": 9998,
    "backgroundColor": "#212529",
    "border": "1px solid #495057",
    "borderRadius": "6px",
    "boxShadow": "0 4px 16px rgba(0,0,0,0.5)",
    "resize": "both",
    "overflow": "hidden",
})


ratings_editor_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Edit Ratings Definitions")),
    dbc.ModalBody(
        html.Div(id="ratings-editor-body"),
        style={"maxHeight": "70vh", "overflowY": "auto"},
    ),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-ratings-editor-cancel", color="secondary", className="me-auto"),
        dbc.Button("Save", id="btn-ratings-editor-save", color="primary"),
    ]),
], id="modal-ratings-editor", size="xl", is_open=False, scrollable=True)


def build_competence_popup_table_rows(defs):
    """Build the competence popup table rows from a list of definition dicts."""
    return [
        html.Tr([
            html.Td(d['stage'], style={
                **_cell_style, "fontWeight": "700", "color": "#adb5bd",
                "width": "100px", "whiteSpace": "nowrap",
                "backgroundColor": "#1a1d21" if i % 2 == 0 else "transparent",
            }),
            html.Td(d['essence'], style={
                **_cell_style, "backgroundColor": "#1a1d21" if i % 2 == 0 else "transparent",
            }),
        ])
        for i, d in enumerate(defs)
    ]


def build_competence_editor_table(defs):
    """Build the full editor table (with header) for the competence editor modal."""
    return html.Table([
        html.Thead(html.Tr([
            html.Th("Stage", style={**_header_cell_style, "width": "100px"}),
            html.Th("Essence", style=_header_cell_style),
        ])),
        html.Tbody(build_competence_editor_rows(defs)),
    ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.8rem", "color": "#dee2e6"})


def build_competence_editor_rows(defs):
    """Build the editor modal rows (textareas) from a list of definition dicts."""
    from dash import dcc
    rows = []
    for i, d in enumerate(defs):
        rows.append(html.Tr([
            html.Td(d['stage'], style={
                **_cell_style, "fontWeight": "700", "color": "#adb5bd",
                "width": "100px", "whiteSpace": "nowrap",
            }),
            html.Td(dcc.Textarea(
                id={"type": "competence-edit-essence", "index": i},
                value=d['essence'],
                style={"width": "100%", "height": "120px", "resize": "vertical",
                       "backgroundColor": "#2b3035", "color": "#dee2e6",
                       "border": "1px solid #495057", "borderRadius": "4px",
                       "padding": "4px", "fontSize": "0.8rem"},
            ), style=_cell_style),
        ]))
    return rows


competence_popup = html.Div([
    # Draggable header
    html.Div([
        html.Span("Competence Reference", style={"fontWeight": "600", "fontSize": "0.9rem"}),
        html.Button(html.I(className="bi bi-pencil"), id="btn-competence-edit", style={
            "background": "none", "border": "none", "color": "#adb5bd",
            "fontSize": "0.85rem", "lineHeight": "1", "cursor": "pointer",
            "padding": "0 6px", "marginLeft": "8px",
        }, title="Edit definitions"),
        html.Button("\u00d7", id="btn-competence-close", style={
            "background": "none", "border": "none", "color": "#adb5bd",
            "fontSize": "1.2rem", "lineHeight": "1", "cursor": "pointer",
            "padding": "0", "marginLeft": "auto",
        }),
    ], id="competence-popup-header", className="d-flex align-items-center", style={
        "cursor": "move",
        "padding": "8px 10px",
        "backgroundColor": "#2b3035",
        "borderBottom": "1px solid #495057",
        "borderRadius": "6px 6px 0 0",
        "flexShrink": "0",
        "userSelect": "none",
    }),
    # Scrollable body
    html.Div([
        html.Table([
            html.Thead(html.Tr([
                html.Th("Stage", style={**_header_cell_style, "width": "100px"}),
                html.Th("Essence", style=_header_cell_style),
            ])),
            html.Tbody(
                id="competence-popup-table-body",
                children=build_competence_popup_table_rows(ConfigManager.get_competence_definitions()),
            ),
        ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.8rem", "color": "#dee2e6"}),
    ], style={"overflow": "auto", "flex": "1", "padding": "4px"}),
], id="competence-popup", style={
    "display": "none",
    "flexDirection": "column",
    "position": "fixed",
    "top": "140px",
    "left": "460px",
    "width": "720px",
    "height": "560px",
    "minWidth": "400px",
    "minHeight": "200px",
    "zIndex": 9998,
    "backgroundColor": "#212529",
    "border": "1px solid #495057",
    "borderRadius": "6px",
    "boxShadow": "0 4px 16px rgba(0,0,0,0.5)",
    "resize": "both",
    "overflow": "hidden",
})


competence_editor_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Edit Competence Definitions")),
    dbc.ModalBody(
        html.Div(id="competence-editor-body"),
        style={"maxHeight": "70vh", "overflowY": "auto"},
    ),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-competence-editor-cancel", color="secondary", className="me-auto"),
        dbc.Button("Save", id="btn-competence-editor-save", color="primary"),
    ]),
], id="modal-competence-editor", size="xl", is_open=False, scrollable=True)


def build_app_layout(initial_elements, env="production"):
    """Assembles the full application layout with pure Flexbox (Push behavior)."""
    
    edit_trigger = html.Button(id="btn-edit-node", style={"visibility": "hidden", "width": 0, "height": 0, "position": "absolute"})
    toggle_trigger = html.Button(id="btn-toggle-done-node", style={"visibility": "hidden", "width": 0, "height": 0, "position": "absolute"})

    context_menu = html.Div(
        id="node-context-menu",
        children=[
            html.Div("Edit", id="ctx-menu-edit", className="ctx-menu-item"),
            html.Div("Details", id="ctx-menu-details", className="ctx-menu-item"),
            html.Div("Done", id="ctx-menu-toggle-done", className="ctx-menu-item"),
            html.Hr(style={"margin": "2px"}),
            html.Div("Obsidian", id="ctx-menu-obsidian", className="ctx-menu-item"),
            html.Div("Drive", id="ctx-menu-drive", className="ctx-menu-item"),
            html.Hr(style={"margin": "2px"}),
            html.Div("Delete", id="ctx-menu-delete", className="ctx-menu-item", style={"color": ConfigManager.get_danger_color()}),
        ],
        style={
            "display": "none",
            "position": "fixed",
            "zIndex": 10000,
            "backgroundColor": "#2b3035",
            "border": "1px solid #495057",
            "borderRadius": "6px",
            "padding": "4px 0",
            "minWidth": "160px",
            "boxShadow": "0 4px 16px rgba(0,0,0,0.4)",
        }
    )

    # --- Tab Navigation (toolbar: left buttons | centered tabs | right buttons) ---
    main_tabs = html.Div([
        # LEFT: Node Editor + Goals + Events (open left-side sidebars)
        html.Div([
            dbc.Button(html.I(className="bi bi-node-plus"), id="btn-add", color="secondary", size="sm", className="me-2"),
            dbc.Tooltip("Node editor", target="btn-add", placement="bottom",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Button(html.I(className="bi bi-star"), id="btn-goals-toggle", color="secondary", size="sm", className="me-2"),
            dbc.Tooltip("Goals", target="btn-goals-toggle", placement="bottom",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Button(html.I(className="bi bi-calendar-event"), id="btn-events-sidebar-toggle", color="secondary", size="sm"),
            dbc.Tooltip("Events", target="btn-events-sidebar-toggle", placement="bottom",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
        ], className="d-flex align-items-center ps-3",
           style={"flex": "0 0 auto"}),

        # CENTER: Tabs
        dbc.Tabs(
            id="main-tabs",
            active_tab="tab-next",
            children=[
                dbc.Tab(label="Next", tab_id="tab-next"),
                dbc.Tab(label="Nodes", tab_id="tab-canvas"),
                dbc.Tab(label="Details", tab_id="tab-details"),
                dbc.Tab(label="Events", tab_id="tab-events"),
                dbc.Tab(label="Analyze", tab_id="tab-analyze"),
                dbc.Tab(label="Settings", tab_id="tab-settings"),
            ],
            className="px-3 pt-1 justify-content-center",
            style={"flex": "1", "backgroundColor": "#1a1d21", "borderBottom": "none"}
        ),

        # RIGHT: Clear Focus + Filters (open right-side sidebar)
        html.Div([
            dbc.Button("Clear Focus", id="btn-clear-focus", color="warning", size="sm",
                       className="me-2", style={"display": "none"}),
            dbc.Button(html.I(className="bi bi-filter"), id="btn-filters-toggle", color="secondary", size="sm"),
            dbc.Tooltip("Filters", target="btn-filters-toggle", placement="bottom",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
        ], className="d-flex align-items-center pe-3",
           style={"flex": "0 0 auto"}),
    ], className="d-flex align-items-center",
       style={"borderBottom": "1px solid #495057", "backgroundColor": "#1a1d21"})

    # --- Canvas Tab Content (existing layout, unchanged) ---
    canvas_tab_content = html.Div(
        id="canvas-tab-content",
        children=[
            # --- MAIN CENTER CONTENT ---
            html.Div(
                style={
                    "flex": "1",
                    "display": "flex",
                    "flexDirection": "column",
                    "minWidth": "0",
                },
                children=[
                    # Canvas Container
                    html.Div(
                        [create_graph_view(initial_elements)],
                        className="flex-grow-1",
                        style={
                            "minHeight": "200px",
                            "position": "relative",
                            "overflow": "hidden"
                        }
                    ),

                    # Hidden outputs for bottom-panel callbacks (IDs must remain in DOM)
                    html.Div([
                        html.Div(id="traversal-chains-hard"),
                        html.Div(id="traversal-chains-soft"),
                        html.Div(id="synergies-list"),
                        html.Div(id="node-info-description"),
                    ], style={"display": "none"})
                ]
            ),

        ],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "hidden",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Events Tab Content (hidden by default) ---
    events_tab_content = html.Div(
        id="events-tab-content",
        children=[build_events_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "hidden",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Next Tab Content (hidden by default) ---
    next_tab_content = html.Div(
        id="next-tab-content",
        children=[
            html.Div([
                html.Div([next_view], className="px-4 pt-3 pb-4"),
            ], style={"flex": "1", "overflowY": "auto"}),
            html.Div(id="next-perf-stats", className="next-perf-overlay"),
        ],
        style={"display": "block", "width": "100%", "height": "100%", "overflow": "auto",
               "position": "absolute", "top": "0", "left": "0", "flexDirection": "column",
               "visibility": "visible"}
    )

    # --- Details Tab Content (hidden by default) ---
    details_tab_content = html.Div(
        id="details-tab-content",
        children=[build_details_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Settings Tab Content (hidden by default) ---
    settings_tab_content = html.Div(
        id="settings-tab-content",
        children=[build_settings_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "auto",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Analyze Tab Content (hidden by default) ---
    analyze_tab_content = html.Div(
        id="analyze-tab-content",
        children=[build_analyze_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "auto",
               "position": "absolute", "top": "0", "left": "0"}
    )

    return html.Div([
        hover_tooltip,
        ratings_popup,
        competence_popup,
        edit_trigger,
        toggle_trigger,
        context_menu,
        dcc.Store(id='ctx-obsidian-path-store', data=None),
        dcc.Store(id='ctx-drive-path-store', data=None),
        dcc.Input(id='group-delete-input', type='text', value='', style={'display': 'none'}),
        dcc.Input(id='group-delete-request-input', type='text', value='', style={'display': 'none'}),
        dcc.Store(id='group-delete-pending-store', data=None),
        dcc.Input(id='edit-trigger-input', type='text', value='', style={'display': 'none'}),
        dcc.Input(id='toggle-done-trigger-input', type='text', value='', style={'display': 'none'}),
        dcc.Input(id='background-click-input', type='text', value='', style={'display': 'none'}),
        dcc.Store(id='pending-navigation-store', data=None),
        dcc.Input(id='details-navigate-trigger-input', type='text', value='', style={'display': 'none'}),
        html.Div(id='canvas-height-config', style={'display': 'none'}, **{'data-height': str(CANVAS_HEIGHT)}),  # type: ignore[reportArgumentType]
        html.Div(id='tooltip-config', style={'display': 'none'}, **{  # type: ignore[reportArgumentType]
            'data-show': str(TOOLTIP_SHOW_DELAY_MS),
            'data-hide': str(TOOLTIP_HIDE_DELAY_MS),
            'data-node-hide': str(TOOLTIP_NODE_HIDE_DELAY_MS),
        }),
        migration_modal,
        error_modal,
        unsaved_changes_modal,
        delete_confirm_modal,
        group_delete_confirm_modal,
        override_conflict_modal,
        override_untoggle_modal,
        ratings_editor_modal,
        competence_editor_modal,
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Events Triggered Since Last Launch")),
            dbc.ModalBody(id="event-announcements-body"),
            dbc.ModalFooter(dbc.Button("Dismiss", id="btn-event-announcements-dismiss",
                                       color="primary")),
        ], id="modal-event-announcements", is_open=False, centered=True, size="lg"),
        dcc.Interval(id='app-load-interval', interval=500, n_intervals=0, max_intervals=1),

        dcc.Store(id='override-store', data={"parent": None, "mode": "hard"}),
        dcc.Store(id='pending-event-override-store', data=None),
        dcc.Store(id='pending-settings-store', data=None),
        dcc.Store(id='migration-mapping-store', data=None),
        dcc.Store(id='freeze-rerender-store', data=False),
        # Intermediate hop for cytoscape elements — core_engine writes here,
        # a clientside callback either applies the delta directly to the cy
        # instance (during freeze) or forwards it to cytoscape-graph.elements
        # (normal operation). See assets/freeze_positions.js. Details and
        # Events tabs each have their own pending store + freeze store.
        dcc.Store(id='elements-pending-store', data=None),
        dcc.Store(id='details-elements-pending-store', data=None),
        dcc.Store(id='events-elements-pending-store', data=None),
        dcc.Store(id='details-freeze-rerender-store', data=False),
        dcc.Store(id='events-freeze-rerender-store', data=False),
        # Bumped by the bridge callback only when GraphManager._graph_version
        # advances (i.e. a real node/edge mutation, not a cosmetic filter change).
        # Downstream listeners use this instead of cytoscape-graph.elements to
        # avoid re-firing on cosmetic updates (filter, depth, highlight).
        dcc.Store(id='graph-version-store', data=0),
        dcc.Interval(id='settings-clear-interval', interval=3000, n_intervals=0, disabled=True),

        main_tabs,
        # Tab content wrapper — only one tab visible at a time
        html.Div([
            next_tab_content,
            canvas_tab_content,
            details_tab_content,
            events_tab_content,
            settings_tab_content,
            analyze_tab_content,
            # --- SHARED NODE EDITOR SIDEBAR (overlay, accessible from any tab) ---
            html.Div(
                id="sidebar-editor-container",
                children=[sidebar_content],
                style={
                    "position": "absolute",
                    "top": "0",
                    "left": "0",
                    "width": "380px",
                    "minWidth": "380px",
                    "height": "100%",
                    "zIndex": 1000,
                    "overflowX": "hidden",
                    "overflowY": "auto",
                    "borderRight": "1px solid #495057",
                    "transition": "transform 0.3s ease",
                    "transform": "translateX(-380px)",
                    "willChange": "transform",
                    "backgroundColor": "#212529"
                }
            ),
            # --- SHARED GOAL SIDEBAR (overlay, accessible from any tab) ---
            html.Div(
                id="details-goal-sidebar",
                children=[
                    html.Div([
                        html.Div([
                            html.H4("Goals", className="mb-0"),
                            dbc.Button("+", id="btn-goals-sidebar-new",
                                       color="link",
                                       className="p-0 ms-2 text-decoration-none text-muted",
                                       style={"fontSize": "1.4rem", "lineHeight": "1"}),
                            dbc.Tooltip("New goal", target="btn-goals-sidebar-new", placement="right",
                                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                        ], className="d-flex align-items-center"),
                        html.Span("\u00d7", id="btn-details-goals-close",
                                   className="fs-3 text-white",
                                   style={"cursor": "pointer"}),
                    ], className="d-flex justify-content-between align-items-center mb-3 mt-2 px-3"),

                    html.Div(
                        dbc.Input(id="details-goal-search", type="text",
                                  placeholder="Search goals...", size="sm",
                                  debounce=False,
                                  style={"backgroundColor": "#2b3035",
                                         "border": "1px solid #495057",
                                         "color": "#dee2e6",
                                         "width": "100%",
                                         "boxSizing": "border-box"}),
                        style={"padding": "0 12px", "marginBottom": "8px"},
                    ),

                    html.Div(
                        dbc.Select(id="details-goal-sort", options=[
                            {"label": "A \u2192 Z", "value": "alpha-asc"},
                            {"label": "Z \u2192 A", "value": "alpha-desc"},
                            {"label": "Time \u2191", "value": "time-asc"},
                            {"label": "Time \u2193", "value": "time-desc"},
                            {"label": "Manual", "value": "manual"},
                        ], value="manual", size="sm",
                            style={"flex": "1", "backgroundColor": "#2b3035",
                                   "border": "1px solid #495057",
                                   "color": "#dee2e6", "fontSize": "0.8rem"}),
                        style={"padding": "0 12px", "marginBottom": "8px"},
                    ),

                    html.Div(id="details-goal-list-container",
                             style={"overflowY": "auto", "flex": "1", "padding": "0 12px"}),
                ],
                style={
                    "position": "absolute",
                    "top": "0",
                    "left": "-380px",
                    "width": "380px",
                    "height": "100%",
                    "zIndex": 100,
                    "overflowX": "hidden",
                    "overflowY": "auto",
                    "borderRight": "1px solid #495057",
                    "transition": "left 0.3s ease",
                    "backgroundColor": "#212529",
                    "display": "flex",
                    "flexDirection": "column",
                }
            ),
            # --- SHARED EVENTS SIDEBAR (overlay, accessible from any tab) ---
            html.Div(
                id="events-sidebar-container",
                children=[build_events_sidebar_content()],
                style={
                    "position": "absolute",
                    "top": "0",
                    "left": "-380px",
                    "width": "380px",
                    "height": "100%",
                    "zIndex": 100,
                    "overflowX": "hidden",
                    "overflowY": "auto",
                    "borderRight": "1px solid #495057",
                    "transition": "left 0.3s ease",
                    "backgroundColor": "#212529",
                    "display": "flex",
                    "flexDirection": "column",
                }
            ),
            # --- SHARED FILTERS SIDEBAR (overlay, accessible from Canvas + Suggestions) ---
            html.Div(
                id="sidebar-filters-container",
                children=[filters_content],
                style={
                    "position": "absolute",
                    "top": "0",
                    "right": "-320px",
                    "width": "320px",
                    "height": "100%",
                    "zIndex": 100,
                    "overflowX": "hidden",
                    "overflowY": "auto",
                    "borderLeft": "1px solid #495057",
                    "transition": "right 0.3s ease",
                    "backgroundColor": "#212529"
                }
            )
        ], style={"flex": "1", "overflow": "hidden", "position": "relative"}),
    ], style={"width": "100vw", "height": "100vh", "overflow": "hidden",
              "display": "flex", "flexDirection": "column"})
