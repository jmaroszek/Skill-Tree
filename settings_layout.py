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
                                                   style={"fontSize": "1.1rem", "lineHeight": "1", "color": "#adb5bd"}),
                                        dbc.Tooltip("Restore defaults", target="btn-restore-shapes", placement="top"),
                                    ]),
                                ], className="d-flex align-items-center mt-2 mb-1"),
                                html.Small("Shape for each node type.", className="text-muted d-block mb-2"),
                                html.Div(id="setting-node-shapes-container"),
                            ], width=6),
                            dbc.Col([
                                html.Div([
                                    dbc.Label("Colors", className="mb-0"),
                                    html.Span([
                                        dbc.Button(_RESTORE_ICON, id="btn-restore-colors",
                                                   color="link", size="sm",
                                                   className="ms-1 p-0",
                                                   style={"fontSize": "1.1rem", "lineHeight": "1", "color": "#adb5bd"}),
                                        dbc.Tooltip("Restore defaults", target="btn-restore-colors", placement="top"),
                                    ]),
                                ], className="d-flex align-items-center mt-2 mb-1"),
                                html.Small("Color for node statuses and type overrides.", className="text-muted d-block mb-2"),
                                html.Div(id="setting-node-colors-container"),
                            ], width=6),
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
                        # --- Profile selector ---
                        html.H5("Algorithm Profile", className="mt-2 mb-1"),
                        dbc.Select(id="setting-hp-profile", options=[
                            {"label": "Default", "value": "Default"},
                            {"label": "Curious", "value": "Curious"},
                            {"label": "Industrious", "value": "Industrious"},
                            {"label": "Custom", "value": "Custom"}
                        ], value="Default"),

                        # --- Intrinsic Value section ---
                        html.Hr(className="my-2"),
                        html.H5("Intrinsic Value", className="mt-2 mb-1"),
                        html.Small("IV = w_v \u00b7 V + w_i \u00b7 I", className="text-muted d-block mb-1",
                                   style={"fontFamily": "monospace"}),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Value Weight"),
                                dbc.Input(id="hp-wv", type="number", step=0.1),
                                html.Small("Scales base value", className="text-muted"),
                            ]),
                            dbc.Col([
                                dbc.Label("Interest Weight"),
                                dbc.Input(id="hp-wi", type="number", step=0.1),
                                html.Small("Scales base interest", className="text-muted"),
                            ]),
                        ], className="mt-1"),

                        # --- Value Propagation section ---
                        html.Hr(className="my-2"),
                        html.H5("Value Propagation", className="mt-2 mb-1"),
                        html.Small("Retention factor per edge type (0\u20131). Higher = more value flows through.",
                                   className="text-muted d-block mb-1"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Hard Need"),
                                dbc.Input(id="hp-dh", type="number", step=0.01),
                                html.Small("Value through hard need edges", className="text-muted"),
                            ]),
                            dbc.Col([
                                dbc.Label("Soft Need"),
                                dbc.Input(id="hp-ds", type="number", step=0.01),
                                html.Small("Value through soft need edges", className="text-muted"),
                            ]),
                            dbc.Col([
                                dbc.Label("Synergy"),
                                dbc.Input(id="hp-dsyn", type="number", step=0.01),
                                html.Small("Value through Helps edges", className="text-muted"),
                            ]),
                        ], className="mt-1"),

                        # --- Perceived Cost section ---
                        html.Hr(className="my-2"),
                        html.H5("Perceived Cost", className="mt-2 mb-1"),
                        html.Small("C = 1 + w_e \u00b7 E + w_t \u00b7 T^\u03b2", className="text-muted d-block mb-1",
                                   style={"fontFamily": "monospace"}),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Effort Weight"),
                                dbc.Input(id="hp-we", type="number", step=0.1),
                                html.Small("Scales effort score", className="text-muted"),
                            ]),
                            dbc.Col([
                                dbc.Label("Time Weight"),
                                dbc.Input(id="hp-wt", type="number", step=0.1),
                                html.Small("Linearly scales time estimates", className="text-muted"),
                            ]),
                            dbc.Col([
                                dbc.Label("Time Dampener"),
                                dbc.Input(id="hp-beta", type="number", step=0.05),
                                html.Small("Sub-linear time scaling. \u03b2 < 1 means a 10h task isn't 10\u00d7 worse than 1h.",
                                           className="text-muted"),
                            ]),
                        ], className="mt-1"),

                        # --- Goal Priority Boost section ---
                        html.Hr(className="my-2"),
                        html.H5("Goal Priority Boost", className="mt-2 mb-1"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Goal Boost"),
                                dbc.Input(id="hp-goal-boost", type="number", step=0.1),
                                html.Small(
                                    "Multiplier applied to nodes in a priority goal's subtree. "
                                    "Rank #1 gets the full boost, #2 gets 66%, #3 gets 33%.",
                                    className="text-muted"),
                            ], width=4),
                        ], className="mt-1"),

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

                        # --- Time Estimates section ---
                        html.Hr(className="my-2"),
                        html.H5("Time Estimates", className="mt-2 mb-1"),
                        html.Small("Estimate productive hours.", className="text-muted d-block mb-1"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Hours per Week"),
                                dbc.Input(id="setting-hpw", type="number", min=1, step=1)
                            ]),
                            dbc.Col([
                                dbc.Label("Hours per Month"),
                                dbc.Input(id="setting-hpm", type="number", min=1, step=1)
                            ]),
                        ], className="mt-1"),
                    ], className="p-2")
                ])
            ]),

            # Save button + status
            html.Div(id="settings-save-status", className="text-success mt-2",
                     style={"fontSize": "0.85rem", "minHeight": "1.2em"}),
            dbc.Button("Save Settings", id="btn-settings-save", color="primary",
                       className="w-100 mt-3", size="lg"),
        ], style={"maxWidth": "900px", "padding": "0 24px"}),
    ], style={
        "flex": "1",
        "overflowY": "auto",
    })
