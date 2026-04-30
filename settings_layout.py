"""
Layout definitions for the Settings tab.
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
)

_RESTORE_ICON = "\u21ba"  # ↺ anticlockwise open circle arrow


def _build_graph_layout_defaults_row():
    gl = ConfigManager.get_graph_layout_defaults()
    dgl = ConfigManager.get_details_graph_layout_defaults()
    egl = ConfigManager.get_events_graph_layout_defaults()
    return html.Div([
        # Header row with column labels
        dbc.Row([
            dbc.Col(width=2),
            dbc.Col(dbc.Label("Edge Length", className="mb-1"), width=3),
            dbc.Col(dbc.Label("Gravity", className="mb-1"), width=3),
            dbc.Col(dbc.Label("Repulsion", className="mb-1"), width=4),
        ], className="mb-1"),
        # Nodes row
        dbc.Row([
            dbc.Col(dbc.Label("Nodes", className="mb-0 fw-bold"), width=2,
                    className="d-flex align-items-center"),
            dbc.Col([
                dbc.Input(id="setting-graph-edge-length", type="number",
                          min=50, max=300, step=10, value=gl.get('edge_length', 100),
                          placeholder="50 – 300"),
            ], width=3),
            dbc.Col([
                dbc.Input(id="setting-graph-gravity", type="number",
                          min=0, max=5, step=0.25, value=gl.get('gravity', 0.25),
                          placeholder="0 – 5"),
            ], width=3),
            dbc.Col([
                dbc.Input(id="setting-graph-repulsion", type="number",
                          min=500, max=100000, step=500, value=gl.get('repulsion', 4500),
                          placeholder="500 – 100,000"),
            ], width=4),
        ], className="mb-2"),
        # Details row
        dbc.Row([
            dbc.Col(dbc.Label("Details", className="mb-0 fw-bold"), width=2,
                    className="d-flex align-items-center"),
            dbc.Col([
                dbc.Input(id="setting-details-graph-edge-length", type="number",
                          min=50, max=300, step=10, value=dgl.get('edge_length', 100),
                          placeholder="50 – 300"),
            ], width=3),
            dbc.Col([
                dbc.Input(id="setting-details-graph-gravity", type="number",
                          min=0, max=5, step=0.25, value=dgl.get('gravity', 0.25),
                          placeholder="0 – 5"),
            ], width=3),
            dbc.Col([
                dbc.Input(id="setting-details-graph-repulsion", type="number",
                          min=500, max=100000, step=500, value=dgl.get('repulsion', 4500),
                          placeholder="500 – 100,000"),
            ], width=4),
        ], className="mb-2"),
        # Events row
        dbc.Row([
            dbc.Col(dbc.Label("Events", className="mb-0 fw-bold"), width=2,
                    className="d-flex align-items-center"),
            dbc.Col([
                dbc.Input(id="setting-events-graph-edge-length", type="number",
                          min=50, max=300, step=10, value=egl.get('edge_length', 50),
                          placeholder="50 – 300"),
            ], width=3),
            dbc.Col([
                dbc.Input(id="setting-events-graph-gravity", type="number",
                          min=0, max=5, step=0.25, value=egl.get('gravity', 0.25),
                          placeholder="0 – 5"),
            ], width=3),
            dbc.Col([
                dbc.Input(id="setting-events-graph-repulsion", type="number",
                          min=500, max=100000, step=500, value=egl.get('repulsion', 4500),
                          placeholder="500 – 100,000"),
            ], width=4),
        ], className="mb-1"),
    ])


def build_settings_tab_content():
    return html.Div([
        html.Div([
            html.H4("Settings", className="mb-3 mt-3"),

            html.Div(style={"position": "relative"}, children=[
            dbc.Tabs(id="settings-modal-tabs", active_tab="tab-nodes", children=[
                dbc.Tab(label="Nodes", tab_id="tab-nodes", children=[
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
                            ], width=4),
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
                                html.Small("Color for Done, Blocked, and Override.", className="text-muted d-block mb-2"),
                                html.Div(id="setting-node-status-colors-container"),
                            ], width=4),
                        ]),

                        # --- Name Linter group ---
                        html.Hr(className="my-2"),
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

                    ], className="p-2")
                ]),
                dbc.Tab(label="Contexts", tab_id="tab-contexts", children=[
                    html.Div([
                        # --- Context definitions ---
                        html.H5("Definitions", className="mt-2 mb-1"),
                        html.Small("One context per line. Optionally add a colon and comma-separated subcontexts.", className="text-muted d-block mb-1"),
                        dbc.Textarea(id="setting-subcontexts", rows=8, placeholder="e.g.\nMind: Rational, Sensory\nBody: Stress, Sleep\nSocial"),

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

                        # --- Priority weights ---
                        html.Hr(className="my-3"),
                        html.H5("Priority Weights", className="mt-2 mb-1"),
                        html.Small(
                            "Relative importance per context. 1.0 = baseline. "
                            "Doubling a weight doubles that context's priority scores relative to others. "
                            "Applies at the parent-context level — subcontexts inherit their parent's weight.",
                            className="text-muted d-block mb-2"),
                        html.Div(id="setting-context-weights-container"),
                    ], className="p-2")
                ]),
                dbc.Tab(label="Scoring", tab_id="tab-scoring", children=[
                    html.Div([
                        # --- Priorities section ---
                        html.H5("Priorities", className="mt-2 mb-1"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Algorithm Profile"),
                                dbc.Select(id="setting-hp-profile", options=[
                                    {"label": "Default", "value": "Default"},
                                    {"label": "Curious", "value": "Curious"},
                                    {"label": "Industrious", "value": "Industrious"},
                                    {"label": "Custom", "value": "Custom"}
                                ], value="Default"),
                            ], width=4),
                        ], className="mt-1"),

                        html.Hr(className="my-3"),

                        # --- Three-column layout: IV | VP | PC (subsections of Priorities) ---
                        # Headings row — H6 so they read as subsections of the Priorities H5
                        dbc.Row([
                            dbc.Col(html.H6("Intrinsic Value", className="mt-2 mb-1")),
                            dbc.Col(html.H6("Value Propagation", className="mt-2 mb-1")),
                            dbc.Col(html.H6("Perceived Cost", className="mt-2 mb-1")),
                        ], className="mt-2"),
                        # Descriptions row — Bootstrap flex makes all cols equal height
                        dbc.Row([
                            dbc.Col(html.Small([
                                html.Span("IV = w_v \u00b7 V + w_i \u00b7 I",
                                          style={"fontFamily": "monospace"}),
                                html.Br(),
                                "The node's worth on its own, before any cascade or synergy.",
                            ], className="text-muted")),
                            dbc.Col(html.Small(
                                "Hard/Soft: value kept per cascade hop. Pending Bonus: additive boost each gets before either is done. Done Multiplier: multiplicative boost the other gets when one is done.",
                                className="text-muted")),
                            dbc.Col(html.Small([
                                html.Span("C = 1 + w_e \u00b7 E + w_t \u00b7 T^\u03b2",
                                          style={"fontFamily": "monospace"}),
                                html.Br(),
                                "\u03b2 controls the time penalty. At \u03b2 = 1, a 4\u00d7 longer task costs 4\u00d7 more. Lower \u03b2 softens this so long tasks don't carry proportional cost.",
                            ], className="text-muted")),
                        ], className="mb-2"),
                        # Row 1
                        dbc.Row([
                            dbc.Col([dbc.Label("Value Weight", className="mt-2"), dbc.Input(id="hp-wv", type="number", step="any")]),
                            dbc.Col([dbc.Label("Hard Need", className="mt-2"), dbc.Input(id="hp-dh", type="number", step="any")]),
                            dbc.Col([dbc.Label("Effort Weight", className="mt-2"), dbc.Input(id="hp-we", type="number", step="any")]),
                        ]),
                        # Row 2
                        dbc.Row([
                            dbc.Col([dbc.Label("Interest Weight", className="mt-2"), dbc.Input(id="hp-wi", type="number", step="any")]),
                            dbc.Col([dbc.Label("Soft Need", className="mt-2"), dbc.Input(id="hp-ds", type="number", step="any")]),
                            dbc.Col([dbc.Label("Time Weight", className="mt-2"), dbc.Input(id="hp-wt", type="number", step="any")]),
                        ]),
                        # Row 3 (IV column empty; VP carries the two synergy params stacked)
                        dbc.Row([
                            dbc.Col([]),
                            dbc.Col([
                                dbc.Label("Pending Bonus", className="mt-2"),
                                dbc.Input(id="hp-dsyn-pair", type="number", step="any"),
                                dbc.Label("Done Multiplier", className="mt-2"),
                                dbc.Input(id="hp-dsyn-mul", type="number", step="any"),
                            ]),
                            dbc.Col([dbc.Label("Time Dampener", className="mt-2"), dbc.Input(id="hp-beta", type="number", step="any")]),
                        ], className="mb-2"),

                        # --- Multipliers section ---
                        html.Hr(className="my-3"),
                        html.H5("Multipliers", className="mt-2 mb-1"),

                        html.H6("Goal Boost", className="mt-2 mb-1"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Input(id="hp-goal-boost", type="number", step="any"),
                            ], width=2),
                            dbc.Col([
                                html.Small(
                                    "Multiplier applied to nodes in a priority goal's subtree. "
                                    "Rank #1 gets the full boost, #2 gets 66%, #3 gets 33%.",
                                    className="text-muted d-block"),
                            ], width=10),
                        ], className="mb-2"),

                        html.H6("Context Density", className="mt-3 mb-1"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Input(id="hp-alpha", type="number",
                                          min=0, max=1.5, step="any"),
                            ], width=2),
                            dbc.Col([
                                html.Small(
                                    "Normalizes scores by (context, subcontext) bucket size "
                                    "(score \u00d7 1 / n^\u03b1). Higher values penalize larger "
                                    "buckets more. Range: 0 disables; 0.3 (Default profile) "
                                    "compensates mildly; 1.0 fully cancels size bias.",
                                    className="text-muted d-block"),
                            ], width=10),
                        ], className="mb-2"),

                        html.Hr(className="my-3"),
                        html.Small(
                            "Context priority weights also affect scoring \u2014 set them in the Contexts tab.",
                            className="text-muted d-block mt-2 mb-2",
                            style={"fontStyle": "italic"},
                        ),

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
                                              size="sm", style={"width": "90px"}),
                                    width="auto"),
                        ], className="g-1 align-items-center mb-2"),
                        html.Div(id="perf-profile-output", className="small mb-2",
                                 style={"fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace"}),
                    ], className="p-2")
                ]),
                dbc.Tab(label="Visuals", tab_id="tab-visuals", children=[
                    html.Div([
                        # --- Graph Layout Defaults group ---
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

                        # --- Visualization Limits group ---
                        html.Hr(className="my-3"),
                        html.H5("Visualization Limits", className="mt-2 mb-1"),
                        html.Small("Maximum items shown in each Analyze tab section.",
                                   className="text-muted d-block mb-2"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Bottleneck nodes"),
                                dbc.Input(id="setting-analyze-bottlenecks", type="number",
                                          min=5, max=100, step=5),
                            ], width=4),
                            dbc.Col([
                                dbc.Label("Goals"),
                                dbc.Input(id="setting-analyze-goals", type="number",
                                          min=5, max=200, step=5),
                            ], width=4),
                            dbc.Col([
                                dbc.Label("Risk nodes"),
                                dbc.Input(id="setting-analyze-risk", type="number",
                                          min=5, max=100, step=5),
                            ], width=4),
                        ], className="mb-2"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Time sinks"),
                                dbc.Input(id="setting-analyze-time-sinks", type="number",
                                          min=5, max=50, step=5),
                            ], width=4),
                            dbc.Col([
                                dbc.Label("Deepest nodes"),
                                dbc.Input(id="setting-analyze-deepest", type="number",
                                          min=5, max=50, step=5),
                            ], width=4),
                            dbc.Col([
                                dbc.Label("Most connected"),
                                dbc.Input(id="setting-analyze-connected", type="number",
                                          min=5, max=50, step=5),
                            ], width=4),
                        ]),
                    ], className="p-2")
                ]),
                dbc.Tab(label="Personal", tab_id="tab-personal", children=[
                    html.Div([
                        # --- Paths group ---
                        html.H5("Paths", className="mt-2 mb-1"),
                        dbc.Label("Obsidian Vault Root Path", className="mt-2"),
                        dbc.Input(id="setting-obsidian-path", type="text", className="mb-2"),

                        dbc.Label("Google Drive Root Path"),
                        dbc.Input(id="setting-gdrive-path", type="text"),

                        # --- Time Estimates section (merged with defaults) ---
                        html.Hr(className="my-2"),
                        html.H5("Time Estimates", className="mt-2 mb-1"),
                        dbc.Row([
                            dbc.Col([
                                html.Small("Productive hours available.", className="text-muted d-block mb-2"),
                                dbc.Label("Hours per Week"),
                                dbc.Input(id="setting-hpw", type="number", min=1, step=1, className="mb-2"),
                                dbc.Label("Hours per Month"),
                                dbc.Input(id="setting-hpm", type="number", min=1, step=1),
                            ], width=4),
                            dbc.Col(style={"borderLeft": "1px solid #444", "paddingLeft": "1.5rem"}, children=[
                                html.Small("Pre-filled values when creating new nodes.", className="text-muted d-block mb-2"),
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Label("Default Unit"),
                                        dbc.Select(id="setting-default-time-unit", options=[
                                            {"label": "Hours", "value": "hours"},
                                            {"label": "Weeks", "value": "weeks"},
                                            {"label": "Months", "value": "months"},
                                        ]),
                                    ], width=4),
                                ], className="mb-2"),
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Label("Optimistic"),
                                        dbc.Input(id="setting-default-time-o", type="number", min=0, step=1),
                                    ], width=4),
                                    dbc.Col([
                                        dbc.Label("Expected"),
                                        dbc.Input(id="setting-default-time-m", type="number", min=0, step=1),
                                    ], width=4),
                                    dbc.Col([
                                        dbc.Label("Pessimistic"),
                                        dbc.Input(id="setting-default-time-p", type="number", min=0, step=1),
                                    ], width=4),
                                ]),
                            ], width=8),
                        ], className="mt-1"),
                    ], className="p-2")
                ]),
            ]),
            html.Div([
                html.Span(id="settings-save-status", className="text-success me-2",
                          style={"fontSize": "0.85rem"}),
                dbc.Button(html.I(className="bi bi-floppy2-fill"), id="btn-settings-save",
                           color="primary", size="sm",
                           style={"fontSize": "0.95rem", "lineHeight": "1", "padding": "4px 7px"}),
                dbc.Tooltip("Save settings", target="btn-settings-save", placement="bottom",
                            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            ], style={"position": "absolute", "top": "5px", "right": "12px"}),
            ]),
        ], style={"maxWidth": "810px", "padding": "0 24px"}),
    ], style={
        "flex": "1",
        "overflowY": "auto",
    })
