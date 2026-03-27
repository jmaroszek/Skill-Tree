"""
Layout definitions for the Events tab.
"""

from dash import html, dcc, no_update
import dash_bootstrap_components as dbc
from config import ConfigManager


def build_events_tab_content():
    """Builds the Events tab UI with a two-panel layout."""

    # --- Left Panel: Event List ---
    event_list_panel = html.Div([
        html.Div([
            html.H4("Events", className="mb-0"),
            dbc.Button("New Event", id="btn-new-event", color="success", size="sm"),
        ], className="d-flex justify-content-between align-items-center mb-3 mt-3"),
        html.Div(id="events-list-container", style={"overflowY": "auto", "flex": "1"}),
    ], style={
        "width": "350px",
        "minWidth": "350px",
        "borderRight": "1px solid #495057",
        "display": "flex",
        "flexDirection": "column",
        "padding": "0 16px",
        "backgroundColor": "#212529",
    })

    # --- Node Editor Modal for Dormant Nodes ---
    dormant_node_modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Add Dormant Node")),
        dbc.ModalBody([
            dbc.Label("Name"),
            dbc.Input(id="dormant-node-name", type="text"),

            dbc.Label("Type", className="mt-2"),
            dbc.Select(id="dormant-node-type", options=[], value="Learn"),

            dbc.Label("Context", className="mt-2"),
            dbc.Select(id="dormant-node-context", options=[{"label": "None", "value": ""}]),

            dbc.Label("Subcontext", className="mt-2"),
            dbc.Select(id="dormant-node-subcontext", options=[{"label": "None", "value": ""}]),

            dbc.Label("Description", className="mt-2"),
            dbc.Textarea(id="dormant-node-desc"),

            dbc.Label("Value", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="dormant-node-value"),

            dbc.Label("Interest", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="dormant-node-interest"),

            dbc.Label("Effort", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="dormant-node-difficulty"),

            dbc.Label("Time Estimates in Hours", className="mt-3"),
            dbc.Row([
                dbc.Col([dbc.Label("Optimistic", className="small text-muted mb-0"), dbc.Input(id="dormant-node-time-o", type="number", min=0, value=0)]),
                dbc.Col([dbc.Label("Expected", className="small text-muted mb-0"), dbc.Input(id="dormant-node-time-m", type="number", min=0, value=0)]),
                dbc.Col([dbc.Label("Pessimistic", className="small text-muted mb-0"), dbc.Input(id="dormant-node-time-p", type="number", min=0, value=0)]),
            ]),

            html.Hr(),
            html.H6("Activation Delay"),
            dbc.Row([
                dbc.Col([
                    dbc.Input(id="dormant-node-delay-value", type="number", min=0, value=0, placeholder="0"),
                ], width=6),
                dbc.Col([
                    dbc.Select(id="dormant-node-delay-unit", options=[
                        {"label": "Days", "value": "days"},
                        {"label": "Weeks", "value": "weeks"},
                        {"label": "Months", "value": "months"},
                    ], value="days"),
                ], width=6),
            ]),
            html.Small("0 = activates immediately when event is triggered.", className="text-muted"),

            html.Div(id="dormant-node-save-status", className="text-danger mt-2"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-dormant-node-cancel", color="secondary", className="me-2"),
            dbc.Button("Add Node", id="btn-dormant-node-save", color="primary"),
        ]),
    ], id="modal-dormant-node", size="lg", is_open=False, centered=True)

    # --- Node Completion Confirmation Modal ---
    node_completion_modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Node Completion Trigger")),
        dbc.ModalBody([
            html.P(id="node-completion-modal-desc", className="mb-3"),
            html.Div(id="node-completion-event-list"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Skip", id="btn-node-completion-skip", color="secondary", className="me-auto"),
            dbc.Button("Trigger Selected", id="btn-node-completion-confirm", color="success"),
        ]),
    ], id="modal-node-completion", is_open=False, centered=True)

    # --- Right Panel: Event Detail ---
    event_detail_panel = html.Div([
        # Shown when no event is selected
        html.Div(
            id="event-detail-empty",
            children=[
                html.Div([
                    html.H5("No Event Selected", className="text-muted mb-2"),
                    html.P("Select an event from the list or create a new one.", className="text-muted"),
                ], style={"textAlign": "center", "marginTop": "20vh"})
            ],
        ),

        # Event editor (hidden when no event selected)
        html.Div(id="event-detail-content", style={"display": "none"}, children=[
            html.Div([
                # Hidden status badge — kept in DOM so callbacks don't break
                dbc.Badge(id="event-status-badge", children="Pending", color="primary",
                          style={"display": "none"}),

                # --- Name ---
                dbc.Input(id="event-name", type="text", placeholder="Event Name",
                          className="mt-3 mb-1",
                          style={"fontSize": "1.4rem", "fontWeight": "300", "backgroundColor": "transparent",
                                 "border": "none", "borderBottom": "1px solid #495057", "color": "#dee2e6",
                                 "borderRadius": "0", "paddingLeft": "0"}),

                html.Div(id="event-save-status", className="text-success mb-2",
                         style={"fontSize": "0.85rem", "minHeight": "1.2em"}),

                # --- Description ---
                dbc.Label("Description", className="mb-1"),
                dbc.Textarea(id="event-description", rows=3,
                             style={"height": "90px", "resize": "vertical"}),

                # --- Trigger Type ---
                dbc.Label("Trigger Type", className="mt-3 mb-1"),
                dbc.RadioItems(
                    id="event-trigger-type",
                    options=[
                        {"label": "Manual", "value": "manual"},
                        {"label": "Date", "value": "date"},
                        {"label": "Node Completion", "value": "node"},
                    ],
                    value="manual",
                    inline=True,
                    className="mb-2",
                ),

                # Date trigger section
                html.Div(id="event-date-section", style={"display": "none"}, children=[
                    html.Div([
                        dbc.Input(id="event-trigger-date", type="date",
                                  style={"maxWidth": "200px"}),
                        html.Small("Auto-triggers on or after this date.",
                                   className="text-muted ms-2 align-self-center",
                                   style={"fontSize": "0.8rem"}),
                    ], className="d-flex align-items-center mb-2"),
                ]),

                # Node completion trigger section
                html.Div(id="event-node-section", style={"display": "none"}, children=[
                    html.Div(
                        dcc.Dropdown(
                            id="event-trigger-node",
                            placeholder="Select a node...",
                        ),
                        className="text-dark mb-2",
                        style={"maxWidth": "350px"},
                    ),
                    html.Small("Auto-triggers when the selected node is marked complete.",
                               className="text-muted d-block mb-2",
                               style={"fontSize": "0.8rem"}),
                ]),

                # --- Action Buttons (right-aligned: Delete | Save | Trigger) ---
                html.Div([
                    html.Div(id="event-trigger-section", className="d-flex align-items-center", children=[
                        dbc.Button("Delete", id="btn-event-delete", color="danger", size="sm",
                                   className="me-2",
                                   style={"backgroundColor": ConfigManager.get_danger_color(),
                                          "borderColor": ConfigManager.get_danger_color()}),
                        dbc.Button("Save", id="btn-event-save", color="primary", size="sm", className="me-2"),
                        dbc.Button("Trigger", id="btn-trigger-event", color="success", size="sm"),
                    ]),
                ], className="d-flex justify-content-end mb-3 mt-2"),

                html.Hr(className="my-3"),

                # Dormant Nodes Section
                html.Div([
                    html.H5("Dormant Nodes", className="mb-0"),
                    dbc.Button("Add Node", id="btn-add-dormant-node", color="success", size="sm"),
                ], className="d-flex justify-content-between align-items-center mb-3"),

                html.Div(id="dormant-nodes-table-container"),

                dbc.Modal([
                    dbc.ModalBody("Choose which nodes to activate. Nodes with a delay will be scheduled for future activation rather than appearing on the canvas right away."),
                    dbc.ModalFooter([
                        dbc.Button("Cancel", id="btn-trigger-cancel", color="secondary", className="me-auto"),
                        dbc.Button("Trigger Checked", id="btn-trigger-confirm", color="success", className="me-2"),
                        dbc.Button("Trigger All", id="btn-trigger-all-confirm", color="success"),
                    ]),
                ], id="modal-confirm-trigger", is_open=False, centered=True),
                dbc.Modal([
                    dbc.ModalBody("Are you sure you want to delete this event? This will also delete all its dormant nodes."),
                    dbc.ModalFooter([
                        dbc.Button("Cancel", id="btn-delete-cancel", color="secondary", className="me-2"),
                        dbc.Button("Delete", id="btn-delete-confirm", color="danger", style={"backgroundColor": ConfigManager.get_danger_color(), "borderColor": ConfigManager.get_danger_color()}),
                    ]),
                ], id="modal-confirm-delete", is_open=False, centered=True),
            ], style={"maxWidth": "650px"}),
        ]),
    ], style={
        "flex": "1",
        "padding": "0 24px",
        "overflowY": "auto",
    })

    return html.Div([
        dcc.Store(id='selected-event-store', data=None),
        dcc.Store(id='events-refresh-trigger', data=0),
        dcc.Store(id='node-completion-events-store', data=None),
        dcc.Interval(id='event-clear-interval', interval=3000, n_intervals=0, disabled=True),
        dormant_node_modal,
        node_completion_modal,
        event_list_panel,
        event_detail_panel,
    ], style={
        "display": "flex",
        "height": "100%",
        "width": "100%",
    })


