"""
Layout definitions for the Details tab.

Provides a consolidated view for drilling into any node's dependencies,
subtasks, and time simulation — merging the best parts of the Goals
and Simulation tabs.
"""

import style_tokens as tokens
from ui_kit import (
    add_button,
    done_color,
    info_button,
    nav_button,
    panel_close_button,
    progress_bar_color,
    restore_button)
from duration_ui import DURATION_UNITS, bracket_label, estimate_guidance, unit_select
from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from typing import Optional, List, Any
from config import (
    ConfigManager,
    badge_style,
    BADGE_PALETTE,
)
from context_picker import build_single_context_picker
from styles import stylesheet
from models import STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from ui_kit import (Tooltip, add_button, info_button, nav_button, panel_close_button,
                    restore_button)

# Weekday toggle-pill options for the habit per-session scheduler. Values are
# weekday indices (0=Mon … 6=Sun); displayed Sunday-first to match the
# Apple-style day picker. Single-letter labels.
WEEKDAY_OPTIONS = [
    {"label": "S", "value": 6}, {"label": "M", "value": 0},
    {"label": "T", "value": 1}, {"label": "W", "value": 2},
    {"label": "T", "value": 3}, {"label": "F", "value": 4},
    {"label": "S", "value": 5},
]


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
            "fontSize": tokens.FS_HEADING,
            "color": tokens.ACCENT_SOFT,
            "textShadow": "0 0 6px rgba(126, 200, 227, 0.5)",
            "pointerEvents": "none",
            "zIndex": 10,
        },
    )


