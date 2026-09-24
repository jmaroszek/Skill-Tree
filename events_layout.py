"""
Layout definitions for the Events tab.
"""

import style_tokens as tokens
from duration_ui import DURATION_UNITS, unit_select, format_duration_days
from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from typing import List, Any
from datetime import date, timedelta
from config import ConfigManager, TOAST_CLEAR_INTERVAL_MS, badge_style
from styles import events_graph_stylesheet
from details_layout import build_graph_settings_panel, _freeze_indicator
from list_toolbar import EVENTS_SORT, SEARCH_STYLE, build_list_toolbar
from ui_kit import (Tooltip, add_button, confirm_action, danger_action,
                    done_color, panel_close_button, primary_action)


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
    # Triggering an event is its "done" moment — tint the button with the
    # node-status Done color rather than a loud default green.
    _done_color = done_color()

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

                # --- Name + close ---
                # The row is a title, not a control strip. Every verb now
                # lives in the Actions section below, so the only thing left
                # up here is the dismiss -- the same panel_close_button, in
                # the same corner, that the Events sidebar header one column
                # to the left already uses.
                html.Div([
                    dbc.Input(id="event-name", type="text", placeholder="Name event...",
                              className="flex-grow-1",
                              style={"fontSize": tokens.FS_2XL, "fontWeight": "300", "backgroundColor": "transparent",
                                     "border": "none", "color": tokens.TEXT_PRIMARY,
                                     "borderRadius": "0", "paddingLeft": "0"}),
                    panel_close_button("btn-event-close",
                                       "Close this event without changing it",
                                       placement="bottom",
                                       className_extra="ms-2"),
                ], className="d-flex align-items-center mt-3 mb-0",
                   style={"borderBottom": f"1px solid {tokens.BORDER_PANEL}"}),

                # --- Description ---
                dbc.Label("Description", className="mt-3 mb-1"),
                dbc.Textarea(id="event-description", rows=3,
                             style={"height": "90px", "resize": "vertical"}),

                # --- Trigger Type ---
                # Section rhythm: every label in this pane carries mt-3 and
                # owns the whole gap above it, and nothing above a label
                # carries a bottom margin. The three sections used to sit 4px,
                # 16px and 24px apart, because a trailing mb-2 inside the
                # trigger sub-sections stacked on the next label's mt-3
                # instead of collapsing into it. Spacing between a control and
                # the one it depends on therefore hangs off the dependent
                # element's top, never the parent's bottom.
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
                    className="mb-0",
                    # Options should sit below their section label, not match
                    # it. Both were at the browser default, which made the
                    # three choices read louder than the question.
                    style={"fontSize": tokens.FS_BASE},
                ),

                # Date trigger section
                html.Div(id="event-date-section", style={"display": "none"}, children=[
                    html.Div([
                        dbc.Input(id="event-trigger-date", type="date",  # type: ignore[reportArgumentType]
                                  style={"maxWidth": "200px"}),
                        html.Small("Auto-triggers on or after this date.",
                                   className="text-muted ms-2 align-self-center",
                                   style={"fontSize": tokens.FS_CAP}),
                    ], className="d-flex align-items-center mt-2"),
                ]),

                # Node completion trigger section
                html.Div(id="event-node-section", style={"display": "none"}, children=[
                    html.Div(
                        dcc.Dropdown(
                            id="event-trigger-node",
                            placeholder="Select one or more nodes...",
                            multi=True,
                        ),
                        className="text-dark mt-2",
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
                        className="mt-2",
                        style={"fontSize": tokens.FS_BASE},
                    ),
                    html.Small(id="event-trigger-mode-hint",
                               className="text-muted d-block mt-1",
                               style={"fontSize": tokens.FS_CAP}),
                ]),

                # --- Actions ---
                # One labelled section holding every verb the event has, in
                # the same shape as the Trigger Type section above it: a
                # dbc.Label, then its controls on the line beneath, left
                # aligned. The buttons used to be scattered -- Delete and Save
                # crowding the title, Trigger down beside the dormant table --
                # which meant no single place answered "what can I do here?".
                #
                # Trigger gives up its adjacency to the roster it fires. The
                # confirm modal already previews exactly which nodes will
                # wake, so the table is not the only preview of the action.
                #
                # Order is the node editor's: danger, then the plain commit,
                # then the commit that also finishes. They take size="sm"
                # rather than the style guide's default form-action size --
                # the pane is narrow and sits beside a dense table, where
                # full-size buttons read as a slab.
                #
                # Neither wrapper may carry a Bootstrap display utility --
                # .d-flex and friends are `!important` and beat the inline
                # `display: none` the callbacks write, which is how Delete
                # stayed on screen for new and triggered events for as long as
                # it shared a .d-flex box with Save.
                dbc.Label("Actions", className="mt-3 mb-1"),
                html.Div([
                    html.Div(
                        danger_action("Delete", "btn-event-delete", size="sm"),
                        id="event-delete-wrapper", className="me-2",
                    ),
                    primary_action("Save", "btn-event-save", size="sm",
                                   className="me-2"),
                    html.Div(
                        confirm_action("Trigger", "btn-trigger-event", size="sm",
                                       style={"backgroundColor": _done_color,
                                              "borderColor": _done_color}),
                        id="event-trigger-btn-wrapper",
                    ),
                    # The save confirmation rides beside the button that
                    # causes it rather than under the title, a panel's height
                    # away, where it used to appear.
                    html.Div(id="event-save-status", className="text-success ms-3",
                             style={"fontSize": tokens.FS_BASE, "minHeight": "1.2em"}),
                ], className="d-flex align-items-center mb-2"),
                Tooltip("Delete this event and its dormant nodes",
                        target="btn-event-delete", placement="bottom"),
                Tooltip("Save changes to this event",
                        target="btn-event-save", placement="bottom"),
                Tooltip("Trigger this event and activate its dormant nodes",
                        target="btn-trigger-event", placement="bottom"),

                html.Hr(className="my-3"),

                # Dormant Nodes Section
                # Heading plus its adders, nothing else: Trigger moved up to
                # the Actions section, so this row is now purely the label for
                # the table under it. "+" opens the node editor on a new node
                # already set Dormant under this event; "Add existing" puts
                # nodes that already exist to sleep here.
                html.Div([
                    html.H5("Dormant Nodes", className="mb-0"),
                    html.Div([
                        add_button("btn-add-dormant-node",
                                   "Add a new dormant node to this event"),
                        dbc.Button("Add existing", id="btn-add-existing-to-event",
                                   color="link", size="sm",
                                   className="p-0 ms-2 text-decoration-none"),
                        Tooltip("Put existing nodes to sleep under this event",
                                target="btn-add-existing-to-event", placement="right"),
                    ], id="dormant-add-btn-wrapper"),
                ], className="d-flex align-items-center mb-3"),

                html.Div(id="dormant-nodes-table-container"),

                # One action. "Trigger Checked" and "Trigger All" used to sit
                # here side by side, but a checked trigger marked the whole
                # event Triggered anyway, so the unchecked rows were stranded
                # rather than staged. The body earns the space instead: it is
                # the last look at what firing will do.
                dbc.Modal([
                    dbc.ModalHeader(dbc.ModalTitle("Trigger Event")),
                    dbc.ModalBody([
                        html.Div(id="trigger-confirm-body"),
                        dbc.Switch(
                            id="manual-now-trigger-toggle",
                            label="Also add every other node that wakes now to the Now list",
                            value=False,
                            className="mt-3",
                        ),
                    ]),
                    dbc.ModalFooter([
                        dbc.Button("Cancel", id="btn-trigger-cancel", color="secondary", className="me-auto"),
                        dbc.Button("Trigger Event", id="btn-trigger-confirm", color="success",
                                   style={"backgroundColor": _done_color, "borderColor": _done_color}),
                    ]),
                ], id="modal-confirm-trigger", size="md", is_open=False,
                   centered=True),
                # Moving is what replaced staged release. Firing takes every
                # node an event holds, so "not this one yet" is said by putting
                # the node somewhere that has not fired.
                dbc.Modal([
                    dbc.ModalHeader(dbc.ModalTitle(id="move-dormant-title")),
                    dbc.ModalBody([
                        dbc.Label("Move to", className="mb-1"),
                        # No preselected event: moving a node is a choice, not
                        # a default. The placeholder is what the empty control
                        # says while that is true -- dropdowns.css already has
                        # the placeholder gray for exactly this shape.
                        dbc.Select(id="move-dormant-target-event", options=[],
                                   value=None,
                                   placeholder="Select an event..."),
                        html.Div(id="move-dormant-note",
                                 className="text-muted mt-2",
                                 style={"fontSize": tokens.FS_CAP}),
                        html.Div(id="move-dormant-status", className="text-danger mt-2"),
                    ]),
                    dbc.ModalFooter([
                        dbc.Button("Cancel", id="btn-move-dormant-cancel",
                                   color="secondary", className="me-2"),
                        dbc.Button("Move", id="btn-move-dormant-confirm",
                                   color="primary"),
                    ]),
                ], id="modal-move-dormant-node", size="md", is_open=False,
                   centered=True),
                dcc.Store(id="move-dormant-node-store", data=None),
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
            Tooltip("Graph layout", target="btn-events-graph-settings", placement="left"),
            _freeze_indicator("events-freeze-indicator"),
            build_graph_settings_panel(
                "events-graph-settings",
                defaults_getter=ConfigManager.get_events_graph_layout_defaults,
            ),
            dbc.Button(html.I(className="bi bi-arrows-fullscreen"),
                       id="btn-events-graph-fullscreen",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right-mid"),
            Tooltip("Toggle fullscreen", target="btn-events-graph-fullscreen", placement="left"),
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
    """Returns (badge_text, badge_palette_name) for an event.

    The three trigger badges name the *mechanism* — Manual, Date, Completion.
    The date one read "Scheduled" until the dormant table started using that
    word for a node whose wake date is set, where it describes a state rather
    than a mechanism. docs/features.md already called this trigger type Date.
    """
    if status == "Triggered":
        return "Triggered", "EventTriggered"
    if trigger_nodes:
        return "Completion", "EventTrigger"
    if trigger_date:
        return "Date", "EventTrigger"
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
        children.append(html.Small(
            description,
            className="event-card-description text-muted mb-1"
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
    # A fired event that is still listed has work outstanding, and the card
    # should say what, rather than leaving the user to wonder why it is here.
    waiting = node_count['total'] - node_count['activated']
    if status == "Triggered" and waiting > 0:
        count_text = (f"{node_count['total']} node"
                      f"{'s' if node_count['total'] != 1 else ''}"
                      f" · {waiting} waking later")
    else:
        count_text = (
            f"{node_count['total']} node{'s' if node_count['total'] != 1 else ''}"
            + (f" ({node_count['activated']} activated)"
               if node_count['activated'] > 0 else "")
        )
    children.append(html.Small(
        count_text,
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
    """"2 finished events hidden" while hidden, "2 finished events" once shown.

    Said "triggered" until a fired event with nodes still waiting started
    staying in the list, at which point "triggered" no longer described the
    ones below the rule. Finished does: fired, with nothing left to wake.
    """
    noun = "event" if count == 1 else "events"
    return f"{count} finished {noun}" + ("" if shown else " hidden")


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


# Fixed column widths hold the dormant table's grid still from one event to
# the next. With `table-layout: fixed` the Name column absorbs whatever is
# left over, so Type no longer shifts sideways just because one event happens
# to hold a longer node name. Name truncates with an ellipsis instead; the
# full text stays available on hover.
DORMANT_COL_WIDTHS = {
    "type": "100px",
    "delay": "90px",
    "wakes": "130px",
    "actions": "112px",
}


def _format_wake_date(iso_date: str) -> str:
    """An ISO date as `Oct 1`, or `Oct 1, 2027` when it is not this year.

    The year is the part that only sometimes carries information, so it only
    sometimes appears. The full ISO string stays in the cell's title.
    """
    try:
        when = date.fromisoformat(iso_date)
    except (TypeError, ValueError):
        return iso_date or ""
    stamp = f"{when.strftime('%b')} {when.day}"
    return stamp if when.year == date.today().year else f"{stamp}, {when.year}"


def _projected_wake(event, delay_days: int) -> str:
    """When an unfired row will wake, as far as the event can say.

    A date-triggered event knows: its date plus the row's delay. Manual and
    completion events do not, so they answer in offsets instead. Naming the
    offset twice (Delay says "2 weeks", this says "2 weeks after") is mild
    redundancy in exchange for the Wakes column always answering its own
    question.
    """
    if event is not None and _event_trigger_type(event) == "date":
        try:
            when = date.fromisoformat(event.trigger_date) + timedelta(days=delay_days)
        except (TypeError, ValueError):
            pass
        else:
            return _format_wake_date(when.isoformat())
    if delay_days == 0:
        return "On trigger"
    return f"{format_duration_days(delay_days)} after"


def _wakes_cell(en, event):
    """The Wakes column: when this node wakes, or that it already has.

    It replaced a Status column that could only say "Dormant" before an event
    fired -- true of every row, so it carried nothing. Status is folded in
    here: a plain date means still waiting, a badge means already awake.

    Contrast does the rest of the work. A projected date is muted because the
    event has not fired and the date can still move; a date written at firing
    is full contrast because it is committed.
    """
    node = en['node']
    activation_date = en.get('activation_date')

    if not node.dormant:
        badge = html.Span("Awake", className="badge",
                          style=badge_style('EventTriggered',
                                            font_size=tokens.FS_XS))
        if en.get('activated'):
            return badge
        # Awake without this row firing: some other event got there first, or
        # the node was woken outside the event system entirely. Either way the
        # old table called it Dormant, which was simply untrue.
        woken_by = en.get('woken_by')
        note = f"via {woken_by}" if woken_by else "woken outside this event"
        return [badge, html.Small(note, className="text-muted d-block",
                                  style={"fontSize": tokens.FS_XS})]

    if activation_date:
        when = html.Span(_format_wake_date(activation_date),
                         title=activation_date)
    else:
        when = html.Span(_projected_wake(event, en['delay_days']),
                         className="text-muted")
    if not en.get('now_on_trigger'):
        return when
    # Only while the node is still asleep: once it wakes the intent is spent,
    # and the badge above reports what actually happened.
    return [when, html.I(
        className="bi bi-play-circle ms-2 dormant-now-marker",
        title="Will be added to Now when it wakes",
        role="img", **{"aria-label": "Will be added to Now when it wakes"})]


def _dormant_row_actions(node_name: str):
    """Edit / Move / Remove for one row, or None when it has nothing to act on.

    Gated per row rather than per event. A Pending event can hold an awake
    node (another event woke it) and a fired event can still hold scheduled
    ones, so the event's own status was never the right question.
    """
    ids = {
        action: {"type": f"btn-{action}-dormant-node", "index": node_name}
        for action in ("edit", "move", "remove")
    }
    specs = [
        ("edit", "bi bi-pencil", f"Edit dormant node {node_name}",
         "Edit dormant node", ""),
        ("move", "bi bi-box-arrow-right",
         f"Move dormant node {node_name} to another event",
         "Move to another event", ""),
        ("remove", "bi bi-x-lg", f"Remove dormant node {node_name}",
         "Remove dormant node", " dormant-node-action-btn-danger"),
    ]
    children = []
    for action, icon, label, tip, extra_class in specs:
        children.append(dbc.Button(
            [
                html.I(className=icon, **{"aria-hidden": "true"}),
                html.Span(label, className="visually-hidden"),
            ],
            id=ids[action], color="link",
            className=f"dormant-node-action-btn{extra_class}",
        ))
        children.append(Tooltip(
            tip, target=ids[action], placement="left"))
    return html.Div(
        children,
        className="dormant-node-actions d-flex gap-1 justify-content-end align-items-center")


#: Above this many scheduled nodes, listing every wake date stops being
#: scannable and the summary gives a count instead.
_TRIGGER_SUMMARY_DATE_LIMIT = 5


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def trigger_confirmation_body(event_name, event_nodes):
    """What firing this event will actually do, for the confirm modal.

    Firing takes every node the event holds, so this summary is the last
    place to notice one you did not mean to release — which is the job the
    row checkboxes used to do badly. It names the nodes waking now for that
    reason, and the wake dates while there are few enough to read.
    """
    pending = [en for en in event_nodes if not en['activated']]
    waking = [en for en in pending if en['node'].dormant and not en['delay_days']]
    scheduled = [en for en in pending if en['node'].dormant and en['delay_days']]
    # Some other event got here first. Counting these as woken would claim a
    # wake that is not going to happen.
    already = [en for en in pending if not en['node'].dormant]

    lines = [html.P(f'Trigger "{event_name}"?', className="mb-2")]

    if not pending:
        lines.append(html.P(
            "This event has no dormant nodes left to wake. Triggering it will "
            "just mark it Triggered.",
            className="text-muted mb-0"))
        return lines

    if waking:
        names = ", ".join(en['node'].name for en in waking)
        lines.append(html.P(
            f"{_plural(len(waking), 'node')} will wake now: {names}.",
            className="mb-2"))
        # Flagged ones only. The switch below widens this to every node that
        # wakes now, and says so itself.
        flagged = [en['node'].name for en in waking if en.get('now_on_trigger')]
        if flagged:
            lines.append(html.P(
                f"Added to Now, if there is room: {', '.join(flagged)}.",
                className="mb-2"))

    if scheduled:
        lines.append(html.P(
            f"{len(scheduled)} will be scheduled for later:"
            if len(scheduled) <= _TRIGGER_SUMMARY_DATE_LIMIT
            else f"{len(scheduled)} will be scheduled for later.",
            className="mb-1"))
        if len(scheduled) <= _TRIGGER_SUMMARY_DATE_LIMIT:
            lines.append(html.Ul(
                [html.Li([
                    en['node'].name,
                    html.Span(
                        f" — wakes {_format_wake_date((date.today() + timedelta(days=en['delay_days'])).isoformat())}"
                        + (", then added to Now" if en.get('now_on_trigger') else ""),
                        className="text-muted"),
                ]) for en in scheduled],
                className="mb-2"))
        else:
            # The list is collapsed, so the Now flag would vanish with it.
            later_now = sum(1 for en in scheduled if en.get('now_on_trigger'))
            if later_now:
                lines.append(html.P(
                    f"{later_now} of them will be added to Now when they wake.",
                    className="text-muted mb-2"))

    if already:
        names = ", ".join(en['node'].name for en in already)
        lines.append(html.P(
            f"{_plural(len(already), 'node')} already awake: {names}.",
            className="text-muted mb-0"))

    return lines


def build_dormant_nodes_table(event_nodes, event=None):
    """Builds the dormant nodes table for an event detail view.

    `event` is only consulted to project a wake date for rows that have not
    fired yet; every row's own state comes from the row. It used to be the
    event's status string, which decided whether a row got actions -- a
    question the row now answers for itself.
    """
    if not event_nodes:
        return html.Div(
            html.P("No dormant nodes yet. Click 'Add Node' to add one.", className="text-muted"),
            className="text-center py-3"
        )

    rows = []
    for en in event_nodes:
        node = en['node']
        delay_days = en['delay_days']

        # A default value recedes rather than disappearing: muted text keeps
        # "None" quiet enough that a real delay still stands out, without the
        # absence of a whole column having to carry that meaning by itself.
        delay_display = format_duration_days(delay_days)
        delay_cell = (html.Span(delay_display, className="text-muted")
                      if delay_days == 0 else html.Span(delay_display))

        rows.append(html.Tr([
            # title= keeps the full name reachable once the cell ellipsizes it.
            html.Td(node.name, className="dormant-node-name-cell", title=node.name,
                    style=tokens.CELL_PRIMARY),
            html.Td(node.type, style=tokens.CELL_MUTED),
            html.Td(delay_cell, style=tokens.CELL_PRIMARY),
            html.Td(_wakes_cell(en, event), style=tokens.CELL_PRIMARY),
            html.Td(None if not node.dormant else _dormant_row_actions(node.name),
                    style={"verticalAlign": "middle", "textAlign": "right"}),
        ], className="dormant-node-row"))

    headers = [
        html.Th("Name"),
        html.Th("Type", style={"width": DORMANT_COL_WIDTHS["type"]}),
        html.Th("Delay", style={"width": DORMANT_COL_WIDTHS["delay"]}),
        html.Th("Wakes", style={"width": DORMANT_COL_WIDTHS["wakes"]}),
        html.Th(html.Span("Actions", className="visually-hidden"),
                style={"width": DORMANT_COL_WIDTHS["actions"]}),
    ]

    return dbc.Table([
        html.Thead(html.Tr(headers)),
        html.Tbody(rows),
    ], **tokens.TABLE_PROPS,
       className=f"dormant-nodes-table {tokens.TABLE_CLASS}",
       style={**tokens.TABLE_STYLE, "tableLayout": "fixed"})


# --- Node editor: Events section ---
# The node editor lists every event a dormant node is waiting on. Each row is
# a [event, delay value, delay unit, wake date, add-to-Now] list from
# callback_helpers.membership_form_rows. Before an event fires the row edits
# a delay; after it fires the row edits the wake date it was given, because
# the delay has nothing left to measure from (see
# docs/dormant_node_triggering.md).

def delay_fields(wrapper_id, value_id, unit_id, value, unit, visible):
    """The "[n] [unit] after it fires" row behind a Delay switch.

    The wrapper carries the shown/hidden style and the inner row the flex:
    Bootstrap's .d-flex is `!important` and would beat `display: none`.
    """
    return html.Div(id=wrapper_id, style={} if visible else {"display": "none"},
                    className="w-100 mb-1", children=html.Div([
        dbc.Input(id=value_id, type="number", min=0, value=value, size="sm",
                  style={"width": "80px"}),
        unit_select(unit_id, units=DURATION_UNITS, value=unit,
                    compact=True, className="ms-2"),
        html.Small("after it fires", className="text-muted ms-2"),
    ], className="d-flex align-items-center"))


def wake_switches(delay_switch, fields, now_switch):
    """Delay and Add to Now side by side, the way the Status toggles sit.

    The delay fields span the full width, so turning Delay on wraps them onto
    their own line and pushes Add to Now below them.
    """
    return html.Div([delay_switch, fields, now_switch],
                    className="d-flex flex-wrap align-items-center",
                    style={"columnGap": "1rem", "rowGap": "0.25rem"})


def build_event_membership_rows(rows):
    """Rows for the node editor's Events section, one per waiting event.

    Each row is headed by its event's name, set as a label like the section's
    other subheadings. Most nodes wake the moment their event fires, so the
    delay stays behind a switch until it is wanted.
    """
    out = []
    for event, delay_value, delay_unit, wake_date, now in rows or []:
        now_switch = dbc.Checklist(
            id={"type": "membership-now", "index": event},
            options=[{"label": "Add to Now", "value": "on"}],
            value=["on"] if now else [],
            switch=True,
        )
        if wake_date is not None:
            when = [
                dbc.Input(id={"type": "membership-wake-date", "index": event},
                          type="date", value=wake_date, size="sm",  # type: ignore[reportArgumentType]
                          style={"maxWidth": "170px"}),
                html.Small("Wake date. This event has already fired.",
                           className="text-muted d-block mt-1 mb-1"),
                now_switch,
            ]
        else:
            has_delay = bool(delay_value)
            when = [wake_switches(
                dbc.Checklist(
                    id={"type": "membership-delay-on", "index": event},
                    options=[{"label": "Delay", "value": "on"}],
                    value=["on"] if has_delay else [],
                    switch=True,
                ),
                delay_fields({"type": "membership-delay-fields", "index": event},
                             {"type": "membership-delay-value", "index": event},
                             {"type": "membership-delay-unit", "index": event},
                             delay_value if has_delay else 0,
                             delay_unit if has_delay else "days", has_delay),
                now_switch,
            )]
        out.append(html.Div([
            dbc.Label(event, className="mt-2 mb-1"),
            *when,
        ], className="event-membership-row"))
    return out


# --- Add to Event modal ---
# Puts existing nodes to sleep under an event, several at once. Opened by the
# canvas context menu's "Add to Event…" and the Events tab's "Add existing".
# Creating nodes, and editing a dormant node, happen in the node editor.

def build_add_to_event_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Add to Event")),
        dbc.ModalBody([
            dbc.Label("Nodes", className="mb-1"),
            html.Div(dcc.Dropdown(id="add-to-event-nodes", multi=True, options=[],
                                  placeholder="Select nodes..."),
                     className="text-dark"),
            dbc.Label("Event", className="mt-3 mb-1"),
            dbc.Select(id="add-to-event-target", options=[], value=None,
                       placeholder="Select an event..."),
            dbc.Label("Activation Delay", className="mt-3 mb-1"),
            html.Div([
                dbc.Input(id="add-to-event-delay-value", type="number", min=0,
                          value=0, style={"width": "90px"}),
                unit_select("add-to-event-delay-unit", units=DURATION_UNITS,
                            value="days", className="ms-2",
                            style={"width": "120px"}),
            ], className="d-flex align-items-center"),
            html.Small("How long after the event fires before these nodes wake.",
                       className="text-muted d-block mt-1"),
            dbc.Checklist(
                id="add-to-event-now",
                options=[{"label": "Add to Now on wake", "value": "on"}],
                value=[],
                switch=True,
                className="mt-3",
            ),
            html.Div(id="add-to-event-status", className="text-danger mt-2"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-add-to-event-cancel", color="secondary",
                       className="me-2"),
            dbc.Button("Add to Event", id="btn-add-to-event-save", color="primary"),
        ]),
    ], id="modal-add-to-event", size="md", is_open=False, centered=True)
