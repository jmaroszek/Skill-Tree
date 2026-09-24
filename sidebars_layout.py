"""Layout helpers for the four cross-tab sidebars.

These overlays float above the tab content and are accessible from any tab:
  - Node Editor    (left, sidebar-editor-container)
  - Goals          (left, details-goal-sidebar)
  - Events         (left, events-sidebar-container)
  - Filters        (right, sidebar-filters-container)

The three left sidebars are mutually exclusive — opening one closes the others
via the cross-sidebar style coordinator in callbacks.py. Filters (right) is
independent.

Per-tab filter sidebars (e.g. the Details tab's mini-graph filter at
`details-filters-sidebar`) live with their owning tab module, not here.
"""

from duration_ui import DURATION_UNITS, bracket_label, estimate_guidance, unit_select
from dash import html, dcc
import dash_bootstrap_components as dbc
from config import (
    ConfigManager,
    TOAST_CLEAR_INTERVAL_MS,
    LOCATE_TOAST_CLEAR_INTERVAL_MS,
    LOADING_SPINNER_STYLE,
    SIDEBAR_WIDTH_PX,
    SIDEBAR_WIDTH_NEG_PX,
    SIDEBAR_TRANSLATE_CLOSED,
    SUPPORTED_NODE_TYPES,
    sort_contexts,
    DEFAULT_NODE_COLORS,
)
from events_layout import build_events_sidebar_content, delay_fields, wake_switches
from list_toolbar import GOALS_SORT, SEARCH_STYLE, build_list_toolbar
from context_picker import build_multi_context_picker, build_single_context_picker
from models import STATUS_DONE
import style_tokens as tokens
from ui_kit import (Tooltip, add_button, cancel_action, confirm_action, danger_action,
                     done_color, info_button, panel_close_button,
                     primary_action)

# Node types have distinct product behavior and are not user-extensible.
NODE_TYPES = list(SUPPORTED_NODE_TYPES)

# Save & Close reuses the canvas "Done" node color (same as the Events tab's
# Trigger button) — a save-and-close is the editor's "done" moment.

# Weekday toggle-pill options for the habit per-session scheduler. Values are
# weekday indices (0=Mon … 6=Sun); displayed Sunday-first to match the
# Apple-style day picker. Single-letter labels.
WEEKDAY_OPTIONS = [
    {"label": "S", "value": 6}, {"label": "M", "value": 0},
    {"label": "T", "value": 1}, {"label": "W", "value": 2},
    {"label": "T", "value": 3}, {"label": "F", "value": 4},
    {"label": "S", "value": 5},
]


# The four editor action buttons share one padding; it was written out
# four times, and one of them differed.
_ACTION_PAD = {"padding": "6px 0"}