def build_graph_settings_panel(
    prefix: str,
    *,
    include_animate: bool = True,
    defaults_getter=ConfigManager.get_graph_layout_defaults,
    max_depth_id: str = None,
    outside_nodes_id: str = None,
):
    """Build a graph-layout panel. Single source of truth for all three canvases
    (Nodes / Details / Events).

    Callers pass the slider `defaults_getter` explicitly to select between
    `get_graph_layout_defaults` (main canvas) and
    `get_details_graph_layout_defaults` (details/events). Pass
    ``include_animate=False`` to render only Freeze in the behavior row.

    ``max_depth_id`` opts a canvas into a Max Depth slider at the top of the
    panel. Only the Details tab passes it, since that's the only canvas that
    examines a local subtree rather than the whole graph. The id is supplied by
    the caller rather than derived from ``prefix`` on purpose: depth is a
    tab-level control that also redraws the subtasks table, milestones strip,
    inherited ratings and Time Simulation, so it keeps the tab-scoped
    ``details-max-depth`` name instead of a panel-scoped one. It sits above a
    divider, separated from the physics sliders below it.

    ``outside_nodes_id`` is the Events canvas's counterpart: a switch that
    shows or hides nodes outside the event that link to its nodes. It is
    remembered in the browser between sessions.
    """
    gl = defaults_getter()
    p = prefix
    reset_btn_id = f"btn-reset-{p}"
    close_btn_id = f"btn-close-{p}"

    children = [
        html.Div([
            html.Div([
                html.Span("Graph Layout", style={"fontWeight": "300", "fontSize": tokens.FS_LG}),
                restore_button(reset_btn_id),
            ], className="d-flex align-items-center"),
            panel_close_button(close_btn_id, "Close graph layout panel"),
        ], className="d-flex justify-content-between align-items-center",
           style={"marginBottom": tokens.SPACE_BLOCK}),
    ]

    children += [
        html.Div([
            *([
                dbc.Switch(
                    id=f"{p}-animate",
                    label="Animate",
                    value=True,
                    style={"fontSize": tokens.FS_BASE},
                ),
            ] if include_animate else []),
            dbc.Switch(
                id=f"{p}-freeze-rerender",
                label="Freeze",
                value=False,
                style={"fontSize": tokens.FS_BASE},
            ),
        ], className="d-flex gap-2"),
        Tooltip("Pause graph updates on save. Use Settle to refresh manually.",
                    target=f"{p}-freeze-rerender", placement="left"),
        html.Hr(style={"borderColor": tokens.BORDER_PANEL, "margin": "12px 0"}),
    ]

    # Scope, not physics — so it leads the panel and gets its own divider
    # rather than sitting among the force-layout sliders.
    if outside_nodes_id:
        children += [
            dbc.Switch(
                id=outside_nodes_id,
                label="Nodes outside event",
                value=True,
                persistence=True,
                persistence_type="local",
                style={"fontSize": tokens.FS_BASE},
            ),
            html.Hr(style={"borderColor": tokens.BORDER_PANEL, "margin": "12px 0"}),
        ]

    if max_depth_id:
        children += [
            html.Div("Max Depth", className="settings-label"),
            dcc.Slider(
                id=max_depth_id,
                min=1, max=6, step=1, value=6,
                marks={1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "All"},
                updatemode="mouseup",
            ),
            html.Hr(style={"borderColor": tokens.BORDER_PANEL, "margin": "12px 0"}),
        ]

    children += [
        html.Div("Edge Length", className="settings-label"),
        dcc.Slider(
            id=f"{p}-edge-length",
            min=50, max=300, step=10, value=gl.get('edge_length', 100),
            marks=None,
            updatemode="mouseup",
        ),
        html.Div([
            html.Span("Short"),
            html.Span("Long"),
        ], id=f"{p}-edge-length-axis", className="graph-settings-axis"),

        html.Div("Gravity", className="settings-label"),
        dcc.Slider(
            id=f"{p}-gravity",
            min=0, max=5, step=0.25, value=gl.get('gravity', 0.25),
            marks=None,
            updatemode="mouseup",
        ),
        html.Div([
            html.Span("Weak"),
            html.Span("Strong"),
        ], id=f"{p}-gravity-axis", className="graph-settings-axis"),

        html.Div("Repulsion", className="settings-label"),
        dcc.Slider(
            id=f"{p}-repulsion",
            min=500, max=100000, step=500, value=gl.get('repulsion', 4500),
            marks=None,
            updatemode="mouseup",
        ),
        html.Div([
            html.Span("Weak"),
            html.Span("Strong"),
        ], id=f"{p}-repulsion-axis", className="graph-settings-axis"),
    ]

    children += [
        html.Hr(style={"borderColor": tokens.BORDER_PANEL, "margin": "12px 0"}),

        dbc.Button("Settle", id=f"{p}-relayout",
                   color="secondary", size="sm", className="w-100 mt-2"),
        Tooltip("Re-run layout physics to untangle nodes",
                    target=f"{p}-relayout", placement="top"),
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
        # Search bar \u2014 full width; node-history arrows live on the node-name row.
        html.Div(dcc.Dropdown(
            id="details-node-select",
            placeholder="Select a node...",
            clearable=True,
            style={"minWidth": "100px"},
        ), className="text-dark", style={"flex": "1", "minWidth": "0"}),
    ], className="d-flex align-items-center py-2",
       style={"borderBottom": f"1px solid {tokens.BORDER_PANEL}", "flexShrink": "0",
              "paddingBottom": "8px", "paddingLeft": "18px", "paddingRight": "18px"})

    # ------------------------------------------------------------------ #
    #  EMPTY STATE  (inside left panel, shown when no node selected)      #
    # ------------------------------------------------------------------ #
    empty_state = html.Div(
        id="details-empty",
        className="details-empty-state",
        children=[
            html.Div([
                html.H6("Suggestions", className="text-muted mb-1",
                        style={"fontWeight": "300", "letterSpacing": "1px"}),
                html.P("Click one, or search above.",
                       className="text-muted small"),
            ], style={"textAlign": "center", "marginTop": "24px",
                      "marginBottom": tokens.SPACE_BLOCK}),
            html.Div(id="details-suggestions-container",
                     style={"padding": "0 12px 24px"}),
        ],
        style={"flex": "1", "overflowY": "auto"},
    )

    # ------------------------------------------------------------------ #
    #  NODE SUMMARY  (inside details-content, shown when node selected)   #
    # ------------------------------------------------------------------ #
    node_summary = html.Div([
        # Node-name row: title (ellipsizes) + node-history back/forward arrows
        # right-aligned. Flat ghost icons (see .details-header-btn).
        html.Div([
            html.H4(id="details-node-name", className="mt-3 mb-2",
                    style={"fontWeight": "300", "letterSpacing": "1px",
                           "overflow": "hidden", "textOverflow": "ellipsis",
                           "whiteSpace": "nowrap", "flex": "1", "minWidth": "0"}),
            html.Div([
                nav_button("btn-details-nav-back", "left", "Back",
                           size="sm", disabled=True),
                nav_button("btn-details-nav-forward", "right", "Forward",
                           size="sm", disabled=True,
                           className_extra="ms-1"),
            ], className="ms-2 mt-3 mb-2", style={"flexShrink": "0", "display": "flex",
                                                  "marginRight": "-8px"}),
        ], className="d-flex align-items-center"),
        # Spacing: the name and badges read as one header. The description,
        # Goal progress and stats grid are separate blocks, so the gaps between
        # them are wider than the gaps inside them.

        # Badges row: type, status, priority
        html.Div(id="details-node-badges",
                 className="d-flex gap-1 flex-wrap",
                 style={"marginBottom": tokens.SPACE_BLOCK}),

        # Description
        html.Div(id="details-node-description",
                 className="text-muted",
                 style={"fontSize": tokens.FS_MD, "whiteSpace": "pre-wrap",
                        "marginBottom": tokens.SPACE_SECTION}),

        # Progress bar. It carries no margin of its own: the description above
        # and the stats grid below supply the gaps on either side.
        html.Div(id="details-progress-section", style={"display": "none"}, children=[
            dbc.Progress(id="details-progress-bar", value=0,
                         className="mb-1", style={"height": "14px"}),
            html.Small(id="details-progress-text", className="text-muted",
                       style={"fontSize": tokens.FS_CAP}),
        ]),

        # Stats grid
        html.Div([
            _attribute_row("Type", "details-attr-type"),
            _attribute_row("Status", "details-attr-status"),
            _attribute_row("Context", "details-attr-context"),
            _attribute_row("Time", "details-attr-time"),
            # Own ratings — shown for manual-rating nodes. Hidden when ratings
            # are inherited (containers / Milestones), where the numbers are
            # scoring-inert; the "Ratings: Inherited" row below shows instead.
            html.Div([
                _attribute_row("Value", "details-attr-value"),
                _attribute_row("Interest", "details-attr-interest"),
                _attribute_row("Effort", "details-attr-effort"),
            ], id="details-attr-ratings-own"),
            html.Div(
                _attribute_row("Ratings", "details-attr-ratings-inherited"),
                id="details-attr-ratings-inherited-wrap",
                style={"display": "none"},
            ),
        ], style={"marginTop": tokens.SPACE_SECTION}),

        # Hidden priority container
        html.Div(id="details-priority-section", style={"display": "none"}, children=[
            html.Div(id="details-priority-badge"),
        ]),

        # Action buttons — Edit | Explain  (Locate moved to the header crosshair;
        # Focus lives on the canvas overlay)
        html.Div([
            dbc.Button("Edit", id="btn-details-edit", color="secondary",
                       size="sm", style={"flex": "1"}),
            Tooltip("Open the node editor", target="btn-details-edit", placement="top"),
            dbc.Button("Explain", id="btn-details-explain", color="secondary",
                       size="sm", className="ms-1", style={"flex": "1"}),
            Tooltip("Show where this node's priority score comes from",
                        target="btn-details-explain", placement="top"),
        ], className="d-flex mt-3"),

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
        "borderRight": f"1px solid {tokens.BORDER_PANEL}",
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
            "borderLeft": f"1px solid {tokens.BORDER_PANEL}",
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
                style={'width': '100%', 'height': '100%', 'backgroundColor': tokens.BG_CANVAS,
                       'borderRadius': '0'},
                stylesheet=stylesheet,
                userZoomingEnabled=False,
                userPanningEnabled=False,
                boxSelectionEnabled=True,
                autoungrabify=False,
                # Details owns layout triggering: the callback responds to a
                # real topology change but filters dash-cytoscape's delayed
                # position-only elements echo. Its built-in add/remove refresh
                # must stay off or it would independently start another pass.
                autoRefreshLayout=False,
            ),
            dbc.Button(html.I(className="bi bi-gear"),
                       id="btn-details-graph-settings",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right"),
            Tooltip("Graph layout", target="btn-details-graph-settings", placement="left"),
            _freeze_indicator("details-freeze-indicator"),
            build_graph_settings_panel(
                "details-graph-settings",
                defaults_getter=ConfigManager.get_details_graph_layout_defaults,
                max_depth_id="details-max-depth",
            ),
            dbc.Button(html.I(className="bi bi-search"),
                       id="btn-details-focus",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right-far"),
            Tooltip("Open this node's subtree in the main canvas",
                        target="btn-details-focus", placement="left"),
            dbc.Button(html.I(className="bi bi-arrows-fullscreen"),
                       id="btn-details-graph-fullscreen",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right-mid"),
            Tooltip("Toggle fullscreen", target="btn-details-graph-fullscreen", placement="left"),
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
            "borderTop": f"1px solid {tokens.BORDER_PANEL}",
            "flexShrink": "0",
            "transition": "background-color 0.15s",
        },
    )

    # ------------------------------------------------------------------ #
    #  LOWER SECTION: Subtasks table + Simulation                         #
    # ------------------------------------------------------------------ #
    # Filter toggles are shared between the Milestones strip (above) and
    # the Subtasks table (below). They live in the top-right of WHICHEVER
    # header is currently topmost, so the user always sees them in the
    # same screen position regardless of whether milestones are present:
    # rendered as TWO physical copies (-top alongside Milestones header,
    # canonical no-suffix alongside Subtasks header), kept in sync by the
    # control callbacks in details_callbacks.py. Existing scoring/filter
    # callbacks listen only to the canonical (no-suffix) IDs.
    def _build_toggles(suffix=""):
        """Return the Details view controls, with optional
        id suffix so two copies (one with -top, one canonical) can co-exist."""
        return html.Div([
            dbc.Checklist(
                id=f"details-include-soft-needs{suffix}",
                options=[{"label": "Soft Needs", "value": "include"}],
                value=["include"],
                switch=True,
                style={"fontSize": tokens.FS_BASE},
            ),
            dbc.Checklist(
                id=f"details-show-cross-links{suffix}",
                options=[{"label": "Show Cross-Links", "value": "show"}],
                value=["show"],
                switch=True,
                style={"fontSize": tokens.FS_BASE},
            ),
            dbc.Checklist(
                id=f"details-include-synergies{suffix}",
                options=[{"label": "Synergies", "value": "include"}],
                value=[],
                switch=True,
                style={"fontSize": tokens.FS_BASE},
            ),
            dbc.Checklist(
                id=f"details-hide-done{suffix}",
                options=[{"label": "Show Done", "value": "show_done"}],
                value=[],
                switch=True,
                style={"fontSize": tokens.FS_BASE},
            ),
            dbc.Checklist(
                id=f"details-hide-blocked{suffix}",
                options=[{"label": "Hide Blocked", "value": "hide_blocked"}],
                value=[],
                switch=True,
                style={"fontSize": tokens.FS_BASE, "marginRight": "12px"},
            ),
        ], className="details-view-controls d-flex align-items-center gap-3")

    subtasks_section = html.Div([
        # Milestones roster: same-rank H5 header as Subtasks below, single-row
        # horizontal strip of tiles. Section (header + top toggles + strip)
        # hidden together when no Milestone survives filtering.
        html.Div(id="details-milestones-section", style={"display": "none"}, children=[
            html.Div([
                html.H5("Milestones", className="mb-0"),
                _build_toggles(suffix="-top"),
            ], className="d-flex align-items-center justify-content-between mb-3"),
            html.Div(id="details-milestones-tiles",
                     className="d-flex flex-nowrap gap-2 mb-4 milestone-tiles-scroll"),
        ]),
        # Subtasks header — same row as the canonical filter toggles. The
        # toggle wrapper has its own id so its visibility can be flipped
        # opposite to the milestones-section: hidden when milestones show
        # (toggles live up there instead), visible otherwise.
        html.Div([
            html.Div([
                html.H5("Subtasks", className="mb-0"),
                add_button("btn-details-add-node", "Add subtask node"),
            ], className="d-flex align-items-center"),
            html.Div(_build_toggles(), id="details-subtask-toggles-bottom"),
        ], className="d-flex align-items-center justify-content-between",
           style={"marginBottom": tokens.SPACE_BLOCK}),
        html.Div(build_no_selection_subtasks(),
                 id="details-subtasks-table-container",
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
            "borderLeft": f"1px solid {tokens.BORDER_PANEL}",
            "flexShrink": "0",
            "transition": "background-color 0.15s",
        },
    )

    sim_section = html.Div([
        dcc.Store(id="details-sim-request"),
        dcc.Store(id="details-sim-result"),
        html.Small(id="details-sim-status", className="text-muted d-block mb-1",
                   style={"fontSize": tokens.FS_BASE}, **{"aria-live": "polite"}),
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
            dcc.Loading(
                id="details-sim-loading",
                type="circle",
                color="#1e90ff",  # literal: dbc.Spinner prop, not CSS
                # No spinner flash on fast machines; only shows once a sim
                # takes longer than half a second.
                delay_show=500,
                parent_style={"height": "100%", "minHeight": "0"},
                children=[
                    dcc.Graph(
                        id="details-sim-chart",
                        config={"displayModeBar": False},
                        responsive=True,
                        style={"height": "100%", "minHeight": "350px"},
                    ),
                ],
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

    explain_legend_items = []
    # Third copy of the same four values; now the one in the palette.
    for label in ('Self', 'Hard', 'Soft', 'Synergy'):
        color = BADGE_PALETTE[f'Edge{label}'][0]
        explain_legend_items.append(html.Span([
            html.Span("\u25A0 ", style={"color": color}),
            html.Span(label, style={"color": tokens.TEXT_SOFT}),
        ], className="me-3"))

    explain_modal = dbc.Modal([
        dbc.ModalHeader(html.Div([
            dbc.ModalTitle(id="details-explain-title"),
            # Total value means little on its own, so the header states where
            # this node lands among comparable ones.
            html.Div(id="details-explain-subtitle", className="text-muted",
                     style={"fontSize": tokens.FS_BASE, "marginTop": "2px"}),
        ])),
        dbc.ModalBody([
            # Contributors lead: "which work is driving this score" is the
            # question the modal is opened to answer. The arithmetic that
            # produces the number is the follow-up, so it sits behind a
            # disclosure rather than ahead of the chart.
            html.Div([
                html.H5("Top Contributors", className="mt-2 mb-1"),
                html.Div([
                    html.Span("Show", style={"color": tokens.TEXT_SOFT,
                                              "fontSize": tokens.FS_BASE,
                                              "marginRight": "6px"}),
                    dbc.Input(id="details-explain-count",
                              type="number", min=1, max=100, step=1, value=10,
                              size="sm", debounce=True,
                              style={"width": "42px",
                                     "height": "22px",
                                     "padding": "0 4px",
                                     "fontSize": tokens.FS_CAP,
                                     "lineHeight": "1",
                                     "textAlign": "center"}),
                ], className="d-flex align-items-center"),
            ], className="d-flex justify-content-between align-items-center"),
            dcc.Store(id="details-explain-contrib-store"),
            # The score callback and chart callback complete in sequence.  Keep
            # Plotly's unstyled first frame out of sight until both are done;
            # for the usual sub-second wait, a quiet caption is less visually
            # noisy than flashing a spinner.
            dcc.Store(id="details-explain-ready-node"),
            html.Div([
                html.Div(
                    "Preparing explanation…",
                    id="details-explain-chart-placeholder",
                    className=(
                        "text-muted d-flex align-items-center "
                        "justify-content-center"
                    ),
                    style={"minHeight": "260px", "fontSize": tokens.FS_BASE},
                    **{"role": "status", "aria-live": "polite"},
                ),
                dcc.Graph(
                    id="details-explain-chart",
                    config={"displayModeBar": False},
                    style={"display": "none"},
                ),
            ]),
            html.Div(explain_legend_items,
                     style={"fontSize": tokens.FS_CAP, "textAlign": "right"}),
            html.Hr(className="my-3"),
            dbc.Button([
                html.Span(id="details-explain-summary-chevron",
                          className="editor-chevron on-dark"),
                html.Span("Calculation details", className="ms-2"),
            ], id="btn-details-explain-summary-toggle", color="link",
               className="p-0 text-decoration-none text-muted d-flex align-items-center"),
            dbc.Collapse(
                html.Div(id="details-explain-summary"),
                id="collapse-details-explain-summary", is_open=False,
            ),
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
                                 "fontSize": tokens.FS_BASE,
                                 "padding": "0",
                                 "border": f"1px solid {tokens.BORDER_PANEL}"}),
            ], style={"width": "auto"}),
            html.Span(id="details-explain-focus-feedback",
                      style={"color": tokens.DANGER_TEXT,
                             "fontSize": tokens.FS_CAP,
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
        # once the open slide finishes so render_goal_list re-runs — but NOT an
        # input to core_engine, so opening doesn't wait on a graph regen.
        dcc.Store(id='goals-ui-refresh-trigger', data=0),
        # Set once, when the browser first goes idle after startup, to build
        # the Goals list in the background (sidebars_callbacks.py).
        dcc.Store(id='goals-prewarm-store', data=None),
        dcc.Store(id='details-goal-order-store', data=ConfigManager.get_goal_order() or None),
        dcc.Store(id='details-nav-history', data=[]),
        dcc.Store(id='details-nav-index', data=-1),
        dcc.Input(id='details-goal-drag-order-input', type='text', value='',
                  style={'display': 'none'}),
        dcc.Input(id='details-simulate-trigger-input', type='text', value='',
                  style={'display': 'none'}),
        # Set by details_deferred_subtasks.js after the newest Details graph
        # layout has stopped. The subtasks table uses it as its render gate.
        dcc.Input(id='details-layout-settled-trigger-input', type='text', value='',
                  style={'display': 'none'}),
        # Emitted after every newest Details layout settles. Time Simulation
        # waits for this separate signal so filter-driven layouts do not
        # compete with the opening animation or delay table-only behavior.
        dcc.Input(id='details-simulation-settled-trigger-input', type='text', value='',
                  style={'display': 'none'}),
        dcc.Input(id='details-edit-trigger-input', type='text', value='',
                  style={'display': 'none'}),
        dcc.Input(id='goal-priority-trigger-input', type='text', value='',
                  style={'display': 'none'}),
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
                  style={"width": "70px", "fontSize": tokens.FS_BASE}),
        html.Span(id=value_id, style={"fontSize": tokens.FS_BASE, "fontWeight": "500"}),
    ], className="d-flex align-items-center mb-1")


def _goal_corner_badge(text, palette_name, class_name="badge"):
    """The fixed-width badge in a goal card's corner: a priority rank or score.

    The Goals sidebar and the Details suggestions share it, so the same number
    looks the same on both.
    """
    return html.Span(text, className=class_name, style={
        **badge_style(palette_name, font_size=tokens.FS_XS),
        "minWidth": "34px", "textAlign": "center", "display": "inline-block",
    })


def _build_suggestion_row(node, priority_rank=None, priority=None):
    """One keyboard-accessible starting-point card in the Details empty state.

    The name, then the context on a muted line. The subcontext is left out,
    since a Goal's subcontext often just repeats its name. The corner matches
    the Goal's card in the Goals sidebar: a Priority Goal shows its rank, and
    another Goal shows its 0-100 ``priority``.

    Every suggestion is a Goal, so anything that only restates that is left
    out: no type color or label, and no status, since Goals are never Blocked
    and Done ones are never suggested.
    """
    if priority_rank is not None:
        label_bits = [f"Priority {priority_rank}"]
        corner = _goal_corner_badge(str(priority_rank), "PriorityRank",
                                    "badge details-suggestion-badge")
    elif priority is not None:
        label_bits = [f"Priority score {priority}"]
        corner = _goal_corner_badge(str(priority), STATUS_OPEN,
                                    "badge details-suggestion-badge")
    else:
        label_bits, corner = [], None
    if node.context:
        label_bits.append(node.context)

    children = [
        html.Span([
            html.Span(node.name, className="details-suggestion-name"),
            html.Small(node.context or "", className="details-suggestion-meta"),
        ], className="details-suggestion-copy"),
    ]
    if corner is not None:
        children.append(corner)

    return html.Button(
        children,
        id={"type": "details-suggestion-item", "index": node.name},
        type="button",
        className="details-suggestion-row",
        **{"aria-label": f"View {node.name}. " + ", ".join(label_bits)},
    )


def build_details_suggestions(goal_rows, explore_rows, filters_active=False):
    """Assemble the Details empty-state starting points from pre-built rows."""
    sections = []

    def _section(title, rows):
        return html.Div([
            html.H6(title, className="text-muted mb-2",
                    style={"fontSize": tokens.FS_CAP, "fontWeight": "500",
                           "letterSpacing": "1px", "textTransform": "uppercase",
                           "marginTop": "12px"}),
            html.Div(rows),
        ])

    if goal_rows:
        sections.append(_section("Priority Goals", goal_rows))
    if explore_rows:
        sections.append(_section("Explore", explore_rows))
    elif goal_rows and filters_active:
        sections.append(_section("Explore", [
            html.P("No areas match the current filters.",
                   className="text-muted small mb-0")
        ]))

    if not sections:
        message = ("No areas match the current filters."
                   if filters_active else "No areas to explore yet.")
        return html.P(message,
                      className="text-muted small text-center mt-3")
    return sections


def build_goal_card(name: str, status: str, completion: dict, subtask_count: int, is_selected: bool = False, priority_rank: Optional[int] = None,
                    show_order_buttons: bool = False, is_first: bool = False, is_last: bool = False,
                    corner_text: Optional[str] = None, menu_attributes: Optional[dict] = None):
    """Builds a single goal card for the goal sidebar list.

    ``menu_attributes`` are the goal's ``node_menu_attributes``, which give the
    card the shared node context menu on right-click.
    """
    border_style = f"2px solid {tokens.ACCENT}" if is_selected else f"1px solid {tokens.BORDER_PANEL}"

    pct = completion.get("pct", 0)
    done = completion.get("done", 0)
    total = completion.get("total", 0)
    formatted_time = ConfigManager.format_time_friendly(completion.get("remaining_time", 0))

    # A goal is effectively Done if its toggle is on OR all subtasks are complete
    if status == STATUS_DONE or (pct == 100 and total > 0):
        effective_status = STATUS_DONE
    elif completion.get("is_blocked", False):
        effective_status = STATUS_BLOCKED
    else:
        effective_status = STATUS_OPEN

    # status badge uses centralized BADGE_PALETTE (constructed inline below)

    # Hidden up/down buttons (kept for Dash pattern-matching callback registration)
    _hidden = {"display": "none"}
    hidden_buttons = html.Div([
        dbc.Button("", id={"type": "goal-up", "index": name}, style=_hidden),
        dbc.Button("", id={"type": "goal-down", "index": name}, style=_hidden),
    ])

    # Drag handle (visible only for non-priority, manual-sort goals)
    drag_handle = html.Span(
        html.I(className="bi bi-grip-horizontal"), className="goal-drag-handle",
        style={"cursor": "grab", "color": tokens.TEXT_DIM, "fontSize": tokens.FS_MD,
               "marginRight": "8px", "userSelect": "none"},
    ) if show_order_buttons else None

    # Top-right indicator: a green "Done" badge for completed goals, otherwise
    # the sort-dependent corner text (priority score / manual rank). Open goals
    # carry no badge under sorts where order is arbitrary (alphabetical).
    _badge_cls = "badge ms-1" if priority_rank is not None else "badge"
    if effective_status == STATUS_DONE:
        corner_badge = html.Span(
            STATUS_DONE, className=_badge_cls,
            style={**badge_style(STATUS_DONE, font_size=tokens.FS_XS),
                   "width": "62px", "textAlign": "center", "display": "inline-block"})
    elif corner_text and priority_rank is None:
        corner_badge = _goal_corner_badge(corner_text, STATUS_OPEN, _badge_cls)
    else:
        corner_badge = None

    children: List[Any] = [
        hidden_buttons,
        html.Div([
            html.Div([
                drag_handle,
                html.H6(name, className="mb-0", style={"fontWeight": "500"}),
            ], className="d-flex align-items-center"),
            html.Div([
                html.Span(
                    _goal_corner_badge(str(priority_rank), "PriorityRank"),
                    className="goal-rank-trigger",
                    **{"data-goal-name": name},
                ) if priority_rank is not None else None,
                corner_badge,
            ], className="d-flex align-items-center ms-2 gap-1"),
        # mb-0, not mb-1: the name and its stats line are one block, and the
        # Small below already carries its own leading. The extra 4px read as a
        # gap between two unrelated things.
        ], className="d-flex align-items-center justify-content-between mb-0"),
    ]

    # Stats line. No percentage: the done/total count already shows progress,
    # and the remaining time carries the sense of size.
    if total > 0:
        _sep = "\u00a0\u00a0\u00b7\u00a0\u00a0"
        stats_text = f"{done}/{total} hard subtasks{_sep}{formatted_time}"
    else:
        stats_text = "No subtasks yet"

    children.append(html.Small(stats_text, className="text-muted", style={"fontSize": tokens.FS_SM}))

    return html.Div(children, id={"type": "goal-card", "index": name},
       className="mb-2 goal-card rounded",
       **{"data-goal-name": name, **(menu_attributes or {})},
       style={
           "border": border_style,
           "backgroundColor": tokens.BG_RAISED if is_selected else tokens.BG_PANEL,
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
                panel_close_button("btn-details-filters-close", "Close graph filters"),
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
                    style={"fontSize": tokens.FS_BASE},
                ),

                dbc.Label("Status", className="text-muted small mb-1"),
                dbc.Checklist(
                    id="details-filter-status",
                    options=[
                        {"label": STATUS_OPEN, "value": STATUS_OPEN},
                        {"label": STATUS_BLOCKED, "value": STATUS_BLOCKED},
                        {"label": STATUS_DONE, "value": STATUS_DONE},
                    ],
                    value=[STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE],
                    className="mb-3",
                    style={"fontSize": tokens.FS_BASE},
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
            "borderLeft": f"1px solid {tokens.BORDER_PANEL}",
            "transition": "right 0.3s ease",
            "backgroundColor": tokens.BG_PANEL,
            "display": "flex",
            "flexDirection": "column",
        }
    )


def _build_add_node_modal(ted):
    """Builds the Add Node modal — mirrors the Goals tab modal with
    Relationships and Resources sections."""
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
                ), className="text-dark mb-2"),
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
                html.Div([
                    dbc.Label("Name", className="mb-0"),
                    add_button("btn-details-add-alias-add", "Add alias"),
                ], className="d-flex align-items-center mb-1"),
                dbc.Input(id="details-add-name", type="text", placeholder="Name node..."),
                dbc.Collapse(
                    html.Div([
                        dbc.Label("Alias", id="details-add-aliases-label",
                                  className="mt-1 mb-1"),
                        html.Div(id='details-add-aliases-container'),
                    ]),
                    id="collapse-details-add-aliases", is_open=False,
                ),
                dcc.Store(id='details-add-aliases-store', data=['']),

                dbc.Label("Type", className="mt-2"),
                dbc.Select(id="details-add-type", options=[], value="Learn"),

                dbc.Label("Description", className="mt-2"),
                dbc.Textarea(id="details-add-desc", placeholder="Describe your project...",
                             style={"height": "80px", "resize": "vertical"}),

                dbc.Label("Context", className="mt-2"),
                build_single_context_picker(
                    "details-add-context-picker",
                    "details-add-context",
                    "details-add-subcontext",
                    context_options=[{"label": "None", "value": ""}],
                    subcontext_options=[{"label": "None", "value": ""}],
                ),

                html.Hr(className="my-2"),
                html.Div([
                    html.H5("Ratings", className="mb-0"),
                    info_button("btn-details-ratings-info", "Ratings reference", placement="right"),
                ], className="d-flex align-items-center mt-2 mb-1"),
                html.Div([
                    dbc.Checklist(
                        options=[{"label": "Inherit", "value": "inherited"}],
                        value=[],
                        id="details-add-value-mode",
                        switch=True,
                        className="mb-0",
                    ),
                ], className="d-flex align-items-center mt-2 mb-2"),
                Tooltip(
                    "Treat this node as a pure container: value, interest, and effort all come from its children via the cascade.",
                    target="details-add-value-mode", placement="left",
                ),
                # Locked-on notice for Milestones (mirrors the main editor).
                html.Div(id="details-add-value-mode-warning",
                         style=tokens.ERROR_TEXT_HIDDEN,
                         className="mt-1 mb-2", children=""),

                html.Div(id="details-add-ratings", children=[
                    dbc.Label("Value", className="mt-2"),
                    dcc.Slider(min=1, max=10, step=1, value=5, id="details-add-value"),

                    dbc.Label("Interest", className="mt-2"),
                    dcc.Slider(min=1, max=10, step=1, value=5, id="details-add-interest"),

                    html.Div(id="details-add-effort-row", children=[
                        dbc.Label("Effort", className="mt-2"),
                        dcc.Slider(min=1, max=10, step=1, value=5, id="details-add-difficulty"),
                    ]),
                    html.Div(id="details-add-effort-caption", style={"display": "none"}, children=[
                        dbc.Label("Effort", className="mt-2"),
                        html.Div("Derived from subtasks", className="text-muted small"),
                    ]),
                ]),
                html.Hr(className="my-2"),
                html.Div([
                    html.H5("Time Estimates", className="mb-0"),
                    estimate_guidance("details-add"),
                ], className="d-flex align-items-center mt-2 mb-2"),
                html.Div([
                    dbc.Checklist(
                        options=[{"label": "Inherit", "value": "inherited"}],
                        value=[],
                        id="details-add-time-mode",
                        switch=True,
                        className="mb-0",
                    ),
                    dbc.Checklist(
                        options=[{"label": "Habit", "value": "habit"}],
                        value=[],
                        id="details-add-time-habit-mode",
                        switch=True,
                        className="mb-0 ms-3 flex-grow-1",
                    ),
                    unit_select("details-add-time-unit",
                                value=ted.get('unit', 'weeks'), compact=True)
                ], className="d-flex align-items-center mb-2"),
                html.Div(id="details-add-time-omp", children=[
                    dbc.Row([
                        dbc.Col([*bracket_label("Lower", "details-add-time-o-label"),
                                 dbc.Input(id="details-add-time-o", type="number", min=0,
                                           value=ted.get('optimistic', 2))]),
                        dbc.Col([*bracket_label("Expected", "details-add-time-m-label"),
                                 dbc.Input(id="details-add-time-m", type="number", min=0,
                                           value=ted.get('expected', 4))]),
                        dbc.Col([*bracket_label("Upper", "details-add-time-p-label"),
                                 dbc.Input(id="details-add-time-p", type="number", min=0,
                                           value=ted.get('pessimistic', 6))]),
                    ]),
                ]),
                html.Div(id="section-details-add-time-habit",
                         style={"display": "none"}, children=[
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Duration", className="mb-0"),
                            dbc.Input(id="details-add-habit-duration",
                                      type="number", min=0, value=0),
                        ], width=7),
                        dbc.Col([
                            dbc.Label(" ", className="mb-0"),
                            unit_select("details-add-habit-duration-unit",
                                        units=DURATION_UNITS, value="weeks"),
                        ], width=5),
                    ], className="mb-2"),
                    dbc.Label("Minutes per Session", className="mb-0 mt-2"),
                    dbc.Row([
                        dbc.Col([*bracket_label("Lower", "details-add-habit-intensity-o-label"),
                                 dbc.Input(id="details-add-habit-intensity-o",
                                           type="number", min=0, value=0)]),
                        dbc.Col([*bracket_label("Expected", "details-add-habit-intensity-m-label"),
                                 dbc.Input(id="details-add-habit-intensity-m",
                                           type="number", min=0, value=0)]),
                        dbc.Col([*bracket_label("Upper", "details-add-habit-intensity-p-label"),
                                 dbc.Input(id="details-add-habit-intensity-p",
                                           type="number", min=0, value=0)]),
                    ]),
                    dcc.Input(id="details-add-habit-intensity-unit", type="hidden",
                              value="min_per_session"),
                    dbc.Label("On these days", className="mb-1 mt-2 d-block"),
                    dbc.Checklist(
                        id="details-add-habit-days",
                        options=WEEKDAY_OPTIONS,
                        value=[0, 1, 2, 3, 4, 5, 6],
                        className="habit-days-picker",
                        inputClassName="btn-check",
                        labelClassName="btn btn-outline-light btn-sm",
                        labelCheckedClassName="active",
                    ),
                    html.Div(id="details-add-habit-total-preview",
                             className="mt-2 small text-muted"),
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

                # --- Resources section (mirrors goals tab) ---
                html.Hr(className="my-2"),
                html.H5("Resources", className="mt-2 mb-1"),
                dcc.Store(id='details-add-obsidian-store', data=['']),
                dcc.Store(id='details-add-drive-store', data=['']),
                dcc.Store(id='details-add-website-store', data=['']),

                html.Div([
                    html.Div([
                        dbc.Label("Obsidian", className="mb-0"),
                        add_button("btn-details-add-obsidian-add", "Add Obsidian link"),
                    ], className="d-flex align-items-center mt-2 mb-1"),
                    html.Div(id='details-add-obsidian-container'),
                ], id='details-add-obsidian-resources',
                   style={} if ConfigManager.get_obsidian_enabled() else {"display": "none"}),

                html.Div([
                    html.Div([
                        dbc.Label("Google Drive", className="mb-0"),
                        add_button("btn-details-add-drive-add", "Add Google Drive link"),
                    ], className="d-flex align-items-center mt-3 mb-1"),
                    html.Div(id='details-add-drive-container'),
                ], id='details-add-drive-resources',
                   style={} if ConfigManager.get_gdrive_enabled() else {"display": "none"}),

                html.Div([
                    dbc.Label("Website", className="mb-0"),
                    add_button("btn-details-add-website-add", "Add Website link"),
                ], className="d-flex align-items-center mt-3 mb-1"),
                html.Div(id='details-add-website-container'),
            ]),

            html.Div(id="details-add-save-status", className="text-danger mt-2",
                     style={"fontSize": tokens.FS_BASE, "minHeight": "1.2em"}),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-details-add-cancel",
                       color="secondary", className="me-2"),
            dbc.Button("Add", id="btn-details-add-save", color="success",
                       style={"backgroundColor": done_color(),
                              "borderColor": done_color()}),
        ]),
    ], id="modal-details-add-node", size="lg", is_open=False, centered=True,
       scrollable=True)


