"""
Layout definitions for the Goals tab.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc
from typing import Optional, List, Any
import dash_cytoscape as cyto
from config import ConfigManager
from models import EDGE_RESOURCE
from styles import stylesheet


def build_goals_tab_content():
    """Builds the Goals tab UI with a two-panel layout."""

    # --- Left Panel: Goal List ---
    goal_list_panel = html.Div([
        html.Div([
            html.H4("Goals", className="mb-0"),
            dbc.Button("New Goal", id="btn-new-goal", color="success", size="sm"),
        ], className="d-flex justify-content-between align-items-center mb-3 mt-3"),
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
                    style={"backgroundColor": "#2b3035", "color": "#dee2e6"},
                ), className="text-dark mb-3"),
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

                dbc.Label("Time Estimates in Hours", className="mt-3"),
                dbc.Row([
                    dbc.Col([dbc.Label("Optimistic", className="small text-muted mb-0"),
                             dbc.Input(id="goal-add-time-o", type="number", min=0, value=0)]),
                    dbc.Col([dbc.Label("Expected", className="small text-muted mb-0"),
                             dbc.Input(id="goal-add-time-m", type="number", min=0, value=0)]),
                    dbc.Col([dbc.Label("Pessimistic", className="small text-muted mb-0"),
                             dbc.Input(id="goal-add-time-p", type="number", min=0, value=0)]),
                ]),
            ]),

            html.Hr(),
            dbc.Label("Edge Type"),
            dbc.Select(
                id="goal-add-edge-type",
                options=[
                    {"label": "Hard Dependency", "value": "Needs_Hard"},
                    {"label": "Soft Dependency", "value": "Needs_Soft"},
                ],
                value="Needs_Hard",
            ),

            html.Div(id="goal-add-save-status", className="text-danger mt-2",
                     style={"fontSize": "0.85rem", "minHeight": "1.2em"}),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-goal-add-cancel", color="secondary", className="me-2"),
            dbc.Button("Add", id="btn-goal-add-save", color="primary"),
        ]),
    ], id="modal-goal-add-node", size="lg", is_open=False, centered=True)

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
                    # --- Toolbar: Name + Buttons ---
                    html.Div([
                        html.Div([
                            dbc.Input(id="goal-name", type="text", placeholder="Goal Name",
                                      style={"fontSize": "1.4rem", "fontWeight": "300", "backgroundColor": "transparent",
                                             "border": "none", "borderBottom": "1px solid #495057", "color": "#dee2e6",
                                             "borderRadius": "0", "paddingLeft": "0"}),
                        ], style={"flex": "1"}),
                        dbc.Button("Delete", id="btn-goal-delete", color="danger", size="sm",
                                   className="ms-2",
                                   style={"backgroundColor": ConfigManager.get_danger_color(),
                                          "borderColor": ConfigManager.get_danger_color()}),
                        dbc.Button("Save", id="btn-goal-save", color="primary", size="sm", className="ms-2"),
                    ], className="d-flex align-items-end mb-2 mt-3"),

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

                        # Right column: priority rank, context, subcontext, progress
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
                        ], width=5),
                    ]),

                    html.Hr(className="my-3"),

                    # --- Subtasks Table ---
                    html.Div([
                        html.H5("Subtasks", className="mb-0"),
                        dbc.Button("Add Node", id="btn-goal-add-node", color="success", size="sm",
                                   className="ms-2"),
                    ], className="d-flex align-items-center mb-3"),
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

            # Add node modal
            add_node_modal,
        ]),
    ], style={
        "flex": "1",
        "padding": "0 24px",
        "overflowY": "auto",
    })

    return html.Div([
        dcc.Store(id='selected-goal-store', data=None),
        dcc.Store(id='goals-refresh-trigger', data=0),
        dcc.Store(id='focus-goal-store', data=None),
        dcc.Store(id='goal-order-store', data=[]),
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
    remaining_hours = round(completion.get("remaining_time", 0))

    # A goal is effectively Done if its toggle is on OR all subtasks are complete
    effective_status = "Done" if (status == "Done" or (pct == 100 and total > 0)) else status
    status_color = "success" if effective_status == "Done" else "primary"

    _btn_style = {"padding": "0 2px", "fontSize": "0.6rem", "background": "none",
                  "border": "none", "lineHeight": "1.2", "color": "#6c757d"}
    order_controls = html.Div([
        dbc.Button("\u25b2", id={"type": "goal-up", "index": name}, disabled=is_first,
                   style={**_btn_style, "opacity": "0.3" if is_first else "1"}),
        dbc.Button("\u25bc", id={"type": "goal-down", "index": name}, disabled=is_last,
                   style={**_btn_style, "opacity": "0.3" if is_last else "1"}),
    ], className="d-flex flex-column me-2", style={"gap": "1px"}) if show_order_buttons else None

    children: List[Any] = [
        html.Div([
            html.Div([
                order_controls,
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
        stats_text = f"{done}/{total} subtasks \u00b7 {pct}% \u00b7 {remaining_hours}h"
    else:
        stats_text = "No subtasks yet"

    children.append(html.Small(stats_text, className="text-muted", style={"fontSize": "0.75rem"}))

    return html.Div(children, id={"type": "goal-card", "index": name},
       className="mb-2 goal-card rounded",
       style={
           "cursor": "pointer",
           "border": border_style,
           "backgroundColor": "#2b3035" if is_selected else "#212529",
           "transition": "border-color 0.2s, background-color 0.2s",
           "padding": "10px 14px",
       })


def build_subtasks_table(subtask_nodes, graph_manager=None, edges=None):
    """Builds the subtasks table for a goal detail view."""
    if not subtask_nodes:
        return html.Div(
            html.P("No subtasks yet. Add prerequisite nodes to this goal to see them here.", className="text-muted"),
            className="text-center py-3"
        )

    edges = edges or []

    rows = []
    for node in subtask_nodes:
        status_color = {"Done": "success", "Blocked": "danger", "Open": "primary"}.get(node.status, "secondary")

        # Unlocks
        unlocks = []
        if graph_manager:
            unlocks = graph_manager.get_directly_unlocked_nodes(node.name)
        unlocks_str = ", ".join(unlocks) if unlocks else "\u2014"

        # Resources
        res = [e['source'] for e in edges if e['target'] == node.name and e['type'] == EDGE_RESOURCE]
        res_str = ", ".join(res) if res else "\u2014"

        rows.append(html.Tr([
            html.Td(
                html.Span(node.name, style={"cursor": "pointer"}),
                id={"type": "subtask-name", "index": node.name},
                style={"verticalAlign": "middle"},
            ),
            html.Td(dbc.Badge(node.status, color=status_color, style={"fontSize": "0.7rem"}),
                    style={"verticalAlign": "middle"}),
            html.Td(node.type, style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.context) if node.context else "\u2014",
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.subcontext) if node.subcontext else "\u2014",
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.value), style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.difficulty), style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(f"{round(node.time)}h" if node.time and node.time > 0 else "\u2014",
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(unlocks_str, style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(res_str, style={"verticalAlign": "middle", "color": "#6c757d"}),
        ]))

    return dbc.Table([
        html.Thead(html.Tr([
            html.Th("Name"),
            html.Th("Status"),
            html.Th("Type"),
            html.Th("Context"),
            html.Th("Subcontext"),
            html.Th("Value"),
            html.Th("Effort"),
            html.Th("Time"),
            html.Th("Unlocks"),
            html.Th("Resources"),
        ])),
        html.Tbody(rows),
    ], bordered=False, hover=True, responsive=True, size="sm",
       className="text-light", style={"fontSize": "0.85rem"})