# --- Node Editor sidebar (left) ---
def build_node_editor_content():
    CONTEXTS = sort_contexts(ConfigManager.get_contexts())
    _TED = ConfigManager.get_time_estimate_defaults()
    _DONE_COLOR = done_color()
    return html.Div(
        [
            html.Div([
                html.Div([
                    html.H4("Node Editor", className="mb-0"),
                    add_button("btn-editor-new", "New node", large=True),
                ], className="d-flex align-items-center"),
                panel_close_button("btn-close-editor", "Close node editor", large=True)
            ], className="d-flex justify-content-between align-items-center mb-1 mt-2"),
            html.Div([
                html.Div([
                    html.H5("Search", className="mb-0"),
                    dbc.Button(html.I(className="bi bi-crosshair"),
                               id="btn-locate-node", color="link",
                               className="p-0 ms-2 text-decoration-none text-muted",
                               style={"fontSize": tokens.FS_LG, "lineHeight": "1"}, disabled=True),
                ], className="d-flex align-items-center mt-0 mb-1"),
                html.Div(dcc.Dropdown(
                    id="search-node",
                    options=[],  # Populated dynamically by core_engine callback
                    value=None,
                    placeholder="Search nodes...",
                    searchable=True,
                    clearable=True,
                ), className="text-dark"),
                Tooltip("Locate node in current view",
                            target="btn-locate-node", placement="right"),
                html.Div(id="locate-message", className="text-warning small mt-1"),
                dcc.Interval(id='locate-clear-interval', interval=LOCATE_TOAST_CLEAR_INTERVAL_MS, n_intervals=0, disabled=True),
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

                html.H5("General", className="mt-3 mb-1"),
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

                dbc.Label("Type", className="mt-2"),
                dbc.Select(id="node-type", options=[{"label": t, "value": t} for t in NODE_TYPES],
                           placeholder="Choose node type..."),

                dbc.Label("Description", className="mt-2"),
                dbc.Textarea(id="node-desc", placeholder="Describe your project...",
                             style={"height": "120px", "resize": "vertical"}),

                dbc.Label("Context", className="mt-2"),
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
                    html.Hr(className="my-2"),
                    html.H5("Status", className="mt-2 mb-1"),
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
                        dbc.Label("Event", className="mt-2 mb-1"),
                        dbc.Select(id="node-dormant-event", options=[], value=None,
                                   placeholder="Choose an event..."),
                        dbc.Input(id="node-dormant-event-name", type="text",
                                  placeholder="Name the new event...",
                                  className="mt-1", style={"display": "none"}),
                        html.Div(id="node-dormant-settings", style={"display": "none"}, children=[
                            dbc.Label("Wake settings", className="mt-2 mb-1"),
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
                html.Hr(className="my-2"),
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
                        className="mb-0",
                    ),
                ], className="d-flex align-items-center mt-2 mb-2"),
                Tooltip(
                    "Treat this node as a pure container: value, interest, and effort all come from its children via the cascade.",
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

                    html.Div(id="node-effort-row", children=[
                        dbc.Label("Effort", className="mt-2"),
                        dcc.Slider(min=1, max=10, step=1, value=5, id="node-difficulty"),
                    ]),
                    html.Div(id="node-effort-caption", style={"display": "none"}, children=[
                        dbc.Label("Effort", className="mt-2"),
                        html.Div("Derived from subtasks", className="text-muted small"),
                    ]),
                ]),
                # --- Section: Time Estimates ---
                html.Div(id="section-time-estimates", children=[
                    html.Hr(className="my-2"),
                    html.Div([
                        html.H5("Time Estimates", className="mb-0"),
                        estimate_guidance("node"),
                    ], className="d-flex align-items-center mt-2 mb-2"),
                    html.Div([
                        dbc.Checklist(
                            options=[{"label": "Inherit", "value": "inherited"}],
                            value=[],
                            id="node-time-mode",
                            switch=True,
                            className="mb-0",
                        ),
                        Tooltip(
                            "Treat this node's time as the sum of its children's. Use for containers whose only work is completing the children.",
                            target="node-time-mode", placement="left",
                        ),
                        html.Div([
                            dbc.Checklist(
                                options=[{"label": "Habit", "value": "habit"}],
                                value=[],
                                id="node-time-habit-mode",
                                switch=True,
                                className="mb-0",
                            ),
                            Tooltip(
                                "Distributed-cadence project (e.g., 30 min/day for 6 weeks). Enter a duration and per-period intensity; total hours are computed and used for scoring.",
                                target="node-time-habit-mode", placement="left",
                            ),
                        ], id="section-time-habit-toggle", className="ms-3 flex-grow-1"),
                        unit_select("node-time-unit", value=_TED.get('unit', 'weeks'),
                                    compact=True),
                    ], className="d-flex align-items-center mb-2"),
                    html.Div(id="time-mode-warning",
                             style=tokens.ERROR_TEXT_HIDDEN,
                             className="mt-1 mb-2",
                             children=""),
                    html.Div(id="section-time-omp", children=[
                        dbc.Row([
                            dbc.Col([*bracket_label("Lower", "node-time-o-label"), dbc.Input(id="node-time-o", type="number", min=0)]),
                            dbc.Col([*bracket_label("Expected", "node-time-m-label"), dbc.Input(id="node-time-m", type="number", min=0)]),
                            dbc.Col([*bracket_label("Upper", "node-time-p-label"), dbc.Input(id="node-time-p", type="number", min=0)]),
                        ]),
                        html.Div(id="time-validation-error", children="",
                                 style=tokens.ERROR_TEXT_HIDDEN,
                                 className="mt-1"),
                    ]),
                    html.Div(id="section-time-habit", style={"display": "none"}, children=[
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Duration", className="mb-0"),
                                dbc.Input(id="node-habit-duration", type="number", min=0),
                            ], width=7),
                            dbc.Col([
                                dbc.Label(" ", className="mb-0"),
                                unit_select("node-habit-duration-unit",
                                            units=DURATION_UNITS, value="weeks"),
                            ], width=5),
                        ], className="mb-2"),
                        dbc.Label("Minutes per Session", className="mb-0 mt-2"),
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
                            value=[0, 1, 2, 3, 4, 5, 6],
                            className="habit-days-picker",
                            inputClassName="btn-check",
                            labelClassName="btn btn-outline-light btn-sm",
                            labelCheckedClassName="active",
                        ),
                        html.Div(id="node-habit-total-preview",
                                 className="mt-2 small text-muted"),
                    ]),
                ]),

                html.Hr(className="my-2"),
                html.H5("Relationships", className="mt-2 mb-1"),
                dbc.Label("Needs", className="mt-2"),
                html.Div([
                    dcc.Dropdown(id="edge-needs-hard", multi=True, placeholder="Hard..."),
                    dcc.Dropdown(id="edge-needs-soft", multi=True, placeholder="Soft...", className="mt-1"),
                ], className="text-dark"),

                dbc.Label("Supports", className="mt-2"),
                html.Div([
                    dcc.Dropdown(id="edge-supports-hard", multi=True, placeholder="Hard..."),
                    dcc.Dropdown(id="edge-supports-soft", multi=True, placeholder="Soft...", className="mt-1"),
                ], className="text-dark"),

                dbc.Label("Helps", className="mt-2"),
                html.Div(dcc.Dropdown(id="edge-helps", multi=True, placeholder="Synergies..."), className="text-dark"),

                dcc.Store(id='edge-resources', data=[]),

                html.Hr(className="my-2"),
                html.H5("Resources", className="mt-2 mb-1"),

                # Stores hold JSON arrays of links for each resource type
                dcc.Store(id='obsidian-links-store', data=['']),
                dcc.Store(id='drive-links-store', data=['']),
                dcc.Store(id='website-links-store', data=['']),

                html.Div([
                    html.Div([
                        dbc.Label("Obsidian", className="mb-0"),
                        add_button("btn-obsidian-add", "Add Obsidian link")
                    ], className="d-flex align-items-center mt-2 mb-1"),
                    html.Div(id='obsidian-links-container'),
                ], id='editor-obsidian-resources',
                   style={} if ConfigManager.get_obsidian_enabled() else {"display": "none"}),

                html.Div([
                    html.Div([
                        dbc.Label("Google Drive", className="mb-0"),
                        add_button("btn-drive-add", "Add Google Drive link")
                    ], className="d-flex align-items-center mt-3 mb-1"),
                    html.Div(id='drive-links-container'),
                ], id='editor-drive-resources',
                   style={} if ConfigManager.get_gdrive_enabled() else {"display": "none"}),

                html.Div([
                    dbc.Label("Website", className="mb-0"),
                    add_button("btn-website-add", "Add Website link")
                ], className="d-flex align-items-center mt-3 mb-1"),
                html.Div(id='website-links-container'),

                # The five actions stay pinned to the bottom of the panel while the
                # fields above them scroll. `position: sticky` keeps them in normal
                # flow, so the panel's full height still scrolls to the very end and
                # nothing sits permanently behind the bar. The opaque background is
                # what stops scrolling fields showing through; it matches the
                # sidebar's own bg-sidebar (see STYLE_GUIDE.md).
                html.Div([
                    html.Hr(className="my-2"),
                    html.Div([
                        # btn-revert was the one button in the app with no
                        # color prop, hand-painting the exact value that
                        # color="secondary" already gives it. Its label also
                        # says Cancel while its tooltip describes a revert;
                        # Revert is what it does, and what the unsaved-changes
                        # modal calls the same choice.
                        danger_action("Delete", "btn-delete",
                                      className="flex-fill me-2", style=_ACTION_PAD),
                        cancel_action("Revert", "btn-revert",
                                      className="flex-fill me-2", style=_ACTION_PAD),
                        primary_action("Save", "btn-save",
                                       className="flex-fill me-2", style=_ACTION_PAD),
                        confirm_action("Save & Close", "btn-save-close",
                                       className="flex-fill",
                                       style={**_ACTION_PAD,
                                              "backgroundColor": _DONE_COLOR,
                                              "borderColor": _DONE_COLOR})
                    ], className="d-flex mt-4"),
                    cancel_action("New Node", "btn-new-node", className="w-100 mt-2",
                                  style={"padding": "8px 0"}),
                    # Kept inside the bar so a save confirmation is visible from
                    # wherever the user was scrolled when they pressed Save.
                    html.Div(id="save-output", className="text-success fw-bold text-end mt-2"),
                ], id="node-editor-actions", style={
                    "position": "sticky",
                    "bottom": "0",
                    "zIndex": 3,
                    "backgroundColor": tokens.BG_PANEL,
                    "paddingBottom": "10px",
                }),
                Tooltip("Discard unsaved changes and revert this node to its last saved state", target="btn-revert", placement="top"),
                Tooltip("Save changes", target="btn-save", placement="top"),
                Tooltip("Save changes and close the node editor", target="btn-save-close", placement="top"),
                Tooltip("Delete this node", target="btn-delete", placement="top"),
                Tooltip("Create a new node", target="btn-new-node", placement="top"),
                dcc.Interval(id='clear-interval', interval=TOAST_CLEAR_INTERVAL_MS, n_intervals=0, disabled=True),
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


