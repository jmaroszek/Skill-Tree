"""
Layout definitions for the Events tab.
"""

import style_tokens as tokens
from duration_ui import DURATION_UNITS, bracket_label, estimate_guidance, unit_select
from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from typing import List, Any
from config import ConfigManager, TOOLTIP_SHOW_DELAY_MS, TOOLTIP_HIDE_DELAY_MS, TOAST_CLEAR_INTERVAL_MS, badge_style
from models import STATUS_DONE
from styles import events_graph_stylesheet
from details_layout import build_graph_settings_panel, _freeze_indicator, WEEKDAY_OPTIONS
from context_picker import build_single_context_picker
from list_toolbar import EVENTS_SORT, SEARCH_STYLE, build_list_toolbar
from ui_kit import (add_button, done_color, panel_close_button)


def build_events_sidebar_content():
    """Builds the content for the global Events sidebar (event list + controls)."""
    return html.Div([
        html.Div([
            html.Div([
                html.H4("Events", className="mb-0"),
                add_button("btn-new-event", "New event", large=True),
            ], className="d-flex align-items-center"),
            panel_close_button("btn-events-sidebar-close", "Close events sidebar",
                               large=True),
        ], className="d-flex justify-content-between align-items-center mb-2 mt-2 px-3"),
        html.Datalist(id="events-search-datalist", children=[]),
        build_list_toolbar(
            dbc.Input(
                id="events-search-input",
                type="search",
                placeholder="Search events...",
                size="sm",
                style=SEARCH_STYLE,
                **{"list": "events-search-datalist"},
            ),
            EVENTS_SORT,
        ),
        # Triggered events start hidden on every load. The line at the end of
        # the list shows or hides them.
        dcc.Store(id="events-show-triggered-store", data=False),
        html.Div(id="events-list-container",
                 style={"overflowY": "auto", "flex": "1", "padding": "0 12px"}),
    ], style={"display": "flex", "flexDirection": "column", "height": "100%"})


