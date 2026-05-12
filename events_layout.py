"""
Layout definitions for the Events tab.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from typing import List, Any
from config import ConfigManager, TOOLTIP_SHOW_DELAY_MS, TOOLTIP_HIDE_DELAY_MS, TOAST_CLEAR_INTERVAL_MS, badge_style
from styles import events_graph_stylesheet
from details_layout import build_graph_settings_panel, _freeze_indicator


def build_events_sidebar_content():
    """Builds the content for the global Events sidebar (event list + controls)."""
    return html.Div([
        html.Div([
            html.Div([
                html.H4("Events", className="mb-0"),
                dbc.Button("+", id="btn-new-event", color="link",
                           className="p-0 ms-2 text-decoration-none text-muted",
                           style={"fontSize": "1.4rem", "lineHeight": "1"}),
                dbc.Tooltip("New event", target="btn-new-event", placement="right",
                            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            ], className="d-flex align-items-center"),
            html.Span("\u00d7", id="btn-events-sidebar-close",
                       className="fs-3 text-white",
                       style={"cursor": "pointer"}),
        ], className="d-flex justify-content-between align-items-center mb-2 mt-2 px-3"),
        html.Div([
            html.Datalist(id="events-search-datalist", children=[]),
            dbc.Input(
                id="events-search-input",
                type="search",
                placeholder="Search events\u2026",
                size="sm",
                className="mb-2",
                style={"backgroundColor": "#2b3035", "border": "1px solid #495057",
                       "color": "#dee2e6", "borderRadius": "6px"},
                **{"list": "events-search-datalist"},
            ),
            html.Div([
                dbc.RadioItems(
                    id="events-sort-mode",
                    options=[
                        {"label": "Manual", "value": "manual"},
                        {"label": "A\u2013Z", "value": "az"},
                        {"label": "Z\u2013A", "value": "za"},
                    ],
                    value="manual",
                    inline=True,
                    style={"fontSize": "0.8rem", "color": "#adb5bd"},
                ),
                dbc.Switch(
                    id="events-hide-triggered-toggle",
                    label="Hide triggered",
                    value=True,
                    style={"fontSize": "0.85rem", "color": "#adb5bd", "marginBottom": "0"},
                ),
            ], className="d-flex justify-content-between align-items-center mb-2"),
        ], style={"padding": "0 12px"}),
        html.Div(id="events-list-container",
                 style={"overflowY": "auto", "flex": "1", "padding": "0 12px"}),
    ], style={"display": "flex", "flexDirection": "column", "height": "100%"})


def build_events_tab_content():
    """Builds the Events tab UI (right panel only — list is now in the global sidebar)."""
    _ted = ConfigManager.get_time_estimate_defaults()

    # --- Node Editor Modal for Dormant Nodes ---
    dormant_node_modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Add Dormant Node", id="modal-dormant-node-title")),
        dbc.ModalBody([
            # Mode toggle: New node (full editor) vs Existing nodes (picker).
            # Hidden during edit — editing only operates on a single dormant node.
            html.Div(id="dormant-mode-toggle-wrapper", children=[
                dbc.RadioItems(
                    id="dormant-node-mode",
                    options=[
                        {"label": "New node", "value": "new"},
                        {"label": "Existing nodes", "value": "existing"},
                    ],
                    value="new",
                    inline=True,
                    className="mb-2",
                ),
                html.Hr(className="my-2"),
            ]),

            # Existing-nodes mode: pick active non-dormant nodes to convert.
            html.Div(id="dormant-mode-existing-fields", style={"display": "none"}, children=[
                dbc.Label("Convert these nodes to dormant"),
                html.Div(
                    dcc.Dropdown(
                        id="dormant-existing-picker",
                        multi=True,
                        placeholder="Select existing nodes…",
                        options=[],
                    ),
                    className="text-dark",
                ),
                # Event target sub-section: visible only when no event is currently selected.
                html.Div(id="dormant-event-target-wrapper", style={"display": "none"}, children=[
                    html.Hr(className="my-2"),
                    html.H5("Add to event", className="mt-2 mb-1"),
                    dbc.RadioItems(
                        id="dormant-event-target-mode",
                        options=[
                            {"label": "New event", "value": "new"},
                            {"label": "Existing event", "value": "existing"},
                        ],
                        value="new",
                        inline=True,
                        className="mb-2",
                    ),
                    html.Div(id="dormant-new-event-section", children=[
                        dbc.Label("Event Name"),
                        dbc.Input(id="dormant-new-event-name", type="text"),
                        dbc.Label("Description", className="mt-2"),
                        dbc.Textarea(id="dormant-new-event-desc", rows=2,
                                     style={"height": "60px", "resize": "vertical"}),
                        dbc.Label("Trigger Type", className="mt-2 mb-1"),
                        dbc.RadioItems(
                            id="dormant-new-event-trigger-type",
                            options=[
                                {"label": "Manual", "value": "manual"},
                                {"label": "Date", "value": "date"},
                                {"label": "Node Completion", "value": "node"},
                            ],
                            value="manual",
                            inline=True,
                            className="mb-2",
                        ),
                        html.Div(id="dormant-new-event-date-section",
                                 style={"display": "none"}, children=[
                            html.Div([
                                dbc.Input(id="dormant-new-event-trigger-date", type="date",  # type: ignore[reportArgumentType]
                                          style={"maxWidth": "200px"}),
                                html.Small("Auto-triggers on or after this date.",
                                           className="text-muted ms-2 align-self-center",
                                           style={"fontSize": "0.8rem"}),
                            ], className="d-flex align-items-center mb-2"),
                        ]),
                        html.Div(id="dormant-new-event-node-section",
                                 style={"display": "none"}, children=[
                            html.Div(
                                dcc.Dropdown(
                                    id="dormant-new-event-trigger-node",
                                    placeholder="Select a node...",
                                    options=[],
                                ),
                                className="text-dark mb-2",
                                style={"maxWidth": "350px"},
                            ),
                            html.Small("Auto-triggers when the selected node is marked complete.",
                                       className="text-muted d-block mb-2",
                                       style={"fontSize": "0.8rem"}),
                        ]),
                    ]),
                    html.Div(id="dormant-existing-event-section", style={"display": "none"}, children=[
                        dbc.Label("Pending Event"),
                        html.Div(
                            dcc.Dropdown(
                                id="dormant-existing-event-picker",
                                placeholder="Select event…",
                                options=[],
                            ),
                            className="text-dark",
                        ),
                    ]),
                ]),
            ]),

            # New-node mode: full node editor (Name through External Resources).
            html.Div(id="dormant-mode-new-fields", children=[
            dbc.Label("Name"),
            dbc.Input(id="dormant-node-name", type="text"),

            dbc.Label("Type", className="mt-2"),
            dbc.Select(id="dormant-node-type", options=[], value="Learn"),

            dbc.Label("Description", className="mt-2"),
            dbc.Textarea(id="dormant-node-desc",
                         style={"height": "80px", "resize": "vertical"}),

            dbc.Label("Context", className="mt-2"),
            html.Div([
                dbc.Select(id="dormant-node-context",
                           options=[],
                           style={'flex': 1}),
                dbc.Button("▾", id="btn-dormant-subcontext-toggle",
                           color="light", className="ms-1 px-2"),
            ], className="d-flex"),
            dbc.Collapse(
                dbc.Select(id="dormant-node-subcontext",
                           options=[{"label": "None", "value": ""}],
                           className="mt-1"),
                id="collapse-dormant-subcontext", is_open=False,
            ),

            html.Hr(className="my-2"),
            html.Div([
                html.H5("Priority Override", className="mb-0"),
                dbc.Switch(
                    id="dormant-override-toggle",
                    label="",
                    value=False,
                    style={"fontSize": "0.82rem", "marginBottom": "0"},
                ),
            ], className="d-flex justify-content-between align-items-center mt-2 mb-1"),
            html.Div(id="dormant-override-options", style={"display": "none"}, children=[
                dbc.RadioItems(
                    id="dormant-override-mode",
                    options=[
                        {"label": "Node Only", "value": "node_only"},
                        {"label": "Node + Hard Dependencies", "value": "hard"},
                        {"label": "Node + Soft Dependencies", "value": "soft"},
                        {"label": "Node + All Dependencies", "value": "all"},
                    ],
                    value="hard",
                    style={"fontSize": "0.85rem"},
                ),
                html.Small(
                    "Applied when this event triggers; you'll be prompted if an override is already active.",
                    className="text-muted d-block mt-1",
                    style={"fontSize": "0.75rem"},
                ),
            ]),

            html.Hr(className="my-2"),
            html.H5("Ratings", className="mt-2 mb-1"),
            dbc.Label("Value", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="dormant-node-value"),

            dbc.Label("Interest", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="dormant-node-interest"),

            dbc.Label("Effort", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="dormant-node-difficulty"),

            html.Hr(className="my-2"),
            html.H5("Time Estimates", className="mt-2 mb-2"),
            html.Div([
                dbc.Checklist(
                    options=[{"label": "Inherit", "value": "inherited"}],
                    value=[],
                    id="dormant-node-time-mode",
                    switch=True,
                    className="mb-0",
                ),
                dbc.Checklist(
                    options=[{"label": "Habit", "value": "habit"}],
                    value=[],
                    id="dormant-node-time-habit-mode",
                    switch=True,
                    className="mb-0 ms-3 flex-grow-1",
                ),
                dbc.Select(id="dormant-node-time-unit", options=[
                    {"label": "Hours", "value": "hours"},
                    {"label": "Weeks", "value": "weeks"},
                    {"label": "Months", "value": "months"},
                    {"label": "Years", "value": "years"},
                ], value=_ted.get('unit', 'weeks'), size="sm", style={"width": "100px"})
            ], className="d-flex align-items-center mb-2"),
            html.Div(id="dormant-node-time-omp", children=[
                dbc.Row([
                    dbc.Col([dbc.Label("Optimistic", className="small text-muted mb-0"), dbc.Input(id="dormant-node-time-o", type="number", min=0, value=_ted.get('optimistic', 0))]),
                    dbc.Col([dbc.Label("Expected", className="small text-muted mb-0"), dbc.Input(id="dormant-node-time-m", type="number", min=0, value=_ted.get('expected', 0))]),
                    dbc.Col([dbc.Label("Pessimistic", className="small text-muted mb-0"), dbc.Input(id="dormant-node-time-p", type="number", min=0, value=_ted.get('pessimistic', 0))]),
                ]),
            ]),
            html.Div(id="section-dormant-node-time-habit",
                     style={"display": "none"}, children=[
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Duration", className="mb-0"),
                        dbc.Input(id="dormant-node-habit-duration", type="number", min=0, value=0),
                    ], width=8),
                    dbc.Col([
                        dbc.Label(" ", className="mb-0"),
                        dbc.Select(id="dormant-node-habit-duration-unit", options=[
                            {"label": "Days", "value": "days"},
                            {"label": "Weeks", "value": "weeks"},
                            {"label": "Months", "value": "months"},
                            {"label": "Years", "value": "years"},
                        ], value="weeks"),
                    ], width=4),
                ], className="mb-2"),
                dbc.Label("Intensity", className="mb-0 mt-2"),
                dbc.Row([
                    dbc.Col([dbc.Label("Optimistic", className="small text-muted mb-0"),
                             dbc.Input(id="dormant-node-habit-intensity-o", type="number", min=0, value=0)]),
                    dbc.Col([dbc.Label("Expected", className="small text-muted mb-0"),
                             dbc.Input(id="dormant-node-habit-intensity-m", type="number", min=0, value=0)]),
                    dbc.Col([dbc.Label("Pessimistic", className="small text-muted mb-0"),
                             dbc.Input(id="dormant-node-habit-intensity-p", type="number", min=0, value=0)]),
                ]),
                dbc.RadioItems(
                    id="dormant-node-habit-intensity-unit",
                    options=[
                        {"label": "min/day", "value": "min_per_day"},
                        {"label": "hr/week", "value": "hr_per_week"},
                    ],
                    value="min_per_day",
                    inline=True,
                    className="mt-2",
                ),
                html.Div(id="dormant-node-habit-total-preview",
                         className="mt-2 small text-muted"),
            ]),

            html.Hr(className="my-2"),
            html.H5("Relationships", className="mt-2 mb-1"),
            dbc.Label("Needs", className="mt-2"),
            html.Div([
                dcc.Dropdown(id="dormant-node-needs-hard", multi=True, placeholder="Hard..."),
                dcc.Dropdown(id="dormant-node-needs-soft", multi=True, placeholder="Soft...", className="mt-1"),
            ], className="text-dark"),
            dbc.Label("Supports", className="mt-2"),
            html.Div([
                dcc.Dropdown(id="dormant-node-supports-hard", multi=True, placeholder="Hard..."),
                dcc.Dropdown(id="dormant-node-supports-soft", multi=True, placeholder="Soft...", className="mt-1"),
            ], className="text-dark"),
            dbc.Label("Helps", className="mt-2"),
            html.Div(dcc.Dropdown(id="dormant-node-helps", multi=True, placeholder="Synergies..."), className="text-dark"),

            html.Hr(className="my-2"),
            html.H5("External Resources", className="mt-2 mb-1"),
            dcc.Store(id='dormant-obsidian-links-store', data=['']),
            dcc.Store(id='dormant-drive-links-store', data=['']),
            dcc.Store(id='dormant-website-links-store', data=['']),
            html.Div([
                dbc.Label("Obsidian", className="mb-0"),
                dbc.Button("+", id="btn-dormant-obsidian-add", color="link", className="p-0 ms-2 text-decoration-none text-muted", title="Add Obsidian link", style={"fontSize": "1.2rem", "lineHeight": "1"}),
            ], className="d-flex align-items-center mt-2 mb-1"),
            html.Div(id='dormant-obsidian-links-container'),
            html.Div([
                dbc.Label("Google Drive", className="mb-0"),
                dbc.Button("+", id="btn-dormant-drive-add", color="link", className="p-0 ms-2 text-decoration-none text-muted", title="Add Google Drive link", style={"fontSize": "1.2rem", "lineHeight": "1"}),
            ], className="d-flex align-items-center mt-3 mb-1"),
            html.Div(id='dormant-drive-links-container'),
            html.Div([
                dbc.Label("Website", className="mb-0"),
                dbc.Button("+", id="btn-dormant-website-add", color="link", className="p-0 ms-2 text-decoration-none text-muted", title="Add Website link", style={"fontSize": "1.2rem", "lineHeight": "1"}),
            ], className="d-flex align-items-center mt-3 mb-1"),
            html.Div(id='dormant-website-links-container'),
            ]),  # end dormant-mode-new-fields

            # Activation Delay — common to both new and existing modes.
            html.Hr(className="my-2"),
            html.H5("Activation Delay", className="mt-2 mb-1"),
            html.Small("How long after the event triggers before this node becomes active.",
                       className="text-muted d-block mb-2"),
            dbc.Row([
                dbc.Col([
                    dbc.Input(id="dormant-node-delay-value", type="number", min=0, value=0, placeholder="0"),
                ], width=6),
                dbc.Col([
                    dbc.Select(id="dormant-node-delay-unit", options=[
                        {"label": "Days", "value": "days"},
                        {"label": "Weeks", "value": "weeks"},
                        {"label": "Months", "value": "months"},
                        {"label": "Years", "value": "years"},
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

    # --- Event Detail (left: fixed natural width, right of it goes to the graph) ---
    event_detail_panel = html.Div([
        # Empty state: shown when no event is selected. Gives the user a clear
        # path to the events sidebar if they haven't opened it yet.
        html.Div(
            id="event-detail-empty",
            children=[
                html.Div([
                    html.H4("No Event Selected", className="text-muted mb-2"),
                    html.P("Open the Events sidebar to browse or create one.",
                           className="text-muted mb-3"),
                    dbc.Button([
                        html.I(className="bi bi-calendar-event me-2"),
                        "Open Events Sidebar",
                    ], id="btn-open-events-sidebar", color="primary"),
                ], style={"textAlign": "center", "marginTop": "20vh",
                          "padding": "0 24px"}),
            ],
            style={"display": "block"},
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
                        dbc.Input(id="event-trigger-date", type="date",  # type: ignore[reportArgumentType]
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
                    html.Div([
                        html.H5("Dormant Nodes", className="mb-0"),
                        dbc.Button("+", id="btn-add-dormant-node", color="link",
                                   className="p-0 ms-2 text-decoration-none text-muted",
                                   style={"fontSize": "1.2rem", "lineHeight": "1"}),
                        dbc.Tooltip("Add dormant node", target="btn-add-dormant-node", placement="right",
                                    delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                    ], className="d-flex align-items-center"),
                ], className="d-flex align-items-center mb-3"),

                html.Div(id="dormant-nodes-table-container"),

                dbc.Modal([
                    dbc.ModalBody([
                        html.P("Choose which nodes to activate. Nodes with a delay will be scheduled for future activation rather than appearing on the canvas right away."),
                        dbc.Switch(
                            id="manual-override-trigger-toggle",
                            label="Pin activated nodes to top of Next suggestions",
                            value=False,
                            className="mt-2",
                        ),
                    ]),
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
        "flex": "0 0 698px",
        "maxWidth": "698px",
        "padding": "0 24px",
        "overflowY": "auto",
        "boxSizing": "border-box",
    })

    # --- Right column: event graph visualization. Fills all remaining space. ---
    gl = ConfigManager.get_events_graph_layout_defaults()
    event_graph_panel = html.Div([
        html.Div([
            cyto.Cytoscape(
                id="events-detail-graph",
                elements=[],
                layout={
                    'name': 'fcose', 'quality': 'proof',
                    'animate': False, 'fit': True,
                    'padding': 20, 'numIter': 2500, 'randomize': False,
                    'idealEdgeLength': gl.get('edge_length', 100),
                    'nodeRepulsion': gl.get('repulsion', 4500),
                    'gravity': gl.get('gravity', 0.25),
                },
                stylesheet=events_graph_stylesheet,
                style={"width": "100%", "height": "100%",
                       "backgroundColor": "#1a1d21"},
                userZoomingEnabled=False,
                userPanningEnabled=False,
                boxSelectionEnabled=True,
                autoungrabify=False,
            ),
            dbc.Button(html.I(className="bi bi-gear"),
                       id="btn-events-graph-settings",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right-mid"),
            dbc.Tooltip("Graph settings", target="btn-events-graph-settings", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            _freeze_indicator("events-freeze-indicator"),
            build_graph_settings_panel(
                "events-graph-settings",
                include_depth_controls=False,
                defaults_getter=ConfigManager.get_details_graph_layout_defaults,
            ),
            dbc.Button(html.I(className="bi bi-arrows-fullscreen"),
                       id="btn-events-graph-fullscreen",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right"),
            dbc.Tooltip("Toggle fullscreen", target="btn-events-graph-fullscreen", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            html.Div(id="events-canvas-node-count", className="canvas-stats-overlay"),
        ], style={"position": "relative", "flex": "1", "minHeight": "0"}),
    ], id="events-detail-graph-container", style={
        "flex": "1 1 0",
        "minWidth": "0",
        "display": "flex",
        "flexDirection": "column",
        "borderLeft": "1px solid #495057",
    })

    return html.Div([
        dcc.Store(id='selected-event-store', data=None),
        dcc.Store(id='editing-dormant-node-store', data=None),
        dcc.Store(id='events-refresh-trigger', data=0),
        # UI-only refresh for the events sidebar list. Bumped by events_sidebar.js
        # on open so render_events_list re-runs — but NOT an input to core_engine,
        # so opening doesn't block the animation on a graph regen.
        dcc.Store(id='events-ui-refresh-trigger', data=0),
        dcc.Store(id='event-order-store', data=[], storage_type='local'),
        dcc.Interval(id='event-clear-interval', interval=TOAST_CLEAR_INTERVAL_MS, n_intervals=0, disabled=True),
        # Hidden input for drag-and-drop reorder (set by JS SortableJS)
        dcc.Input(id='event-drag-order-input', type='text', value='', style={'display': 'none'}),
        # Hidden input: context-menu Edit on a dormant node routes here (set by context_menu.js)
        dcc.Input(id='dormant-edit-trigger-input', type='text', value='', style={'display': 'none'}),
        dormant_node_modal,
        html.Div([
            event_detail_panel,
            event_graph_panel,
        ], id="events-tab-inner", style={
            "display": "flex",
            "flexDirection": "row",
            "height": "100%",
            "width": "100%",
            "marginLeft": "0",
            "transition": "margin-left 0.3s ease, width 0.3s ease",
        }),
    ], style={
        "display": "flex",
        "flexDirection": "row",
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
    """Returns (badge_text, badge_palette_name) for an event."""
    if status == "Triggered":
        return "Triggered", "EventTriggered"
    if trigger_node:
        return "Completion", "EventTrigger"
    if trigger_date:
        return "Scheduled", "EventTrigger"
    return "Manual", "EventTrigger"


def build_event_card(event_name, description, status, node_count, is_selected=False,
                     trigger_date=None, trigger_node=None):
    """Builds a single event card for the list."""
    badge_text, badge_name = _event_badge(status, trigger_date, trigger_node)
    border_style = "2px solid #0d6efd" if is_selected else "1px solid #495057"

    drag_handle = html.Span(
        "\u2630", className="event-drag-handle",
        style={"cursor": "grab", "color": "#6c757d", "fontSize": "0.9rem",
               "marginRight": "8px", "userSelect": "none"},
    )

    children: List[Any] = [
        html.Div([
            html.Div([
                drag_handle,
                html.H6(event_name, className="mb-0", style={"fontWeight": "500"}),
            ], className="d-flex align-items-center"),
            html.Span(badge_text, className="badge ms-2",
                      style=badge_style(badge_name, font_size="0.7rem")),
        ], className="d-flex align-items-center justify-content-between mb-1"),
    ]
    if description:
        description_str = description[:80] + "..." if len(description) > 80 else description
        children.append(html.Small(
            description_str,
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
            f"Trigger: {trigger_node}",
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
       **{"data-event-name": event_name},
       style={
           "cursor": "pointer",
           "border": border_style,
           "backgroundColor": "#2b3035" if is_selected else "#212529",
           "transition": "border-color 0.2s, background-color 0.2s",
           "padding": "10px 14px",
       })


def _delay_days_to_form(delay_days: int) -> tuple[int, str]:
    """Invert a delay_days integer back to the (value, unit) pair used by
    the Dormant Node modal's delay input. Mirrors save_dormant_node's
    forward arithmetic: years × 365, months × 30, weeks × 7, else days."""
    if delay_days == 0:
        return 0, "days"
    if delay_days % 365 == 0 and delay_days >= 365:
        return delay_days // 365, "years"
    if delay_days % 30 == 0 and delay_days >= 30:
        return delay_days // 30, "months"
    if delay_days % 7 == 0 and delay_days >= 7:
        return delay_days // 7, "weeks"
    return delay_days, "days"


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
            delay_display = "None"
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

        action_btns = None
        if not activated and event_status != "Triggered":
            edit_btn = dbc.Button(
                "✎",
                id={"type": "btn-edit-dormant-node", "index": node.name},
                color="secondary", size="sm",
                style={"fontSize": "0.7rem", "padding": "1px 6px", "lineHeight": "1"}
            )
            remove_btn = dbc.Button(
                "x", id={"type": "btn-remove-dormant-node", "index": node.name},
                color="danger", size="sm",
                style={"fontSize": "0.7rem", "padding": "1px 6px", "lineHeight": "1"}
            )
            action_btns = html.Div([edit_btn, remove_btn], className="d-flex gap-1 justify-content-end")

        rows.append(html.Tr([
            html.Td(trigger_checkbox, style={"verticalAlign": "middle", "width": "32px"}),
            html.Td(node.name, style={"verticalAlign": "middle"}),
            html.Td(node.type, style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td([delay_display, activation_info], style={"verticalAlign": "middle"}),
            html.Td(status_badge, style={"verticalAlign": "middle"}),
            html.Td(action_btns, style={"verticalAlign": "middle", "textAlign": "right"}),
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
