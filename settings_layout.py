"""
Layout definitions for the Settings modal.
"""

from dash import html
import dash_bootstrap_components as dbc
from config import (
    ConfigManager,
    TOOLTIP_SHOW_DELAY_MS,
    TOOLTIP_HIDE_DELAY_MS,
    SUBCONTEXT_SORT_DEFINITION,
    SUBCONTEXT_SORT_LENGTH,
    SUBCONTEXT_SORT_ALPHABETICAL,
    CONTEXT_SORT_DEFINITION,
    CONTEXT_SORT_LENGTH,
    CONTEXT_SORT_ALPHABETICAL,
    DEFAULT_GRAPH_LAYOUT,
    DEFAULT_DETAILS_GRAPH_LAYOUT,
    DEFAULT_EVENTS_GRAPH_LAYOUT,
)

_RESTORE_ICON = "↺"  # ↺ anticlockwise open circle arrow


def _build_graph_layout_defaults_row():
    gl = ConfigManager.get_graph_layout_defaults()
    dgl = ConfigManager.get_details_graph_layout_defaults()
    egl = ConfigManager.get_events_graph_layout_defaults()

    _label_w = "76px"
    _col_w = "116px"

    def _cell(child, width):
        return html.Div(child, style={"width": width, "flex": "0 0 auto"})

    def _data_row(label, ids, vals, last=False):
        return html.Div([
            _cell(dbc.Label(label, className="mb-0 fw-bold"), _label_w),
            _cell(dbc.Input(id=ids[0], type="number", min=50, max=300, step=10,
                            value=vals[0], placeholder="50 – 300"), _col_w),
            _cell(dbc.Input(id=ids[1], type="number", min=0, max=5, step=0.25,
                            value=vals[1], placeholder="0 – 5"), _col_w),
            _cell(dbc.Input(id=ids[2], type="number", min=500, max=100000, step=500,
                            value=vals[2], placeholder="500 – 100,000"), _col_w),
        ], className="d-flex align-items-center gap-4 " + ("mb-1" if last else "mb-2"))

    return html.Div([
        # Header row with column labels
        html.Div([
            _cell(None, _label_w),
            _cell(dbc.Label("Edge Length", className="mb-1"), _col_w),
            _cell(dbc.Label("Gravity", className="mb-1"), _col_w),
            _cell(dbc.Label("Repulsion", className="mb-1"), _col_w),
        ], className="d-flex gap-4 mb-1"),
        _data_row("Nodes",
                  ["setting-graph-edge-length", "setting-graph-gravity",
                   "setting-graph-repulsion"],
                  [gl.get('edge_length', DEFAULT_GRAPH_LAYOUT['edge_length']),
                   gl.get('gravity', DEFAULT_GRAPH_LAYOUT['gravity']),
                   gl.get('repulsion', DEFAULT_GRAPH_LAYOUT['repulsion'])]),
        _data_row("Details",
                  ["setting-details-graph-edge-length", "setting-details-graph-gravity",
                   "setting-details-graph-repulsion"],
                  [dgl.get('edge_length', DEFAULT_DETAILS_GRAPH_LAYOUT['edge_length']),
                   dgl.get('gravity', DEFAULT_DETAILS_GRAPH_LAYOUT['gravity']),
                   dgl.get('repulsion', DEFAULT_DETAILS_GRAPH_LAYOUT['repulsion'])]),
        _data_row("Events",
                  ["setting-events-graph-edge-length", "setting-events-graph-gravity",
                   "setting-events-graph-repulsion"],
                  [egl.get('edge_length', DEFAULT_EVENTS_GRAPH_LAYOUT['edge_length']),
                   egl.get('gravity', DEFAULT_EVENTS_GRAPH_LAYOUT['gravity']),
                   egl.get('repulsion', DEFAULT_EVENTS_GRAPH_LAYOUT['repulsion'])], last=True),
    ])


