"""
Layout definitions for the Details tab.

Provides a consolidated view for drilling into any node's dependencies,
subtasks, and time simulation — merging the best parts of the Goals
and Simulation tabs.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from typing import Optional, List, Any
from config import (
    ConfigManager,
    TOOLTIP_SHOW_DELAY_MS,
    TOOLTIP_HIDE_DELAY_MS,
    badge_style,
)
from styles import stylesheet


def _freeze_indicator(indicator_id: str):
    """Snowflake overlay shown on a canvas while its freeze toggle is on.

    Hidden by default; a clientside callback flips display + keeps the style
    in sync with the freeze-rerender store. Centered horizontally with the
    tab bar's Filters button (`right: 19px` with a 1.6rem icon).
    """
    return html.I(
        className="bi bi-snow",
        id=indicator_id,
        style={
            "display": "none",
            "position": "absolute",
            "top": "12px",
            "right": "19px",
            "fontSize": "1.6rem",
            "color": "#7ec8e3",
            "textShadow": "0 0 6px rgba(126, 200, 227, 0.5)",
            "pointerEvents": "none",
            "zIndex": 10,
        },
    )


def build_graph_settings_panel(
    prefix: str,
    *,
    include_depth_controls: bool = True,
    defaults_getter=ConfigManager.get_graph_layout_defaults,
):
    """Build a graph settings panel. Single source of truth for all three canvases
    (Nodes / Details / Events).

    Callers pass the slider `defaults_getter` explicitly to select between
    `get_graph_layout_defaults` (main canvas) and
    `get_details_graph_layout_defaults` (details/events). Set
    ``include_depth_controls=False`` to hide the Max-Depth and Neighbors/Smooth
    toggles (they only make sense where a root-relative subtree is being
    rendered, which the events canvas isn't) — a standalone Freeze switch
    replaces the toggle row in that mode.
    """
    gl = defaults_getter()
    p = prefix
    reset_btn_id = f"btn-reset-{p}"

    children = [
        html.Div([
            html.Span("Graph Settings", style={"fontWeight": "300", "fontSize": "1.05rem"}),
            dbc.Button("\u21ba", id=reset_btn_id, color="link", size="sm",
                       className="ms-2 p-0",
                       style={"fontSize": "1.1rem", "lineHeight": "1",
                              "color": "#adb5bd", "position": "relative",
                              "top": "0px", "textDecoration": "none"}),
            dbc.Tooltip("Restore defaults", target=reset_btn_id, placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
        ], className="d-flex align-items-center",
           style={"marginBottom": "12px"}),
    ]

    # Panels without the top toggle row (e.g. events) still need a Freeze
    # switch; render it standalone right under the title so it sits in the
    # same visual zone as the toggles row on other panels.
    if not include_depth_controls:
        children += [
            dbc.Switch(
                id=f"{p}-freeze-rerender",
                label="Freeze",
                value=False,
                style={"fontSize": "0.82rem"},
            ),
            dbc.Tooltip("Pause graph updates on save. Use Settle to refresh manually.",
                        target=f"{p}-freeze-rerender", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            html.Hr(style={"borderColor": "#495057", "margin": "12px 0"}),
        ]

    if include_depth_controls:
        children += [
            html.Div("Max Depth", className="settings-label"),
            dcc.Slider(
                id=f"{p}-max-depth",
                min=0, max=5, step=1, value=0,
                marks={0: "All", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5"},
                updatemode="mouseup",
            ),

            html.Div([
                dbc.Switch(
                    id=f"{p}-neighbor-links",
                    label="Neighbors",
                    value=True,
                    style={"fontSize": "0.82rem"},
                ),
                dbc.Switch(
                    id=f"{p}-animate",
                    label="Smooth",
                    value=True,
                    style={"fontSize": "0.82rem"},
                ),
                dbc.Switch(
                    id=f"{p}-freeze-rerender",
                    label="Freeze",
                    value=False,
                    style={"fontSize": "0.82rem"},
                ),
            ], className="d-flex gap-2 mt-3"),
            dbc.Tooltip("Pause graph updates on save. Use Settle to refresh manually.",
                        target=f"{p}-freeze-rerender", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),

            html.Hr(style={"borderColor": "#495057", "margin": "12px 0"}),
        ]

    children += [
        html.Div("Edge Length", className="settings-label"),
        dcc.Slider(
            id=f"{p}-edge-length",
            min=50, max=300, step=10, value=gl.get('edge_length', 100),
            marks={50: "50", 100: "100", 150: "150", 200: "200", 250: "250", 300: "300"},
            updatemode="mouseup",
        ),

        html.Div("Gravity", className="settings-label"),
        dcc.Slider(
            id=f"{p}-gravity",
            min=0, max=5, step=0.25, value=gl.get('gravity', 0.25),
            marks={0: "0", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5"},
            updatemode="mouseup",
        ),

        html.Div("Repulsion", className="settings-label"),
        dcc.Slider(
            id=f"{p}-repulsion",
            min=500, max=100000, step=500, value=gl.get('repulsion', 4500),
            marks={500: "500", 25000: "25k", 50000: "50k", 75000: "75k", 100000: "100k"},
            updatemode="mouseup",
        ),
    ]

    children += [
        html.Hr(style={"borderColor": "#495057", "margin": "12px 0"}),

        dbc.Button("Settle", id=f"{p}-relayout",
                   color="secondary", size="sm", className="w-100 mt-2"),
        dbc.Tooltip("Re-run layout physics to untangle nodes",
                    target=f"{p}-relayout", placement="top",
                    delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
    ]

    return html.Div(children, id=f"{p}-panel", className="graph-settings-panel",
                    style={"display": "none"})


def build_details_tab_content():
    """Builds the Details tab UI.

    Layout (two vertical zones):
      ┌─────────────────────────────────┬─────────────────────────────────┐
      │  LEFT PANEL (orange)            │  CANVAS (teal) — full height    │
      │  ┌─────────────────────────┐   │                                  │
      │  │ ☰  [Search ▾] [← ] [→] │   │   Cytoscape dependency graph     │
      │  ├─────────────────────────┤   │                                  │
      │  │ Node name / details /   │   │   (Focus ⌕ overlay, bot-left)    │
      │  │ Locate | Edit           │   │                                  │
      │  └─────────────────────────┘   │                                  │
      ├─────────────────────────────────┴──────────────────── (h-drag) ───┤
      │  Subtasks table                     │  Simulation chart           │
      └─────────────────────────────────────┴─────────────────────────────┘
    """

    _ted = ConfigManager.get_time_estimate_defaults()

    # ------------------------------------------------------------------ #
    #  LEFT PANEL HEADER  (search bar + nav + goals toggle)               #
    #  This is the ONLY place these controls live — no full-width top bar  #
    # ------------------------------------------------------------------ #
    left_panel_header = html.Div([
        # Search bar wrapping container
        html.Div(dcc.Dropdown(
            id="details-node-select",
            placeholder="Select a node...",
            clearable=True,
            style={"minWidth": "100px"},
        ), className="text-dark", style={"flex": "1", "minWidth": "0", "margin": "0 8px"}),

        # Navigation arrows wrapping container (centers them in their right-side space)
        html.Div([
            dbc.Button("\u2190", id="btn-details-nav-back", color="secondary",
                       size="sm", disabled=True,
                       style={"whiteSpace": "nowrap", "minWidth": "30px",
                              "padding": "2px 6px"}),
            dbc.Button("\u2192", id="btn-details-nav-forward", color="secondary",
                       size="sm", className="ms-1", disabled=True,
                       style={"whiteSpace": "nowrap", "minWidth": "30px",
                              "padding": "2px 6px"}),
        ], style={"flex": "0 0 75px", "display": "flex", "justifyContent": "center"}),
    ], className="d-flex align-items-center py-2 px-2",
       style={"borderBottom": "1px solid #495057", "flexShrink": "0", "paddingBottom": "8px"})

    # ------------------------------------------------------------------ #
    #  EMPTY STATE  (inside left panel, shown when no node selected)      #
    # ------------------------------------------------------------------ #
    empty_state = html.Div(
        id="details-empty",
        children=[
            html.Div([
                html.H6("Suggestions", className="text-muted mb-1",
                        style={"fontWeight": "300", "letterSpacing": "1px"}),
                html.P("Click one, or search above.",
                       className="text-muted small"),
            ], style={"textAlign": "center", "marginTop": "24px",
                      "marginBottom": "12px"}),
            html.Div(id="details-suggestions-container",
                     style={"padding": "0 12px"}),
        ],
        style={"flex": "1", "overflowY": "auto"},
    )

    # ------------------------------------------------------------------ #
    #  NODE SUMMARY  (inside details-content, shown when node selected)   #
    # ------------------------------------------------------------------ #
    node_summary = html.Div([
        html.H4(id="details-node-name", className="mt-3 mb-2",
                style={"fontWeight": "300", "letterSpacing": "1px",
                       "overflow": "hidden", "textOverflow": "ellipsis",
                       "whiteSpace": "nowrap"}),
        # Badges row: type, status, priority
        html.Div(id="details-node-badges",
                 className="d-flex gap-1 flex-wrap mb-2"),

        # Description
        html.Div(id="details-node-description",
                 className="text-muted mb-2",
                 style={"fontSize": "0.9rem", "whiteSpace": "pre-wrap",
                        "maxHeight": "160px", "overflowY": "auto",
                        "minHeight": "40px"}),

        # Progress bar
        html.Div(id="details-progress-section", style={"display": "none"}, children=[
            dbc.Progress(id="details-progress-bar", value=0,
                         className="mb-1", style={"height": "14px"}),
            html.Small(id="details-progress-text", className="text-muted",
                       style={"fontSize": "0.78rem"}),
        ]),

        # Stats grid
        html.Div([
            _attribute_row("Type", "details-attr-type"),
            _attribute_row("Status", "details-attr-status"),
            _attribute_row("Context", "details-attr-context"),
            _attribute_row("Time", "details-attr-time"),
            _attribute_row("Value", "details-attr-value"),
            _attribute_row("Interest", "details-attr-interest"),
            _attribute_row("Effort", "details-attr-effort"),
        ], className="mt-2"),

        # Hidden priority container
        html.Div(id="details-priority-section", style={"display": "none"}, children=[
            html.Div(id="details-priority-badge"),
        ]),

        # Action buttons — Edit | Explain | Locate  (Focus lives on the canvas overlay)
        html.Div([
            dbc.Button("Edit", id="btn-details-edit", color="secondary",
                       size="sm", style={"flex": "1"}),
            dbc.Tooltip("Open the node editor", target="btn-details-edit", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Button("Explain", id="btn-details-explain", color="secondary",
                       size="sm", className="ms-1", style={"flex": "1"}),
            dbc.Tooltip("Show where this node's priority score comes from",
                        target="btn-details-explain", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Button("Locate", id="btn-details-locate", color="secondary",
                       size="sm", className="ms-1", style={"flex": "1"}),
            dbc.Tooltip("Briefly pulse this node in the mini-graph",
                        target="btn-details-locate", placement="top",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
        ], className="d-flex mt-3"),

        # Hidden sink for the Locate clientside callback (Dash requires an Output).
        html.Div(id="details-locate-dummy", style={"display": "none"}),

    ], id="details-node-summary",
       style={"overflowY": "auto"})

    # details-content: wraps node_summary, shown/hidden by callback
    detail_content = html.Div(
        id="details-content",
        style={"display": "none", "flexDirection": "column", "flex": "1",
               "padding": "24px 14px 12px 14px", "overflowY": "auto"},
        children=[node_summary],
    )

    # ------------------------------------------------------------------ #
    #  LEFT PANEL  (orange area: header + empty/content)                  #
    # ------------------------------------------------------------------ #
    left_panel = html.Div([
        left_panel_header,
        empty_state,
        detail_content,
    ], id="details-left-panel", style={
        "width": "375px",
        "minWidth": "260px",
        "display": "flex",
        "flexDirection": "column",
        "borderRight": "1px solid #495057",
        "flexShrink": "0",
        "overflow": "hidden",
    })

    # ------------------------------------------------------------------ #
    #  VERTICAL DRAG HANDLE (between left panel and canvas)               #
    # ------------------------------------------------------------------ #
    v_drag_handle_upper = html.Div(
        id="details-v-drag-upper",
        style={
            "width": "6px",
            "cursor": "col-resize",
            "backgroundColor": "transparent",
            "borderLeft": "1px solid #495057",
            "flexShrink": "0",
            "transition": "background-color 0.15s",
        },
    )

    # ------------------------------------------------------------------ #
    #  DEPENDENCY GRAPH  (teal area: full height, starts at tab bar)      #
    # ------------------------------------------------------------------ #
    gl = ConfigManager.get_details_graph_layout_defaults()
    dep_graph = html.Div([
        html.Div([
            cyto.Cytoscape(
                id='details-mini-graph',
                elements=[],
                layout={
                    'name': 'fcose', 'quality': 'proof',
                    'animate': False, 'fit': True,
                    'padding': 20, 'numIter': 2500, 'randomize': False,
                    'idealEdgeLength': gl.get('edge_length', 100),
                    'nodeRepulsion': gl.get('repulsion', 4500),
                    'gravity': gl.get('gravity', 0.25),
                },
                style={'width': '100%', 'height': '100%', 'backgroundColor': '#1a1d21',
                       'borderRadius': '0'},
                stylesheet=stylesheet,
                userZoomingEnabled=False,
                userPanningEnabled=False,
                boxSelectionEnabled=True,
                autoungrabify=False,
            ),
            dbc.Button(html.I(className="bi bi-gear"),
                       id="btn-details-graph-settings",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right-mid"),
            dbc.Tooltip("Graph settings", target="btn-details-graph-settings", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            _freeze_indicator("details-freeze-indicator"),
            build_graph_settings_panel(
                "details-graph-settings",
                defaults_getter=ConfigManager.get_details_graph_layout_defaults,
            ),
            dbc.Button(html.I(className="bi bi-search"),
                       id="btn-details-focus",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right-far"),
            dbc.Tooltip("Open this node's subtree in the main canvas",
                        target="btn-details-focus", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Button(html.I(className="bi bi-arrows-fullscreen"),
                       id="btn-details-graph-fullscreen",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right"),
            dbc.Tooltip("Toggle fullscreen", target="btn-details-graph-fullscreen", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            html.Div(id="details-canvas-node-count", className="canvas-stats-overlay"),
        ], style={"position": "relative", "flex": "1", "minHeight": "0"}),
    ], id="details-dep-graph-container", style={
        "flex": "1",
        "minWidth": "300px",
        "display": "flex",
        "flexDirection": "column",
    })

    # UPPER SECTION: left panel + drag + canvas — no padding at top so
    # canvas reaches flush to the tab bar
    upper_section = html.Div([
        left_panel,
        v_drag_handle_upper,
        dep_graph,
    ], id="details-upper-section",
       style={"display": "flex", "flex": "1.6", "minHeight": "0"})

    # ------------------------------------------------------------------ #
    #  HORIZONTAL DRAG HANDLE                                             #
    # ------------------------------------------------------------------ #
    h_drag_handle = html.Div(
        id="details-h-drag",
        style={
            "height": "6px",
            "cursor": "ns-resize",
            "backgroundColor": "transparent",
            "borderTop": "1px solid #495057",
            "flexShrink": "0",
            "transition": "background-color 0.15s",
        },
    )

    # ------------------------------------------------------------------ #
    #  LOWER SECTION: Subtasks table + Simulation                         #
    # ------------------------------------------------------------------ #
    subtasks_section = html.Div([
        html.Div([
            html.Div([
                html.H5("Subtasks", className="mb-0"),
                dbc.Button("+", id="btn-details-add-node", color="link",
                           className="p-0 ms-2 text-decoration-none text-muted",
                           style={"fontSize": "1.2rem", "lineHeight": "1"}),
                dbc.Tooltip("Add subtask node", target="btn-details-add-node", placement="right",
                            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            ], className="d-flex align-items-center"),
            html.Div([
                dbc.Checklist(
                    id="details-include-soft-needs",
                    options=[{"label": "Soft Needs", "value": "include"}],
                    value=["include"],
                    switch=True,
                    style={"fontSize": "0.82rem"},
                ),
                dbc.Checklist(
                    id="details-include-transitive",
                    options=[{"label": "Transitive", "value": "include"}],
                    value=["include"],
                    switch=True,
                    style={"fontSize": "0.82rem"},
                ),
                dbc.Checklist(
                    id="details-include-synergies",
                    options=[{"label": "Synergies", "value": "include"}],
                    value=["include"],
                    switch=True,
                    style={"fontSize": "0.82rem"},
                ),
                dbc.Checklist(
                    id="details-hide-done",
                    options=[{"label": "Hide Done", "value": "hide_done"}],
                    value=["hide_done"],
                    switch=True,
                    style={"fontSize": "0.82rem", "marginRight": "12px"},
                ),
            ], className="d-flex gap-3"),
        ], className="d-flex align-items-center justify-content-between mb-2"),
        html.Div(id="details-subtasks-table-container",
                 style={"overflowY": "visible", "flex": "none"}),
    ], id="details-subtasks-section",
       style={"flex": "1", "minWidth": "300px", "display": "flex",
              "flexDirection": "column", "paddingRight": "8px",
              "overflowY": "auto"})

    v_drag_handle_lower = html.Div(
        id="details-v-drag-lower",
        style={
            "width": "6px",
            "cursor": "col-resize",
            "backgroundColor": "transparent",
            "borderLeft": "1px solid #495057",
            "flexShrink": "0",
            "transition": "background-color 0.15s",
        },
    )

    sim_section = html.Div([
        html.Div(id="details-sim-empty", children=[
            html.Div([
                html.P("Select a node to see the time distribution.",
                       className="text-muted text-center",
                       style={"marginTop": "40px"}),
            ]),
        ]),
        html.Div(id="details-sim-results",
                 style={"display": "none", "flex": "1", "minHeight": "0"},
                 children=[
            dcc.Graph(
                id="details-sim-chart",
                config={"displayModeBar": False},
                responsive=True,
                style={"height": "100%", "minHeight": "350px"},
            ),
        ]),
    ], id="details-sim-section",
       style={"width": "42%", "minWidth": "250px", "paddingLeft": "12px",
              "display": "flex", "flexDirection": "column"})

    lower_section = html.Div([
        subtasks_section,
        v_drag_handle_lower,
        sim_section,
    ], id="details-lower-section",
       style={"display": "flex", "padding": "8px 24px", "flex": "1", "minHeight": "0"})

    # ------------------------------------------------------------------ #
    #  MODALS & SIDEBARS                                                  #
    # ------------------------------------------------------------------ #
    filters_sidebar = _build_filters_sidebar()
    add_node_modal = _build_add_node_modal(_ted)

    subtask_remove_modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Remove Subtask")),
        dbc.ModalBody(id="details-subtask-remove-modal-body"),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-details-subtask-remove-cancel",
                       color="secondary", className="me-auto"),
            dbc.Button("Remove Edge", id="btn-details-subtask-remove-edge",
                       color="warning", className="me-2"),
            dbc.Button("Delete Node", id="btn-details-subtask-delete-node",
                       color="danger"),
        ]),
    ], id="modal-details-subtask-remove", is_open=False, centered=True)

    explain_legend_items = []
    for label, color in (('Self', '#7a6e62'), ('Hard', '#375a7f'),
                         ('Soft', '#6c7682'), ('Synergy', '#5a8088')):
        explain_legend_items.append(html.Span([
            html.Span("\u25A0 ", style={"color": color}),
            html.Span(label, style={"color": "#adb5bd"}),
        ], className="me-3"))

    explain_modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle(id="details-explain-title")),
        dbc.ModalBody([
            html.Div(id="details-explain-summary"),
            html.Hr(className="my-3"),
            html.Div([
                html.H5("Top Contributors", className="mt-2 mb-1"),
                html.Div([
                    html.Span("Show", style={"color": "#adb5bd",
                                              "fontSize": "0.85rem",
                                              "marginRight": "6px"}),
                    dbc.Input(id="details-explain-count",
                              type="number", min=1, max=100, step=1, value=10,
                              size="sm", debounce=True,
                              style={"width": "42px",
                                     "height": "22px",
                                     "padding": "0 4px",
                                     "fontSize": "0.8rem",
                                     "lineHeight": "1",
                                     "textAlign": "center"}),
                ], className="d-flex align-items-center"),
            ], className="d-flex justify-content-between align-items-center"),
            dcc.Store(id="details-explain-contrib-store"),
            dcc.Graph(id="details-explain-chart",
                      config={"displayModeBar": False}),
            html.Div(explain_legend_items,
                     style={"fontSize": "0.78rem", "textAlign": "right"}),
        ]),
        dbc.ModalFooter([
            dbc.InputGroup([
                dbc.Button("Focus top",
                           id="btn-details-explain-focus",
                           color="primary", size="sm",
                           style={"height": "31px"}),
                dbc.Input(id="details-explain-focus-count",
                          type="number", step=1, value=3,
                          debounce=True,
                          style={"width": "52px",
                                 "height": "31px",
                                 "textAlign": "center",
                                 "fontSize": "0.85rem",
                                 "padding": "0",
                                 "border": "1px solid #495057"}),
            ], style={"width": "auto"}),
            html.Span(id="details-explain-focus-feedback",
                      style={"color": "#dc3545",
                             "fontSize": "0.8rem",
                             "marginLeft": "10px",
                             "alignSelf": "center"}),
            dbc.Button("Close", id="btn-details-explain-close",
                       color="secondary", className="ms-auto"),
        ], className="d-flex"),
    ], id="modal-details-explain", size="lg", is_open=False,
       centered=True, scrollable=True)

    return html.Div([
        dcc.Store(id='details-selected-node-store', data=None),
        dcc.Store(id='details-refresh-trigger', data=0),
        # UI-only refresh for the goals sidebar list. Bumped by goals_sidebar.js
        # on open so render_goal_list re-runs — but NOT an input to core_engine,
        # so opening doesn't block the animation on a graph regen.
        dcc.Store(id='goals-ui-refresh-trigger', data=0),
        dcc.Store(id='details-subtask-remove-pending', data=None),
        dcc.Store(id='details-goal-order-store', data=ConfigManager.get_goal_order() or None),
        dcc.Store(id='details-nav-history', data=[]),
        dcc.Store(id='details-nav-index', data=-1),
        dcc.Input(id='details-goal-drag-order-input', type='text', value='',
                  style={'display': 'none'}),
        dcc.Input(id='details-simulate-trigger-input', type='text', value='',
                  style={'display': 'none'}),
        dcc.Input(id='details-edit-trigger-input', type='text', value='',
                  style={'display': 'none'}),
        subtask_remove_modal,
        add_node_modal,
        explain_modal,

        # Main content: upper (left panel + canvas) + lower (subtasks + sim)
        html.Div([
            upper_section,
            h_drag_handle,
            lower_section,
        ], style={"flex": "1", "display": "flex", "flexDirection": "column",
                  "overflow": "hidden"}),

        filters_sidebar,
    ], style={
        "display": "flex",
        "height": "100%",
        "width": "100%",
        "position": "relative",
    })


def _attribute_row(label, value_id):
    """Creates a compact attribute display row."""
    return html.Div([
        html.Span(f"{label}:", className="text-muted",
                  style={"width": "70px", "fontSize": "0.82rem"}),
        html.Span(id=value_id, style={"fontSize": "0.85rem", "fontWeight": "500"}),
    ], className="d-flex align-items-center mb-1")


def _build_suggestion_row(node_name, badge_text, badge_color,
                          badge_id=None, tooltip_text=None):
    """One clickable suggestion row in the Details empty state.

    Optional badge_id + tooltip_text attach a hover tooltip (0.7s delay) to the
    badge — used for recommendation score badges.
    """
    # Force white text everywhere for visual consistency — overrides
    # Bootstrap's default dark-on-yellow for warning badges.
    badge_style = {"fontSize": "0.7rem", "color": "#ffffff"}
    badge_kwargs = {"id": badge_id} if badge_id else {}
    if badge_color == "pink":
        badge_style.update({"backgroundColor": "#e83e8c"})
        badge = html.Span(badge_text, className="badge",
                          style=badge_style, **badge_kwargs)
    else:
        badge = dbc.Badge(badge_text, color=badge_color,
                          style=badge_style, **badge_kwargs)

    children = [
        html.Span(node_name, style={"fontWeight": "500", "fontSize": "0.9rem",
                                     "overflow": "hidden",
                                     "textOverflow": "ellipsis",
                                     "whiteSpace": "nowrap",
                                     "flex": "1", "minWidth": "0"}),
        badge,
    ]
    if badge_id and tooltip_text:
        children.append(dbc.Tooltip(
            tooltip_text, target=badge_id, placement="left",
            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS},
        ))

    return html.Div(
        children,
        id={"type": "details-suggestion-item", "index": node_name},
        className="d-flex align-items-center justify-content-between",
        style={
            "cursor": "pointer",
            "border": "1px solid #495057",
            "backgroundColor": "#212529",
            "borderRadius": "4px",
            "padding": "8px 12px",
            "marginBottom": "6px",
            "gap": "8px",
        },
    )


def build_details_suggestions(override_row, goal_rows, rec_rows):
    """Assemble the Details empty-state suggestion list from pre-built rows."""
    sections = []

    def _section(title, rows):
        return html.Div([
            html.H6(title, className="text-muted mb-2",
                    style={"fontSize": "0.78rem", "fontWeight": "500",
                           "letterSpacing": "1px", "textTransform": "uppercase",
                           "marginTop": "12px"}),
            html.Div(rows),
        ])

    if override_row is not None:
        sections.append(_section("Manual Override", [override_row]))
    if goal_rows:
        sections.append(_section("Priority Goals", goal_rows))
    if rec_rows:
        sections.append(_section("Top Recommendations", rec_rows))

    if not sections:
        return html.P("No suggestions yet — add priority goals or an override.",
                      className="text-muted small text-center mt-3")
    return sections


def build_goal_card(name: str, status: str, completion: dict, subtask_count: int, is_selected: bool = False, priority_rank: Optional[int] = None,
                    show_order_buttons: bool = False, is_first: bool = False, is_last: bool = False):
    """Builds a single goal card for the goal sidebar list."""
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

    # status badge uses centralized BADGE_PALETTE (constructed inline below)

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
                dbc.Badge(str(priority_rank), color="warning",
                          style={"fontSize": "0.7rem", "color": "#ffffff"}) if priority_rank is not None else None,
                html.Span(effective_status,
                          className="badge ms-1" if priority_rank is not None else "badge",
                          style={**badge_style(effective_status, font_size="0.7rem"),
                                 "width": "62px", "textAlign": "center",
                                 "display": "inline-block"}),
            ], className="d-flex align-items-center ms-2 gap-1"),
        ], className="d-flex align-items-center justify-content-between mb-1"),
    ]

    # Stats line
    if total > 0:
        stats_text = f"{done}/{total} hard subtasks \u00b7 {pct}% \u00b7 {formatted_time}"
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


def _build_filters_sidebar():
    """Builds the filters sidebar for the Details tab dependency graph."""
    return html.Div(
        id="details-filters-sidebar",
        children=[
            html.Div([
                html.H5("Graph Filters", className="mb-0"),
                html.Span("×", id="btn-details-filters-close",
                           className="fs-4 text-white",
                           style={"cursor": "pointer"}),
            ], className="d-flex justify-content-between align-items-center mb-3 mt-3 px-3"),

            html.Div([
                dbc.Label("Node Types", className="text-muted small mb-1"),
                dbc.Checklist(
                    id="details-filter-types",
                    options=[
                        {"label": "Learn", "value": "Learn"},
                        {"label": "Goal", "value": "Goal"},
                        {"label": "Action", "value": "Action"},
                        {"label": "Resource", "value": "Resource"},
                    ],
                    value=["Learn", "Goal", "Action", "Resource"],
                    className="mb-3",
                    style={"fontSize": "0.85rem"},
                ),

                dbc.Label("Status", className="text-muted small mb-1"),
                dbc.Checklist(
                    id="details-filter-status",
                    options=[
                        {"label": "Open", "value": "Open"},
                        {"label": "Blocked", "value": "Blocked"},
                        {"label": "Done", "value": "Done"},
                    ],
                    value=["Open", "Blocked", "Done"],
                    className="mb-3",
                    style={"fontSize": "0.85rem"},
                ),

                dbc.Button("Reset Filters", id="btn-details-filters-reset",
                           color="secondary", size="sm", className="w-100 mt-2"),
            ], style={"padding": "0 16px"}),
        ],
        style={
            "position": "absolute",
            "top": "0",
            "right": "-280px",
            "width": "280px",
            "height": "100%",
            "zIndex": 100,
            "overflowX": "hidden",
            "overflowY": "auto",
            "borderLeft": "1px solid #495057",
            "transition": "right 0.3s ease",
            "backgroundColor": "#212529",
            "display": "flex",
            "flexDirection": "column",
        }
    )


def _build_add_node_modal(ted):
    """Builds the Add Node modal — mirrors the Goals tab modal with
    Relationships and External Resources sections."""
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Add Subtask Node")),
        dbc.ModalBody([
            dbc.RadioItems(
                id="details-add-mode",
                options=[
                    {"label": "Create New Node", "value": "create"},
                    {"label": "Link Existing Node", "value": "link"},
                ],
                value="create",
                inline=True,
                className="mb-3",
            ),

            # --- Link Existing mode ---
            html.Div(id="details-add-link-section", style={"display": "none"}, children=[
                dbc.Label("Select Node"),
                html.Div(dcc.Dropdown(
                    id="details-add-existing-dropdown",
                    placeholder="Search for a node...",
                    style={"backgroundColor": "#ffffff", "color": "#000000"},
                ), className="mb-2"),
                dbc.Label("Edge Type"),
                dbc.Select(
                    id="details-add-link-edge-type",
                    options=[
                        {"label": "Hard", "value": "hard"},
                        {"label": "Soft", "value": "soft"},
                    ],
                    value="hard",
                    className="mb-3",
                ),
            ]),

            # --- Create New mode ---
            html.Div(id="details-add-create-section", children=[
                dbc.Label("Name"),
                dbc.Input(id="details-add-name", type="text"),

                dbc.Label("Type", className="mt-2"),
                dbc.Select(id="details-add-type", options=[], value="Learn"),

                dbc.Label("Context", className="mt-2"),
                html.Div([
                    dbc.Select(id="details-add-context",
                               options=[{"label": "None", "value": ""}],
                               style={'flex': 1}),
                    dbc.Button("▾", id="btn-details-add-subcontext-toggle",
                               color="light", className="ms-1 px-2"),
                ], className="d-flex"),
                dbc.Collapse(
                    dbc.Select(id="details-add-subcontext",
                               options=[{"label": "None", "value": ""}],
                               className="mt-1"),
                    id="collapse-details-add-subcontext", is_open=False,
                ),

                dbc.Label("Description", className="mt-2"),
                dbc.Textarea(id="details-add-desc",
                             style={"height": "80px", "resize": "vertical"}),

                html.Div([
                    dbc.Label("Competence", className="mb-0"),
                    html.Button(
                        html.I(className="bi bi-info-circle"),
                        id="btn-details-competence-info",
                        style={
                            "background": "none", "border": "none", "padding": "0 0 0 6px",
                            "color": "#6c757d", "cursor": "pointer", "fontSize": "0.8rem",
                            "lineHeight": "1", "position": "relative", "top": "1px"
                        }
                    ),
                    dbc.Tooltip("Competence reference", target="btn-details-competence-info", placement="right",
                                delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                ], className="d-flex align-items-center mt-2"),
                dbc.Select(
                    id="details-add-competence",
                    options=[
                        {"label": "\u2014", "value": ""},
                        {"label": "Outsider", "value": "outsider"},
                        {"label": "Reciter", "value": "reciter"},
                        {"label": "Processor", "value": "processor"},
                        {"label": "Thinker", "value": "thinker"},
                        {"label": "Creator", "value": "creator"},
                        {"label": "Master", "value": "master"},
                        {"label": "Innovator", "value": "innovator"},
                    ],
                    value="",
                ),

                html.Hr(className="my-2"),
                html.Div([
                    html.H5("Priority Override", className="mb-0"),
                    dbc.Switch(
                        id="details-add-override-toggle",
                        label="",
                        value=False,
                        style={"fontSize": "0.82rem", "marginBottom": "0"},
                    ),
                ], className="d-flex justify-content-between align-items-center mt-2 mb-1"),
                html.Div(id="details-add-override-options", style={"display": "none"}, children=[
                    dbc.RadioItems(
                        id="details-add-override-mode",
                        options=[
                            {"label": "Node Only", "value": "node_only"},
                            {"label": "Node + Hard Dependencies", "value": "hard"},
                            {"label": "Node + Soft Dependencies", "value": "soft"},
                            {"label": "Node + All Dependencies", "value": "all"},
                        ],
                        value="hard",
                        style={"fontSize": "0.85rem"},
                    ),
                ]),

                html.Hr(className="my-2"),
                html.H5("Ratings", className="mt-2 mb-1"),
                dbc.Label("Value", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5, id="details-add-value"),

                dbc.Label("Interest", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5, id="details-add-interest"),

                dbc.Label("Effort", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5, id="details-add-difficulty"),

                html.Hr(className="my-2"),
                html.H5("Time Estimates", className="mt-2 mb-2"),
                html.Div([
                    dbc.Checklist(
                        options=[{"label": "Inherit", "value": "inherited"}],
                        value=[],
                        id="details-add-time-mode",
                        switch=True,
                        className="mb-0 flex-grow-1",
                    ),
                    dbc.Select(id="details-add-time-unit", options=[
                        {"label": "Hours", "value": "hours"},
                        {"label": "Weeks", "value": "weeks"},
                        {"label": "Months", "value": "months"},
                    ], value=ted.get('unit', 'weeks'), size="sm",
                        style={"width": "100px"})
                ], className="d-flex align-items-center mb-2"),
                html.Div(id="details-add-time-omp", children=[
                    dbc.Row([
                        dbc.Col([dbc.Label("Optimistic", className="small text-muted mb-0"),
                                 dbc.Input(id="details-add-time-o", type="number", min=0,
                                           value=ted.get('optimistic', 2))]),
                        dbc.Col([dbc.Label("Expected", className="small text-muted mb-0"),
                                 dbc.Input(id="details-add-time-m", type="number", min=0,
                                           value=ted.get('expected', 4))]),
                        dbc.Col([dbc.Label("Pessimistic", className="small text-muted mb-0"),
                                 dbc.Input(id="details-add-time-p", type="number", min=0,
                                           value=ted.get('pessimistic', 6))]),
                    ]),
                ]),

                # --- Relationships section (mirrors goals tab) ---
                html.Hr(className="my-2"),
                html.H5("Relationships", className="mt-2 mb-1"),
                dbc.Label("Needs"),
                html.Div([
                    dcc.Dropdown(id="details-add-needs-hard", multi=True,
                                 placeholder="Hard..."),
                    dcc.Dropdown(id="details-add-needs-soft", multi=True,
                                 placeholder="Soft...", className="mt-1"),
                ], className="text-dark"),

                dbc.Label("Supports", className="mt-2"),
                html.Div([
                    dcc.Dropdown(id="details-add-supports-hard", multi=True,
                                 placeholder="Hard..."),
                    dcc.Dropdown(id="details-add-supports-soft", multi=True,
                                 placeholder="Soft...", className="mt-1"),
                ], className="text-dark"),

                dbc.Label("Helps", className="mt-2"),
                html.Div(dcc.Dropdown(id="details-add-helps", multi=True,
                                       placeholder="Synergistic Nodes..."),
                         className="text-dark"),

                # --- External Resources section (mirrors goals tab) ---
                html.Hr(className="my-2"),
                html.H5("External Resources", className="mt-2 mb-1"),
                dcc.Store(id='details-add-obsidian-store', data=['']),
                dcc.Store(id='details-add-drive-store', data=['']),
                dcc.Store(id='details-add-website-store', data=['']),

                html.Div([
                    dbc.Label("Obsidian", className="mb-0"),
                    dbc.Button("+", id="btn-details-add-obsidian-add", color="link",
                               className="p-0 ms-2 text-decoration-none text-muted",
                               title="Add Obsidian link",
                               style={"fontSize": "1.2rem", "lineHeight": "1"}),
                ], className="d-flex align-items-center mt-2 mb-1"),
                html.Div(id='details-add-obsidian-container'),

                html.Div([
                    dbc.Label("Google Drive", className="mb-0"),
                    dbc.Button("+", id="btn-details-add-drive-add", color="link",
                               className="p-0 ms-2 text-decoration-none text-muted",
                               title="Add Google Drive link",
                               style={"fontSize": "1.2rem", "lineHeight": "1"}),
                ], className="d-flex align-items-center mt-3 mb-1"),
                html.Div(id='details-add-drive-container'),

                html.Div([
                    dbc.Label("Website", className="mb-0"),
                    dbc.Button("+", id="btn-details-add-website-add", color="link",
                               className="p-0 ms-2 text-decoration-none text-muted",
                               title="Add Website link",
                               style={"fontSize": "1.2rem", "lineHeight": "1"}),
                ], className="d-flex align-items-center mt-3 mb-1"),
                html.Div(id='details-add-website-container'),
            ]),

            html.Div(id="details-add-save-status", className="text-danger mt-2",
                     style={"fontSize": "0.85rem", "minHeight": "1.2em"}),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-details-add-cancel",
                       color="secondary", className="me-2"),
            dbc.Button("Add", id="btn-details-add-save", color="primary"),
        ]),
    ], id="modal-details-add-node", size="lg", is_open=False, centered=True,
       scrollable=True)


def build_details_subtasks_table(subtask_nodes, graph_manager=None, edges=None,
                                  parent_name=None, include_soft=True,
                                  include_transitive=True,
                                  include_synergies=False):
    """Builds the subtasks table for any node's detail view.

    Columns: Name | Status | Relationship | Type | Context | Subcontext |
             Priority | Value | Interest | Effort | Time | (remove)

    Priority is computed via the same ROI scoring algorithm used in the
    Suggestions tab, normalized 0–100.  Ineligible/Done/Goal nodes show '—'.

    Args:
        subtask_nodes: List of Node objects in the dependency subtree.
        graph_manager: GraphManager instance for looking up nodes.
        edges: List of all edge dicts.
        parent_name: The root node name, used to compute need types.
        include_soft: If False, only hard-need subtasks are shown.
        include_transitive: If False, only direct children are shown.
        include_synergies: If True, Helps-linked nodes get a "Synergy" relationship label.
    """
    if not subtask_nodes:
        return html.Div(
            html.P("No subtasks found. Add prerequisite nodes to see them here.",
                   className="text-muted"),
            className="text-center py-3"
        )

    edges = edges or []
    relationship_types = {}
    if parent_name and graph_manager:
        from models import EDGE_NEEDS_SOFT, EDGE_HELPS, EDGE_NEEDS_HARD
        hard_subtree = graph_manager.get_goal_subtree(parent_name,
                                                       edge_types=(EDGE_NEEDS_HARD,))
        synergy_nodes = set()
        if include_synergies:
            # "Synergy" = nodes pulled in by the Helps seed (direct partner or
            # one of its Hard/Soft prereqs) that aren't already in the goal's
            # Hard/Soft subtree.
            overall_subtree = graph_manager.get_goal_subtree(
                parent_name,
                edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS))
            hard_soft_subtree = graph_manager.get_goal_subtree(
                parent_name, edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT))
            synergy_nodes = overall_subtree - hard_soft_subtree

        for node in subtask_nodes:
            if node.name in synergy_nodes:
                relationship_types[node.name] = "Synergy"
            elif node.name in hard_subtree:
                relationship_types[node.name] = "Hard"
            else:
                relationship_types[node.name] = "Soft"
    else:
        for node in subtask_nodes:
            relationship_types[node.name] = "Hard"

    if not include_soft:
        subtask_nodes = [n for n in subtask_nodes
                         if relationship_types.get(n.name) in ("Hard", "Synergy")]

    if not subtask_nodes:
        return html.Div(
            html.P("No hard-need subtasks for this node.", className="text-muted"),
            className="text-center py-3"
        )

    # Build set of nodes with a direct edge to the parent (removable)
    direct_children = set()
    if parent_name:
        from models import EDGE_NEEDS_SOFT, EDGE_HELPS, EDGE_NEEDS_HARD
        for e in edges:
            if e['target'] == parent_name and e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
                direct_children.add(e['source'])
            if e['type'] == EDGE_HELPS:
                if e['target'] == parent_name:
                    direct_children.add(e['source'])
                elif e['source'] == parent_name:
                    direct_children.add(e['target'])

    if not include_transitive:
        subtask_nodes = [n for n in subtask_nodes if n.name in direct_children]

    if not subtask_nodes:
        return html.Div(
            html.P("No direct subtasks for this node.", className="text-muted"),
            className="text-center py-3"
        )

    # --- Priority scoring (same ROI algorithm as Suggestions tab, normalized 0–100) ---
    # Nodes receive "—" when: status is Done/Blocked, type is Goal, or any hard
    # prerequisite is not yet Done (ineligible per the scoring algorithm).
    priority_scores = {}
    priority_sort_key = {}  # numeric value used for sorting; -1 for unscored nodes
    if graph_manager:
        scored = graph_manager.calculate_priority_scores(subtask_nodes)
        raw_scores = [getattr(n, 'priority_score', -1.0) for n in scored]
        valid_scores = [s for s in raw_scores if s >= 0]
        max_score = max(valid_scores) if valid_scores else 0.0
        for n in scored:
            raw = getattr(n, 'priority_score', -1.0)
            if raw < 0 or max_score == 0:
                priority_scores[n.name] = "—"
                priority_sort_key[n.name] = -1.0
            else:
                normalized = round((raw / max_score) * 100)
                priority_scores[n.name] = str(normalized)
                priority_sort_key[n.name] = normalized

    # Sort: eligible nodes descending by score, then unscored alphabetically below
    subtask_nodes = sorted(
        subtask_nodes,
        key=lambda n: (
            priority_sort_key.get(n.name, -1.0) < 0,  # False (eligible) sorts before True
            -priority_sort_key.get(n.name, 0.0),       # higher score first
            n.name.lower(),                              # alpha tie-break / ineligible order
        ),
    )

    # Cool & quiet palette. Hard is a darker rugged blue (matches the
    # HardRelPri badge in the node-info stack so the same hue means the
    # same thing app-wide); Soft a neutral slate; Synergy a cyan-teal
    # (categorically different from the Hard/Soft necessity axis).
    # Matches _VIA_COLORS in the explain modal.
    _REL_BADGE_STYLES = {
        "Hard":    {"backgroundColor": "#375a7f", "color": "#d6e0ee"},
        "Soft":    {"backgroundColor": "#6c7682", "color": "#dde0e5"},
        "Synergy": {"backgroundColor": "#5a8088", "color": "#d8e6e9"},
    }

    rows = []
    for node in subtask_nodes:
        # Status badge uses the centralized BADGE_PALETTE so the muted
        # Done/Blocked values match the Details info pane.
        rel = relationship_types.get(node.name, "Hard")
        rel_style = _REL_BADGE_STYLES.get(rel, _REL_BADGE_STYLES["Hard"])
        is_direct = node.name in direct_children
        if is_direct:
            btn_id = {"type": "details-subtask-remove", "index": node.name}
            remove_btn = [
                dbc.Button(
                    "×",
                    id=btn_id,
                    color="link",
                    className="p-0 text-decoration-none text-muted",
                    style={"fontSize": "1.1rem", "lineHeight": "1"},
                ),
                dbc.Tooltip(
                    "Remove edge or delete node",
                    target=btn_id,
                    placement="left",
                    delay={"show": TOOLTIP_SHOW_DELAY_MS,
                           "hide": TOOLTIP_HIDE_DELAY_MS},
                ),
            ]
        else:
            remove_btn = None

        _eff = graph_manager.get_effective_time(node.name) if graph_manager else 0.0
        _time_cell = ConfigManager.format_time_friendly(_eff) if _eff > 0 else "—"

        rows.append(html.Tr([
            html.Td(
                html.Span(node.name, title="Open in Details tab",
                          style={"cursor": "pointer"}),
                id={"type": "details-subtask-name", "index": node.name},
                style={"verticalAlign": "middle"},
            ),
            html.Td(html.Span(node.status, className="badge",
                              style=badge_style(node.status, font_size="0.7rem")),
                    style={"verticalAlign": "middle"}),
            html.Td(html.Span(rel, className="badge",
                              style={**rel_style, "fontSize": "0.7rem",
                                     "padding": "4px 8px", "borderRadius": "4px"}),
                    style={"verticalAlign": "middle"}),
            html.Td(node.type, style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.context) if node.context else "—",
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.subcontext) if node.subcontext else "—",
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(priority_scores.get(node.name, "—"),
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.value),
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.interest),
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(str(node.difficulty),
                    style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(_time_cell, style={"verticalAlign": "middle", "color": "#6c757d"}),
            html.Td(remove_btn, style={"verticalAlign": "middle"}),
        ]))

    return dbc.Table([
        html.Thead(html.Tr([
            html.Th("Name"),
            html.Th("Status"),
            html.Th("Relationship"),
            html.Th("Type"),
            html.Th("Context"),
            html.Th("Subcontext"),
            html.Th("Priority"),
            html.Th("Value"),
            html.Th("Interest"),
            html.Th("Effort"),
            html.Th("Time"),
            html.Th(""),
        ])),
        html.Tbody(rows),
    ], bordered=False, hover=True, responsive=True, size="sm",
       className="text-light", style={"fontSize": "0.82rem"})