# --- Goals sidebar (left) ---
def build_goals_sidebar():
    """Container Div for the goals overlay (left, closed initially)."""
    return html.Div(
        id="details-goal-sidebar",
        children=[
            html.Div([
                html.Div([
                    html.H4("Goals", className="mb-0"),
                    add_button("btn-goals-sidebar-new", "New goal", large=True),
                ], className="d-flex align-items-center"),
                panel_close_button("btn-details-goals-close", "Close goals sidebar",
                                   large=True),
            ], className="d-flex justify-content-between align-items-center mb-2 mt-2 px-3"),

            build_list_toolbar(
                dbc.Input(id="details-goal-search", type="text",
                          placeholder="Search goals...", size="sm",
                          debounce=False, style=SEARCH_STYLE),
                GOALS_SORT,
            ),

            # The list is first built in the background once the app is idle,
            # or on the sidebar's first open if that comes sooner. Later opens
            # show the previous list until the new one arrives, so only this
            # first wait needs a spinner.
            html.Div(
                html.Div([
                    dbc.Spinner(spinner_style=LOADING_SPINNER_STYLE),
                    html.Div("Preparing your goals…", className="canvas-cover-label"),
                ], className="loading-cover", role="status",
                    **{"aria-live": "polite"}),  # type: ignore[reportArgumentType]
                id="details-goal-list-container",
                style={"overflowY": "auto", "flex": "1", "padding": "0 12px"}),
        ],
        style={
            "position": "absolute",
            "top": "0",
            "left": "0",
            "width": SIDEBAR_WIDTH_PX,
            "height": "100%",
            "zIndex": 100,
            "overflowX": "hidden",
            "overflowY": "auto",
            "borderRight": f"1px solid {tokens.BORDER_PANEL}",
            "transition": "transform 0.3s ease",
            "transform": SIDEBAR_TRANSLATE_CLOSED,
            "willChange": "transform",
            "backgroundColor": tokens.BG_PANEL,
            "display": "flex",
            "flexDirection": "column",
        }
    )