def _build_appearance_tab():
    return dbc.Tab(label="Appearance", tab_id="tab-appearance", children=[
        html.Div([
            # --- Node Appearance group ---
            html.H5("Node Appearance", className="mt-2 mb-1"),
            dbc.Label("Types", className="mt-2"),
            dbc.Textarea(id="setting-node-types", rows=2, placeholder="e.g. Topic, Goal, Skill, Action, Resource"),
            html.Small("Comma-separated list. Order is preserved in drop-downs.", className="text-muted d-block mb-1"),

            dbc.Row([
                dbc.Col([
                    html.Div([
                        dbc.Label("Shapes", className="mb-0"),
                        html.Span([
                            dbc.Button(_RESTORE_ICON, id="btn-restore-shapes",
                                       color="link", size="sm",
                                       className="ms-1 p-0",
                                       style={"fontSize": "1.1rem", "lineHeight": "1", "color": "#adb5bd", "position": "relative", "top": "-2px"}),
                            dbc.Tooltip("Restore defaults", target="btn-restore-shapes", placement="top",
                                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                        ]),
                    ], className="d-flex align-items-center mt-2 mb-1"),
                    html.Small("Shape for each node type.", className="text-muted d-block mb-2"),
                    html.Div(id="setting-node-shapes-container"),
                ], width=4),
                dbc.Col([
                    html.Div([
                        dbc.Label("Type Colors", className="mb-0"),
                        html.Span([
                            dbc.Button(_RESTORE_ICON, id="btn-restore-type-colors",
                                       color="link", size="sm",
                                       className="ms-1 p-0",
                                       style={"fontSize": "1.1rem", "lineHeight": "1", "color": "#adb5bd", "position": "relative", "top": "-2px"}),
                            dbc.Tooltip("Restore defaults", target="btn-restore-type-colors", placement="top",
                                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                        ]),
                    ], className="d-flex align-items-center mt-2 mb-1"),
                    html.Small("Open color for each node type.", className="text-muted d-block mb-2"),
                    html.Div(id="setting-node-type-colors-container"),
                ], width=3),
                dbc.Col([
                    html.Div([
                        dbc.Label("Status Colors", className="mb-0"),
                        html.Span([
                            dbc.Button(_RESTORE_ICON, id="btn-restore-status-colors",
                                       color="link", size="sm",
                                       className="ms-1 p-0",
                                       style={"fontSize": "1.1rem", "lineHeight": "1", "color": "#adb5bd", "position": "relative", "top": "-2px"}),
                            dbc.Tooltip("Restore defaults", target="btn-restore-status-colors", placement="top",
                                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                        ]),
                    ], className="d-flex align-items-center mt-2 mb-1"),
                    html.Small("Color for Done, Blocked, Override, and Now.", className="text-muted d-block mb-2"),
                    html.Div(id="setting-node-status-colors-container"),
                ], width=5),
            ]),

            # --- Graph Layout Defaults group ---
            html.Hr(className="my-3"),
            html.Div([
                html.H5("Graph Layout Defaults", className="mb-0"),
                html.Span([
                    dbc.Button(_RESTORE_ICON, id="btn-restore-graph-layout",
                               color="link", size="sm",
                               className="ms-1 p-0",
                               style={"fontSize": "1.1rem", "lineHeight": "1", "color": "#adb5bd", "position": "relative", "top": "-2px", "textDecoration": "none"}),
                    dbc.Tooltip("Restore defaults", target="btn-restore-graph-layout", placement="top",
                                delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                ]),
            ], className="d-flex align-items-center mt-2 mb-1"),
            html.Small("Default parameters for the fcose layout algorithm.", className="text-muted d-block mb-2"),
            _build_graph_layout_defaults_row(),

            # --- Name Linter group ---
            html.Hr(className="my-3"),
            html.H5("Name Linter", className="mt-2 mb-1"),
            dbc.Checklist(
                id="setting-linter-enabled",
                options=[{"label": "Auto-convert node names and aliases to title case on save", "value": "enabled"}],
                value=["enabled"],
                switch=True,
                className="mb-2",
            ),
            dbc.Label("Lowercase exceptions", className="mt-1"),
            dbc.Textarea(id="setting-linter-exclusions", rows=2,
                         placeholder="e.g. a, an, the, and, or, of"),
            html.Small("Comma-separated words that stay lowercase (except at the start of a name). These words are also ignored when checking for duplicate names while creating or renaming nodes.", className="text-muted d-block mb-1"),

            # --- Next Table group ---
            html.Hr(className="my-3"),
            html.H5("Next Table", className="mt-2 mb-1"),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Default Rows", className="mb-0 mt-1"),
                ], width="auto", className="pe-1"),
                dbc.Col([
                    dbc.Input(id="setting-next-table-rows", type="number", min=1, max=100, step=1,
                              style={"width": "80px"}, size="sm"),
                ], width="auto"),
            ], className="g-1 align-items-center mb-1"),
            html.Small("Number of suggestion rows to display in the Next tab by default.", className="text-muted d-block mb-1"),

            # --- Repair Graph group ---
            html.Hr(className="my-2"),
            html.H5("Repair Graph", className="mt-2 mb-1"),
            html.Small(
                "Re-derives Open/Blocked status for every non-Goal node. Runs automatically at startup; trigger manually after programmatic edits that bypassed the cascade.",
                className="text-muted d-block mb-2",
            ),
            dbc.Row([
                dbc.Col(dbc.Button("Repair Graph", id="btn-repair-graph",
                                   color="secondary", size="sm"),
                        width="auto", className="pe-2"),
                dbc.Col(html.Span(id="repair-graph-status",
                                  className="text-muted",
                                  style={"fontSize": "0.85rem"}),
                        className="d-flex align-items-center"),
            ], className="g-1 align-items-center mb-2"),

        ], className="p-2")
    ])


