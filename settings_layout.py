"""
Layout definitions for the Settings tab.
"""

from dash import html
import dash_bootstrap_components as dbc

_RESTORE_ICON = "\u21ba"  # ↺ anticlockwise open circle arrow


def build_settings_tab_content():
    return html.Div([
        html.Div([
            html.H4("Settings", className="mb-3 mt-3"),

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
                                        dbc.Tooltip("Restore defaults", target="btn-restore-shapes", placement="top"),
                                    ]),
                                ], className="d-flex align-items-center mt-2 mb-1"),
                                html.Small("Shape for each node type.", className="text-muted d-block mb-2"),
                                html.Div(id="setting-node-shapes-container"),
                            ], width=4),
                            dbc.Col([
                                html.Div([
                                    dbc.Label("Status Colors", className="mb-0"),
                                    html.Span([
                                        dbc.Button(_RESTORE_ICON, id="btn-restore-status-colors",
                                                   color="link", size="sm",
                                                   className="ms-1 p-0",
                                                   style={"fontSize": "1.1rem", "lineHeight": "1", "color": "#adb5bd", "position": "relative", "top": "-2px"}),
                                        dbc.Tooltip("Restore defaults", target="btn-restore-status-colors", placement="top"),
                                    ]),
                                ], className="d-flex align-items-center mt-2 mb-1"),
                                html.Small("Color for Open, Blocked, and Done.", className="text-muted d-block mb-2"),
                                html.Div(id="setting-node-status-colors-container"),
                            ], width=4),
                            dbc.Col([
                                html.Div([
                                    dbc.Label("Type Colors", className="mb-0"),
                                    html.Span([
                                        dbc.Button(_RESTORE_ICON, id="btn-restore-type-colors",
                                                   color="link", size="sm",
                                                   className="ms-1 p-0",
                                                   style={"fontSize": "1.1rem", "lineHeight": "1", "color": "#adb5bd", "position": "relative", "top": "-2px"}),
                                        dbc.Tooltip("Restore defaults", target="btn-restore-type-colors", placement="top"),
                                    ]),
                                ], className="d-flex align-items-center mt-2 mb-1"),
                                html.Small("Color overrides for Goal and Resource types.", className="text-muted d-block mb-2"),
                                html.Div(id="setting-node-type-colors-container"),
                            ], width=4),
                        ]),

                        # --- Contexts group ---
                        html.Hr(className="my-2"),
                        html.H5("Contexts", className="mt-2 mb-1"),
                        dbc.Label("Contexts", className="mt-2"),
                        dbc.Textarea(id="setting-contexts", rows=2, placeholder="e.g. Mind, Body, Social"),
                        html.Small("Comma-separated list. Order is preserved in drop-downs.", className="text-muted d-block mb-1"),

                        dbc.Label("Subcontexts", className="mt-2"),
                        dbc.Textarea(id="setting-subcontexts", rows=6, placeholder="e.g.\nMind: Rational, Sensory\nBody: Stress, Sleep"),
                        html.Small("One context per line. Comma-separated subcontexts after the colon.", className="text-muted d-block mb-1"),
                    ], className="p-2")
                ]),
                dbc.Tab(label="Algorithm", tab_id="tab-algorithm", children=[
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
                            dbc.Col([
                                dbc.Label("Goal Boost"),
                                html.Div([
                                    dbc.Input(id="hp-goal-boost", type="number", step=0.1,
                                              style={"maxWidth": "120px", "flexShrink": "0"}),
                                    html.Small(
                                        "Multiplier applied to nodes in a priority goal's subtree. "
                                        "Rank #1 gets the full boost, #2 gets 66%, #3 gets 33%.",
                                        className="text-muted ms-3"),
                                ], className="d-flex align-items-center"),
                            ], width=8),
                        ], className="mt-1"),

                        # --- Three-column layout: IV | VP | PC ---
                        html.Hr(className="my-2"),
                        # Headings row
                        dbc.Row([
                            dbc.Col(html.H5("Intrinsic Value", className="mt-2 mb-1")),
                            dbc.Col(html.H5("Value Propagation", className="mt-2 mb-1")),
                            dbc.Col(html.H5("Perceived Cost", className="mt-2 mb-1")),
                        ], className="mt-1"),
                        # Descriptions row — Bootstrap flex makes all cols equal height
                        dbc.Row([
                            dbc.Col(html.Small("IV = w_v \u00b7 V + w_i \u00b7 I", className="text-muted",
                                               style={"fontFamily": "monospace"})),
                            dbc.Col(html.Small("Retention factor per edge type (0\u20131). Higher = more value flows through.",
                                               className="text-muted")),
                            dbc.Col(html.Small("C = 1 + w_e \u00b7 E + w_t \u00b7 T^\u03b2", className="text-muted",
                                               style={"fontFamily": "monospace"})),
                        ], className="mb-2"),
                        # Row 1
                        dbc.Row([
                            dbc.Col([dbc.Label("Value Weight", className="mt-2"), dbc.Input(id="hp-wv", type="number", step=0.1)]),
                            dbc.Col([dbc.Label("Hard Need", className="mt-2"), dbc.Input(id="hp-dh", type="number", step=0.01)]),
                            dbc.Col([dbc.Label("Effort Weight", className="mt-2"), dbc.Input(id="hp-we", type="number", step=0.1)]),
                        ]),
                        # Row 2
                        dbc.Row([
                            dbc.Col([dbc.Label("Interest Weight", className="mt-2"), dbc.Input(id="hp-wi", type="number", step=0.1)]),
                            dbc.Col([dbc.Label("Soft Need", className="mt-2"), dbc.Input(id="hp-ds", type="number", step=0.01)]),
                            dbc.Col([dbc.Label("Time Weight", className="mt-2"), dbc.Input(id="hp-wt", type="number", step=0.1)]),
                        ]),
                        # Row 3 (IV column empty)
                        dbc.Row([
                            dbc.Col([]),
                            dbc.Col([dbc.Label("Synergy", className="mt-2"), dbc.Input(id="hp-dsyn", type="number", step=0.01)]),
                            dbc.Col([dbc.Label("Time Dampener", className="mt-2"), dbc.Input(id="hp-beta", type="number", step=0.05)]),
                        ]),


                    ], className="p-2")
                ]),
                dbc.Tab(label="Me", tab_id="tab-paths", children=[
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
                                    ], width=3),
                                    dbc.Col([
                                        dbc.Label("Optimistic"),
                                        dbc.Input(id="setting-default-time-o", type="number", min=0, step=1),
                                    ], width=3),
                                    dbc.Col([
                                        dbc.Label("Expected"),
                                        dbc.Input(id="setting-default-time-m", type="number", min=0, step=1),
                                    ], width=3),
                                    dbc.Col([
                                        dbc.Label("Pessimistic"),
                                        dbc.Input(id="setting-default-time-p", type="number", min=0, step=1),
                                    ], width=3),
                                ]),
                            ], width=8),
                        ], className="mt-1"),
                    ], className="p-2")
                ])
            ]),

            # Save button + status
            html.Div(id="settings-save-status", className="text-success mt-2 ps-2",
                     style={"fontSize": "0.85rem", "minHeight": "1.2em"}),
            html.Div(
                dbc.Button("Save Settings", id="btn-settings-save", color="primary",
                           className="px-4"),
                className="d-flex justify-content-start mt-2 ps-2"
            ),
        ], style={"maxWidth": "900px", "padding": "0 24px"}),
    ], style={
        "flex": "1",
        "overflowY": "auto",
    })
