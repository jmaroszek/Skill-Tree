"""
Layout definitions for the Goals tab.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc
from config import ConfigManager
from models import EDGE_RESOURCE


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
        html.Div(id="goal-detail-content", style={"display": "none"}, children=[
            # --- Toolbar: Name + Buttons ---
            html.Div([
                html.Div([
                    dbc.Input(id="goal-name", type="text", placeholder="Goal Name",
                              style={"fontSize": "1.4rem", "fontWeight": "300", "backgroundColor": "transparent",
                                     "border": "none", "borderBottom": "1px solid #495057", "color": "#dee2e6",
                                     "borderRadius": "0", "paddingLeft": "0"}),
                ], style={"flex": "1"}),
                dbc.Button("Focus", id="btn-goal-focus", color="info", size="sm",
                           className="ms-2", title="Show this goal's subtree on the canvas"),
                dbc.Button("Save", id="btn-goal-save", color="primary", size="sm", className="ms-2"),
                dbc.Button("Delete", id="btn-goal-delete", color="danger", size="sm",
                           className="ms-2",
                           style={"backgroundColor": ConfigManager.get_danger_color(),
                                  "borderColor": ConfigManager.get_danger_color()}),
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

            # --- Subtasks Table (full width) ---
            html.H5("Subtasks", className="mb-3"),
            html.Div(id="goal-subtasks-table-container"),

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
        ]),
    ], style={
        "flex": "1",
        "padding": "0 24px",
        "overflowY": "auto",
        "maxWidth": "900px",
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


def build_goal_card(name, status, completion, subtask_count, is_selected=False, priority_rank=None,
                    show_order_buttons=False, is_first=False, is_last=False):
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
        dbc.Button("▲", id={"type": "goal-up", "index": name}, disabled=is_first,
                   style={**_btn_style, "opacity": "0.3" if is_first else "1"}),
        dbc.Button("▼", id={"type": "goal-down", "index": name}, disabled=is_last,
                   style={**_btn_style, "opacity": "0.3" if is_last else "1"}),
    ], className="d-flex flex-column me-2", style={"gap": "1px"}) if show_order_buttons else None

    children = [
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

    # Stats line (no progress bar — keep it clean)
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
        unlocks_str = ", ".join(unlocks) if unlocks else "—"

        # Resources
        res = [e['source'] for e in edges if e['target'] == node.name and e['type'] == EDGE_RESOURCE]
        res_str = ", ".join(res) if res else "—"

        rows.append(html.Tr([
            html.Td(
                html.Span(node.name, style={"cursor": "pointer"}),
                id={"type": "subtask-name", "index": node.name},
                style={"verticalAlign": "middle"},
            ),
            html.Td(dbc.Badge(node.status, color=status_color, style={"fontSize": "0.7rem"}),
                    style={"verticalAlign": "middle"}),
            html.Td(node.type, style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.context) if node.context else "—",
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.subcontext) if node.subcontext else "—",
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.value), style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.difficulty), style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(f"{round(node.time)}h" if node.time and node.time > 0 else "—",
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