def _build_contexts_tab():
    return dbc.Tab(label="Contexts", tab_id="tab-contexts", children=[
        html.Div([
            # --- Context definitions ---
            html.H5("Definitions", className="mt-2 mb-1"),
            html.Small("One context per line. Optionally add a colon and comma-separated subcontexts.", className="text-muted d-block mb-1"),
            dbc.Textarea(
                id="setting-subcontexts",
                rows=3,
                placeholder="e.g.\nMind: Rational, Sensory\nBody: Stress, Sleep\nSocial",
                style={"resize": "none", "overflow": "hidden"},
            ),

            # --- Context dropdown sort order ---
            dbc.Label("Context Dropdown Order", className="mt-2"),
            dbc.RadioItems(
                id="setting-context-sort-mode",
                options=[
                    {"label": "None", "value": CONTEXT_SORT_DEFINITION},
                    {"label": "Length", "value": CONTEXT_SORT_LENGTH},
                    {"label": "Alphabetical", "value": CONTEXT_SORT_ALPHABETICAL},
                ],
                value=CONTEXT_SORT_DEFINITION,
                inline=True,
            ),
            html.Small(
                "None keeps the order defined above. Length sorts shortest first. Alphabetical sorts A–Z.",
                className="text-muted d-block mb-1"),

            # --- Subcontext dropdown sort order ---
            dbc.Label("Subcontext Dropdown Order", className="mt-2"),
            dbc.RadioItems(
                id="setting-subcontext-sort-mode",
                options=[
                    {"label": "None", "value": SUBCONTEXT_SORT_DEFINITION},
                    {"label": "Length", "value": SUBCONTEXT_SORT_LENGTH},
                    {"label": "Alphabetical", "value": SUBCONTEXT_SORT_ALPHABETICAL},
                ],
                value=SUBCONTEXT_SORT_DEFINITION,
                inline=True,
            ),
            html.Small(
                "None keeps the order defined above. Length sorts shortest first. Alphabetical sorts A–Z.",
                className="text-muted d-block mb-1"),
        ], className="p-2")
    ])


