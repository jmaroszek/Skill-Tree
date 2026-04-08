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
    """Builds the Details tab UI."""

    _ted = ConfigManager.get_time_estimate_defaults()

    # --- Top Bar: node selector + nav + action buttons ---
    top_bar = html.Div([
        dbc.Button("☰ Goals", id="btn-details-goals-toggle", color="secondary",
                   size="sm", className="me-2", style={"whiteSpace": "nowrap"}),
        html.Div(dcc.Dropdown(
            id="details-node-select",
            placeholder="Select a node to view details...",
            clearable=True,
            style={"minWidth": "200px"},
        ), className="text-dark", style={"flex": "0 1 320px"}),
        # Back / Forward navigation — right of dropdown
        dbc.Button("←", id="btn-details-nav-back", color="secondary",
                   size="sm", className="ms-1", disabled=True,
                   style={"whiteSpace": "nowrap", "minWidth": "32px"}),
        dbc.Button("→", id="btn-details-nav-forward", color="secondary",
                   size="sm", className="ms-1", disabled=True,
                   style={"whiteSpace": "nowrap", "minWidth": "32px"}),
        html.Div(style={"flex": "1"}),  # Spacer
        dbc.Button("Filters", id="btn-details-filters-toggle", color="secondary",
                   size="sm", className="ms-2", style={"whiteSpace": "nowrap"}),
        dbc.Button("Simulate", id="btn-details-simulate", color="info",
                   size="sm", className="ms-2", style={"whiteSpace": "nowrap"}),
    ], className="d-flex align-items-center py-2 px-3",
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
        # Badges row: type, status, and priority badge all inline
        html.Div(id="details-node-badges", className="d-flex gap-1 flex-wrap mb-2"),

        # Description — taller default
        html.Div(id="details-node-description",
                 className="text-muted mb-2",
                 style={"fontSize": "0.9rem", "whiteSpace": "pre-wrap",
                        "maxHeight": "160px", "overflowY": "auto",
                        "minHeight": "40px"}),

        # Progress bar (above stats, below description)
        html.Div(id="details-progress-section", style={"display": "none"}, children=[
            dbc.Progress(id="details-progress-bar", value=0,
                         className="mb-1", style={"height": "14px"}),
            html.Small(id="details-progress-text", className="text-muted",
                       style={"fontSize": "0.78rem"}),
        ]),

        # Stats grid
        html.Div([
            _attribute_row("Type", "details-attr-type"),
            _attribute_row("Status", "details-attr-status"),
            _attribute_row("Context", "details-attr-context"),
            _attribute_row("Time", "details-attr-time"),
            _attribute_row("Value", "details-attr-value"),
            _attribute_row("Interest", "details-attr-interest"),
            _attribute_row("Effort", "details-attr-effort"),
        ], className="mt-2"),

        # Hidden container for priority data (badge is merged into badges row)
        html.Div(id="details-priority-section", style={"display": "none"}, children=[
            html.Div(id="details-priority-badge"),
        ]),

        # Action buttons — Edit Node first, then Focus on Canvas
        html.Div([
            dbc.Button("Edit Node", id="btn-details-edit", color="secondary",
                       size="sm", className="mt-3 w-100"),
            dbc.Button("Focus on Canvas", id="btn-details-focus", color="info",
                       size="sm", className="mt-1 w-100"),
        ]),

    ], id="details-node-summary",
       style={"minWidth": "240px", "maxWidth": "280px", "paddingRight": "16px",
              "overflowY": "auto"})

    # --- Vertical drag handle between node summary and dep graph ---
    v_drag_handle_upper = html.Div(
        id="details-v-drag-upper",
        style={
            "width": "6px",
            "cursor": "col-resize",
            "backgroundColor": "transparent",
            "borderLeft": "1px solid #495057",
            "flexShrink": "0",
            "transition": "background-color 0.15s",
        },
    )

    # --- Dependency Graph (right column of upper section) ---
    dep_graph = html.Div([
        # Graph container with relative positioning for fullscreen button overlay
        html.Div([
            cyto.Cytoscape(
                id='details-mini-graph',
                elements=[],
                layout={'name': 'cose', 'animate': False, 'fit': True, 'padding': 20},
                style={'width': '100%', 'height': '100%', 'backgroundColor': '#1a1d21',
                       'borderRadius': '8px'},
                stylesheet=stylesheet,
                userZoomingEnabled=False,
                userPanningEnabled=False,
                boxSelectionEnabled=False,
                autoungrabify=False,
            ),
            dbc.Button("⛶", id="btn-details-graph-fullscreen",
                       color="secondary", size="sm",
                       className="btn-fullscreen-toggle",
                       title="Toggle fullscreen",
                       style={"position": "absolute", "bottom": "12px",
                              "right": "12px", "zIndex": "10",
                              "fontSize": "1.15rem", "lineHeight": "1",
                              "padding": "4px 9px", "opacity": "0.55"}),
        ], style={"position": "relative", "flex": "1", "minHeight": "200px"}),
    ], id="details-dep-graph-container", style={
        "flex": "1",
        "minWidth": "300px",
        "paddingLeft": "12px",
        "display": "flex",
        "flexDirection": "column",
    })

    # Upper section: attributes + graph — proportionally taller than lower
    upper_section = html.Div([
        node_summary,
        v_drag_handle_upper,
        dep_graph,
    ], id="details-upper-section",
       style={"display": "flex", "padding": "16px 0", "flex": "1.6", "minHeight": "0"})

    # --- Horizontal drag handle between upper and lower sections ---
    h_drag_handle = html.Div(
        id="details-h-drag",
        style={
            "height": "6px",
            "cursor": "ns-resize",
            "backgroundColor": "transparent",
            "borderTop": "1px solid #495057",
            "flexShrink": "0",
            "transition": "background-color 0.15s",
        },
    )

    # --- Subtasks Table (left of lower section) ---
    subtasks_section = html.Div([
        html.Div([
            html.Div([
                html.H5("Subtasks", className="mb-0"),
                dbc.Button("+", id="btn-details-add-node", color="link",
                           className="p-0 ms-2 text-decoration-none text-muted",
                           title="Add subtask node",
                           style={"fontSize": "1.2rem", "lineHeight": "1"}),
            ], className="d-flex align-items-center"),
            html.Div([
                dbc.Checklist(
                    id="details-include-soft-needs",
                    options=[{"label": "Soft Needs", "value": "include"}],
                    value=["include"],
                    switch=True,
                    style={"fontSize": "0.82rem"},
                ),
                dbc.Checklist(
                    id="details-include-transitive",
                    options=[{"label": "Transitive", "value": "include"}],
                    value=["include"],
                    switch=True,
                    style={"fontSize": "0.82rem"},
                ),
                dbc.Checklist(
                    id="details-include-synergies",
                    options=[{"label": "Synergies", "value": "include"}],
                    value=["include"],
                    switch=True,
                    style={"fontSize": "0.82rem", "marginRight": "12px"},
                ),
            ], className="d-flex gap-3"),
        ], className="d-flex align-items-center justify-content-between mb-2"),
        html.Div(id="details-subtasks-table-container",
                 style={"overflowY": "visible", "flex": "none"}),
    ], id="details-subtasks-section",
       style={"flex": "1", "minWidth": "300px", "display": "flex",
              "flexDirection": "column", "paddingRight": "8px",
              "overflowY": "auto"})

    # --- Vertical drag handle between subtasks and simulation ---
    v_drag_handle_lower = html.Div(
        id="details-v-drag-lower",
        style={
            "width": "6px",
            "cursor": "col-resize",
            "backgroundColor": "transparent",
            "borderLeft": "1px solid #495057",
            "flexShrink": "0",
            "transition": "background-color 0.15s",
        },
    )

    # --- Simulation Section (right of lower section) ---
    sim_section = html.Div([
        html.Div(id="details-sim-empty", children=[
            html.Div([
                html.P("Click 'Simulate' to see the time distribution.",
                       className="text-muted text-center",
                       style={"marginTop": "40px"}),
            ]),
        ]),
        html.Div(id="details-sim-results", style={"display": "none"}, children=[
            dcc.Graph(
                id="details-sim-chart",
                config={"displayModeBar": False},
                style={"height": "350px"},
            ),
        ]),
    ], id="details-sim-section",
       style={"width": "42%", "minWidth": "250px", "paddingLeft": "12px",
              "display": "flex", "flexDirection": "column"})

    # Lower section: subtasks + simulation — taller so x-axis label is visible
    lower_section = html.Div([
        subtasks_section,
        v_drag_handle_lower,
        sim_section,
    ], id="details-lower-section",
       style={"display": "flex", "paddingTop": "8px", "flex": "1", "minHeight": "0"})

    # --- Detail content (hidden when no node selected) ---
    detail_content = html.Div(
        id="details-content",
        style={"display": "none", "flexDirection": "column", "flex": "1",
               "padding": "0 24px", "overflowY": "auto"},
        children=[upper_section, h_drag_handle, lower_section],
    )

    # --- Filters Sidebar (right overlay) ---
    filters_sidebar = _build_filters_sidebar()

    # --- Add Node Modal ---
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
        dcc.Store(id='details-goal-order-store', data=None),
        # Navigation history for back/forward
        dcc.Store(id='details-nav-history', data=[]),
        dcc.Store(id='details-nav-index', data=-1),
        # Hidden input for SortableJS drag-and-drop reordering
        dcc.Input(id='details-goal-drag-order-input', type='text', value='',
                  style={'display': 'none'}),
        # Hidden input for simulate trigger from context menu
        dcc.Input(id='details-simulate-trigger-input', type='text', value='',
                  style={'display': 'none'}),
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

        # Filters sidebar (overlay from right)
        filters_sidebar,
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

            # Search bar — constrained inside sidebar
            html.Div(
                dbc.Input(id="details-goal-search", type="text",
                          placeholder="Search goals...", size="sm",
                          debounce=True,
                          style={"backgroundColor": "#2b3035",
                                 "border": "1px solid #495057",
                                 "color": "#dee2e6",
                                 "width": "100%",
                                 "boxSizing": "border-box"}),
                style={"padding": "0 12px", "marginBottom": "8px"},
            ),

            # Sort
            html.Div(
                dbc.Select(id="details-goal-sort", options=[
                    {"label": "A → Z", "value": "alpha-asc"},
                    {"label": "Z → A", "value": "alpha-desc"},
                    {"label": "Time ↑", "value": "time-asc"},
                    {"label": "Time ↓", "value": "time-desc"},
                    {"label": "Manual", "value": "manual"},
                ], value="alpha-asc", size="sm",
                    style={"flex": "1", "backgroundColor": "#2b3035",
                           "border": "1px solid #495057",
                           "color": "#dee2e6", "fontSize": "0.8rem"}),
                style={"padding": "0 12px", "marginBottom": "8px"},
            ),

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