def build_events_tab_content():
    """Builds the Events tab UI (right panel only — list is now in the global sidebar)."""
    _ted = ConfigManager.get_time_estimate_defaults()
    # Triggering an event is its "done" moment — tint the button with the
    # node-status Done color rather than a loud default green.
    _done_color = done_color()

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

            # Existing-nodes mode: pick live non-dormant nodes to convert.
            html.Div(id="dormant-mode-existing-fields", style={"display": "none"}, children=[
                dbc.Label("Convert these nodes to dormant"),
                html.Div(
                    dcc.Dropdown(
                        id="dormant-existing-picker",
                        multi=True,
                        placeholder="Select existing nodes...",
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
                                           style={"fontSize": tokens.FS_CAP}),
                            ], className="d-flex align-items-center mb-2"),
                        ]),
                        html.Div(id="dormant-new-event-node-section",
                                 style={"display": "none"}, children=[
                            html.Div(
                                dcc.Dropdown(
                                    id="dormant-new-event-trigger-node",
                                    placeholder="Select one or more nodes...",
                                    options=[],
                                    multi=True,
                                ),
                                className="text-dark mb-2",
                                style={"maxWidth": "350px"},
                            ),
                            dbc.RadioItems(
                                id="dormant-new-event-trigger-mode",
                                options=[
                                    {"label": "Any", "value": "any"},
                                    {"label": "All", "value": "all"},
                                ],
                                value="any",
                                inline=True,
                                className="mb-1",
                                style={"fontSize": tokens.FS_BASE},
                            ),
                            html.Small(id="dormant-new-event-trigger-mode-hint",
                                       className="text-muted d-block mb-2",
                                       style={"fontSize": tokens.FS_CAP}),
                        ]),
                    ]),
                    html.Div(id="dormant-existing-event-section", style={"display": "none"}, children=[
                        dbc.Label("Pending Event"),
                        html.Div(
                            dcc.Dropdown(
                                id="dormant-existing-event-picker",
                                placeholder="Select event...",
                                options=[],
                            ),
                            className="text-dark",
                        ),
                    ]),
                ]),
            ]),

            # New-node mode: full node editor (Name through Resources).
            html.Div(id="dormant-mode-new-fields", children=[
            html.Div([
                dbc.Label("Name", className="mb-0"),
                add_button("btn-dormant-alias-add", "Add alias"),
            ], className="d-flex align-items-center mb-1"),
            dbc.Input(id="dormant-node-name", type="text", placeholder="Name node..."),
            dbc.Collapse(
                html.Div([
                    dbc.Label("Alias", id="dormant-aliases-label",
                              className="mt-1 mb-1"),
                    html.Div(id='dormant-aliases-container'),
                ]),
                id="collapse-dormant-aliases", is_open=False,
            ),
            dcc.Store(id='dormant-aliases-store', data=['']),

            dbc.Label("Type", className="mt-2"),
            dbc.Select(id="dormant-node-type", options=[],
                       placeholder="Choose node type..."),

            dbc.Label("Description", className="mt-2"),
            dbc.Textarea(id="dormant-node-desc", placeholder="Describe your project...",
                         style={"height": "80px", "resize": "vertical"}),

            dbc.Label("Context", className="mt-2"),
            build_single_context_picker(
                "dormant-node-context-picker",
                "dormant-node-context",
                "dormant-node-subcontext",
                subcontext_options=[{"label": "None", "value": ""}],
            ),

            html.Hr(className="my-2"),
            html.H5("Ratings", className="mt-2 mb-1"),
            # Inherit-value + Add-to-Now toggles on one row — mirrors the main
            # node editor (sidebars_layout). Both are switch-style checklists.
            html.Div([
                dbc.Checklist(
                    options=[{"label": "Inherit", "value": "inherited"}],
                    value=[],
                    id="dormant-node-value-mode",
                    switch=True,
                    className="mb-0 me-3",
                ),
                dbc.Checklist(
                    options=[{"label": "Add to Now", "value": "on"}],
                    value=[],
                    id="dormant-now-toggle",
                    switch=True,
                    className="mb-0",
                ),
            ], className="d-flex align-items-center mt-2 mb-2"),
            dbc.Tooltip(
                "Treat this node as a pure container: value, interest, and effort all come from its children via the cascade.",
                target="dormant-node-value-mode", placement="left",
                delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS},
            ),
            dbc.Tooltip(
                "When this event wakes the node, move it straight onto the Now list. Skipped if Now is already full.",
                target="dormant-now-toggle", placement="left",
                delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS},
            ),
            # Locked-on notice for Milestones (mirrors the time-mode warning).
            html.Div(id="dormant-value-mode-warning",
                     style=tokens.ERROR_TEXT_HIDDEN,
                     className="mt-1 mb-2", children=""),
            html.Div(id="section-dormant-ratings", children=[
                dbc.Label("Value", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5, id="dormant-node-value"),

                dbc.Label("Interest", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5, id="dormant-node-interest"),

                html.Div(id="dormant-node-effort-row", children=[
                    dbc.Label("Effort", className="mt-2"),
                    dcc.Slider(min=1, max=10, step=1, value=5, id="dormant-node-difficulty"),
                ]),
                html.Div(id="dormant-node-effort-caption", style={"display": "none"}, children=[
                    dbc.Label("Effort", className="mt-2"),
                    html.Div("Derived from subtasks", className="text-muted small"),
                ]),
            ]),
            html.Hr(className="my-2"),
            html.Div([
                html.H5("Time Estimates", className="mb-0"),
                estimate_guidance("dormant-node"),
            ], className="d-flex align-items-center mt-2 mb-2"),
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
                unit_select("dormant-node-time-unit",
                            value=_ted.get('unit', 'weeks'), compact=True)
            ], className="d-flex align-items-center mb-2"),
            html.Div(id="dormant-node-time-omp", children=[
                dbc.Row([
                    dbc.Col([*bracket_label("Lower", "dormant-node-time-o-label"), dbc.Input(id="dormant-node-time-o", type="number", min=0, value=_ted.get('optimistic', 0))]),
                    dbc.Col([*bracket_label("Expected", "dormant-node-time-m-label"), dbc.Input(id="dormant-node-time-m", type="number", min=0, value=_ted.get('expected', 0))]),
                    dbc.Col([*bracket_label("Upper", "dormant-node-time-p-label"), dbc.Input(id="dormant-node-time-p", type="number", min=0, value=_ted.get('pessimistic', 0))]),
                ]),
            ]),
            html.Div(id="section-dormant-node-time-habit",
                     style={"display": "none"}, children=[
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Duration", className="mb-0"),
                        dbc.Input(id="dormant-node-habit-duration", type="number", min=0, value=0),
                    ], width=7),
                    dbc.Col([
                        dbc.Label(" ", className="mb-0"),
                        unit_select("dormant-node-habit-duration-unit",
                                    units=DURATION_UNITS, value="weeks"),
                    ], width=5),
                ], className="mb-2"),
                dbc.Label("Minutes per Session", className="mb-0 mt-2"),
                dbc.Row([
                    dbc.Col([*bracket_label("Lower", "dormant-node-habit-intensity-o-label"),
                             dbc.Input(id="dormant-node-habit-intensity-o", type="number", min=0, value=0)]),
                    dbc.Col([*bracket_label("Expected", "dormant-node-habit-intensity-m-label"),
                             dbc.Input(id="dormant-node-habit-intensity-m", type="number", min=0, value=0)]),
                    dbc.Col([*bracket_label("Upper", "dormant-node-habit-intensity-p-label"),
                             dbc.Input(id="dormant-node-habit-intensity-p", type="number", min=0, value=0)]),
                ]),
                dcc.Input(id="dormant-node-habit-intensity-unit", type="hidden",
                          value="min_per_session"),
                dbc.Label("On these days", className="mb-1 mt-2 d-block"),
                dbc.Checklist(
                    id="dormant-node-habit-days",
                    options=WEEKDAY_OPTIONS,
                    value=[0, 1, 2, 3, 4, 5, 6],
                    className="habit-days-picker",
                    inputClassName="btn-check",
                    labelClassName="btn btn-outline-light btn-sm",
                    labelCheckedClassName="active",
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
            html.H5("Resources", className="mt-2 mb-1"),
            dcc.Store(id='dormant-obsidian-links-store', data=['']),
            dcc.Store(id='dormant-drive-links-store', data=['']),
            dcc.Store(id='dormant-website-links-store', data=['']),
            html.Div([
                dbc.Label("Obsidian", className="mb-0"),
                add_button("btn-dormant-obsidian-add", "Add Obsidian link"),
            ], className="d-flex align-items-center mt-2 mb-1"),
            html.Div(id='dormant-obsidian-links-container'),
            html.Div([
                dbc.Label("Google Drive", className="mb-0"),
                add_button("btn-dormant-drive-add", "Add Google Drive link"),
            ], className="d-flex align-items-center mt-3 mb-1"),
            html.Div(id='dormant-drive-links-container'),
            html.Div([
                dbc.Label("Website", className="mb-0"),
                add_button("btn-dormant-website-add", "Add Website link"),
            ], className="d-flex align-items-center mt-3 mb-1"),
            html.Div(id='dormant-website-links-container'),
            ]),  # end dormant-mode-new-fields

            # Activation Delay — common to both new and existing modes.
            html.Hr(className="my-2"),
            html.H5("Activation Delay", className="mt-2 mb-1"),
            html.Small("How long after the event triggers before this node wakes up.",
                       className="text-muted d-block mb-2"),
            dbc.Row([
                dbc.Col([
                    dbc.Input(id="dormant-node-delay-value", type="number", min=0, value=0, placeholder="0"),
                ], width=6),
                dbc.Col([
                    unit_select("dormant-node-delay-unit",
                                units=DURATION_UNITS, value="days"),
                ], width=6),
            ]),
            html.Small("0 = activates immediately when event is triggered.", className="text-muted"),

            html.Div(id="dormant-node-save-status", className="text-danger mt-2"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-dormant-node-cancel", color="secondary", className="me-2"),
            dbc.Button("Add Node", id="btn-dormant-node-save", color="success",
                       style={"backgroundColor": _done_color, "borderColor": _done_color}),
        ]),
    ], id="modal-dormant-node", size="lg", is_open=False, centered=True)

    # --- Event Detail (left: fixed natural width, right of it goes to the graph) ---
    event_detail_panel = html.Div([
        # Empty state: shown alongside the automatically opened Events sidebar
        # when no event is selected.
        html.Div(
            id="event-detail-empty",
            children=[
                html.Div([
                    html.H4("No Event Selected", className="text-muted mb-2"),
                    html.P("Select an event from the sidebar or create a new one.",
                           className="text-muted mb-0"),
                ], style={"textAlign": "center", "marginTop": "20vh",
                          "padding": "0 24px"}),
            ],
            style={"display": "block"},
        ),

        # Event editor (hidden when no event selected)
        html.Div(id="event-detail-content", style={"display": "none"}, children=[
            html.Div([
                # Hidden status badge — kept in the DOM so the three callbacks
                # that still target its children/color/style Outputs keep
                # working. It stays a dbc.Badge for the `color` prop those
                # Outputs write; it is never shown, so that colour is inert.
                # If it is ever un-hidden, move it to config.badge_style like
                # every other badge rather than trusting the stock palette.
                dbc.Badge(id="event-status-badge", children="Pending", color="primary",
                          style={"display": "none"}),

                # --- Name + event actions ---
                # Delete/Save act on the whole event, so they sit with the
                # event's title rather than on a line of their own. The
                # event-trigger-section wrapper still governs their visibility
                # (hidden for new + triggered events) and feeds the mirror
                # callback that shows/hides the relocated Trigger button.
                html.Div([
                    dbc.Input(id="event-name", type="text", placeholder="Name event...",
                              className="flex-grow-1",
                              style={"fontSize": tokens.FS_2XL, "fontWeight": "300", "backgroundColor": "transparent",
                                     "border": "none", "color": tokens.TEXT_PRIMARY,
                                     "borderRadius": "0", "paddingLeft": "0"}),
                    html.Div([
                        dbc.Button("Close", id="btn-event-close", color="secondary", size="sm",
                                   className="me-2"),
                        dbc.Tooltip("Close this event without changing it", target="btn-event-close", placement="bottom",
                                    delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                        html.Div(id="event-trigger-section", className="d-flex align-items-center", children=[
                            dbc.Button("Delete", id="btn-event-delete", color="danger", size="sm",
                                       className="me-2"),
                            dbc.Tooltip("Delete this event and its dormant nodes", target="btn-event-delete", placement="bottom",
                                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                            dbc.Button("Save", id="btn-event-save", color="primary", size="sm"),
                            dbc.Tooltip("Save changes to this event", target="btn-event-save", placement="bottom",
                                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                        ]),
                    ], className="d-flex align-items-center ms-3"),
                ], className="d-flex align-items-center mt-3 mb-1",
                   style={"borderBottom": f"1px solid {tokens.BORDER_PANEL}"}),

                html.Div(id="event-save-status", className="text-success mb-2",
                         style={"fontSize": tokens.FS_BASE, "minHeight": "1.2em"}),

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
                                   style={"fontSize": tokens.FS_CAP}),
                    ], className="d-flex align-items-center mb-2"),
                ]),

                # Node completion trigger section
                html.Div(id="event-node-section", style={"display": "none"}, children=[
                    html.Div(
                        dcc.Dropdown(
                            id="event-trigger-node",
                            placeholder="Select one or more nodes...",
                            multi=True,
                        ),
                        className="text-dark mb-2",
                        style={"maxWidth": "350px"},
                    ),
                    # Sub-choice of the Node Completion trigger, so it takes the
                    # reduced size used by other in-section radios rather than
                    # competing visually with the Trigger Type row above.
                    dbc.RadioItems(
                        id="event-trigger-mode",
                        options=[
                            {"label": "Any", "value": "any"},
                            {"label": "All", "value": "all"},
                        ],
                        value="any",
                        inline=True,
                        className="mb-1",
                        style={"fontSize": tokens.FS_BASE},
                    ),
                    html.Small(id="event-trigger-mode-hint",
                               className="text-muted d-block mb-2",
                               style={"fontSize": tokens.FS_CAP}),
                ]),

                html.Hr(className="my-3"),

                # Dormant Nodes Section
                html.Div([
                    html.Div([
                        html.H5("Dormant Nodes", className="mb-0"),
                        add_button("btn-add-dormant-node", "Add a dormant node to this event"),
                    ], className="d-flex align-items-center"),
                    # Trigger acts on the dormant nodes — placed here, not with
                    # Save/Delete. Visibility mirrors event-trigger-section.
                    html.Div(
                        dbc.Button("Trigger", id="btn-trigger-event", color="success", size="sm",
                                   style={"backgroundColor": _done_color, "borderColor": _done_color}),
                        id="event-trigger-btn-wrapper", className="ms-auto",
                    ),
                    dbc.Tooltip("Trigger this event and activate selected dormant nodes", target="btn-trigger-event", placement="left",
                                delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                ], className="d-flex align-items-center mb-3"),

                html.Div(id="dormant-nodes-table-container"),

                dbc.Modal([
                    dbc.ModalHeader(dbc.ModalTitle("Trigger Event")),
                    dbc.ModalBody([
                        html.P("Choose which nodes to activate. Nodes with a delay will be scheduled for future activation rather than appearing on the canvas right away."),
                        dbc.Switch(
                            id="manual-now-trigger-toggle",
                            label="Add nodes flagged \"Add to Now\" to the Now list",
                            value=False,
                            className="mt-2",
                        ),
                    ]),
                    dbc.ModalFooter([
                        dbc.Button("Cancel", id="btn-trigger-cancel", color="secondary", className="me-auto"),
                        dbc.Button("Trigger Checked", id="btn-trigger-confirm", color="success", className="me-2",
                                   style={"backgroundColor": _done_color, "borderColor": _done_color}),
                        dbc.Button("Trigger All", id="btn-trigger-all-confirm", color="success",
                                   style={"backgroundColor": _done_color, "borderColor": _done_color}),
                    ]),
                ], id="modal-confirm-trigger", size="md", is_open=False,
                   centered=True),
                dbc.Modal([
                    # Was the only delete confirm in the app opening as a naked
                    # body; the node-delete confirm in layout.py has carried a
                    # title all along for identical copy.
                    dbc.ModalHeader(dbc.ModalTitle("Confirm Delete")),
                    dbc.ModalBody("Are you sure you want to delete this event? This will also delete all its dormant nodes."),
                    dbc.ModalFooter([
                        dbc.Button("Cancel", id="btn-delete-cancel", color="secondary", className="me-2"),
                        dbc.Button("Delete", id="btn-delete-confirm", color="danger"),
                    ]),
                ], id="modal-confirm-delete", size="sm", is_open=False,
                   centered=True),
            ], style={"maxWidth": "650px"}),
        ]),
    ], id="events-detail-panel", style={
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
                       "backgroundColor": tokens.BG_CANVAS},
                userZoomingEnabled=False,
                userPanningEnabled=False,
                boxSelectionEnabled=True,
                autoungrabify=False,
                # Same reason as details-mini-graph: this canvas's layout
                # callback already takes `elements` as an Input, so
                # dash-cytoscape's own add/remove refresh would run fcose a
                # second time and restart the animation. See details_layout.py.
                autoRefreshLayout=False,
            ),
            dbc.Button(html.I(className="bi bi-gear"),
                       id="btn-events-graph-settings",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right"),
            dbc.Tooltip("Graph layout", target="btn-events-graph-settings", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            _freeze_indicator("events-freeze-indicator"),
            build_graph_settings_panel(
                "events-graph-settings",
                defaults_getter=ConfigManager.get_events_graph_layout_defaults,
            ),
            dbc.Button(html.I(className="bi bi-arrows-fullscreen"),
                       id="btn-events-graph-fullscreen",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right-mid"),
            dbc.Tooltip("Toggle fullscreen", target="btn-events-graph-fullscreen", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            html.Div(id="events-canvas-node-count", className="canvas-stats-overlay"),
        ], style={"position": "relative", "flex": "1", "minHeight": "0"}),
    ], id="events-detail-graph-container", style={
        "flex": "1 1 0",
        "minWidth": "0",
        "display": "flex",
        "flexDirection": "column",
    })

    # Draggable handle between the event detail panel and the event graph.
    # Wired by assets/events_resize.js; mirrors the details-tab vertical drag.
    v_drag_handle = html.Div(
        id="events-v-drag",
        style={
            "width": "6px",
            "cursor": "col-resize",
            "backgroundColor": "transparent",
            "borderLeft": f"1px solid {tokens.BORDER_PANEL}",
            "flexShrink": "0",
            "transition": "background-color 0.15s",
        },
    )

    return html.Div([
        dcc.Store(id='selected-event-store', data=None),
        dcc.Store(id='editing-dormant-node-store', data=None),
        dcc.Store(id='events-refresh-trigger', data=0),
        # Bumped clientside only when Events is actually opened. Heavy Events
        # content listens here instead of to every main-tab switch.
        dcc.Store(id='events-active-store', data=None),
        # UI-only refresh for the events sidebar list. Bumped by events_sidebar.js
        # once the open slide finishes so render_events_list re-runs — but NOT
        # an input to core_engine, so opening doesn't wait on a graph regen.
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
            v_drag_handle,
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
    if event.trigger_nodes:
        return "node"
    if event.trigger_date:
        return "date"
    return "manual"


def _event_badge(status, trigger_date, trigger_nodes=None):
    """Returns (badge_text, badge_palette_name) for an event."""
    if status == "Triggered":
        return "Triggered", "EventTriggered"
    if trigger_nodes:
        return "Completion", "EventTrigger"
    if trigger_date:
        return "Scheduled", "EventTrigger"
    return "Manual", "EventTrigger"


def format_trigger_summary(trigger_nodes, trigger_mode="any"):
    """One-line description of a node-completion trigger set.

    A single node reads as a plain name — the any/all distinction is
    meaningless at size 1 and would only add noise.
    """
    nodes = [n for n in (trigger_nodes or []) if n]
    if not nodes:
        return ""
    if len(nodes) == 1:
        return nodes[0]
    joiner = " AND " if trigger_mode == "all" else " OR "
    return joiner.join(nodes)


def build_event_card(event_name, description, status, node_count, is_selected=False,
                     trigger_date=None, trigger_nodes=None, trigger_mode="any",
                     show_drag_handle=True):
    """Builds a single event card for the list."""
    badge_text, badge_name = _event_badge(status, trigger_date, trigger_nodes)
    trigger_summary = format_trigger_summary(trigger_nodes, trigger_mode)
    border_style = f"2px solid {tokens.ACCENT}" if is_selected else f"1px solid {tokens.BORDER_PANEL}"

    drag_handle = html.Span(
        html.I(className="bi bi-grip-horizontal"), className="event-drag-handle",
        style={"cursor": "grab", "color": tokens.TEXT_DIM, "fontSize": tokens.FS_MD,
               "marginRight": "8px", "userSelect": "none"},
    ) if show_drag_handle else None

    children: List[Any] = [
        html.Div([
            html.Div([
                drag_handle,
                html.H6(event_name, className="mb-0", style={"fontWeight": "500"}),
            ], className="d-flex align-items-center"),
            html.Span(badge_text, className="badge ms-2",
                      style=badge_style(badge_name, font_size=tokens.FS_XS)),
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
            style={"fontSize": tokens.FS_SM}
        ))
    if trigger_summary and status != "Triggered":
        children.append(html.Small(
            f"Trigger: {trigger_summary}",
            className="text-muted d-block",
            style={"fontSize": tokens.FS_SM}
        ))
    children.append(html.Small(
        f"{node_count['total']} node{'s' if node_count['total'] != 1 else ''}"
        + (f" ({node_count['activated']} activated)" if node_count['activated'] > 0 else ""),
        className="text-muted",
        style={"fontSize": tokens.FS_SM}
    ))

    return html.Div(children, id={"type": "event-card", "index": event_name},
       className="mb-2 event-card rounded",
       **{"data-event-name": event_name, "data-event-status": status},
       style={
           "cursor": "pointer",
           "border": border_style,
           "backgroundColor": tokens.BG_RAISED if is_selected else tokens.BG_PANEL,
           "transition": "border-color 0.2s, background-color 0.2s",
           "padding": "10px 14px",
       })


def triggered_divider_text(count: int, shown: bool) -> str:
    """"2 triggered events hidden" while hidden, "2 triggered events" once shown."""
    noun = "event" if count == 1 else "events"
    return f"{count} triggered {noun}" + ("" if shown else " hidden")


def build_triggered_divider(count: int, shown: bool):
    """The rule at the end of the Events list that shows or hides triggered events.

    While shown, it sits above the triggered cards as their heading.
    """
    return html.Div([
        html.Span(className="events-triggered-rule"),
        html.Span([
            triggered_divider_text(count, shown),
            " · ",
            html.Button(
                "Hide" if shown else "Show",
                id={"type": "events-triggered-toggle", "index": "list"},
                type="button",
                className="events-triggered-toggle",
            ),
        ]),
        html.Span(className="events-triggered-rule"),
    ], className="events-triggered-divider")


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


# Fixed column widths hold the dormant table's grid still from one event to
# the next. With `table-layout: fixed` the Name column absorbs whatever is
# left over, so Type no longer shifts sideways just because one event happens
# to hold a longer node name. Name truncates with an ellipsis instead; the
# full text stays available on hover.
DORMANT_COL_WIDTHS = {
    "select": "32px",
    "type": "110px",
    "delay": "110px",
    "status": "90px",
    "actions": "84px",
}


def build_dormant_nodes_table(event_nodes, event_status):
    """Builds the dormant nodes table for an event detail view."""
    if not event_nodes:
        return html.Div(
            html.P("No dormant nodes yet. Click 'Add Node' to add one.", className="text-muted"),
            className="text-center py-3"
        )

    rows = []
    for en in event_nodes:
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

        # Every row carries Delay and Status, so the column grid is identical
        # for every event. A default value recedes rather than disappearing:
        # muted text keeps "None" and "Dormant" quiet enough that a real delay
        # or a woken node still stands out — without the absence of a whole
        # column having to carry that meaning by itself.
        if delay_days == 0:
            delay_cell = html.Span(delay_display, className="text-muted")
        else:
            delay_cell = [html.Span(delay_display)]
            if en.get('activation_date') and not activated:
                delay_cell.append(html.Small(
                    f"Scheduled: {en['activation_date']}",
                    className="text-muted d-block",
                    style={"fontSize": tokens.FS_XS}
                ))

        if activated:
            # Was dbc.Badge(color="success"), i.e. stock Bootstrap #198754 --
            # a visibly different green from the Done badge one table over.
            # EventTriggered is the palette's name for "the event fired", and
            # deliberately shares Done's value. Dormant stays muted text: a
            # default should recede rather than compete, which is the contract
            # test_events_layout.py pins down.
            status_cell = html.Span("Awake", className="badge",
                                    style=badge_style('EventTriggered',
                                                      font_size=tokens.FS_XS))
        else:
            status_cell = html.Span("Dormant", className="text-muted")

        # Checkbox: only shown for dormant (non-activated) nodes on non-triggered events
        if not activated and event_status != "Triggered":
            # The whole cell is the click target, not just this 14px box — see
            # the .dormant-node-select-cell rules in theme.css.
            trigger_checkbox = dbc.Checkbox(
                id={"type": "dormant-node-select", "index": node.name},
                value=True,
            )
        else:
            trigger_checkbox = html.Span()

        action_btns = None
        if not activated and event_status != "Triggered":
            edit_id = {"type": "btn-edit-dormant-node", "index": node.name}
            remove_id = {"type": "btn-remove-dormant-node", "index": node.name}
            edit_btn = dbc.Button(
                [
                    html.I(className="bi bi-pencil", **{"aria-hidden": "true"}),
                    html.Span(f"Edit dormant node {node.name}", className="visually-hidden"),
                ],
                id=edit_id, color="link",
                className="dormant-node-action-btn",
            )
            remove_btn = dbc.Button(
                [
                    html.I(className="bi bi-x-lg", **{"aria-hidden": "true"}),
                    html.Span(f"Remove dormant node {node.name}", className="visually-hidden"),
                ],
                id=remove_id, color="link",
                className="dormant-node-action-btn dormant-node-action-btn-danger",
            )
            action_btns = html.Div([
                edit_btn,
                dbc.Tooltip("Edit dormant node", target=edit_id, placement="left",
                            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                remove_btn,
                dbc.Tooltip("Remove dormant node", target=remove_id, placement="left",
                            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            ], className="dormant-node-actions d-flex gap-1 justify-content-end align-items-center")

        rows.append(html.Tr([
            html.Td(trigger_checkbox, className="dormant-node-select-cell",
                    style=tokens.CELL_PRIMARY),
            # title= keeps the full name reachable once the cell ellipsizes it.
            html.Td(node.name, className="dormant-node-name-cell", title=node.name,
                    style=tokens.CELL_PRIMARY),
            html.Td(node.type, style=tokens.CELL_MUTED),
            html.Td(delay_cell, style=tokens.CELL_PRIMARY),
            html.Td(status_cell, style=tokens.CELL_PRIMARY),
            html.Td(action_btns, style={"verticalAlign": "middle", "textAlign": "right"}),
        ], className="dormant-node-row"))

    headers = [
        html.Th("", style={"width": DORMANT_COL_WIDTHS["select"]}),
        html.Th("Name"),
        html.Th("Type", style={"width": DORMANT_COL_WIDTHS["type"]}),
        html.Th("Delay", style={"width": DORMANT_COL_WIDTHS["delay"]}),
        html.Th("Status", style={"width": DORMANT_COL_WIDTHS["status"]}),
        html.Th(html.Span("Actions", className="visually-hidden"),
                style={"width": DORMANT_COL_WIDTHS["actions"]}),
    ]

    return dbc.Table([
        html.Thead(html.Tr(headers)),
        html.Tbody(rows),
    ], **tokens.TABLE_PROPS,
       className=f"dormant-nodes-table {tokens.TABLE_CLASS}",
       style={**tokens.TABLE_STYLE, "tableLayout": "fixed"})