def _build_scoring_tab():
    return dbc.Tab(label="Scoring", tab_id="tab-scoring", children=[
        html.Div([
            # --- Priorities section ---
            html.H5("Priorities", className="mt-2 mb-1"),
            dbc.Row([
                dbc.Col([
                    html.Div([
                        dbc.Label("Algorithm Profile", className="mb-0"),
                        html.Button(
                            html.I(className="bi bi-info-circle"),
                            id="btn-hp-profile-info",
                            style={
                                "background": "none", "border": "none",
                                "padding": "0 0 0 6px",
                                "color": "#6c757d", "cursor": "pointer",
                                "fontSize": "0.95rem", "lineHeight": "1",
                                "position": "relative", "top": "1px",
                            },
                        ),
                        dbc.Popover(
                            [
                                dbc.PopoverHeader("Scoring Profiles"),
                                dbc.PopoverBody(
                                    dbc.Table(
                                        [
                                            html.Thead(html.Tr([
                                                html.Th("Profile"),
                                                html.Th("What it does"),
                                                html.Th("Use when"),
                                            ])),
                                            html.Tbody([
                                                html.Tr([
                                                    html.Td(html.Strong("Sage")),
                                                    html.Td("Balanced across all five factors. The sensible baseline."),
                                                    html.Td("No strong reason to pick something else."),
                                                ]),
                                                html.Tr([
                                                    html.Td(html.Strong("Explorer")),
                                                    html.Td("Interest weighted over Value. Synergies hit harder. Cross-context links are rewarded. Sparser subcontexts get a fairer shot at surfacing."),
                                                    html.Td("You want to follow rabbit holes and let enjoyable, exploratory work surface."),
                                                ]),
                                                html.Tr([
                                                    html.Td(html.Strong("Compounder")),
                                                    html.Td("The cascade is amplified; time is less punishing."),
                                                    html.Td("You're willing to invest now for downstream payoff — sabbatical months, quiet quarters."),
                                                ]),
                                                html.Tr([
                                                    html.Td(html.Strong("Pragmatist")),
                                                    html.Td("Value beats Interest. Priority-Goal boost is dialed up; synergies and Soft edges are minimized."),
                                                    html.Td("You have a clear Goal and want the algorithm to drive everything toward it."),
                                                ]),
                                                html.Tr([
                                                    html.Td(html.Strong("Creator")),
                                                    html.Td("Synergies are massively amplified, especially across contexts."),
                                                    html.Td("You're synthesizing across domains — writing, designing, building something new."),
                                                ]),
                                                html.Tr([
                                                    html.Td(html.Strong("Glider")),
                                                    html.Td("Time and effort weigh more heavily, so short and easy work rises. Cascade, synergies, and the Priority-Goal boost are all dialed back — non-priority work gets a fair chance to surface."),
                                                    html.Td("Light-effort days — a break from the priority grind, or just a lap through small things."),
                                                ]),
                                            ]),
                                        ],
                                        bordered=False,
                                        color="dark",
                                        hover=False,
                                        size="sm",
                                        className="mb-0",
                                    ),
                                    style={"padding": "0.5rem"},
                                ),
                            ],
                            id="popover-hp-profile-info",
                            target="btn-hp-profile-info",
                            is_open=False,
                            placement="bottom",
                            style={"maxWidth": "640px", "minWidth": "560px"},
                        ),
                    ], className="d-flex align-items-center mb-1"),
                    dbc.Select(id="setting-hp-profile", options=[
                        {"label": "Sage", "value": "Sage"},
                        {"label": "Explorer", "value": "Explorer"},
                        {"label": "Compounder", "value": "Compounder"},
                        {"label": "Pragmatist", "value": "Pragmatist"},
                        {"label": "Creator", "value": "Creator"},
                        {"label": "Glider", "value": "Glider"},
                        {"label": "Custom", "value": "Custom"}
                    ], value="Sage"),
                ], width=4),
            ], className="mt-1"),

            html.Hr(className="my-3"),

            # --- Four-column layout: IV | Cascade | Synergy | PC (subsections of Priorities) ---
            # Headings row — H6 so they read as subsections of the Priorities H5
            dbc.Row([
                dbc.Col(html.H6("Intrinsic Value", className="mt-2 mb-1")),
                dbc.Col(html.H6("Cascade", className="mt-2 mb-1")),
                dbc.Col(html.H6("Synergy", className="mt-2 mb-1")),
                dbc.Col(html.H6("Perceived Cost", className="mt-2 mb-1")),
            ], className="mt-2"),
            # Descriptions row — Bootstrap flex makes all cols equal height
            dbc.Row([
                dbc.Col(html.Small(
                    "The node's worth on its own, before any cascade or synergy.",
                    className="text-muted")),
                dbc.Col(html.Small(
                    "Fraction of value kept per cascade hop along prerequisite edges. Hard edges propagate more strongly than Soft.",
                    className="text-muted")),
                dbc.Col(html.Small(
                    "Pending Bonus: additive boost each partner gets before either is done. Done Multiplier: multiplicative boost the other gets when one is done.",
                    className="text-muted")),
                dbc.Col(html.Small(
                    "Effort and time weights are linear. The time dampener (β) is exponential; a lower β softens the penalty for long tasks.",
                    className="text-muted")),
            ], className="mb-2"),
            # Row 1
            dbc.Row([
                dbc.Col([dbc.Label("Value Weight", className="mt-2"), dbc.Input(id="hp-wv", type="number", step="any")]),
                dbc.Col([dbc.Label("Hard Need", className="mt-2"), dbc.Input(id="hp-dh", type="number", step="any")]),
                dbc.Col([dbc.Label("Pending Bonus", className="mt-2"), dbc.Input(id="hp-dsyn-pair", type="number", step="any")]),
                dbc.Col([dbc.Label("Effort Weight", className="mt-2"), dbc.Input(id="hp-we", type="number", step="any")]),
            ]),
            # Row 2
            dbc.Row([
                dbc.Col([dbc.Label("Interest Weight", className="mt-2"), dbc.Input(id="hp-wi", type="number", step="any")]),
                dbc.Col([dbc.Label("Soft Need", className="mt-2"), dbc.Input(id="hp-ds", type="number", step="any")]),
                dbc.Col([dbc.Label("Done Multiplier", className="mt-2"), dbc.Input(id="hp-dsyn-mul", type="number", step="any")]),
                dbc.Col([dbc.Label("Time Weight", className="mt-2"), dbc.Input(id="hp-wt", type="number", step="any")]),
            ]),
            # Row 3 (only Perceived Cost carries a third param)
            dbc.Row([
                dbc.Col([]),
                dbc.Col([]),
                dbc.Col([]),
                dbc.Col([dbc.Label("Time Dampener", className="mt-2"), dbc.Input(id="hp-beta", type="number", step="any")]),
            ], className="mb-2"),

            # --- Multipliers section ---
            html.Hr(className="my-3"),
            html.H5("Multipliers", className="mt-2 mb-1"),

            html.H6("Goal Boost", className="mt-2 mb-1"),
            dbc.Row([
                dbc.Col([
                    dbc.Input(id="hp-goal-boost", type="number", step="any"),
                ], width=3),
                dbc.Col([
                    html.Small(
                        id="hp-goal-boost-description",
                        className="text-muted d-block"),
                ], width=9),
            ], className="mb-2"),

            html.H6("Cross-Context Boost", className="mt-3 mb-1"),
            dbc.Row([
                dbc.Col([
                    dbc.Input(id="hp-cross-context-mult", type="number", step="any"),
                ], width=3),
                dbc.Col([
                    html.Small(
                        "Scales the synergy Pending Bonus when partners live in "
                        "different contexts. 1.0 = off; higher rewards "
                        "cross-domain synergies.",
                        className="text-muted d-block"),
                ], width=9),
            ], className="mb-2"),

            html.H6("Context Density", className="mt-3 mb-1"),
            dbc.Row([
                dbc.Col([
                    dbc.Input(id="hp-alpha", type="number",
                              min=0, max=1.5, step="any"),
                ], width=3),
                dbc.Col([
                    html.Small(
                        "Normalizes scores by (context, subcontext) bucket size "
                        "(score × 1 / n^α). Higher values penalize larger "
                        "buckets more. 0 disables; 0.3 (Sage profile) "
                        "compensates mildly; 1.0 fully cancels size bias.",
                        className="text-muted d-block"),
                ], width=9),
            ], className="mb-2"),

            # --- Context Priority Weights ---
            html.H6("Context Priority Weights", className="mt-3 mb-1"),
            html.Small(
                "Relative importance per context. 1.0 = baseline. "
                "Doubling a weight doubles that context's priority scores relative to others. "
                "Applies at the parent-context level — subcontexts inherit their parent's weight. "
                "Contexts are defined in the Contexts tab.",
                className="text-muted d-block mb-2"),
            html.Div(id="setting-context-weights-container"),

            # --- Performance group ---
            html.Hr(className="my-3"),
            html.H5("Performance", className="mt-2 mb-1"),

            # Startup analysis: timing + log on the first scoring run only
            html.H6("Startup Analysis", className="mt-2 mb-1"),
            dbc.Checklist(
                id="setting-show-scoring-perf",
                options=[{"label": "Run on startup", "value": "enabled"}],
                value=[],
                switch=True,
                className="mb-1",
                labelStyle={"fontWeight": "normal", "fontSize": "0.9rem"},
            ),
            html.Small(
                "Analyzes the entire graph upon initialization.",
                className="text-muted d-block mb-3",
            ),

            # Manual benchmark: always available
            html.H6("Manual Benchmark", className="mt-2 mb-1"),
            html.Small(
                ["Runs scoring ", html.I("n"), " times with a cold memo and "
                 "reports statistics. Does not append to log."],
                className="text-muted d-block mb-2",
            ),
            dbc.Row([
                dbc.Col(dbc.Button("Run Benchmark", id="btn-run-perf-profile",
                                   color="secondary", size="sm"),
                        width="auto", className="pe-2"),
                dbc.Col(dbc.Label("Runs:", html_for="perf-profile-runs",
                                  className="mb-0 mt-1"),
                        width="auto", className="pe-1"),
                dbc.Col(dbc.Input(id="perf-profile-runs", type="number",
                                  min=1, max=10000, step=1, value=100,
                                  size="sm", style={"width": "68px"}),
                        width="auto"),
            ], className="g-1 align-items-center mb-2"),
            html.Div(id="perf-profile-output", className="small mb-2",
                     style={"fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace"}),
        ], className="p-2")
    ])