def _build_filters_sidebar():
    """Builds the filters sidebar for the Details tab dependency graph."""
    return html.Div(
        id="details-filters-sidebar",
        children=[
            html.Div([
                html.H5("Graph Filters", className="mb-0"),
                html.Span("×", id="btn-details-filters-close",
                           className="fs-4 text-white",
                           style={"cursor": "pointer"}),
            ], className="d-flex justify-content-between align-items-center mb-3 mt-3 px-3"),

            html.Div([
                dbc.Label("Node Types", className="text-muted small mb-1"),
                dbc.Checklist(
                    id="details-filter-types",
                    options=[
                        {"label": "Learn", "value": "Learn"},
                        {"label": "Goal", "value": "Goal"},
                        {"label": "Action", "value": "Action"},
                        {"label": "Resource", "value": "Resource"},
                    ],
                    value=["Learn", "Goal", "Action", "Resource"],
                    className="mb-3",
                    style={"fontSize": "0.85rem"},
                ),

                dbc.Label("Status", className="text-muted small mb-1"),
                dbc.Checklist(
                    id="details-filter-status",
                    options=[
                        {"label": "Open", "value": "Open"},
                        {"label": "Blocked", "value": "Blocked"},
                        {"label": "Done", "value": "Done"},
                    ],
                    value=["Open", "Blocked", "Done"],
                    className="mb-3",
                    style={"fontSize": "0.85rem"},
                ),

                dbc.Button("Reset Filters", id="btn-details-filters-reset",
                           color="secondary", size="sm", className="w-100 mt-2"),
            ], style={"padding": "0 16px"}),
        ],
        style={
            "position": "absolute",
            "top": "0",
            "right": "-280px",
            "width": "280px",
            "height": "100%",
            "zIndex": 100,
            "overflowX": "hidden",
            "overflowY": "auto",
            "borderLeft": "1px solid #495057",
            "transition": "right 0.3s ease",
            "backgroundColor": "#212529",
            "display": "flex",
            "flexDirection": "column",
        }
    )


