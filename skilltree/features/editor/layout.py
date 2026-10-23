"""The node editor's layout."""
import dash
import dash_bootstrap_components as dbc
from dash import html
from skilltree.store import settings
from skilltree.ui import tokens
from skilltree.ui.components.ratings_table import (
    HEADER_CELL_STYLE,
)
from skilltree.ui.components.ratings_table import build_popup_table_rows
from skilltree.ui.kit import edit_button
from skilltree.ui.kit import panel_close_button
from skilltree.ui.components.duration import DURATION_UNITS
from skilltree.ui.components.duration import unit_select
from dash import dcc
from skilltree.domain.contexts import sort_contexts
from skilltree.domain.models import STATUS_DONE
from skilltree.store.settings import SUPPORTED_NODE_TYPES
from skilltree.ui.components.context_picker import build_single_context_picker
from skilltree.ui.components.duration import NEW_NODE_TIME_UNIT
from skilltree.ui.components.duration import bracket_label
from skilltree.ui.components.duration import time_estimates_heading
from skilltree.ui.kit import Tooltip
from skilltree.ui.kit import add_button
from skilltree.ui.kit import bullet_hint
from skilltree.ui.kit import cancel_action
from skilltree.ui.kit import danger_action
from skilltree.ui.kit import hover_label
from skilltree.ui.kit import info_button
from skilltree.ui.kit import primary_action
from skilltree.ui.styles import SIDEBAR_TRANSLATE_CLOSED
from skilltree.ui.styles import SIDEBAR_WIDTH_PX


def render_alias_rows(aliases, input_type="alias-input", remove_type="btn-alias-remove"):
    """Build the alias input rows (one unified field per alias, trailing ×).

    Shared by the main node editor and the add-node modals (dormant / subtask);
    callers pass the prefixed pattern-matching id types so each surface keeps
    its own component namespace. Mirrors render_resource_sections' visual style.
    """
    alias_list = aliases or ['']
    rows = []
    for i, val in enumerate(alias_list):
        rows.append(html.Div([
            dbc.Input(id={'type': input_type, 'index': i}, type='text',
                      value=val or '', placeholder='Enter alias...'),
            dbc.Button(html.I(className='bi bi-x-lg'),
                       id={'type': remove_type, 'index': i}, title='Remove alias',
                       className='editor-icon-btn editor-icon-btn-danger'),
        ], className='d-flex editor-field-group mb-1'))
    return rows


def alias_rows_label(aliases):
    """Return the singular/plural label for the rendered alias row count."""
    return "Alias" if len(aliases or ['']) == 1 else "Aliases"


def update_alias_rows(trigger, current_values, stored_values, aliases_open,
                      add_button_id, remove_button_type):
    """Apply one add/remove action to an editor's repeatable alias rows.

    The first click on the Name-label ``+`` reveals the existing first row;
    later clicks add rows. Removing the final row closes the optional section,
    ready for the next ``+`` click to reveal a fresh blank row.
    """
    aliases = (list(current_values) if current_values
               else list(stored_values or ['']))
    collapse_update = dash.no_update

    if trigger == add_button_id:
        if aliases_open:
            aliases.append('')
        collapse_update = True
    elif (isinstance(trigger, dict)
          and trigger.get('type') == remove_button_type):
        idx = trigger.get('index')
        if isinstance(idx, int) and 0 <= idx < len(aliases):
            aliases.pop(idx)
            if not aliases:
                collapse_update = False

    return aliases, collapse_update


def build_unsaved_changes_modal():
    return dbc.Modal([
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


def build_delete_confirm_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Confirm Delete")),
        # Names the node when it opens (callbacks.toggle_delete_modal).
        dbc.ModalBody("Are you sure you want to delete this node? This action cannot be undone.",
                      id="node-delete-confirm-body"),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-node-delete-cancel", color="secondary", className="flex-fill me-2"),
            dbc.Button("Delete", id="btn-node-delete-confirm", color="danger", className="flex-fill"),
        ], className="d-flex"),
    ], id="modal-node-delete-confirm", size="sm", is_open=False, centered=True)