def _build_time_tab():
    return dbc.Tab(label="Time", tab_id="tab-time", children=[
        html.Div([
            # --- Time Estimates section (merged with defaults) ---
            html.H5("Time Estimates", className="mt-2 mb-1"),
            dbc.Row([
                dbc.Col([
                    html.Small("Productive hours available.", className="text-muted d-block mb-2"),
                    dbc.Label("Hours per Week"),
                    dbc.Input(id="setting-hpw", type="number", min=1, step=1,
                              className="mb-2", style={"width": "128px"}),
                    dbc.Label("Hours per Month"),
                    dbc.Input(id="setting-hpm", type="number", min=1, step=1,
                              className="mb-2", style={"width": "128px"}),
                    dbc.Label("Hours per Year"),
                    dbc.Input(id="setting-hpy", type="number", min=1, step=1,
                              style={"width": "128px"}),
                ], width="auto"),
                dbc.Col(style={"borderLeft": "1px solid #444", "paddingLeft": "1.5rem"}, children=[
                    html.Small("Pre-filled values when creating new nodes.", className="text-muted d-block mb-2"),
                    dbc.Label("Default Unit"),
                    dbc.Select(id="setting-default-time-unit", className="mb-2", options=[
                        {"label": "Hours", "value": "hours"},
                        {"label": "Weeks", "value": "weeks"},
                        {"label": "Months", "value": "months"},
                        {"label": "Years", "value": "years"},
                    ]),
                    html.Div([
                        html.Div([
                            dbc.Label("Lower"),
                            dbc.Input(id="setting-default-time-o", type="number",
                                      min=0, step=1, style={"width": "128px"}),
                        ]),
                        html.Div([
                            dbc.Label("Expected"),
                            dbc.Input(id="setting-default-time-m", type="number",
                                      min=0, step=1, style={"width": "128px"}),
                        ]),
                        html.Div([
                            dbc.Label("Upper"),
                            dbc.Input(id="setting-default-time-p", type="number",
                                      min=0, step=1, style={"width": "128px"}),
                        ]),
                    ], className="d-flex gap-3"),
                ], width=True),
            ], className="mt-1"),

            # --- Reflection section ---
            html.Hr(className="my-2"),
            html.H5("Reflection", className="mt-2 mb-1"),
            html.Small(
                "When a node is marked Done, prompt for actuals — time, "
                "value, interest, and effort.",
                className="text-muted d-block mb-2"),
            dbc.Checklist(
                id="setting-time-calibration-enabled",
                options=[{"label": "Prompt for reflection on completion",
                          "value": "enabled"}],
                value=["enabled"],
                switch=True,
                className="mb-2",
            ),
            html.Small(
                "Manage the queue (start a session, browse history, "
                "restore excluded nodes) from the Reflection Hub — the "
                "journal icon in the top toolbar.",
                className="text-muted d-block",
            ),
        ], className="p-2")
    ])