def _event_trigger_type(event):
    """Returns the trigger type string for an event."""
    if event.trigger_node:
        return "node"
    if event.trigger_date:
        return "date"
    return "manual"


def _event_badge(status, trigger_date, trigger_node=None):
    """Returns (badge_text, badge_color) for an event."""
    if status == "Triggered":
        return "Triggered", "success"
    if trigger_node:
        return "On Completion", "warning"
    if trigger_date:
        return "Scheduled", "info"
    return "Manual", "secondary"


def build_event_card(event_name, description, status, node_count, is_selected=False,
                     trigger_date=None, trigger_node=None):
    """Builds a single event card for the list."""
    badge_text, badge_color = _event_badge(status, trigger_date, trigger_node)
    border_style = "2px solid #0d6efd" if is_selected else "1px solid #495057"

    children = [
        html.Div([
            html.H6(event_name, className="mb-0", style={"fontWeight": "500"}),
            dbc.Badge(badge_text, color=badge_color, className="ms-2",
                      style={"fontSize": "0.7rem"}),
        ], className="d-flex align-items-center mb-1"),
    ]
    if description:
        children.append(html.Small(
            description[:80] + "..." if len(description) > 80 else description,
            className="text-muted d-block mb-1"
        ))
    if trigger_date and status != "Triggered":
        children.append(html.Small(
            f"Date: {trigger_date}",
            className="text-muted d-block",
            style={"fontSize": "0.75rem"}
        ))
    if trigger_node and status != "Triggered":
        children.append(html.Small(
            f"Node: {trigger_node}",
            className="text-muted d-block",
            style={"fontSize": "0.75rem"}
        ))
    children.append(html.Small(
        f"{node_count['total']} node{'s' if node_count['total'] != 1 else ''}"
        + (f" ({node_count['activated']} activated)" if node_count['activated'] > 0 else ""),
        className="text-muted",
        style={"fontSize": "0.75rem"}
    ))

    return html.Div(children, id={"type": "event-card", "index": event_name},
       className="mb-2 event-card rounded",
       style={
           "cursor": "pointer",
           "border": border_style,
           "backgroundColor": "#2b3035" if is_selected else "#212529",
           "transition": "border-color 0.2s, background-color 0.2s",
           "padding": "10px 14px",
       })