# The same question for a node editor save: a new Hard prerequisite that isn't
# Done reopens the Done node it leads to. core_engine holds the save, and its
# Save button runs it again once the user agrees.
def build_editor_reopen_confirm_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Reopen Done Nodes?")),
        dbc.ModalBody(id="editor-reopen-confirm-body"),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-editor-reopen-cancel", color="secondary", className="flex-fill me-2"),
            dbc.Button("Save", id="btn-editor-reopen-confirm", color="warning", className="flex-fill"),
        ], className="d-flex"),
    ], id="modal-editor-reopen-confirm", size="sm", is_open=False, centered=True)


def build_ratings_popup():
    return html.Div([
        # Draggable header
        html.Div([
            html.Span("Ratings Reference", style={"fontWeight": "600", "fontSize": tokens.FS_MD}),
            edit_button("btn-ratings-edit", "Edit definitions",
                        className_extra="ms-2"),
            panel_close_button("btn-ratings-close", "Close ratings reference",
                               style={"marginLeft": "auto"}),
        ], id="ratings-popup-header", className="d-flex align-items-center", style={
            "cursor": "move",
            "padding": "8px 10px",
            "backgroundColor": tokens.BG_RAISED,
            "borderBottom": f"1px solid {tokens.BORDER_PANEL}",
            "borderRadius": "6px 6px 0 0",
            "flexShrink": "0",
            "userSelect": "none",
        }),
        # Scrollable body
        html.Div([
            html.Table([
                html.Thead(html.Tr([
                    html.Th("#", style={**HEADER_CELL_STYLE, "width": "36px"}),
                    html.Th("Value", style=HEADER_CELL_STYLE),
                    html.Th("Interest", style=HEADER_CELL_STYLE),
                    html.Th("Effort", style=HEADER_CELL_STYLE),
                ])),
                html.Tbody(
                    id="ratings-popup-table-body",
                    children=build_popup_table_rows(settings.RATINGS_DEFINITIONS.get()),
                ),
            ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": tokens.FS_CAP, "color": tokens.TEXT_PRIMARY}),
        ], style={"overflow": "auto", "flex": "1", "padding": "4px"}),
    ], id="ratings-popup", style={
        "display": "none",
        "flexDirection": "column",
        "position": "fixed",
        "top": "120px",
        "left": "420px",
        "width": "960px",
        "height": "auto",
        "maxHeight": "calc(100vh - 160px)",
        "minWidth": "400px",
        "minHeight": "200px",
        "zIndex": 9998,
        "backgroundColor": tokens.BG_PANEL,
        "border": f"1px solid {tokens.BORDER_PANEL}",
        "borderRadius": "6px",
        "boxShadow": "0 4px 16px rgba(0,0,0,0.5)",
        "resize": "both",
        "overflow": "hidden",
    })


def build_ratings_editor_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Edit Ratings Definitions")),
        dbc.ModalBody(
            html.Div(id="ratings-editor-body"),
            style={"maxHeight": "70vh", "overflowY": "auto"},
        ),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-ratings-editor-cancel", color="secondary", className="me-auto"),
            dbc.Button("Save", id="btn-ratings-editor-save", color="primary"),
        ]),
    ], id="modal-ratings-editor", size="xl", is_open=False, centered=True,
       scrollable=True)


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


# Weekday toggle-pill options for the habit per-session scheduler. Values are
# weekday indices (0=Mon … 6=Sun); displayed Sunday-first to match the
# Apple-style day picker. Single-letter labels.
# Save's tooltip while it is on. While it is off, the tooltip says why.
SAVE_HINT = "Save changes"


WEEKDAY_OPTIONS = [
    {"label": "S", "value": 6}, {"label": "M", "value": 0},
    {"label": "T", "value": 1}, {"label": "W", "value": 2},
    {"label": "T", "value": 3}, {"label": "F", "value": 4},
    {"label": "S", "value": 5},
]