# --- Events sidebar (left) ---
def build_events_sidebar():
    """Container Div for the events overlay (left, closed initially).

    Body content comes from events_layout.build_events_sidebar_content so the
    Events tab module owns its own internal markup.
    """
    return html.Div(
        id="events-sidebar-container",
        children=[build_events_sidebar_content()],
        style={
            "position": "absolute",
            "top": "0",
            "left": "0",
            "width": SIDEBAR_WIDTH_PX,
            "height": "100%",
            "zIndex": 100,
            "overflowX": "hidden",
            "overflowY": "auto",
            "borderRight": f"1px solid {tokens.BORDER_PANEL}",
            "transition": "transform 0.3s ease",
            "transform": SIDEBAR_TRANSLATE_CLOSED,
            "willChange": "transform",
            "backgroundColor": tokens.BG_PANEL,
            "display": "flex",
            "flexDirection": "column",
        }
    )


# --- Filters sidebar (right) ---
def build_filters_content():
    # Filters are session state, never saved state. Every control below opens
    # at the value "Clear Filters" resets it to, so a restart always shows the
    # whole graph. A narrowing the user set weeks ago and forgot would quietly
    # scope every ranking the app produces, which is the one answer it exists
    # to give. Values here must stay in step with the clear_filters() callback.
    return html.Div([
        html.Div([
            html.H4("Filters", className="mb-0"),
            panel_close_button("btn-close-filters", "Close filters", large=True,
                               className_extra="float-end")
        ], className="d-flex justify-content-between align-items-center mb-1 mt-2"),

        html.H5("General", className="mt-2 mb-1"),
        dbc.Label("Context", className="mt-2"),
        build_multi_context_picker(
            "filter-context-picker",
            "filter-context",
            "filter-subcontext",
            context_value=[],
            subcontext_value=[],
        ),

        dbc.Label("Node Type", className="mt-2"),
        dcc.Dropdown(
            id="filter-node-type",
            options=[{"label": t, "value": t} for t in NODE_TYPES],
            value=[],
            multi=True,
            placeholder="All",
            className="text-dark",
        ),

        html.Hr(className="my-3"),

        html.H5("Ratings", className="mt-2 mb-1"),
        dbc.Label("Min Value", className="mt-2"),
        dcc.Slider(min=1, max=10, step=1, value=1, id="filter-value",
                   marks={i: str(i) for i in range(1, 11)}),

        dbc.Label("Min Interest", className="mt-2"),
        dcc.Slider(min=1, max=10, step=1, value=1, id="filter-interest",
                   marks={i: str(i) for i in range(1, 11)}),

        dbc.Label("Max Effort", className="mt-3"),
        dcc.Slider(min=1, max=10, step=1, value=10, id="filter-difficulty",
                   marks={i: str(i) for i in range(1, 11)}),

        dbc.Label("Max Time", className="mt-2"),
        html.Div([
            dbc.Input(id="filter-time", type="number", min=0.1,
                      value=None,
                      placeholder="No limit", size="sm",
                      className="flex-grow-1"),
            unit_select("filter-time-unit", value="hours", compact=True),
        ], className="d-flex gap-2"),

        html.Hr(className="my-3"),

        html.H5("Status", className="mt-2 mb-1"),
        html.Div([
            dbc.Checklist(
                options=[{"label": "Show Done", "value": "show_done"}],
                value=[],
                id="filter-done",
                switch=True,
            ),
            dbc.Checklist(
                options=[{"label": "Show Dormant", "value": "show_dormant"}],
                value=[],
                id="filter-dormant",
                switch=True,
            ),
        ], className="d-flex gap-3 flex-wrap"),

        html.Hr(className="my-3"),

        html.H5("Communities", className="mt-2 mb-1"),
        dbc.Label("Detection Method", className="mt-2"),
        dbc.Select(id="community-method", options=[
            {"label": "Clusters", "value": "louvain"},
            {"label": "Islands", "value": "components"},
            {"label": "Orphans", "value": "orphans"},
        ], value="louvain"),

        dbc.Label("Community", className="mt-3"),
        dbc.Select(id="filter-community", options=[{"label": "All", "value": "All"}], value="All"),

        Tooltip(
            "Show Done nodes on the canvas. Off = hide them.",
            target="filter-done", placement="top",
        ),
        Tooltip(
            "Show dormant (event-deferred) nodes on the canvas. Off = hide them. "
            "The events tab graph always shows them regardless.",
            target="filter-dormant", placement="top",
        ),

        html.Hr(className="my-3"),
        # Filters decide what the canvas shows; layout physics live in the
        # graph-settings panel next to the sliders they re-run (and next to
        # Freeze, which depends on Settle). The Details tab's filters sidebar
        # has never carried a Settle button — this one matches it now.
        html.Div([
            dbc.Button("Clear Filters", id="btn-clear-filters", color="secondary", size="sm", className="flex-fill"),
        ], className="d-flex gap-2 mb-3"),
    ], className="px-3 pb-2 pt-0", style={"width": SIDEBAR_WIDTH_PX, "minWidth": SIDEBAR_WIDTH_PX})


