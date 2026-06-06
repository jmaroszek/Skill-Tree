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

from dash import html, dcc
import dash_bootstrap_components as dbc
from config import (
    ConfigManager,
    TOOLTIP_SHOW_DELAY_MS,
    TOOLTIP_HIDE_DELAY_MS,
    TOAST_CLEAR_INTERVAL_MS,
    LOCATE_TOAST_CLEAR_INTERVAL_MS,
    SIDEBAR_WIDTH_PX,
    SIDEBAR_WIDTH_NEG_PX,
    SIDEBAR_TRANSLATE_CLOSED,
    sort_subcontexts,
    sort_contexts,
)
from events_layout import build_events_sidebar_content
from models import STATUS_DONE

# Only used for the initial render; core_engine refreshes them dynamically.
NODE_TYPES = ConfigManager.get_node_types()
CONTEXTS = sort_contexts(ConfigManager.get_contexts())
_TED = ConfigManager.get_time_estimate_defaults()

# Save & Close reuses the canvas "Done" node color (same as the Events tab's
# Trigger button) — a save-and-close is the editor's "done" moment.
_DONE_COLOR = ConfigManager.get_node_colors().get(STATUS_DONE, "#198754")

# Weekday toggle-pill options for the habit per-session scheduler. Values are
# weekday indices (0=Mon … 6=Sun); displayed Sunday-first to match the
# Apple-style day picker. Single-letter labels.
WEEKDAY_OPTIONS = [
    {"label": "S", "value": 6}, {"label": "M", "value": 0},
    {"label": "T", "value": 1}, {"label": "W", "value": 2},
    {"label": "T", "value": 3}, {"label": "F", "value": 4},
    {"label": "S", "value": 5},
]