# Hover copy for the editor's labels: short, with the long form in docs/. Anything
# that enumerates is a bullet list. Edge direction is easy to get backwards:
# A --Needs--> B means A unlocks B.
_EDITOR_HINTS = {
    "type": bullet_hint(
        "What kind of node this is:",
        "Resource: a book, course or notes.",
        "Action: a practice with a definite end.",
        "Milestone: a measurable one-time achievement.",
        "Goal: an area you are developing.",
        "Learn: a topic to understand."),
    "context": "The broad area. The subcontext narrows it.",
    "status": bullet_hint(
        "Where this node stands:",
        "Now: something you want to do now.",
        "Done: finished.",
        "Dormant: asleep until an event wakes it."),
    "event": "The event that wakes this node.",
    "wake": bullet_hint(
        "When the event fires:",
        "Delay: wait longer before waking.",
        "Add to Now: put the node on your Now list."),
    "relationships": "Needs and Supports are the same links seen from opposite ends.",
    "needs": bullet_hint(
        "Prerequisites. They come first and unlock this node.",
        "Hard: blocks this node until done.",
        "Soft: helps, but does not block."),
    "supports": bullet_hint(
        "What this node unlocks.",
        "Hard: blocks them until this is done.",
        "Soft: helps them, but does not block."),
    "helps": "Mutual boost: doing both is worth more than the sum. Does not block.",
    "resources": "External material that helps with this project. Add more types in Settings.",
    "ratings_inherit": "Take value and interest from the nodes inside this one.",
    "time_inherit": "Take time from the nodes inside this one.",
    "habit": "A routine spread over weeks. Enter how long it runs, the minutes per session and the days.",
}


