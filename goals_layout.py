"""
Layout definitions for the Goals tab.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc
from typing import Optional, List, Any
import dash_cytoscape as cyto
from config import ConfigManager, DEFAULT_TIME_ESTIMATE_DEFAULTS
from models import EDGE_NEEDS_HARD
from styles import stylesheet


def build_goals_tab_content():
    """Builds the Goals tab UI with a two-panel layout."""
    _ted = ConfigManager.get_time_estimate_defaults()

    # --- Left Panel: Goal List ---
    goal_list_panel = html.Div([
        html.Div([
            html.H4("Goals", className="mb-0"),
            dbc.Button("New Goal", id="btn-new-goal", color="success", size="sm"),
        ], className="d-flex justify-content-between align-items-center mb-3 mt-3"),

        # Search bar
        dbc.Input(id="goal-search-input", type="text", placeholder="Search goals...",
                  size="sm", debounce=True, className="mb-2",
                  style={"backgroundColor": "#2b3035", "border": "1px solid #495057",
                         "color": "#dee2e6"}),

        # Sort + Filters on one row
        html.Div([
            dbc.Select(id="goal-sort-mode", options=[
                {"label": "Manual", "value": "manual"},
                {"label": "A \u2192 Z", "value": "alpha-asc"},
                {"label": "Z \u2192 A", "value": "alpha-desc"},
                {"label": "Time \u2191", "value": "time-asc"},
                {"label": "Time \u2193", "value": "time-desc"},
            ], value="manual", size="sm",
                style={"flex": "1", "backgroundColor": "#2b3035", "border": "1px solid #495057",
                       "color": "#dee2e6", "fontSize": "0.8rem"}),
            dbc.Button("Filters", id="btn-goal-filters-toggle", color="secondary", size="sm",
                       className="ms-2"),
        ], className="d-flex align-items-center mb-2"),

        # Collapsible filters panel
        dbc.Collapse(id="goal-filters-collapse", is_open=False, children=[
            html.Div([
                dbc.Label("Context", className="mb-1", style={"fontSize": "0.8rem"}),
                dbc.Select(id="goal-filter-context", options=[{"label": "All", "value": "All"}],
                           value="All", size="sm", className="mb-2"),
                dbc.Label("Subcontext", className="mb-1", style={"fontSize": "0.8rem"}),
                dbc.Select(id="goal-filter-subcontext", options=[{"label": "All", "value": "All"}],
                           value="All", size="sm", className="mb-2"),
                dbc.Label("Min Value", className="mb-0", style={"fontSize": "0.8rem"}),
                dcc.Slider(id="goal-filter-value", min=1, max=10, step=1, value=1,
                           marks=None, tooltip={"placement": "bottom", "always_visible": False}),
                dbc.Label("Min Interest", className="mb-0", style={"fontSize": "0.8rem"}),
                dcc.Slider(id="goal-filter-interest", min=1, max=10, step=1, value=1,
                           marks=None, tooltip={"placement": "bottom", "always_visible": False}),
                dbc.Label("Max Difficulty", className="mb-0", style={"fontSize": "0.8rem"}),
                dcc.Slider(id="goal-filter-difficulty", min=1, max=10, step=1, value=10,
                           marks=None, tooltip={"placement": "bottom", "always_visible": False}),
            ], style={"padding": "8px 4px", "borderBottom": "1px solid #495057", "marginBottom": "8px"}),
        ]),

        html.Div(id="goals-list-container", style={"overflowY": "auto", "flex": "1"}),
    ], style={
        "width": "350px",
        "minWidth": "350px",
        "borderRight": "1px solid #495057",
        "display": "flex",
        "flexDirection": "column",
        "padding": "0 16px",
        "backgroundColor": "#212529",
    })

    # --- Right Panel: Goal Detail ---

    # Right column: full-height dependency graph
    graph_column = html.Div([
        html.Div([
            html.H5("Dependency Graph", className="mb-0",
                     style={"lineHeight": "1.2"}),
            dbc.Button("Focus", id="btn-goal-focus", color="info", size="sm",
                       className="ms-2"),
            dbc.Tooltip("Focus this goal's subtree on the Nodes tab canvas",
                        target="btn-goal-focus", placement="bottom"),
        ], className="d-flex align-items-center mt-3 mb-2"),
        cyto.Cytoscape(
            id='goal-mini-graph',
            elements=[],
            layout={'name': 'cose', 'animate': False, 'fit': True, 'padding': 20},
            style={'width': '100%', 'flex': '1', 'backgroundColor': '#1a1d21',
                   'borderRadius': '8px', 'minHeight': '300px', 'marginBottom': '12px'},
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
        "marginLeft": "16px",
        "display": "flex",
        "flexDirection": "column",
    })

    # Add Node modal
    add_node_modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Add Node to Goal")),
        dbc.ModalBody([
            dbc.RadioItems(
                id="goal-add-mode",
                options=[
                    {"label": "Create New Node", "value": "create"},
                    {"label": "Link Existing Node", "value": "link"},
                ],
                value="create",
                inline=True,
                className="mb-3",
            ),

            # --- Link Existing mode ---
            html.Div(id="goal-add-link-section", style={"display": "none"}, children=[
                dbc.Label("Select Node"),
                html.Div(dcc.Dropdown(
                    id="goal-add-existing-dropdown",
                    placeholder="Search for a node...",
                    style={"backgroundColor": "#ffffff", "color": "#000000"},
                ), className="mb-2"),
                dbc.Label("Edge Type"),
                dbc.Select(
                    id="goal-add-link-edge-type",
                    options=[
                        {"label": "Hard", "value": "hard"},
                        {"label": "Soft", "value": "soft"},
                    ],
                    value="hard",
                    className="mb-3",
                ),
            ]),

            # --- Create New mode ---
            html.Div(id="goal-add-create-section", children=[
                dbc.Label("Name"),
                dbc.Input(id="goal-add-name", type="text"),

                dbc.Label("Type", className="mt-2"),
                dbc.Select(id="goal-add-type", options=[], value="Learn"),

                dbc.Label("Context", className="mt-2"),
                dbc.Select(id="goal-add-context", options=[{"label": "None", "value": ""}]),

                dbc.Label("Subcontext", className="mt-2"),
                dbc.Select(id="goal-add-subcontext", options=[{"label": "None", "value": ""}]),

                dbc.Label("Description", className="mt-2"),
                dbc.Textarea(id="goal-add-desc"),

                dbc.Label("Value", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5, id="goal-add-value"),

                dbc.Label("Interest", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5, id="goal-add-interest"),

                dbc.Label("Effort", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5, id="goal-add-difficulty"),

                html.Div([
                    dbc.Label("Time Estimates", className="mb-0"),
                    dbc.Select(id="goal-node-time-unit", options=[
                        {"label": "Hours", "value": "hours"},
                        {"label": "Weeks", "value": "weeks"},
                        {"label": "Months", "value": "months"},
                    ], value=_ted.get('unit', 'weeks'), size="sm", style={"width": "100px", "marginLeft": "auto"})
                ], className="d-flex align-items-center mt-3 mb-1"),
                dbc.Row([
                    dbc.Col([dbc.Label("Optimistic", className="small text-muted mb-0"),
                             dbc.Input(id="goal-add-time-o", type="number", min=0, value=_ted.get('optimistic', 2))]),
                    dbc.Col([dbc.Label("Expected", className="small text-muted mb-0"),
                             dbc.Input(id="goal-add-time-m", type="number", min=0, value=_ted.get('expected', 4))]),
                    dbc.Col([dbc.Label("Pessimistic", className="small text-muted mb-0"),
                             dbc.Input(id="goal-add-time-p", type="number", min=0, value=_ted.get('pessimistic', 6))]),
                ]),

                html.Hr(className="my-2"),
                html.H6("Relationships", className="mt-2 mb-1"),
                dbc.Label("Needs"),
                html.Div([
                    dcc.Dropdown(id="goal-add-needs-hard", multi=True, placeholder="Hard..."),
                    dcc.Dropdown(id="goal-add-needs-soft", multi=True, placeholder="Soft...", className="mt-1"),
                ], className="text-dark"),

                dbc.Label("Supports", className="mt-2"),
                html.Div([
                    dcc.Dropdown(id="goal-add-supports-hard", multi=True, placeholder="Hard..."),
                    dcc.Dropdown(id="goal-add-supports-soft", multi=True, placeholder="Soft...", className="mt-1"),
                ], className="text-dark"),

                dbc.Label("Helps", className="mt-2"),
                html.Div(dcc.Dropdown(id="goal-add-helps", multi=True, placeholder="Synergistic Nodes..."), className="text-dark"),

                dcc.Store(id='goal-add-edge-resources', data=[]),

                html.Hr(className="my-2"),
                html.H6("External Resources", className="mt-2 mb-1"),
                dcc.Store(id='goal-add-obsidian-store', data=['']),
                dcc.Store(id='goal-add-drive-store', data=['']),
                dcc.Store(id='goal-add-website-store', data=['']),

                html.Div([
                    dbc.Label("Obsidian", className="mb-0"),
                    dbc.Button("+", id="btn-goal-add-obsidian-add", color="link",
                               className="p-0 ms-2 text-decoration-none text-muted",
                               title="Add Obsidian link", style={"fontSize": "1.2rem", "lineHeight": "1"}),
                ], className="d-flex align-items-center mt-2 mb-1"),
                html.Div(id='goal-add-obsidian-container'),

                html.Div([
                    dbc.Label("Google Drive", className="mb-0"),
                    dbc.Button("+", id="btn-goal-add-drive-add", color="link",
                               className="p-0 ms-2 text-decoration-none text-muted",
                               title="Add Google Drive link", style={"fontSize": "1.2rem", "lineHeight": "1"}),
                ], className="d-flex align-items-center mt-3 mb-1"),
                html.Div(id='goal-add-drive-container'),

                html.Div([
                    dbc.Label("Website", className="mb-0"),
                    dbc.Button("+", id="btn-goal-add-website-add", color="link",
                               className="p-0 ms-2 text-decoration-none text-muted",
                               title="Add Website link", style={"fontSize": "1.2rem", "lineHeight": "1"}),
                ], className="d-flex align-items-center mt-3 mb-1"),
                html.Div(id='goal-add-website-container'),
            ]),


            html.Div(id="goal-add-save-status", className="text-danger mt-2",
                     style={"fontSize": "0.85rem", "minHeight": "1.2em"}),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-goal-add-cancel", color="secondary", className="me-2"),
            dbc.Button("Add", id="btn-goal-add-save", color="primary"),
        ]),
    ], id="modal-goal-add-node", size="lg", is_open=False, centered=True,
       scrollable=True)

    goal_detail_panel = html.Div([
        # Shown when no goal is selected
        html.Div(
            id="goal-detail-empty",
            children=[
                html.Div([
                    html.H5("No Goal Selected", className="text-muted mb-2"),
                    html.P("Select a goal from the list or create a new one.", className="text-muted"),
                ], style={"textAlign": "center", "marginTop": "20vh"})
            ],
        ),

        # Goal editor (hidden when no goal selected)
        html.Div(id="goal-detail-content", style={"display": "none", "flexDirection": "column", "height": "100%"}, children=[
            # Two-column layout: left (editor+subtasks) + right (graph)
            html.Div([
                # Left column: editor form + subtasks
                html.Div([
                    # --- Toolbar: Name only ---
                    html.Div([
                        dbc.Input(id="goal-name", type="text", placeholder="Goal Name",
                                  style={"fontSize": "1.4rem", "fontWeight": "300", "backgroundColor": "transparent",
                                         "border": "none", "borderBottom": "1px solid #495057", "color": "#dee2e6",
                                         "borderRadius": "0", "paddingLeft": "0"}),
                    ], className="mb-2 mt-3"),

                    # Save status feedback
                    html.Div(id="goal-save-status", className="text-success mb-3",
                             style={"fontSize": "0.85rem", "minHeight": "1.2em"}),

                    # --- Two-Column Body ---
                    dbc.Row([
                        # Left column: description, sliders, done toggle
                        dbc.Col([
                            dbc.Label("Description", className="mb-1"),
                            dbc.Textarea(id="goal-description", rows=2,
                                         style={"height": "80px", "resize": "vertical"}),

                            dbc.Label("Value", className="mt-3 mb-0"),
                            dcc.Slider(min=1, max=10, step=1, value=5, id="goal-value"),

                            dbc.Label("Interest", className="mt-2 mb-0"),
                            dcc.Slider(min=1, max=10, step=1, value=5, id="goal-interest"),

                            dbc.Label("Difficulty", className="mt-2 mb-0"),
                            dcc.Slider(min=1, max=10, step=1, value=5, id="goal-difficulty"),

                            dbc.Checklist(
                                id="goal-done-toggle",
                                options=[{"label": "Done", "value": "done"}],
                                value=[],
                                switch=True,
                                className="mt-3",
                            ),
                        ], width=7),

                        # Right column: priority rank, context, subcontext, progress, save/delete
                        dbc.Col([
                            html.H6("Priority Rank", className="mb-2"),
                            dbc.Select(
                                id="goal-priority-rank",
                                options=[
                                    {"label": "\u2014", "value": "none"},
                                    {"label": "#1 Priority", "value": "1"},
                                    {"label": "#2 Priority", "value": "2"},
                                    {"label": "#3 Priority", "value": "3"},
                                ],
                                value="none",
                                className="mb-1",
                            ),
                            html.Small("Higher rank = stronger score boost", className="text-muted d-block mb-3",
                                       style={"fontSize": "0.75rem"}),

                            dbc.Label("Context", className="mb-1"),
                            dbc.Select(id="goal-context", options=[], className="mb-2"),

                            dbc.Label("Subcontext", className="mb-1"),
                            dbc.Select(id="goal-subcontext", options=[], className="mb-3"),

                            html.Div(id="goal-stats-section", children=[
                                html.H6("Progress", className="mb-2"),
                                dbc.Progress(id="goal-progress-bar", value=0,
                                             className="mb-2", style={"height": "20px"}),
                                html.Div(id="goal-stats-text", className="text-muted mb-3",
                                         style={"fontSize": "0.85rem"}),
                            ]),

                            html.Div([
                                dbc.Button("Delete", id="btn-goal-delete", color="danger", size="sm",
                                           className="me-2",
                                           style={"backgroundColor": ConfigManager.get_danger_color(),
                                                  "borderColor": ConfigManager.get_danger_color()}),
                                dbc.Button("Save", id="btn-goal-save", color="primary", size="sm"),
                            ], className="d-flex justify-content-end mt-2"),
                        ], width=5),
                    ]),

                    html.Hr(className="my-2"),

                    # --- Relationships + External Resources Side by Side ---
                    dcc.Store(id='goal-obsidian-links-store', data=['']),
                    dcc.Store(id='goal-drive-links-store', data=['']),
                    dcc.Store(id='goal-website-links-store', data=['']),

                    html.Div([
                        # Left: Relationships
                        html.Div([
                            html.H5("Relationships", className="mt-2 mb-1"),
                            dbc.Label("Needs", className="mt-2"),
                            html.Div([
                                dcc.Dropdown(id="goal-edge-needs-hard", multi=True, placeholder="Hard..."),
                                dcc.Dropdown(id="goal-edge-needs-soft", multi=True, placeholder="Soft...", className="mt-1"),
                            ], className="text-dark"),

                            dbc.Label("Supports", className="mt-2"),
                            html.Div([
                                dcc.Dropdown(id="goal-edge-supports-hard", multi=True, placeholder="Hard..."),
                                dcc.Dropdown(id="goal-edge-supports-soft", multi=True, placeholder="Soft...", className="mt-1"),
                            ], className="text-dark"),

                            dbc.Label("Helps", className="mt-2"),
                            html.Div(dcc.Dropdown(id="goal-edge-helps", multi=True, placeholder="Synergies..."), className="text-dark"),
                        ], style={"flex": "1", "minWidth": "0", "paddingRight": "16px"}),

                        # Right: External Resources
                        html.Div([
                            html.H5("External Resources", className="mt-2 mb-1"),

                            html.Div([
                                dbc.Label("Obsidian", className="mb-0"),
                                dbc.Button("+", id="btn-goal-obsidian-add", color="link",
                                           className="p-0 ms-2 text-decoration-none text-muted",
                                           title="Add Obsidian link", style={"fontSize": "1.2rem", "lineHeight": "1"}),
                            ], className="d-flex align-items-center mt-2 mb-1"),
                            html.Div(id='goal-obsidian-links-container'),

                            html.Div([
                                dbc.Label("Google Drive", className="mb-0"),
                                dbc.Button("+", id="btn-goal-drive-add", color="link",
                                           className="p-0 ms-2 text-decoration-none text-muted",
                                           title="Add Google Drive link", style={"fontSize": "1.2rem", "lineHeight": "1"}),
                            ], className="d-flex align-items-center mt-3 mb-1"),
                            html.Div(id='goal-drive-links-container'),

                            html.Div([
                                dbc.Label("Website", className="mb-0"),
                                dbc.Button("+", id="btn-goal-website-add", color="link",
                                           className="p-0 ms-2 text-decoration-none text-muted",
                                           title="Add Website link", style={"fontSize": "1.2rem", "lineHeight": "1"}),
                            ], className="d-flex align-items-center mt-3 mb-1"),
                            html.Div(id='goal-website-links-container'),
                        ], style={"flex": "1", "minWidth": "0", "paddingLeft": "16px",
                                  "borderLeft": "1px solid #495057"}),
                    ], style={"display": "flex"}),

                    html.Hr(className="my-3"),

                    # --- Subtasks Table ---
                    html.Div([
                        html.Div([
                            html.H5("Subtasks", className="mb-0"),
                            dbc.Button("Add Node", id="btn-goal-add-node", color="success", size="sm",
                                       className="ms-2"),
                        ], className="d-flex align-items-center"),
                        html.Div([
                            dbc.Checklist(
                                id="goal-include-soft-needs",
                                options=[{"label": "Include Soft Needs", "value": "include"}],
                                value=[],
                                switch=True,
                                style={"fontSize": "0.85rem"},
                            ),
                            dbc.Checklist(
                                id="goal-include-transitive",
                                options=[{"label": "Include Transitive Dependencies", "value": "include"}],
                                value=[],
                                switch=True,
                                style={"fontSize": "0.85rem"},
                            ),
                        ], className="d-flex gap-3"),
                    ], className="d-flex align-items-center justify-content-between mb-3"),
                    html.Div(id="goal-subtasks-table-container"),
                ], className="goal-left-column", style={"flex": "1", "minWidth": "500px", "overflowY": "auto", "paddingRight": "8px"}),

                # Right column: full-height dependency graph
                graph_column,
            ], style={"display": "flex", "height": "100%"}),

            # Delete confirmation modal
            dbc.Modal([
                dbc.ModalBody("Are you sure you want to delete this goal? The goal node will be removed, but its subtask nodes will remain."),
                dbc.ModalFooter([
                    dbc.Button("Cancel", id="btn-goal-delete-cancel", color="secondary", className="me-2"),
                    dbc.Button("Delete", id="btn-goal-delete-confirm", color="danger",
                               style={"backgroundColor": ConfigManager.get_danger_color(),
                                      "borderColor": ConfigManager.get_danger_color()}),
                ]),
            ], id="modal-goal-confirm-delete", is_open=False, centered=True),

            # Rename confirmation modal
            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle("Rename Goal")),
                dbc.ModalBody(id="goal-rename-modal-body"),
                dbc.ModalFooter([
                    dbc.Button("Cancel", id="btn-goal-rename-cancel", color="secondary", className="me-2"),
                    dbc.Button("Rename", id="btn-goal-rename-confirm", color="primary"),
                ]),
            ], id="modal-goal-confirm-rename", is_open=False, centered=True),

            # Add node modal
            add_node_modal,
        ]),
    ], style={
        "flex": "1",
        "padding": "0 24px",
        "overflowY": "auto",
    })

    # --- Subtask Remove Confirmation Modal ---
    subtask_remove_modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Remove Subtask")),
        dbc.ModalBody(id="subtask-remove-modal-body"),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-subtask-remove-cancel", color="secondary", className="me-auto"),
            dbc.Button("Remove from Goal", id="btn-subtask-remove-edge", color="warning", className="me-2"),
            dbc.Button("Delete Node", id="btn-subtask-delete-node", color="danger"),
        ]),
    ], id="modal-subtask-remove-confirm", is_open=False, centered=True)

    return html.Div([
        dcc.Store(id='selected-goal-store', data=None),
        dcc.Store(id='goals-refresh-trigger', data=0),
        dcc.Store(id='focus-goal-store', data=None),
        dcc.Store(id='goal-order-store', data=[]),
        dcc.Store(id='subtask-remove-pending', data=None),
        dcc.Store(id='goal-rename-pending', data=None),
        # Hidden input for drag-and-drop reorder (set by JS SortableJS)
        dcc.Input(id='goal-drag-order-input', type='text', value='', style={'display': 'none'}),
        subtask_remove_modal,
        goal_list_panel,
        goal_detail_panel,
    ], style={
        "display": "flex",
        "height": "100%",
        "width": "100%",
    })


def build_goal_card(name: str, status: str, completion: dict, subtask_count: int, is_selected: bool = False, priority_rank: Optional[int] = None,
                    show_order_buttons: bool = False, is_first: bool = False, is_last: bool = False):
    """Builds a single goal card for the list."""
    border_style = "2px solid #0d6efd" if is_selected else "1px solid #495057"

    pct = completion.get("pct", 0)
    done = completion.get("done", 0)
    total = completion.get("total", 0)
    formatted_time = ConfigManager.format_time_friendly(completion.get("remaining_time", 0))

    # A goal is effectively Done if its toggle is on OR all subtasks are complete
    if status == "Done" or (pct == 100 and total > 0):
        effective_status = "Done"
    elif completion.get("is_blocked", False):
        effective_status = "Blocked"
    else:
        effective_status = "Open"

    status_color = {"Done": "success", "Blocked": "danger", "Open": "primary"}.get(effective_status, "primary")

    # Hidden up/down buttons (kept for Dash pattern-matching callback registration)
    _hidden = {"display": "none"}
    hidden_buttons = html.Div([
        dbc.Button("", id={"type": "goal-up", "index": name}, style=_hidden),
        dbc.Button("", id={"type": "goal-down", "index": name}, style=_hidden),
    ])

    # Drag handle (visible only for non-priority, manual-sort goals)
    drag_handle = html.Span(
        "\u2630", className="goal-drag-handle",
        style={"cursor": "grab", "color": "#6c757d", "fontSize": "0.9rem",
               "marginRight": "8px", "userSelect": "none"},
    ) if show_order_buttons else None

    children: List[Any] = [
        hidden_buttons,
        html.Div([
            html.Div([
                drag_handle,
                html.H6(name, className="mb-0", style={"fontWeight": "500"}),
            ], className="d-flex align-items-center"),
            html.Div([
                dbc.Badge(f"#{priority_rank}", color="warning",
                          style={"fontSize": "0.7rem"}) if priority_rank is not None else None,
                dbc.Badge(effective_status, color=status_color, className="ms-1" if priority_rank is not None else "",
                          style={"fontSize": "0.7rem", "width": "62px", "textAlign": "center",
                                 "display": "inline-block"}),
            ], className="d-flex align-items-center ms-2 gap-1"),
        ], className="d-flex align-items-center justify-content-between mb-1"),
    ]

    # Stats line (no progress bar -- keep it clean)
    if total > 0:
        stats_text = f"{done}/{total} subtasks \u00b7 {pct}% \u00b7 {formatted_time}"
    else:
        stats_text = "No subtasks yet"

    children.append(html.Small(stats_text, className="text-muted", style={"fontSize": "0.75rem"}))

    return html.Div(children, id={"type": "goal-card", "index": name},
       className="mb-2 goal-card rounded",
       **{"data-goal-name": name},
       style={
           "cursor": "pointer",
           "border": border_style,
           "backgroundColor": "#2b3035" if is_selected else "#212529",
           "transition": "border-color 0.2s, background-color 0.2s",
           "padding": "10px 14px",
       })


def build_subtasks_table(subtask_nodes, graph_manager=None, edges=None, goal_name=None, include_soft=True, include_transitive=True):
    """Builds the subtasks table for a goal detail view.

    Args:
        subtask_nodes: List of Node objects in the full goal subtree.
        graph_manager: GraphManager instance for looking up unlocked nodes.
        edges: List of all edge dicts.
        goal_name: The goal node name, used to compute need types.
        include_soft: If False, only hard-need subtasks are shown.
        include_transitive: If False, only direct children of the goal are shown.
    """
    if not subtask_nodes:
        return html.Div(
            html.P("No subtasks yet. Add prerequisite nodes to this goal to see them here.", className="text-muted"),
            className="text-center py-3"
        )

    edges = edges or []

    # Determine need type for each subtask: "Hard" if reachable via hard-only edges, else "Soft"
    need_types = {}
    if goal_name and graph_manager:
        hard_subtree = graph_manager.get_goal_subtree(goal_name, edge_types=(EDGE_NEEDS_HARD,))
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
            html.P("No hard-need subtasks for this goal.", className="text-muted"),
            className="text-center py-3"
        )

    # Build set of nodes with a direct edge to the goal (removable)
    direct_children = set()
    if goal_name:
        from models import EDGE_NEEDS_SOFT
        for e in edges:
            if e['target'] == goal_name and e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
                direct_children.add(e['source'])

    # Filter to direct-only if requested
    if not include_transitive:
        subtask_nodes = [n for n in subtask_nodes if n.name in direct_children]

    if not subtask_nodes:
        return html.Div(
            html.P("No direct subtasks for this goal.", className="text-muted"),
            className="text-center py-3"
        )

    rows = []
    for node in subtask_nodes:
        status_color = {"Done": "success", "Blocked": "danger", "Open": "primary"}.get(node.status, "secondary")
        need = need_types.get(node.name, "Hard")
        need_color = "primary" if need == "Hard" else "info"

        is_direct = node.name in direct_children
        btn = dbc.Button(
            "\u00d7",
            id={"type": "subtask-remove", "index": node.name},
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
                id={"type": "subtask-name", "index": node.name},
                style={"verticalAlign": "middle"},
            ),
            html.Td(dbc.Badge(node.status, color=status_color, style={"fontSize": "0.7rem"}),
                    style={"verticalAlign": "middle"}),
            html.Td(dbc.Badge(need, color=need_color, style={"fontSize": "0.7rem"}),
                    style={"verticalAlign": "middle"}),
            html.Td(node.type, style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.context) if node.context else "\u2014",
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.subcontext) if node.subcontext else "\u2014",
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.value), style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.interest), style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.difficulty), style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(ConfigManager.format_time_friendly(node.time) if node.time and node.time > 0 else "\u2014",
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
            html.Th("Subcontext"),
            html.Th("Value"),
            html.Th("Interest"),
            html.Th("Effort"),
            html.Th("Time"),
            html.Th(""),
        ])),
        html.Tbody(rows),
    ], bordered=False, hover=True, responsive=True, size="sm",
       className="text-light", style={"fontSize": "0.85rem"})