def build_dormant_nodes_table(event_nodes, event_status):
    """Builds the dormant nodes table for an event detail view."""
    if not event_nodes:
        return html.Div(
            html.P("No dormant nodes yet. Click 'Add Node' to add one.", className="text-muted"),
            className="text-center py-3"
        )

    rows = []
    for i, en in enumerate(event_nodes):
        node = en['node']
        delay_days = en['delay_days']
        activated = en['activated']

        # Convert delay_days back to a friendly display
        if delay_days == 0:
            delay_display = "Immediate"
        elif delay_days % 30 == 0 and delay_days >= 30:
            months = delay_days // 30
            delay_display = f"{months} month{'s' if months > 1 else ''}"
        elif delay_days % 7 == 0:
            weeks = delay_days // 7
            delay_display = f"{weeks} week{'s' if weeks > 1 else ''}"
        else:
            delay_display = f"{delay_days} day{'s' if delay_days != 1 else ''}"

        status_badge = dbc.Badge(
            "Active" if activated else "Dormant",
            color="success" if activated else "secondary",
            style={"fontSize": "0.7rem"}
        )

        activation_info = ""
        if en.get('activation_date') and not activated:
            activation_info = html.Small(
                f"Scheduled: {en['activation_date']}",
                className="text-muted ms-2",
                style={"fontSize": "0.7rem"}
            )

        # Checkbox: only shown for dormant (non-activated) nodes on non-triggered events
        if not activated and event_status != "Triggered":
            trigger_checkbox = dbc.Checkbox(
                id={"type": "dormant-node-select", "index": node.name},
                value=True,
                style={"cursor": "pointer"}
            )
        else:
            trigger_checkbox = html.Span()

        remove_btn = None
        if not activated and event_status != "Triggered":
            remove_btn = dbc.Button(
                "x", id={"type": "btn-remove-dormant-node", "index": node.name},
                color="danger", size="sm",
                style={"fontSize": "0.7rem", "padding": "1px 6px", "lineHeight": "1"}
            )

        rows.append(html.Tr([
            html.Td(trigger_checkbox, style={"verticalAlign": "middle", "width": "32px"}),
            html.Td(node.name, style={"verticalAlign": "middle"}),
            html.Td(node.type, style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td([delay_display, activation_info], style={"verticalAlign": "middle"}),
            html.Td(status_badge, style={"verticalAlign": "middle"}),
            html.Td(remove_btn, style={"verticalAlign": "middle", "textAlign": "right"}),
        ]))

    return dbc.Table([
        html.Thead(html.Tr([
            html.Th("", style={"width": "32px"}),
            html.Th("Name"),
            html.Th("Type"),
            html.Th("Delay"),
            html.Th("Status"),
            html.Th("", style={"width": "40px"}),
        ])),
        html.Tbody(rows),
    ], bordered=False, hover=True, responsive=True, size="sm",
       className="text-light", style={"fontSize": "0.85rem"})
