"""
Layout definitions for the Details tab.

Provides a consolidated view for drilling into any node's dependencies,
subtasks, and time simulation — merging the best parts of the Goals
and Simulation tabs.
"""

from skilltree.ui import tokens
from skilltree.ui.kit import (
    Tooltip,
    add_button,
    done_color,
    filter_chip,
    nav_button,
    panel_close_button,
    progress_bar_color,
    split_handle)
from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from skilltree.store.settings import ConfigManager
from skilltree.ui.styles import badge_style, BADGE_PALETTE
from skilltree.ui.styles import stylesheet
from skilltree.domain.models import STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from skilltree.ui.components.duration import format_time_friendly
from skilltree.ui.canvas.settings_panel import (
    freeze_indicator, build_graph_settings_panel,
)
from skilltree.ui.kit import goal_corner_badge


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
        className="details-empty-state scroll-fade-bottom",
        children=[
            html.Div([
                html.H6("Suggestions", className="text-muted mb-0",
                        style={"fontWeight": "300", "letterSpacing": "1px"}),
            ], style={"textAlign": "center", "marginTop": "15px",
                      "marginBottom": tokens.SPACE_BLOCK}),
            html.Div(id="details-suggestions-container",
                     style={"padding": "0 12px 12px"}),
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
            ], id="details-attr-ratings-own"),
            html.Div(
                _attribute_row("Ratings", "details-attr-ratings-inherited"),
                id="details-attr-ratings-inherited-wrap",
                style={"display": "none"},
            ),
            # Effort follows the node's own hours, not its ratings: hidden
            # only when the node has no work of its own.
            html.Div(
                _attribute_row("Effort", "details-attr-effort"),
                id="details-attr-effort-wrap",
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
    v_drag_handle_upper = split_handle("details-v-drag-upper", "cols", 150)

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
            freeze_indicator("details-freeze-indicator"),
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
            filter_chip("details-filter-chip", "filter-chip-overlay"),
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
       style={"display": "flex", "flex": "1.618", "minHeight": "0"})

    # ------------------------------------------------------------------ #
    #  HORIZONTAL DRAG HANDLE                                             #
    # ------------------------------------------------------------------ #
    h_drag_handle = split_handle("details-h-drag", "rows", 100)

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
                add_button("btn-details-add-node", None,
                           label="Add subtask node"),
            ], className="d-flex align-items-center"),
            html.Div(_build_toggles(), id="details-subtask-toggles-bottom"),
        ], className="d-flex align-items-center justify-content-between",
           style={"marginBottom": tokens.SPACE_BLOCK}),
        html.Div(build_no_selection_subtasks(),
                 id="details-subtasks-table-container",
                 style={"overflowY": "visible", "flex": "none"}),
    ], id="details-subtasks-section", className="scroll-fade-bottom",
       style={"flex": "1", "minWidth": "300px", "display": "flex",
              "flexDirection": "column", "paddingRight": "8px",
              "overflowY": "auto"})

    v_drag_handle_lower = split_handle("details-v-drag-lower", "cols", 150)

    sim_section = html.Div([
        dcc.Store(id="details-sim-request"),
        dcc.Store(id="details-sim-server-request"),
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
    link_node_modal = _build_link_node_modal()

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
            # The selection, as the modal sees it: written only while the modal
            # is open, so a selection made with it closed asks the server
            # nothing.
            dcc.Store(id="details-explain-node"),
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
        # once an open or close slide finishes, so render_goal_list builds or
        # clears the list — but NOT an input to core_engine, so opening
        # doesn't wait on a graph regen.
        dcc.Store(id='goals-ui-refresh-trigger', data=0),
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
        dcc.Input(id='details-add-choice-input', type='text', value='',
                  style={'display': 'none'}),
        dcc.Input(id='goal-priority-trigger-input', type='text', value='',
                  style={'display': 'none'}),
        link_node_modal,
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


def build_suggestion_row(node, priority_rank=None, priority=None):
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
        corner = goal_corner_badge(str(priority_rank), "PriorityRank",
                                    "badge details-suggestion-badge")
    elif priority is not None:
        label_bits = [f"Priority score {priority}"]
        corner = goal_corner_badge(str(priority), STATUS_OPEN,
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
        # A later list sits a little further from the one above it than the
        # first list does from the title.
        return html.Div([
            html.H6(title, className="text-muted mb-2",
                    style={"fontSize": tokens.FS_CAP, "fontWeight": "500",
                           "letterSpacing": "1px", "textTransform": "uppercase",
                           "marginTop": "20px" if sections else "12px"}),
            html.Div(rows),
        ])

    if goal_rows:
        sections.append(_section("Priority Goals", goal_rows))
    if explore_rows:
        sections.append(_section("Goals", explore_rows))
    elif goal_rows and filters_active:
        sections.append(_section("Goals", [
            html.P("No areas match the current filters.",
                   className="text-muted small mb-0")
        ]))

    if not sections:
        message = ("No areas match the current filters."
                   if filters_active else "No areas to explore yet.")
        return html.P(message,
                      className="text-muted small text-center mt-3")
    return sections


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
            "right": "0px",
            "transform": "translateX(100%)",
            "width": "280px",
            "height": "100%",
            "zIndex": 100,
            "overflowX": "hidden",
            "overflowY": "auto",
            "borderLeft": f"1px solid {tokens.BORDER_PANEL}",
            "transition": "transform 0.3s ease",
            "willChange": "transform",
            "backgroundColor": tokens.BG_PANEL,
            "display": "flex",
            "flexDirection": "column",
        }
    )


def _build_link_node_modal():
    """Link an existing node as a direct prerequisite of the Details node."""
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Link Existing Node")),
        dbc.ModalBody([
            dbc.Label("Node"),
            html.Div(dcc.Dropdown(
                id="details-add-existing-dropdown",
                placeholder="Search for a node...",
            ), className="text-dark mb-3"),
            dbc.Label("Relationship"),
            dbc.Select(
                id="details-add-link-edge-type",
                options=[
                    {"label": "Hard", "value": "hard"},
                    {"label": "Soft", "value": "soft"},
                ],
                value="hard",
            ),
            html.Div(id="details-add-save-status", className="text-danger mt-2",
                     style={"fontSize": tokens.FS_BASE, "minHeight": "1.2em"}),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-details-add-cancel",
                       color="secondary", className="me-2"),
            dbc.Button("Link", id="btn-details-add-save", color="success",
                       style={"backgroundColor": done_color(),
                              "borderColor": done_color()}),
        ]),
    ], id="modal-details-link-node", is_open=False, centered=True)