def _build_paths_tab():
    return dbc.Tab(label="Paths", tab_id="tab-paths", children=[
        html.Div([
            # --- Paths group ---
            html.H5("Paths", className="mt-2 mb-1"),
            dbc.Label("Obsidian Vault Root Path", className="mt-2"),
            dbc.Input(id="setting-obsidian-path", type="text", className="mb-2"),

            dbc.Label("Google Drive Root Path"),
            dbc.Input(id="setting-gdrive-path", type="text"),
        ], className="p-2")
    ])


def build_settings_modal():
    """The Settings modal — opened by the gear button in the top toolbar."""
    save_group = html.Div([
        dbc.Button(html.I(className="bi bi-floppy2-fill"), id="btn-settings-save",
                   color="primary", size="sm",
                   style={"fontSize": "0.95rem", "lineHeight": "1", "padding": "4px 7px"}),
        html.Span(id="settings-save-status", className="text-success ms-2",
                  style={"fontSize": "0.85rem"}),
        dbc.Tooltip("Save settings", target="btn-settings-save", placement="bottom",
                    delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
    ], className="ms-3 d-flex align-items-center")

    return dbc.Modal([
        dbc.ModalHeader([
            dbc.ModalTitle("Settings"),
            save_group,
        ]),
        dbc.ModalBody(
            dbc.Tabs(id="settings-modal-tabs", active_tab="tab-appearance", children=[
                _build_appearance_tab(),
                _build_contexts_tab(),
                _build_scoring_tab(),
                _build_time_tab(),
                _build_paths_tab(),
            ]),
        ),
    ], id="settings-modal", dialog_style={"maxWidth": "900px"},
       is_open=False, scrollable=True)