def build_no_selection_subtasks():
    """What the subtasks table shows before any node is selected."""
    return html.Div("Select a node to see subtasks.",
                    className="text-muted text-center py-3")


def build_details_subtasks_table(subtask_nodes, graph_manager=None, edges=None,
                                  parent_name=None, include_soft=True,
                                  include_synergies=False):
    """Builds the subtasks table for any node's detail view.

    Columns: Name | Status | Relationship | Type | Context | Subcontext |
             Priority | Value | Interest | Effort | Time | Edit

    Priority is computed via the same ROI scoring algorithm used in the
    Suggestions tab, normalized 0–100.  Ineligible/Done/Goal nodes show '—'.

    Args:
        subtask_nodes: List of Node objects in the dependency subtree.
        graph_manager: GraphManager instance for looking up nodes.
        edges: List of all edge dicts.
        parent_name: The root node name, used to compute need types.
        include_soft: If False, only hard-need subtasks are shown.
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

    # --- Priority scoring (same ROI algorithm as Suggestions tab, normalized 0–100) ---
    # Nodes receive "—" when: status is Done/Blocked, type is Goal, or any hard
    # prerequisite is not yet Done (ineligible per the scoring algorithm).
    priority_scores = {}
    priority_sort_key = {}  # numeric value used for sorting; -1 for unscored nodes
    if graph_manager:
        scored = graph_manager.calculate_priority_scores(subtask_nodes)
        # Normalized against the whole graph, not against these few rows: a
        # child's priority has to read the same here as on the Home tab and
        # in the Explain modal. A local maximum would print 100 next to the
        # best of a weak set.
        max_score = graph_manager.get_priority_normalizer()
        for n in scored:
            raw = getattr(n, 'priority_score', -1.0)
            if raw < 0 or max_score == 0:
                priority_scores[n.name] = "—"
                priority_sort_key[n.name] = -1.0
            else:
                priority_scores[n.name] = str(round((raw / max_score) * 100))
                # Sort on the unrounded score so rows that print the same
                # number still fall in true priority order.
                priority_sort_key[n.name] = raw

    # Sort: eligible nodes descending by score, then unscored alphabetically below
    subtask_nodes = sorted(
        subtask_nodes,
        key=lambda n: (
            priority_sort_key.get(n.name, -1.0) < 0,  # False (eligible) sorts before True
            -priority_sort_key.get(n.name, 0.0),       # higher score first
            n.name.lower(),                              # alpha tie-break / ineligible order
        ),
    )

    # Cool & quiet palette: Hard a darker rugged blue (the same value as the
    # HardRelPri badge, so one hue means one thing app-wide); Soft a neutral
    # slate; Synergy a cyan-teal, categorically off the Hard/Soft necessity
    # axis. These used to be written out here AND in callback_helpers as
    # _VIA_COLORS, kept in step by a comment saying they matched.
    _REL_BADGE_STYLES = {
        rel: {"backgroundColor": BADGE_PALETTE[f"Edge{rel}"][0],
              "color": BADGE_PALETTE[f"Edge{rel}"][1]}
        for rel in ("Hard", "Soft", "Synergy")
    }

    rows = []
    for node in subtask_nodes:
        # Status badge uses the centralized BADGE_PALETTE so the muted
        # Done/Blocked values match the Details info pane.
        rel = relationship_types.get(node.name, "Hard")
        rel_style = _REL_BADGE_STYLES.get(rel, _REL_BADGE_STYLES["Hard"])
        edit_id = {"type": "details-subtask-edit", "index": node.name}
        edit_btn = html.Div([
            dbc.Button(
                [
                    html.I(className="bi bi-pencil", **{"aria-hidden": "true"}),
                    html.Span(f"Edit {node.name}", className="visually-hidden"),
                ],
                id=edit_id,
                color="link",
                className="details-subtask-edit-btn",
            ),
            Tooltip(
                "Open the node editor",
                target=edit_id,
                placement="left",
            ),
        ], className="details-subtask-actions")

        _eff = graph_manager.get_effective_time(node.name) if graph_manager else 0.0
        _time_cell = ConfigManager.format_time_friendly(_eff) if _eff > 0 else "—"

        rows.append(html.Tr([
            html.Td(
                html.Span(
                    node.name,
                    title=f"{node.name} — open in Details",
                    className="details-subtask-name-link",
                    style={"cursor": "pointer"},
                ),
                id={"type": "details-subtask-name", "index": node.name},
                className="details-subtask-name-cell",
                style=tokens.CELL_PRIMARY,
            ),
            html.Td(html.Span(node.status, className="badge",
                              style=badge_style(node.status, font_size=tokens.FS_XS)),
                    style=tokens.CELL_PRIMARY),
            html.Td(html.Span(rel, className="badge",
                              style={**rel_style, "fontSize": tokens.FS_XS,
                                     "padding": "4px 8px", "borderRadius": "4px"}),
                    style=tokens.CELL_PRIMARY),
            html.Td(node.type, style=tokens.CELL_MUTED),
            html.Td(str(node.context) if node.context else "—",
                    style=tokens.CELL_MUTED),
            html.Td(str(node.subcontext) if node.subcontext else "—",
                    style=tokens.CELL_MUTED),
            html.Td(priority_scores.get(node.name, "—"),
                    style=tokens.CELL_MUTED),
            html.Td(str(node.value),
                    style=tokens.CELL_MUTED),
            html.Td(str(node.interest),
                    style=tokens.CELL_MUTED),
            html.Td(str(node.difficulty),
                    style=tokens.CELL_MUTED),
            html.Td(_time_cell, style=tokens.CELL_MUTED),
            html.Td(edit_btn, style=tokens.CELL_PRIMARY),
        ], className="details-subtask-row"))

    return dbc.Table([
        html.Thead(html.Tr([
            html.Th("Name", className="details-subtask-name-heading"),
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
    ], **tokens.TABLE_PROPS,
       className=f"details-subtasks-table {tokens.TABLE_CLASS}",
       style=tokens.TABLE_STYLE)


def build_milestone_tile(milestone_node, completion: dict):
    """Compact tile for the Details-tab Milestones roster.

    Layout (~280px wide, single horizontal scroll row in the strip):
      Name                     [Status]
      ▰▰▰▰▰▱▱▱▱▱  47% · 18.2h

    Leaf Milestones (no Hard children, total == 0) skip the progress bar
    and show just name + status pill — mirrors the canvas hover tooltip's
    "no subtasks yet" branch behavior.

    The whole tile is keyed for the pattern-matched click callback in
    details_callbacks; clicking navigates Details to this Milestone.
    """
    total = (completion or {}).get('total', 0)
    pct = (completion or {}).get('pct', 0)
    remaining = (completion or {}).get('remaining_time', 0)

    # Header row: name (truncated) + status pill.
    header = html.Div([
        html.Span(
            milestone_node.name,
            style={
                "flex": "1",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
                "whiteSpace": "nowrap",
                "fontSize": tokens.FS_BASE,
                "fontWeight": "500",
            },
            title=milestone_node.name,
        ),
        html.Span(
            milestone_node.status,
            className="badge",
            style={**badge_style(milestone_node.status, font_size=tokens.FS_XS),
                   "marginLeft": "6px"},
        ),
    ], className="d-flex align-items-center")

    children = [header]

    if total > 0:
        bar_color = progress_bar_color(pct)
        children += [
            # Progress bar — same style as the canvas hover tooltip so the two
            # surfaces read identically when hovering vs. browsing.
            html.Div(
                html.Div(style={
                    "width": f"{pct}%", "height": "5px",
                    "backgroundColor": bar_color, "borderRadius": "3px",
                    "transition": "width 0.3s ease"
                }),
                style={"backgroundColor": tokens.BORDER_PANEL, "borderRadius": "3px",
                       "marginTop": "10px", "marginBottom": "5px",
                       "overflow": "hidden"},
            ),
            html.Div(
                f"{pct}% · {ConfigManager.format_time_friendly(remaining)}",
                className="text-muted",
                style={"fontSize": tokens.FS_XS},
            ),
        ]

    # Whole tile is clickable — pattern-matched id picked up by
    # navigate_to_milestone_tile in details_callbacks. Subtle gray border
    # matches the app's separator color; the colored canvas shape is the
    # primary visual cue for "milestone" elsewhere.
    return html.Div(
        children,
        id={"type": "details-milestone-tile", "index": milestone_node.name},
        n_clicks=0,
        style={
            "flex": "0 0 280px",
            "padding": "10px 12px",
            "backgroundColor": tokens.BG_RAISED,
            "border": f"1px solid {tokens.BORDER_PANEL}",
            "borderRadius": "6px",
            "cursor": "pointer",
            "minWidth": "0",
        },
        className="details-milestone-tile",
    )