def build_no_selection_subtasks():
    """What the subtasks table shows before any node is selected."""
    return html.Div("Select a node to see subtasks.",
                    className="text-muted text-center py-3")


def build_details_subtasks_table(subtask_nodes, graph_manager=None, edges=None,
                                  parent_name=None, include_soft=True,
                                  include_synergies=False, milestones_only=False):
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
        milestones_only: True when the node's only prerequisites are the
            Milestones shown in the strip above, so the empty table says that.
    """
    if not subtask_nodes:
        message = ("Only Milestones lead into this node so far. Add the work "
                   "that gets you there to see it here." if milestones_only
                   else "No subtasks found. Add prerequisite nodes to see them here.")
        return html.Div(
            html.P(message, className="text-muted"),
            className="text-center py-3"
        )

    edges = edges or []
    relationship_types = {}
    if parent_name and graph_manager:
        from skilltree.domain.models import EDGE_NEEDS_SOFT, EDGE_HELPS, EDGE_NEEDS_HARD
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
        # With the priority Goals, as Home and Explain score: without them a
        # task under a priority Goal read lower here than there.
        scored = graph_manager.calculate_priority_scores(
            subtask_nodes, priority_goals=ConfigManager.get_priority_goals())
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
    # axis. These used to be written out here AND in details/explain.py as
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
        _time_cell = format_time_friendly(_eff) if _eff > 0 else "—"

        rows.append(html.Tr([
            html.Td(
                html.Span(
                    node.name,
                    title=f"{node.name} — open in Details",
                    className="details-subtask-name-link",
                    role="button", tabIndex=0,
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
            html.Th([
                html.Span("Time", id="details-subtasks-time-heading", className="hover-hint"),
                Tooltip("Work time: hours of focused effort, not calendar time.",
                        target="details-subtasks-time-heading", placement="top"),
            ]),
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

    A Milestone with no estimated work beneath it (no Hard children, or only
    other Milestones) skips the progress bar and hours and shows just name +
    status pill — mirrors the canvas hover tooltip.

    The whole tile is keyed for the pattern-matched click callback in
    details_callbacks; clicking navigates Details to this Milestone.
    """
    has_work = (completion or {}).get('has_work', False)
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

    if has_work:
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
                f"{pct}% · {format_time_friendly(remaining)}",
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
        role="button", tabIndex=0,
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


def normalize_max_depth(value):
    """Map the Details slider's ``All`` sentinel to an uncapped traversal."""
    return None if value in (None, 0, 6) else int(value)
