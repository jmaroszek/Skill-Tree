"""
Layout definitions for the Details tab.

Provides a consolidated view for drilling into any node's dependencies,
subtasks, and time simulation — merging the best parts of the Goals
and Simulation tabs.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from config import ConfigManager, DEFAULT_TIME_ESTIMATE_DEFAULTS
from models import EDGE_NEEDS_HARD
from styles import stylesheet


def build_details_tab_content():
    """Builds the Details tab UI.

    Layout:
      ┌──────────────────────────────────────────────────────┐
      │ [☰ Goals]       Node Selector         [Simulate ▶]  │
      ├─────────────────┬────────────────────────────────────┤
      │ Node Attributes │ Dependency Graph (Cytoscape)       │
      │ (read-only      │                                    │
      │  summary)       │                                    │
      ├─────────────────┴────────────────┬───────────────────┤
      │ Subtasks Table                   │ Time Distribution │
      │ [Add Node] toggles              │ (histogram+stats) │
      └─────────────────────────────────┴───────────────────┘

      Left overlay: Goal List sidebar (toggle via ☰)
    """

    _ted = ConfigManager.get_time_estimate_defaults()

    # --- Top Bar: node selector + action buttons ---
    top_bar = html.Div([
        dbc.Button("☰ Goals", id="btn-details-goals-toggle", color="secondary",
                   size="sm", className="me-3"),
        html.Div(dcc.Dropdown(
            id="details-node-select",
            placeholder="Select a node to view details...",
            clearable=True,
            style={"minWidth": "350px"},
        ), className="text-dark", style={"flex": "1"}),
        dbc.Button("Simulate ▶", id="btn-details-simulate", color="info",
                   size="sm", className="ms-3"),
    ], className="d-flex align-items-center py-3 px-3",
       style={"borderBottom": "1px solid #495057"})

    # --- Empty state ---
    empty_state = html.Div(
        id="details-empty",
        children=[
            html.Div([
                html.H5("No Node Selected", className="text-muted mb-2"),
                html.P("Select a node from the dropdown or goal list to see its details.",
                       className="text-muted"),
            ], style={"textAlign": "center", "marginTop": "20vh"})
        ],
    )

    # --- Node attributes summary (left column of upper section) ---
    node_summary = html.Div([
        html.H4(id="details-node-name", className="mb-2",
                style={"fontWeight": "300", "letterSpacing": "1px"}),
        html.Div(id="details-node-badges", className="d-flex gap-1 flex-wrap mb-2"),

        # Description
        html.Div(id="details-node-description",
                 className="text-muted mb-3",
                 style={"fontSize": "0.9rem", "whiteSpace": "pre-wrap",
                        "maxHeight": "80px", "overflowY": "auto"}),

        # Stats grid
        html.Div([
            _attribute_row("Type", "details-attr-type"),
            _attribute_row("Status", "details-attr-status"),
            _attribute_row("Context", "details-attr-context"),
            _attribute_row("Time", "details-attr-time"),
            _attribute_row("Value", "details-attr-value"),
            _attribute_row("Interest", "details-attr-interest"),
            _attribute_row("Effort", "details-attr-effort"),
        ]),

        # Progress bar (for goals)
        html.Div(id="details-progress-section", style={"display": "none"}, children=[
            html.Hr(className="my-2"),
            html.H6("Progress", className="mb-1"),
            dbc.Progress(id="details-progress-bar", value=0,
                         className="mb-1", style={"height": "16px"}),
            html.Small(id="details-progress-text", className="text-muted",
                       style={"fontSize": "0.8rem"}),
        ]),

        # Priority rank badge
        html.Div(id="details-priority-section", style={"display": "none"}, children=[
            html.Hr(className="my-2"),
            html.Div([
                html.H6("Priority Rank", className="mb-0"),
                html.Div(id="details-priority-badge"),
            ], className="d-flex align-items-center gap-2"),
        ]),

        # Focus on canvas button
        html.Div([
            dbc.Button("Focus on Canvas", id="btn-details-focus", color="outline-info",
                       size="sm", className="mt-2 w-100"),
            dbc.Button("Edit Node", id="btn-details-edit", color="outline-secondary",
                       size="sm", className="mt-1 w-100"),
        ]),

    ], style={"minWidth": "280px", "maxWidth": "320px", "paddingRight": "16px"})

    # --- Dependency Graph (right column of upper section) ---
    dep_graph = html.Div([
        html.Div([
            html.H5("Dependency Graph", className="mb-0",
                     style={"lineHeight": "1.2"}),
        ], className="d-flex align-items-center mb-2"),
        cyto.Cytoscape(
            id='details-mini-graph',
            elements=[],
            layout={'name': 'cose', 'animate': False, 'fit': True, 'padding': 20},
            style={'width': '100%', 'flex': '1', 'backgroundColor': '#1a1d21',
                   'borderRadius': '8px', 'minHeight': '250px'},
            stylesheet=stylesheet,
            userZoomingEnabled=False,
            userPanningEnabled=False,
            boxSelectionEnabled=False,
            autoungrabify=False,
        ),
    ], style={
        "flex": "1",
        "minWidth": "350px",
        "paddingLeft": "16px",
        "borderLeft": "1px solid #495057",
        "display": "flex",
        "flexDirection": "column",
    })

    # Upper section: attributes + graph
    upper_section = html.Div([
        node_summary,
        dep_graph,
    ], style={"display": "flex", "padding": "16px 0"})

    # --- Subtasks Table (left of lower section) ---
    subtasks_section = html.Div([
        html.Div([
            html.Div([
                html.H5("Subtasks", className="mb-0"),
                dbc.Button("Add Node", id="btn-details-add-node", color="success",
                           size="sm", className="ms-2"),
            ], className="d-flex align-items-center"),
            html.Div([
                dbc.Checklist(
                    id="details-include-soft-needs",
                    options=[{"label": "Soft Needs", "value": "include"}],
                    value=[],
                    switch=True,
                    style={"fontSize": "0.82rem"},
                ),
                dbc.Checklist(
                    id="details-include-transitive",
                    options=[{"label": "Transitive", "value": "include"}],
                    value=[],
                    switch=True,
                    style={"fontSize": "0.82rem"},
                ),
                dbc.Checklist(
                    id="details-include-synergies",
                    options=[{"label": "Synergies", "value": "include"}],
                    value=[],
                    switch=True,
                    style={"fontSize": "0.82rem"},
                ),
            ], className="d-flex gap-3"),
        ], className="d-flex align-items-center justify-content-between mb-2"),
        html.Div(id="details-subtasks-table-container",
                 style={"overflowY": "auto", "flex": "1"}),
    ], style={"flex": "1", "minWidth": "400px", "display": "flex",
              "flexDirection": "column"})

    # --- Simulation Section (right of lower section) ---
    sim_section = html.Div([
        html.Div(id="details-sim-empty", children=[
            html.Div([
                html.P("Click 'Simulate ▶' to see the time distribution.",
                       className="text-muted text-center",
                       style={"marginTop": "80px"}),
            ]),
        ]),
        html.Div(id="details-sim-results", style={"display": "none"}, children=[
            html.H6(id="details-sim-title", className="mb-2"),
            dcc.Graph(
                id="details-sim-chart",
                config={"displayModeBar": False},
                style={"height": "350px"},
            ),
            html.Div(id="details-sim-stats", className="mt-2"),
        ]),
    ], style={"width": "45%", "minWidth": "350px", "paddingLeft": "16px",
              "borderLeft": "1px solid #495057", "display": "flex",
              "flexDirection": "column"})

    # Lower section: subtasks + simulation
    lower_section = html.Div([
        subtasks_section,
        sim_section,
    ], style={"display": "flex", "borderTop": "1px solid #495057",
              "paddingTop": "12px", "flex": "1", "minHeight": "0"})

    # --- Detail content (hidden when no node selected) ---
    detail_content = html.Div(
        id="details-content",
        style={"display": "none", "flexDirection": "column", "flex": "1",
               "padding": "0 24px", "overflowY": "auto"},
        children=[upper_section, lower_section],
    )

    # --- Add Node Modal (reused from goals, with details- prefix) ---
    add_node_modal = _build_add_node_modal(_ted)

    # --- Subtask Remove Confirmation Modal ---
    subtask_remove_modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Remove Subtask")),
        dbc.ModalBody(id="details-subtask-remove-modal-body"),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-details-subtask-remove-cancel",
                       color="secondary", className="me-auto"),
            dbc.Button("Remove Edge", id="btn-details-subtask-remove-edge",
                       color="warning", className="me-2"),
            dbc.Button("Delete Node", id="btn-details-subtask-delete-node",
                       color="danger"),
        ]),
    ], id="modal-details-subtask-remove", is_open=False, centered=True)

    # --- Goal List Sidebar (left overlay) ---
    goal_sidebar = _build_goal_sidebar()

    return html.Div([
        dcc.Store(id='details-selected-node-store', data=None),
        dcc.Store(id='details-refresh-trigger', data=0),
        dcc.Store(id='details-subtask-remove-pending', data=None),
        subtask_remove_modal,
        add_node_modal,

        # Goal sidebar (overlay from left)
        goal_sidebar,

        # Main content area
        html.Div([
            top_bar,
            empty_state,
            detail_content,
        ], style={"flex": "1", "display": "flex", "flexDirection": "column",
                  "overflow": "hidden"}),
    ], style={
        "display": "flex",
        "height": "100%",
        "width": "100%",
        "position": "relative",
    })


def _attribute_row(label, value_id):
    """Creates a compact attribute display row."""
    return html.Div([
        html.Span(f"{label}:", className="text-muted",
                  style={"width": "70px", "fontSize": "0.82rem"}),
        html.Span(id=value_id, style={"fontSize": "0.85rem", "fontWeight": "500"}),
    ], className="d-flex align-items-center mb-1")


def _build_goal_sidebar():
    """Builds the collapsible goal list sidebar for the Details tab."""
    return html.Div(
        id="details-goal-sidebar",
        children=[
            html.Div([
                html.H5("Goals", className="mb-0"),
                html.Span("×", id="btn-details-goals-close",
                           className="fs-4 text-white",
                           style={"cursor": "pointer"}),
            ], className="d-flex justify-content-between align-items-center mb-3 mt-3 px-3"),

            # Search bar
            dbc.Input(id="details-goal-search", type="text",
                      placeholder="Search goals...", size="sm",
                      debounce=True, className="mb-2 mx-3",
                      style={"backgroundColor": "#2b3035",
                             "border": "1px solid #495057",
                             "color": "#dee2e6"}),

            # Sort
            html.Div([
                dbc.Select(id="details-goal-sort", options=[
                    {"label": "A → Z", "value": "alpha-asc"},
                    {"label": "Z → A", "value": "alpha-desc"},
                    {"label": "Time ↑", "value": "time-asc"},
                    {"label": "Time ↓", "value": "time-desc"},
                ], value="alpha-asc", size="sm",
                    style={"flex": "1", "backgroundColor": "#2b3035",
                           "border": "1px solid #495057",
                           "color": "#dee2e6", "fontSize": "0.8rem"}),
            ], className="d-flex align-items-center mb-2 mx-3"),

            # Goal cards container
            html.Div(id="details-goal-list-container",
                     style={"overflowY": "auto", "flex": "1", "padding": "0 12px"}),
        ],
        style={
            "position": "absolute",
            "top": "0",
            "left": "-320px",
            "width": "320px",
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
    )


def _build_add_node_modal(ted):
    """Builds the Add Node modal, identical in structure to the goals tab version
    but with details-specific IDs."""
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Add Subtask Node")),
        dbc.ModalBody([
            dbc.RadioItems(
                id="details-add-mode",
                options=[
                    {"label": "Create New Node", "value": "create"},
                    {"label": "Link Existing Node", "value": "link"},
                ],
                value="create",
                inline=True,
                className="mb-3",
            ),

            # --- Link Existing mode ---
            html.Div(id="details-add-link-section", style={"display": "none"}, children=[
                dbc.Label("Select Node"),
                html.Div(dcc.Dropdown(
                    id="details-add-existing-dropdown",
                    placeholder="Search for a node...",
                    style={"backgroundColor": "#ffffff", "color": "#000000"},
                ), className="mb-2"),
                dbc.Label("Edge Type"),
                dbc.Select(
                    id="details-add-link-edge-type",
                    options=[
                        {"label": "Hard", "value": "hard"},
                        {"label": "Soft", "value": "soft"},
                    ],
                    value="hard",
                    className="mb-3",
                ),
            ]),

            # --- Create New mode ---
            html.Div(id="details-add-create-section", children=[
                dbc.Label("Name"),
                dbc.Input(id="details-add-name", type="text"),

                dbc.Label("Type", className="mt-2"),
                dbc.Select(id="details-add-type", options=[], value="Learn"),

                dbc.Label("Context", className="mt-2"),
                dbc.Select(id="details-add-context",
                           options=[{"label": "None", "value": ""}]),

                dbc.Label("Subcontext", className="mt-2"),
                dbc.Select(id="details-add-subcontext",
                           options=[{"label": "None", "value": ""}]),

                dbc.Label("Description", className="mt-2"),
                dbc.Textarea(id="details-add-desc"),

                dbc.Label("Value", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5, id="details-add-value"),

                dbc.Label("Interest", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5, id="details-add-interest"),

                dbc.Label("Effort", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5, id="details-add-difficulty"),

                html.Div([
                    dbc.Label("Time Estimates", className="mb-0"),
                    dbc.Select(id="details-add-time-unit", options=[
                        {"label": "Hours", "value": "hours"},
                        {"label": "Weeks", "value": "weeks"},
                        {"label": "Months", "value": "months"},
                    ], value=ted.get('unit', 'weeks'), size="sm",
                        style={"width": "100px", "marginLeft": "auto"})
                ], className="d-flex align-items-center mt-3 mb-1"),
                dbc.Row([
                    dbc.Col([dbc.Label("Optimistic", className="small text-muted mb-0"),
                             dbc.Input(id="details-add-time-o", type="number", min=0,
                                       value=ted.get('optimistic', 2))]),
                    dbc.Col([dbc.Label("Expected", className="small text-muted mb-0"),
                             dbc.Input(id="details-add-time-m", type="number", min=0,
                                       value=ted.get('expected', 4))]),
                    dbc.Col([dbc.Label("Pessimistic", className="small text-muted mb-0"),
                             dbc.Input(id="details-add-time-p", type="number", min=0,
                                       value=ted.get('pessimistic', 6))]),
                ]),
            ]),

            html.Div(id="details-add-save-status", className="text-danger mt-2",
                     style={"fontSize": "0.85rem", "minHeight": "1.2em"}),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-details-add-cancel",
                       color="secondary", className="me-2"),
            dbc.Button("Add", id="btn-details-add-save", color="primary"),
        ]),
    ], id="modal-details-add-node", size="lg", is_open=False, centered=True,
       scrollable=True)


def build_details_subtasks_table(subtask_nodes, graph_manager=None, edges=None,
                                  parent_name=None, include_soft=True,
                                  include_transitive=True):
    """Builds the subtasks table for any node's detail view.

    This is a generalized version of the goals subtasks table.

    Args:
        subtask_nodes: List of Node objects in the dependency subtree.
        graph_manager: GraphManager instance for looking up nodes.
        edges: List of all edge dicts.
        parent_name: The root node name, used to compute need types.
        include_soft: If False, only hard-need subtasks are shown.
        include_transitive: If False, only direct children are shown.
    """
    if not subtask_nodes:
        return html.Div(
            html.P("No subtasks found. Add prerequisite nodes to see them here.",
                   className="text-muted"),
            className="text-center py-3"
        )

    edges = edges or []

    # Determine need type for each subtask
    need_types = {}
    if parent_name and graph_manager:
        hard_subtree = graph_manager.get_goal_subtree(parent_name,
                                                       edge_types=(EDGE_NEEDS_HARD,))
        for node in subtask_nodes:
            need_types[node.name] = "Hard" if node.name in hard_subtree else "Soft"
    else:
        for node in subtask_nodes:
            need_types[node.name] = "Hard"

    # Filter to hard-only if requested
    if not include_soft:
        subtask_nodes = [n for n in subtask_nodes if need_types.get(n.name) == "Hard"]

    if not subtask_nodes:
        return html.Div(
            html.P("No hard-need subtasks for this node.", className="text-muted"),
            className="text-center py-3"
        )

    # Build set of nodes with a direct edge to the parent (removable)
    direct_children = set()
    if parent_name:
        from models import EDGE_NEEDS_SOFT
        for e in edges:
            if e['target'] == parent_name and e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
                direct_children.add(e['source'])

    # Filter to direct-only if requested
    if not include_transitive:
        subtask_nodes = [n for n in subtask_nodes if n.name in direct_children]

    if not subtask_nodes:
        return html.Div(
            html.P("No direct subtasks for this node.", className="text-muted"),
            className="text-center py-3"
        )

    rows = []
    for node in subtask_nodes:
        status_color = {"Done": "success", "Blocked": "danger",
                        "Open": "primary"}.get(node.status, "secondary")
        need = need_types.get(node.name, "Hard")
        need_color = "primary" if need == "Hard" else "info"

        is_direct = node.name in direct_children
        btn = dbc.Button(
            "×",
            id={"type": "details-subtask-remove", "index": node.name},
            color="danger",
            size="sm",
            disabled=not is_direct,
            style={
                "padding": "0 5px",
                "fontSize": "0.75rem",
                "lineHeight": "1.4",
                "opacity": "1" if is_direct else "0.25",
                "pointerEvents": "auto" if is_direct else "none",
            },
        )
        if is_direct:
            remove_btn = btn
        else:
            remove_btn = html.Span(
                btn,
                title="Transitive dependency — remove from its parent instead",
                style={"cursor": "not-allowed", "display": "inline-block"},
            )

        rows.append(html.Tr([
            html.Td(
                html.Span(node.name, style={"cursor": "pointer"}),
                id={"type": "details-subtask-name", "index": node.name},
                style={"verticalAlign": "middle"},
            ),
            html.Td(dbc.Badge(node.status, color=status_color,
                              style={"fontSize": "0.7rem"}),
                    style={"verticalAlign": "middle"}),
            html.Td(dbc.Badge(need, color=need_color,
                              style={"fontSize": "0.7rem"}),
                    style={"verticalAlign": "middle"}),
            html.Td(node.type, style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.context) if node.context else "—",
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.value),
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.interest),
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.difficulty),
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(ConfigManager.format_time_friendly(node.time)
                    if node.time and node.time > 0 else "—",
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(remove_btn, style={"verticalAlign": "middle"}),
        ]))

    return dbc.Table([
        html.Thead(html.Tr([
            html.Th("Name"),
            html.Th("Status"),
            html.Th("Need"),
            html.Th("Type"),
            html.Th("Context"),
            html.Th("Value"),
            html.Th("Interest"),
            html.Th("Effort"),
            html.Th("Time"),
            html.Th(""),
        ])),
        html.Tbody(rows),
    ], bordered=False, hover=True, responsive=True, size="sm",
       className="text-light", style={"fontSize": "0.85rem"})