# --- Node Editor sidebar (left) ---
def build_node_editor_content():
    CONTEXTS = sort_contexts(settings.CONTEXTS.get(),
                             settings.CONTEXT_SORT_MODE.get())
    return html.Div(
        [
            html.Div([
                html.Div([
                    html.H4("Node Editor", className="mb-0"),
                    add_button("btn-editor-new", "New node", large=True),
                ], className="d-flex align-items-center"),
                panel_close_button("btn-close-editor", "Close node editor", large=True)
            # Sticky, so New node and Close stay in reach from anywhere in the
            # form; the action bar at the bottom holds only Delete, Revert and
            # Save. Padding rather than margin: a stuck element's margin lets
            # scrolled fields show above it. The opaque background hides them.
            ], id="node-editor-header",
               className="d-flex justify-content-between align-items-center",
               style={"position": "sticky", "top": "0", "zIndex": 3,
                      "backgroundColor": tokens.BG_PANEL,
                      "paddingTop": "0.5rem", "paddingBottom": "0.25rem"}),
            html.Div([
                html.Div([
                    html.H5("Search", className="mb-0"),
                    dbc.Button(html.I(className="bi bi-crosshair"),
                               id="btn-locate-node", color="link",
                               className="p-0 ms-2 text-decoration-none text-muted",
                               style={"fontSize": tokens.FS_LG, "lineHeight": "1"}, disabled=True),
                ], className="d-flex align-items-center mt-3", style={"marginBottom": "0.75rem"}),
                html.Div(dcc.Dropdown(
                    id="search-node",
                    options=[],  # Populated dynamically by core_engine callback
                    value=None,
                    placeholder="Search by names and aliases...",
                    searchable=True,
                    clearable=True,
                ), className="text-dark"),
                Tooltip("Locate node in current view",
                            target="btn-locate-node", placement="right"),
                html.Div(id="locate-message", className="text-warning small mt-1"),
                dcc.Store(id='locate-animate-trigger', data=None),
                dcc.Store(id='locate-request-store', data=None),
                dcc.Store(id='locate-result-store', data=None),
                dcc.Store(id='locate-missing-node-store', data=None),
                dbc.Modal([
                    dbc.ModalHeader(dbc.ModalTitle(id='locate-missing-title'),
                                    close_button=False),
                    dbc.ModalBody("What would you like to do?"),
                    dbc.ModalFooter([
                        # The only modal footer with no spacing class at all.
                        cancel_action("Dismiss", 'btn-locate-dismiss',
                                      className="me-2"),
                        primary_action("View Details", 'btn-locate-view-details'),
                    ]),
                ], id='modal-locate-missing', size="sm", is_open=False,
                   centered=True),

                # More room above: the field has no control beneath it, as the
                # filters sidebar's has, to hold the divider off.
                html.Hr(className="mt-3 mb-3"),
                html.H5("General", className="mt-2 mb-1"),
                html.Div([
                    dbc.Label("Name", className="mb-0"),
                    add_button("btn-alias-add", "Add alias"),
                ], className="d-flex align-items-center mt-2 mb-1"),
                dbc.Input(id="node-name", type="text", placeholder="Name node..."),
                html.Div(id="node-name-duplicate-warning", children="",
                         style={"display": "none"}, className="mt-1"),
                dbc.Collapse(
                    html.Div([
                        dbc.Label("Alias", id="aliases-label",
                                  className="mt-1 mb-1"),
                        html.Div(id='aliases-container'),
                    ]),
                    id="collapse-aliases",
                    is_open=False,
                ),
                dcc.Store(id='aliases-store', data=['']),
                dcc.Store(id='editor-pristine-snapshot', data=None),
                # The Nodes canvas taps the editor loads: held ones are left
                # out (callbacks.py, relay_editor_tap).
                dcc.Store(id='editor-tap-store', data=None),
                # Relationship lists the open node's edges now call for, with
                # the form they were worked out against (callbacks.py,
                # follow_editor_relationships).
                dcc.Store(id='editor-relationships-follow', data=None),

                hover_label("Type", "node-type-label", _EDITOR_HINTS["type"],
                             className="mt-2"),
                dbc.Select(id="node-type", options=[{"label": t, "value": t} for t in SUPPORTED_NODE_TYPES],
                           placeholder="Choose node type..."),

                dbc.Label("Description", className="mt-2"),
                dbc.Textarea(id="node-desc", placeholder="Describe your project...",
                             style={"height": "120px", "resize": "vertical"}),

                hover_label("Context", "node-context-label", _EDITOR_HINTS["context"],
                             className="mt-2"),
                build_single_context_picker(
                    "node-context-picker",
                    "node-context",
                    "node-subcontext",
                    context_options=[{"label": c, "value": c} for c in CONTEXTS],
                    context_value="",
                ),

                # A Goal's priority rank is set in the Goals sidebar, which is
                # the one place that can see the ranking as a whole. Editing it
                # here too meant two controls for one value, and the editor's
                # copy won on save simply because that was the last write.
                #
                # The select stays in the DOM, permanently hidden: six
                # callbacks read it as State and the form snapshot includes it
                # for dirty-checking. It is populated from the node and never
                # written back (see the save path in callbacks.py), so it is
                # inert -- opening a Goal in the editor and saving no longer
                # touches its rank.
                html.Div(id="section-priority-rank", style={"display": "none"}, children=[
                    dbc.Select(
                        id="node-priority-rank",
                        options=[
                            {"label": "—", "value": "none"},
                            {"label": "#1 Priority", "value": "1"},
                            {"label": "#2 Priority", "value": "2"},
                            {"label": "#3 Priority", "value": "3"},
                        ],
                        value="none",
                    ),
                ]),

                html.Div(id="auto-status-display", className="d-none"),

                # --- Section: Status (Now + Done + Dormant toggles) ---
                # Dormant is a form field, saved with Save like the rest. While
                # it is on, Now and Done are hidden (a sleeping node is neither
                # being worked on nor finished) and the Event section below
                # says which event will wake it. Now and Done hide Dormant in
                # turn.
                # The wrappers carry no Bootstrap display utility: those are
                # `!important` and would beat the inline `display: none`.
                html.Div(id="section-done-time", children=[
                    html.Hr(className="my-3"),
                    hover_label("Status", "node-status-heading", _EDITOR_HINTS["status"],
                                component=html.H5, placement="right", className="mt-2 mb-1"),
                    html.Div([
                        html.Div(dbc.Checklist(
                            options=[{"label": "Now", "value": "now"}],
                            value=[],
                            id="node-now",
                            switch=True,
                        ), id="node-now-wrapper"),
                        html.Div(dbc.Checklist(
                            options=[{"label": STATUS_DONE, "value": STATUS_DONE}],
                            value=[],
                            id="node-status-done",
                            switch=True,
                        ), id="node-status-done-wrapper"),
                        html.Div(dbc.Checklist(
                            options=[{"label": "Dormant", "value": "dormant"}],
                            value=[],
                            id="node-dormant",
                            switch=True,
                        ), id="node-dormant-wrapper"),
                    ], className="d-flex justify-content-start gap-3 mt-2"),
                    html.Div(id="node-dormant-wake-warning",
                             className="small text-warning mt-1",
                             style={"display": "none"}),
                    html.Div(id="node-dormant-section", style={"display": "none"}, children=[
                        hover_label("Event", "node-dormant-event-label", _EDITOR_HINTS["event"],
                                     className="mt-2 mb-1"),
                        dbc.Select(id="node-dormant-event", options=[], value=None,
                                   placeholder="Choose an event..."),
                        dbc.Input(id="node-dormant-event-name", type="text",
                                  placeholder="Name the new event...",
                                  className="mt-1", style={"display": "none"}),
                        html.Div(id="node-dormant-settings", style={"display": "none"}, children=[
                            hover_label("Wake settings", "node-dormant-settings-label",
                                         _EDITOR_HINTS["wake"], className="mt-2 mb-1"),
                            # A fired event gave the node a date instead of a
                            # delay. Shown only while it stays in that event.
                            html.Div(id="node-dormant-wake-date-wrapper",
                                     style={"display": "none"}, children=[
                                dbc.Input(id="node-dormant-wake-date", type="date",
                                          size="sm", style={"maxWidth": "170px"}),
                                html.Small("Wake date. This event has already fired.",
                                           className="text-muted d-block mt-1 mb-1"),
                            ]),
                            wake_switches(
                                html.Div(dbc.Checklist(
                                    id="node-dormant-delay-on",
                                    options=[{"label": "Delay", "value": "on"}],
                                    value=[],
                                    switch=True,
                                ), id="node-dormant-delay-switch"),
                                delay_fields("node-dormant-delay-fields",
                                             "node-dormant-delay-value", "node-dormant-delay-unit",
                                             0, "days", False),
                                dbc.Checklist(
                                    id="node-dormant-now",
                                    options=[{"label": "Add to Now", "value": "on"}],
                                    value=[],
                                    switch=True,
                                ),
                            ),
                        ]),
                    ]),
                    # The whole Event section as one dict, collected clientside
                    # (event_callbacks.py). Save and the dirty check read this.
                    dcc.Store(id="node-dormancy-form", data=None),
                    # Whether the loaded node was asleep when the section was
                    # last filled from the database.
                    dcc.Store(id="node-dormant-loaded", data=False),
                    # Set by the Events tab's "+": {event, ts}. The next blank
                    # form opens with Dormant on under that event.
                    dcc.Store(id="editor-dormant-preset", data=None),
                    # Read-only badge — shown only when the node was excluded from
                    # the calibration review cycle ("Don't ask again").
                    html.Div(id="node-calibration-dismissed-badge",
                             className="small text-warning mt-1",
                             style={"display": "none"}),
                ]),

                # Numeric inputs (shared by all types)
                html.Hr(className="my-3"),
                html.Div([
                    html.H5("Ratings", className="mb-0"),
                    info_button("btn-ratings-info", "Ratings reference", placement="right"),
                ], className="d-flex align-items-center mt-2 mb-1"),
                html.Div([
                    dbc.Checklist(
                        options=[{"label": "Inherit", "value": "inherited"}],
                        value=[],
                        id="node-value-mode",
                        switch=True,
                        className="mb-0 hover-hint-label",
                    ),
                ], className="d-flex align-items-center mt-2 mb-2"),
                Tooltip(
                    _EDITOR_HINTS["ratings_inherit"],
                    target="node-value-mode", placement="left",
                ),
                # Locked-on notice for Milestones (mirrors the time-mode warning).
                html.Div(id="value-mode-warning",
                         style=tokens.ERROR_TEXT_HIDDEN,
                         className="mt-1 mb-2", children=""),

                html.Div(id="section-ratings", children=[
                    dbc.Label("Value", className="mt-2"),
                    dcc.Slider(min=1, max=10, step=1, value=5, id="node-value"),

                    dbc.Label("Interest", className="mt-2"),
                    dcc.Slider(min=1, max=10, step=1, value=5, id="node-interest"),
                ]),
                # Effort stays outside section-ratings: it describes the
                # node's own hours, so inheriting ratings leaves it in place.
                html.Div(id="node-effort-row", children=[
                    dbc.Label("Effort", className="mt-2"),
                    dcc.Slider(min=1, max=10, step=1, value=5, id="node-difficulty"),
                ]),
                html.Div(id="node-effort-caption", style={"display": "none"}, children=[
                    dbc.Label("Effort", className="mt-2"),
                    html.Div("Derived from subtasks", className="text-muted small"),
                ]),
                # --- Section: Time Estimates ---
                html.Div(id="section-time-estimates", **{'data-validation-ready': 'false'}, children=[
                    html.Hr(className="my-3"),
                    time_estimates_heading("node"),
                    html.Div([
                        dbc.Checklist(
                            options=[{"label": "Inherit", "value": "inherited"}],
                            value=[],
                            id="node-time-mode",
                            switch=True,
                            className="mb-0 hover-hint-label",
                        ),
                        Tooltip(
                            _EDITOR_HINTS["time_inherit"],
                            target="node-time-mode", placement="left",
                        ),
                        html.Div([
                            dbc.Checklist(
                                options=[{"label": "Habit", "value": "habit"}],
                                value=[],
                                id="node-time-habit-mode",
                                switch=True,
                                className="mb-0 hover-hint-label",
                            ),
                            Tooltip(
                                _EDITOR_HINTS["habit"],
                                target="node-time-habit-mode", placement="left",
                            ),
                        ], id="section-time-habit-toggle", className="ms-3 flex-grow-1"),
                        unit_select("node-time-unit", value=NEW_NODE_TIME_UNIT,
                                    compact=True),
                    ], className="d-flex align-items-center mb-2"),
                    html.Div(id="time-mode-warning",
                             style=tokens.ERROR_TEXT_HIDDEN,
                             className="mt-1 mb-2",
                             children=""),
                    html.Div(id="section-time-omp", children=[
                        dbc.Row([
                            dbc.Col([
                                *bracket_label(label, f"node-time-{field}-label"),
                                dbc.Input(id=f"node-time-{field}", type="number", min=0),
                                html.Small(id=f"node-time-{field}-hours",
                                           className="time-hour-hint text-muted mt-1",
                                           style={"display": "none"}),
                            ]) for field, label in (("o", "Lower"), ("m", "Expected"),
                                                   ("p", "Upper"))
                        ], id="node-time-bracket-row"),
                        dcc.Store(id="editor-time-settings", data=settings.TIME_SETTINGS.get()),
                        html.Div(id="time-validation-error", children="",
                                 style=tokens.ERROR_TEXT_HIDDEN,
                                 className="mt-1"),
                    ]),
                    html.Div(id="section-time-habit", style={"display": "none"}, children=[
                        dbc.Label("Calendar duration", className="mb-0"),
                        # A two- or three-digit count, so the field is sized
                        # for one, with its unit beside it.
                        html.Div([
                            dbc.Input(id="node-habit-duration", type="number", min=0,
                                      className="habit-duration-input"),
                            unit_select("node-habit-duration-unit",
                                        units=DURATION_UNITS, value="weeks",
                                        className="habit-duration-unit"),
                        ], className="d-flex gap-2 mb-2"),
                        dbc.Label("Minutes per session", className="mb-0 mt-2"),
                        dbc.Row([
                            dbc.Col([*bracket_label("Lower", "node-habit-intensity-o-label"),
                                     dbc.Input(id="node-habit-intensity-o", type="number", min=0)]),
                            dbc.Col([*bracket_label("Expected", "node-habit-intensity-m-label"),
                                     dbc.Input(id="node-habit-intensity-m", type="number", min=0)]),
                            dbc.Col([*bracket_label("Upper", "node-habit-intensity-p-label"),
                                     dbc.Input(id="node-habit-intensity-p", type="number", min=0)]),
                        ]),
                        # Cadence is always minutes-per-session; the unit is fixed
                        # but kept as a hidden field so the save/populate wiring is
                        # unchanged (and legacy units still round-trip through it).
                        dcc.Input(id="node-habit-intensity-unit", type="hidden",
                                  value="min_per_session"),
                        dbc.Label("On these days", className="mb-1 mt-2 d-block"),
                        dbc.Checklist(
                            id="node-habit-days",
                            options=WEEKDAY_OPTIONS,
                            # No days until the user picks them.
                            value=[],
                            className="habit-days-picker",
                            inputClassName="btn-check",
                            labelClassName="btn btn-outline-light btn-sm",
                            labelCheckedClassName="active",
                        ),
                        html.Div(id="node-habit-total-preview",
                                 className="mt-2 small text-muted"),
                        html.Div(id="habit-validation-error", children="",
                                 style=tokens.ERROR_TEXT_HIDDEN,
                                 className="mt-1"),
                    ]),
                ]),

                html.Hr(className="my-3"),
                hover_label("Relationships", "node-relationships-heading",
                             _EDITOR_HINTS["relationships"], component=html.H5,
                             placement="right", className="mt-2 mb-1"),
                hover_label("Needs", "node-needs-label", _EDITOR_HINTS["needs"],
                             className="mt-2"),
                html.Div([
                    dcc.Dropdown(id="edge-needs-hard", multi=True, placeholder="Hard..."),
                    dcc.Dropdown(id="edge-needs-soft", multi=True, placeholder="Soft...", className="mt-1"),
                ], className="text-dark"),

                hover_label("Supports", "node-supports-label", _EDITOR_HINTS["supports"],
                             className="mt-2"),
                html.Div([
                    dcc.Dropdown(id="edge-supports-hard", multi=True, placeholder="Hard..."),
                    dcc.Dropdown(id="edge-supports-soft", multi=True, placeholder="Soft...", className="mt-1"),
                ], className="text-dark"),

                hover_label("Helps", "node-helps-label", _EDITOR_HINTS["helps"],
                             className="mt-2"),
                html.Div(dcc.Dropdown(id="edge-helps", multi=True, placeholder="Synergies..."), className="text-dark"),

                dcc.Store(id='edge-resources', data=[]),

                html.Hr(className="my-3"),
                hover_label("Resources", "node-resources-heading", _EDITOR_HINTS["resources"],
                            component=html.H5, placement="right", className="mt-2 mb-1"),

                # The loaded node's links by section id. The rows below are
                # rendered from it and read back through their pattern ids.
                dcc.Store(id='resource-links-store', data={}),
                dcc.Input(id='electron-file-picked-input', value='', type='text',
                          style={'display': 'none'}),
                html.Div(id='editor-resources'),

                # The three actions stay pinned to the bottom of the panel while the
                # fields above them scroll. `position: sticky` keeps them in normal
                # flow, so the panel's full height still scrolls to the very end and
                # nothing sits permanently behind the bar. The opaque background is
                # what stops scrolling fields showing through; it matches the
                # sidebar's own bg-sidebar (see STYLE_GUIDE.md).
                html.Div([
                    html.Hr(className="my-2"),
                    html.Div([
                        danger_action("Delete", "btn-delete"),
                        html.Div(className="flex-grow-1"),
                        cancel_action("Revert", "btn-revert", className="me-2"),
                        # Bootstrap turns off pointer events on a disabled
                        # button, so the tooltip hangs on this wrapper: it
                        # can still say why Save is off.
                        html.Span(primary_action("Save", "btn-save"),
                                  id="btn-save-wrap", className="d-inline-block"),
                    ], className="form-actions form-actions-lg d-flex align-items-center mt-3"),
                    # Kept inside the bar so a save confirmation is visible from
                    # wherever the user was scrolled when they pressed Save.
                    html.Div(id="save-output", className="text-success fw-bold text-end mt-2"),
                    dcc.Store(id="editor-feedback-timer-store"),
                ], id="node-editor-actions", style={
                    "position": "sticky",
                    "bottom": "0",
                    "zIndex": 3,
                    "backgroundColor": tokens.BG_PANEL,
                    "paddingBottom": "10px",
                }),
                Tooltip("Discard unsaved changes and revert this node to its last saved state", id="editor-revert-tooltip", target="btn-revert", placement="top"),
                Tooltip(SAVE_HINT, id="editor-save-tooltip", target="btn-save-wrap", placement="top"),
                Tooltip("Delete this node", id="editor-delete-tooltip", target="btn-delete", placement="top"),
                dcc.Store(id='node-time-unit-prev', data='weeks'),
                dcc.Store(id='node-original-name', data=None)
            ])
        ],
        className="ps-3 pe-4 pb-2 pt-0",
        style={"width": SIDEBAR_WIDTH_PX, "minWidth": SIDEBAR_WIDTH_PX}
    )


def build_node_editor_sidebar():
    """Container Div for the node editor overlay (left, closed initially)."""
    return html.Div(
        id="sidebar-editor-container",
        children=[build_node_editor_content()],
        style={
            "position": "absolute",
            "top": "0",
            "left": "0",
            "width": SIDEBAR_WIDTH_PX,
            "minWidth": SIDEBAR_WIDTH_PX,
            "height": "100%",
            "zIndex": 1000,
            "overflowX": "hidden",
            "overflowY": "auto",
            "borderRight": f"1px solid {tokens.BORDER_PANEL}",
            "transition": "transform 0.3s ease",
            "transform": SIDEBAR_TRANSLATE_CLOSED,
            "willChange": "transform",
            "backgroundColor": tokens.BG_PANEL
        }
    )