def build_filters_sidebar():
    """Container Div for the filters overlay (right, closed initially)."""
    return html.Div(
        id="sidebar-filters-container",
        children=[build_filters_content()],
        style={
            "position": "absolute",
            "top": "0",
            "right": SIDEBAR_WIDTH_NEG_PX,
            "width": SIDEBAR_WIDTH_PX,
            "height": "100%",
            "zIndex": 100,
            "overflowX": "hidden",
            "overflowY": "auto",
            "borderLeft": f"1px solid {tokens.BORDER_PANEL}",
            "transition": "right 0.3s ease",
            "backgroundColor": tokens.BG_PANEL
        }
    )


def build_all_sidebars():
    """Return the four cross-tab sidebar overlay Divs as a list, in order
    (editor, goals, events, filters). layout.py splats this into the main
    content area so all four float above the tabs."""
    return [
        build_node_editor_sidebar(),
        build_goals_sidebar(),
        build_events_sidebar(),
        build_filters_sidebar(),
    ]


# Compatibility for Python callers that previously imported component templates.
_TEMPLATE_BUILDERS = {
    'node_editor_content': build_node_editor_content,
}


def __getattr__(name):
    if name in _TEMPLATE_BUILDERS:
        return _TEMPLATE_BUILDERS[name]()
    raise AttributeError(name)