# --- Node Editor sidebar (left) ---
node_editor_content = html.Div(
    [
        html.Div([
            html.Div([
                html.H4("Node Editor", className="mb-0"),
                dbc.Button("+", id="btn-editor-new",
                           color="link",
                           className="p-0 ms-2 text-decoration-none text-muted",
                           style={"fontSize": "1.4rem", "lineHeight": "1"}),
                dbc.Tooltip("New node", target="btn-editor-new", placement="right",
                            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            ], className="d-flex align-items-center"),
            html.Span("×", id="btn-close-editor", className="fs-3 text-white", style={"cursor": "pointer"})
        ], className="d-flex justify-content-between align-items-center mb-1 mt-2"),
        html.Div([
            html.Div(id="node-priority-badge", children=[],
                     className="d-flex gap-1 flex-wrap mb-2",
                     style={"display": "none"}),
            html.Div([
                html.H5("Search", className="mb-0"),
                dbc.Button(html.I(className="bi bi-crosshair"),
                           id="btn-locate-node", color="link",
                           className="p-0 ms-2 text-decoration-none text-muted",
                           style={"fontSize": "1rem", "lineHeight": "1"}, disabled=True),
            ], className="d-flex align-items-center mt-0 mb-1"),
            html.Div(dcc.Dropdown(
                id="search-node",
                options=[],  # Populated dynamically by core_engine callback
                value=None,
                searchable=True,
                clearable=True,
            ), className="text-dark"),
            dbc.Tooltip("Locate node on graph",
                        target="btn-locate-node", placement="right",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            html.Div(id="locate-message", className="text-warning small mt-1"),
            dcc.Interval(id='locate-clear-interval', interval=LOCATE_TOAST_CLEAR_INTERVAL_MS, n_intervals=0, disabled=True),
            dcc.Store(id='locate-animate-trigger', data=None),

            html.H5("General", className="mt-3 mb-1"),
            dbc.Label("Name", className="mt-2"),
            html.Div([
                dbc.Input(id="node-name", type="text"),
                dbc.Button(html.Span(id="aliases-chevron", className="editor-chevron"),
                           id="btn-aliases-toggle", title="Aliases",
                           className="editor-icon-btn editor-disclosure-btn"),
            ], className="d-flex editor-field-group"),
            html.Div(id="node-name-duplicate-warning", children="",
                     style={"display": "none"}, className="mt-1"),
            dbc.Collapse(
                html.Div([
                    html.Div([
                        dbc.Label("Aliases", className="mb-0"),
                        dbc.Button("+", id="btn-alias-add", color="link",
                                   className="p-0 ms-2 text-decoration-none text-muted",
                                   title="Add alias",
                                   style={"fontSize": "1.2rem", "lineHeight": "1"}),
                    ], className="d-flex align-items-center mt-1 mb-1"),
                    html.Div(id='aliases-container'),
                ]),
                id="collapse-aliases",
                is_open=False,
            ),
            dcc.Store(id='aliases-store', data=['']),
            dcc.Store(id='editor-pristine-snapshot', data=None),

            dbc.Label("Type", className="mt-2"),
            dbc.Select(id="node-type", options=[{"label": t, "value": t} for t in NODE_TYPES]),

            dbc.Label("Description", className="mt-2"),
            dbc.Textarea(id="node-desc", style={"height": "120px", "resize": "vertical"}),

            dbc.Label("Context", className="mt-2"),
            dbc.Select(id="node-context", options=[{"label": c, "value": c} for c in CONTEXTS], value=""),  # type: ignore[reportArgumentType]

            dbc.Label("Subcontext", className="mt-2"),
            dbc.Select(id="node-subcontext", options=[]),

            html.Div(id="section-priority-rank", style={"display": "none"}, children=[
                dbc.Label("Priority Rank", className="mt-2"),
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
            html.Div(id="section-done-time", children=[
                html.Hr(className="my-2"),
                html.H5("Status", className="mt-2 mb-2"),
                html.Div([
                    dbc.Checklist(
                        options=[{"label": "Now", "value": "now"}],
                        value=[],
                        id="node-now",
                        switch=True,
                    ),
                    dbc.Checklist(
                        options=[{"label": STATUS_DONE, "value": STATUS_DONE}],
                        value=[],
                        id="node-status-done",
                        switch=True,
                    ),
                    dbc.Checklist(
                        options=[{"label": "Dormant", "value": "dormant"}],
                        value=[],
                        id="node-dormant",
                        switch=True,
                    ),
                ], className="d-flex justify-content-start gap-3 mt-3"),
                html.Div(id="node-dormant-event-info",
                         className="small text-muted mt-1"),
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
                html.Button(
                    html.I(className="bi bi-info-circle"),
                    id="btn-ratings-info",
                    style={
                        "background": "none", "border": "none", "padding": "0 0 0 6px",
                        "color": "#6c757d", "cursor": "pointer", "fontSize": "0.95rem",
                        "lineHeight": "1", "position": "relative", "top": "3px"
                    }
                ),
                dbc.Tooltip("Ratings reference", target="btn-ratings-info", placement="right",
                            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            ], className="d-flex align-items-center mt-2 mb-1"),
            html.Div([
                dbc.Checklist(
                    options=[{"label": "Inherit", "value": "inherited"}],
                    value=[],
                    id="node-value-mode",
                    switch=True,
                    className="mb-0 me-3",
                ),
                dbc.Checklist(
                    options=[{"label": "Override", "value": "on"}],
                    value=[],
                    id="override-toggle",
                    switch=True,
                    className="mb-0",
                ),
            ], className="d-flex align-items-center mt-2 mb-2"),
            dbc.Tooltip(
                "Treat this node as a pure container: value, interest, and effort all come from its children via the cascade.",
                target="node-value-mode", placement="left",
                delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS},
            ),
            dbc.Tooltip(
                "Boost this node's priority manually. Click for scope options.",
                target="override-toggle", placement="left",
                delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS},
            ),
            # Locked-on notice for Milestones (mirrors the time-mode warning).
            html.Div(id="value-mode-warning",
                     style={"display": "none", "color": "#dc3545", "fontSize": "0.85rem"},
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
            dbc.Popover(
                [
                    dbc.PopoverHeader("Override Mode"),
                    dbc.PopoverBody([
                        dbc.RadioItems(
                            id="override-mode-radio",
                            options=[
                                {"label": "Node Only", "value": "node_only"},
                                {"label": "Node + Hard Dependencies", "value": "hard"},
                                {"label": "Node + Soft Dependencies", "value": "soft"},
                                {"label": "Node + All Dependencies", "value": "all"},
                            ],
                            value="hard",
                            className="mb-2",
                        ),
                        dbc.Button("Apply", id="btn-override-apply", color="primary",
                                   size="sm", className="w-100"),
                    ]),
                ],
                id="popover-override-mode",
                target="override-toggle",
                is_open=False,
                placement="bottom",
            ),

            # --- Section: Time Estimates ---
            html.Div(id="section-time-estimates", children=[
                html.Hr(className="my-2"),
                html.H5("Time Estimates", className="mt-2 mb-2"),
                html.Div([
                    dbc.Checklist(
                        options=[{"label": "Inherit", "value": "inherited"}],
                        value=[],
                        id="node-time-mode",
                        switch=True,
                        className="mb-0",
                    ),
                    dbc.Tooltip(
                        "Treat this node's time as the sum of its children's. Use for containers whose only work is completing the children.",
                        target="node-time-mode", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS},
                    ),
                    html.Div([
                        dbc.Checklist(
                            options=[{"label": "Habit", "value": "habit"}],
                            value=[],
                            id="node-time-habit-mode",
                            switch=True,
                            className="mb-0",
                        ),
                        dbc.Tooltip(
                            "Distributed-cadence project (e.g., 30 min/day for 6 weeks). Enter a duration and per-period intensity; total hours are computed and used for scoring.",
                            target="node-time-habit-mode", placement="left",
                            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS},
                        ),
                    ], id="section-time-habit-toggle", className="ms-3 flex-grow-1"),
                    dbc.Select(id="node-time-unit", options=[
                        {"label": "Hours", "value": "hours"},
                        {"label": "Weeks", "value": "weeks"},
                        {"label": "Months", "value": "months"},
                        {"label": "Years", "value": "years"},
                    ], value=_TED.get('unit', 'weeks'), size="sm", style={"width": "100px"}),
                ], className="d-flex align-items-center mb-2"),
                html.Div(id="time-mode-warning",
                         style={"display": "none", "color": "#dc3545", "fontSize": "0.85rem"},
                         className="mt-1 mb-2",
                         children=""),
                html.Div(id="section-time-omp", children=[
                    dbc.Row([
                        dbc.Col([dbc.Label("Lower", className="small text-muted mb-0"), dbc.Input(id="node-time-o", type="number", min=0)]),
                        dbc.Col([dbc.Label("Expected", className="small text-muted mb-0"), dbc.Input(id="node-time-m", type="number", min=0)]),
                        dbc.Col([dbc.Label("Upper", className="small text-muted mb-0"), dbc.Input(id="node-time-p", type="number", min=0)]),
                    ]),
                    html.Div(id="time-validation-error", children="",
                             style={"display": "none", "color": "#dc3545", "fontSize": "0.85rem"},
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
                            dbc.Select(id="node-habit-duration-unit", options=[
                                {"label": "Days", "value": "days"},
                                {"label": "Weeks", "value": "weeks"},
                                {"label": "Months", "value": "months"},
                                {"label": "Years", "value": "years"},
                            ], value="weeks"),
                        ], width=5),
                    ], className="mb-2"),
                    dbc.Label("Minutes per Session", className="mb-0 mt-2"),
                    dbc.Row([
                        dbc.Col([dbc.Label("Lower", className="small text-muted mb-0"),
                                 dbc.Input(id="node-habit-intensity-o", type="number", min=0)]),
                        dbc.Col([dbc.Label("Expected", className="small text-muted mb-0"),
                                 dbc.Input(id="node-habit-intensity-m", type="number", min=0)]),
                        dbc.Col([dbc.Label("Upper", className="small text-muted mb-0"),
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
            html.H5("External Resources", className="mt-2 mb-1"),

            # Stores hold JSON arrays of links for each resource type
            dcc.Store(id='obsidian-links-store', data=['']),
            dcc.Store(id='drive-links-store', data=['']),
            dcc.Store(id='website-links-store', data=['']),

            html.Div([
                dbc.Label("Obsidian", className="mb-0"),
                dbc.Button("+", id="btn-obsidian-add", color="link", className="p-0 ms-2 text-decoration-none text-muted", title="Add Obsidian link", style={"fontSize": "1.2rem", "lineHeight": "1"})
            ], className="d-flex align-items-center mt-2 mb-1"),
            html.Div(id='obsidian-links-container'),

            html.Div([
                dbc.Label("Google Drive", className="mb-0"),
                dbc.Button("+", id="btn-drive-add", color="link", className="p-0 ms-2 text-decoration-none text-muted", title="Add Google Drive link", style={"fontSize": "1.2rem", "lineHeight": "1"})
            ], className="d-flex align-items-center mt-3 mb-1"),
            html.Div(id='drive-links-container'),

            html.Div([
                dbc.Label("Website", className="mb-0"),
                dbc.Button("+", id="btn-website-add", color="link", className="p-0 ms-2 text-decoration-none text-muted", title="Add Website link", style={"fontSize": "1.2rem", "lineHeight": "1"})
            ], className="d-flex align-items-center mt-3 mb-1"),
            html.Div(id='website-links-container'),

            html.Hr(className="my-2"),
            html.Div([
                dbc.Button("Delete", id="btn-delete", color="danger", className="flex-fill me-2", style={"backgroundColor": ConfigManager.get_danger_color(), "borderColor": ConfigManager.get_danger_color(), "padding": "6px 0"}),
                dbc.Button("Cancel", id="btn-revert", className="flex-fill me-2", style={"padding": "6px 0", "backgroundColor": "#6c757d", "borderColor": "#6c757d", "color": "#fff"}),
                dbc.Button("Save", id="btn-save", color="primary", className="flex-fill me-2", style={"padding": "6px 0"}),
                dbc.Button("Save & Close", id="btn-save-close", color="success", className="flex-fill", style={"padding": "6px 0", "backgroundColor": _DONE_COLOR, "borderColor": _DONE_COLOR})
            ], className="d-flex mt-4"),
            dbc.Button("New Node", id="btn-new-node", color="secondary", className="w-100 mt-2",
                       style={"padding": "8px 0"}),
            dbc.Tooltip("Discard unsaved changes and revert this node to its last saved state", target="btn-revert", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Tooltip("Save changes", target="btn-save", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Tooltip("Save changes and close the node editor", target="btn-save-close", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Tooltip("Delete this node", target="btn-delete", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Tooltip("Create a new node", target="btn-new-node", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            html.Div(id="save-output", className="text-success fw-bold text-end mt-2 mb-5"),
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
        children=[node_editor_content],
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
            "borderRight": "1px solid #495057",
            "transition": "transform 0.3s ease",
            "transform": SIDEBAR_TRANSLATE_CLOSED,
            "willChange": "transform",
            "backgroundColor": "#212529"
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
                    dbc.Button("+", id="btn-goals-sidebar-new",
                               color="link",
                               className="p-0 ms-2 text-decoration-none text-muted",
                               style={"fontSize": "1.4rem", "lineHeight": "1"}),
                    dbc.Tooltip("New goal", target="btn-goals-sidebar-new", placement="right",
                                delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                ], className="d-flex align-items-center"),
                html.Span("×", id="btn-details-goals-close",
                           className="fs-3 text-white",
                           style={"cursor": "pointer"}),
            ], className="d-flex justify-content-between align-items-center mb-2 mt-2 px-3"),

            html.Div(
                dbc.Input(id="details-goal-search", type="text",
                          placeholder="Search goals...", size="sm",
                          debounce=False,
                          style={"backgroundColor": "#2b3035",
                                 "border": "1px solid #495057",
                                 "color": "#dee2e6",
                                 "width": "100%",
                                 "boxSizing": "border-box"}),
                style={"padding": "0 12px", "marginBottom": "8px"},
            ),

            html.Div(
                dbc.Select(id="details-goal-sort", options=[
                    {"label": "Priority", "value": "priority"},
                    {"label": "Time", "value": "time-desc"},
                    {"label": "Manual", "value": "manual"},
                    {"label": "Alphabetical", "value": "alpha-asc"},
                ], value="priority", size="sm",
                    persistence=True, persistence_type="local",
                    style={"flex": "1", "backgroundColor": "#2b3035",
                           "border": "1px solid #495057",
                           "color": "#dee2e6", "fontSize": "0.8rem"}),
                style={"padding": "0 12px", "marginBottom": "12px"},
            ),

            html.Div(id="details-goal-list-container",
                     style={"overflowY": "auto", "flex": "1", "padding": "0 12px"}),
        ],
        style={
            "position": "absolute",
            "top": "0",
            "left": SIDEBAR_WIDTH_NEG_PX,
            "width": SIDEBAR_WIDTH_PX,
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
            "left": SIDEBAR_WIDTH_NEG_PX,
            "width": SIDEBAR_WIDTH_PX,
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


# --- Filters sidebar (right) ---
def build_filters_content():
    # Hydrate from persisted state when remember-filters is enabled; otherwise
    # fall back to hardcoded defaults so a fresh session looks unchanged.
    if ConfigManager.get_remember_filters():
        f = ConfigManager.get_filters()
    else:
        f = ConfigManager._FILTER_DEFAULTS

    # Pre-build subcontext options for the persisted context selection so the
    # restored value sticks on initial render. The encoding "ctx\x1fsub" uses
    # ASCII unit-separator instead of "::" because Dash mangles dropdown
    # values containing "::" (it overlaps with internal dependency notation),
    # silently dropping them during layout serialization.
    initial_sub_opts = []
    persisted_contexts = f["context"] if isinstance(f["context"], list) else ([f["context"]] if f["context"] else [])
    if persisted_contexts:
        all_subs = ConfigManager.get_subcontexts()
        multi_context = len(persisted_contexts) > 1
        for c in persisted_contexts:
            none_label = f"{c} > None" if multi_context else "None"
            initial_sub_opts.append({"label": none_label, "value": f"{c}\x1f"})
            for s in sort_subcontexts(all_subs.get(c, [])):
                label = f"{c} > {s}" if multi_context else s
                initial_sub_opts.append({"label": label, "value": f"{c}\x1f{s}"})
    # Migrate any legacy "::" values from before the separator change.
    persisted_subs = [v.replace("::", "\x1f", 1) if isinstance(v, str) and "\x1f" not in v else v
                      for v in (f["subcontext"] or [])]
    valid_subs = {o["value"] for o in initial_sub_opts}
    initial_sub_value = [v for v in persisted_subs if v in valid_subs]

    return html.Div([
        html.Div([
            html.H4("Filters"),
            html.Span("×", id="btn-close-filters", className="fs-3 text-white float-end", style={"cursor": "pointer"})
        ], className="d-flex justify-content-between align-items-center mb-1 mt-2"),

        html.H5("General", className="mt-2 mb-1"),
        dbc.Label("Node Type", className="mt-2"),
        dcc.Dropdown(
            id="filter-node-type",
            options=[{"label": t, "value": t} for t in NODE_TYPES],
            value=f["node_type"],
            multi=True,
            placeholder="All",
            style={"color": "#212529"},
        ),

        dbc.Label("Context", className="mt-2"),
        dcc.Dropdown(
            id="filter-context",
            options=[{"label": c, "value": c} for c in CONTEXTS],
            value=f["context"],
            multi=True,
            placeholder="All",
            style={"color": "#212529"},
        ),

        dbc.Label("Subcontext", className="mt-2"),
        dcc.Dropdown(
            id="filter-subcontext",
            options=initial_sub_opts,
            value=initial_sub_value,
            multi=True,
            placeholder="All",
            style={"color": "#212529"},
        ),

        html.Hr(className="my-3"),

        html.H5("Ratings", className="mt-2 mb-1"),
        dbc.Label("Min Value", className="mt-2"),
        dcc.Slider(min=1, max=10, step=1, value=f["value"], id="filter-value",
                   marks={i: str(i) for i in range(1, 11)}),

        dbc.Label("Min Interest", className="mt-2"),
        dcc.Slider(min=1, max=10, step=1, value=f["interest"], id="filter-interest",
                   marks={i: str(i) for i in range(1, 11)}),

        dbc.Label("Max Effort", className="mt-3"),
        dcc.Slider(min=1, max=10, step=1, value=f["difficulty"], id="filter-difficulty",
                   marks={i: str(i) for i in range(1, 11)}),

        dbc.Label("Max Time", className="mt-2"),
        html.Div([
            dbc.Input(id="filter-time", type="number", min=0.1,
                      value=f["time"] if f["time"] != "" else None,
                      placeholder="No limit", size="sm",
                      className="flex-grow-1"),
            dbc.Select(id="filter-time-unit", options=[
                {"label": "Hours", "value": "hours"},
                {"label": "Weeks", "value": "weeks"},
                {"label": "Months", "value": "months"},
                {"label": "Years", "value": "years"},
            ], value=f["time_unit"], size="sm", style={"width": "100px"}),
        ], className="d-flex gap-2"),

        html.Hr(className="my-3"),

        html.H5("Status", className="mt-2 mb-1"),
        html.Div([
            dbc.Checklist(
                options=[{"label": "Show Done", "value": "show_done"}],
                value=f["done"],
                id="filter-done",
                switch=True,
            ),
            dbc.Checklist(
                options=[{"label": "Show Dormant", "value": "show_dormant"}],
                value=f.get("show_dormant", []),
                id="filter-dormant",
                switch=True,
            ),
        ], className="d-flex gap-3 flex-wrap"),

        html.Hr(className="my-3"),

        html.H5("Communities", className="mt-2 mb-1"),
        dbc.Label("Detection Method", className="mt-2"),
        dbc.Select(id="community-method", options=[
            {"label": "Islands", "value": "components"},
            {"label": "Clusters", "value": "louvain"},
            {"label": "Orphans", "value": "orphans"},
        ], value=f["community_method"]),

        dbc.Label("Community", className="mt-3"),
        dbc.Select(id="filter-community", options=[{"label": "All", "value": "All"}], value=f["community"]),

        html.Hr(className="my-3"),

        html.Div([
            dbc.Checklist(
                options=[{"label": "Memory", "value": "enabled"}],
                value=["enabled"] if ConfigManager.get_remember_filters() else [],
                id="filter-remember",
                switch=True,
            ),
        ], className="d-flex gap-3 flex-wrap"),
        dbc.Tooltip(
            "Show Done nodes on the canvas. Off = hide them.",
            target="filter-done", placement="top",
            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS},
        ),
        dbc.Tooltip(
            "Show dormant (event-deferred) nodes on the canvas. Off = hide them. "
            "The events tab graph always shows them regardless.",
            target="filter-dormant", placement="top",
            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS},
        ),
        dbc.Tooltip(
            "Remember main canvas filters across sessions and browser refreshes. "
            "When off, filters reset to defaults on app start.",
            target="filter-remember", placement="top",
            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS},
        ),

        html.Hr(className="my-3"),
        html.Div([
            dbc.Button("Clear Filters", id="btn-clear-filters", color="secondary", size="sm", className="flex-fill"),
            dbc.Button("Settle", id="btn-sidebar-relayout", color="secondary", size="sm", className="flex-fill"),
            dbc.Tooltip("Re-run layout physics to untangle nodes",
                        target="btn-sidebar-relayout", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
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
            "borderLeft": "1px solid #495057",
            "transition": "right 0.3s ease",
            "backgroundColor": "#212529"
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