def _build_add_node_modal(ted):
    """Builds the Add Node modal — mirrors the Goals tab modal with
    Relationships and External Resources sections."""
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

                # --- Relationships section (mirrors goals tab) ---
                html.Hr(className="my-2"),
                html.H6("Relationships", className="mt-2 mb-1"),
                dbc.Label("Needs"),
                html.Div([
                    dcc.Dropdown(id="details-add-needs-hard", multi=True,
                                 placeholder="Hard..."),
                    dcc.Dropdown(id="details-add-needs-soft", multi=True,
                                 placeholder="Soft...", className="mt-1"),
                ], className="text-dark"),

                dbc.Label("Supports", className="mt-2"),
                html.Div([
                    dcc.Dropdown(id="details-add-supports-hard", multi=True,
                                 placeholder="Hard..."),
                    dcc.Dropdown(id="details-add-supports-soft", multi=True,
                                 placeholder="Soft...", className="mt-1"),
                ], className="text-dark"),

                dbc.Label("Helps", className="mt-2"),
                html.Div(dcc.Dropdown(id="details-add-helps", multi=True,
                                       placeholder="Synergistic Nodes..."),
                         className="text-dark"),

                # --- External Resources section (mirrors goals tab) ---
                html.Hr(className="my-2"),
                html.H6("External Resources", className="mt-2 mb-1"),
                dcc.Store(id='details-add-obsidian-store', data=['']),
                dcc.Store(id='details-add-drive-store', data=['']),
                dcc.Store(id='details-add-website-store', data=['']),

                html.Div([
                    dbc.Label("Obsidian", className="mb-0"),
                    dbc.Button("+", id="btn-details-add-obsidian-add", color="link",
                               className="p-0 ms-2 text-decoration-none text-muted",
                               title="Add Obsidian link",
                               style={"fontSize": "1.2rem", "lineHeight": "1"}),
                ], className="d-flex align-items-center mt-2 mb-1"),
                html.Div(id='details-add-obsidian-container'),

                html.Div([
                    dbc.Label("Google Drive", className="mb-0"),
                    dbc.Button("+", id="btn-details-add-drive-add", color="link",
                               className="p-0 ms-2 text-decoration-none text-muted",
                               title="Add Google Drive link",
                               style={"fontSize": "1.2rem", "lineHeight": "1"}),
                ], className="d-flex align-items-center mt-3 mb-1"),
                html.Div(id='details-add-drive-container'),

                html.Div([
                    dbc.Label("Website", className="mb-0"),
                    dbc.Button("+", id="btn-details-add-website-add", color="link",
                               className="p-0 ms-2 text-decoration-none text-muted",
                               title="Add Website link",
                               style={"fontSize": "1.2rem", "lineHeight": "1"}),
                ], className="d-flex align-items-center mt-3 mb-1"),
                html.Div(id='details-add-website-container'),
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
                                  include_transitive=True,
                                  include_synergies=False):
    """Builds the subtasks table for any node's detail view.

    Args:
        subtask_nodes: List of Node objects in the dependency subtree.
        graph_manager: GraphManager instance for looking up nodes.
        edges: List of all edge dicts.
        parent_name: The root node name, used to compute need types.
        include_soft: If False, only hard-need subtasks are shown.
        include_transitive: If False, only direct children are shown.
        include_synergies: If True, Helps-linked nodes get a "Synergy" relationship label.
    """
    if not subtask_nodes:
        return html.Div(
            html.P("No subtasks found. Add prerequisite nodes to see them here.",
                   className="text-muted"),
            className="text-center py-3"
        )

    edges = edges or []

    # Determine relationship type for each subtask
    relationship_types = {}
    if parent_name and graph_manager:
        from models import EDGE_NEEDS_SOFT, EDGE_HELPS
        hard_subtree = graph_manager.get_goal_subtree(parent_name,
                                                       edge_types=(EDGE_NEEDS_HARD,))
        # Determine synergy nodes (those reachable only via Helps edges)
        synergy_nodes = set()
        if include_synergies:
            helps_subtree = graph_manager.get_goal_subtree(
                parent_name, edge_types=(EDGE_HELPS,))
            soft_subtree = graph_manager.get_goal_subtree(
                parent_name, edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT))
            synergy_nodes = helps_subtree - soft_subtree - hard_subtree

        for node in subtask_nodes:
            if node.name in synergy_nodes:
                relationship_types[node.name] = "Synergy"
            elif node.name in hard_subtree:
                relationship_types[node.name] = "Hard"
            else:
                relationship_types[node.name] = "Soft"
    else:
        for node in subtask_nodes:
            relationship_types[node.name] = "Hard"

    # Filter to hard-only if requested
    if not include_soft:
        subtask_nodes = [n for n in subtask_nodes
                         if relationship_types.get(n.name) in ("Hard", "Synergy")]

    if not subtask_nodes:
        return html.Div(
            html.P("No hard-need subtasks for this node.", className="text-muted"),
            className="text-center py-3"
        )

    # Build set of nodes with a direct edge to the parent (removable)
    direct_children = set()
    if parent_name:
        from models import EDGE_NEEDS_SOFT, EDGE_HELPS
        for e in edges:
            if e['target'] == parent_name and e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
                direct_children.add(e['source'])
            # Also include Helps partners as direct (bidirectional)
            if e['type'] == EDGE_HELPS:
                if e['target'] == parent_name:
                    direct_children.add(e['source'])
                elif e['source'] == parent_name:
                    direct_children.add(e['target'])

    # Filter to direct-only if requested
    if not include_transitive:
        subtask_nodes = [n for n in subtask_nodes if n.name in direct_children]

    if not subtask_nodes:
        return html.Div(
            html.P("No direct subtasks for this node.", className="text-muted"),
            className="text-center py-3"
        )

    # Muted, desaturated blue palette for relationship badges:
    #   Hard    = deep steel blue
    #   Soft    = dusty slate blue
    #   Synergy = pale ice blue
    _REL_BADGE_STYLES = {
        "Hard": {"backgroundColor": "#3a5f8c", "color": "#d6e4f0"},
        "Soft": {"backgroundColor": "#5a6f80", "color": "#d0dae3"},
        "Synergy": {"backgroundColor": "#6e8fa8", "color": "#e8f0f6"},
    }

    rows = []
    for node in subtask_nodes:
        status_color = {"Done": "success", "Blocked": "danger",
                        "Open": "primary"}.get(node.status, "secondary")
        rel = relationship_types.get(node.name, "Hard")
        rel_style = _REL_BADGE_STYLES.get(rel, _REL_BADGE_STYLES["Hard"])

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
            html.Td(html.Span(rel, className="badge",
                              style={**rel_style, "fontSize": "0.7rem",
                                     "padding": "4px 8px", "borderRadius": "4px"}),
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
            html.Th("Relationship"),
            html.Th("Type"),
            html.Th("Context"),
            html.Th("Val"),
            html.Th("Int"),
            html.Th("Eff"),
            html.Th("Time"),
            html.Th(""),
        ])),
        html.Tbody(rows),
    ], bordered=False, hover=True, responsive=True, size="sm",
       className="text-light", style={"fontSize": "0.82rem"})
