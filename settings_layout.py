"""
Layout definitions for the Settings modal.
"""

from duration_ui import bracket_label
from dash import html
import dash_bootstrap_components as dbc
from config import (
    TOOLTIP_SHOW_DELAY_MS,
    TOOLTIP_HIDE_DELAY_MS,
    SUBCONTEXT_SORT_DEFINITION,
    SUBCONTEXT_SORT_ALPHABETICAL,
    CONTEXT_SORT_DEFINITION,
    CONTEXT_SORT_ALPHABETICAL,
)

_RESTORE_ICON = "↺"  # ↺ anticlockwise open circle arrow


def _build_appearance_tab():
    return dbc.Tab(label="Appearance", tab_id="tab-appearance", children=[
        html.Div([
            # --- Node Appearance group ---
            html.H5("Node Appearance", className="mt-2 mb-1"),
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
                    html.Small("Color for Done, Blocked, and Now.", className="text-muted d-block mb-2"),
                    html.Div(id="setting-node-status-colors-container"),
                ], width=5),
            ]),

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
                    {"label": "Defined order", "value": CONTEXT_SORT_DEFINITION},
                    {"label": "Alphabetical", "value": CONTEXT_SORT_ALPHABETICAL},
                ],
                value=CONTEXT_SORT_DEFINITION,
                inline=True,
            ),
            html.Small(
                "Defined order follows the list above. Alphabetical sorts A–Z.",
                className="text-muted d-block mb-1"),

            # --- Subcontext dropdown sort order ---
            dbc.Label("Subcontext Dropdown Order", className="mt-2"),
            dbc.RadioItems(
                id="setting-subcontext-sort-mode",
                options=[
                    {"label": "Defined order", "value": SUBCONTEXT_SORT_DEFINITION},
                    {"label": "Alphabetical", "value": SUBCONTEXT_SORT_ALPHABETICAL},
                ],
                value=SUBCONTEXT_SORT_DEFINITION,
                inline=True,
            ),
            html.Small(
                "Defined order follows the list above. Alphabetical sorts A–Z.",
                className="text-muted d-block mb-1"),

            # --- Context priorities ---
            html.Hr(className="my-3"),
            html.H5("Context Priorities", className="mt-2 mb-1"),
            html.Small(
                "Choose how strongly each area should influence what appears next. "
                "1 is the normal priority; higher numbers bring an area forward, "
                "while lower numbers let it recede. Subcontexts share their "
                "parent context's priority.",
                className="text-muted d-block mb-2"),
            html.Div(id="setting-context-weights-container"),
        ], className="p-2")
    ])


def _build_scoring_tab():
    return dbc.Tab(label="Scoring", tab_id="tab-scoring", children=[
        html.Div([
            # --- Scoring Profile section ---
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.H5("Scoring Profile", className="mt-2 mb-1"),
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
                    ], value="Sage"),
                ], width=4),
            ], className="mt-1"),

            html.Hr(className="my-3"),
            # Startup analysis: timing + log on the first scoring run only
            html.H5("Startup Analysis", className="mt-2 mb-1"),
            dbc.Checklist(
                id="setting-show-scoring-perf",
                options=[{"label": "Run on startup", "value": "enabled"}],
                value=[],
                switch=True,
                className="mb-1",
                labelStyle={"fontWeight": "normal", "fontSize": "0.9rem"},
            ),
            html.Small(
                "Shows node, edge, and scoring-time totals on the Next tab and "
                "records the first scoring run after launch.",
                className="text-muted d-block mb-1",
            ),
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
                            *bracket_label("Lower", "setting-default-time-o-label", className=None),
                            dbc.Input(id="setting-default-time-o", type="number",
                                      min=0, step=1, style={"width": "128px"}),
                        ]),
                        html.Div([
                            *bracket_label("Expected", "setting-default-time-m-label", className=None),
                            dbc.Input(id="setting-default-time-m", type="number",
                                      min=0, step=1, style={"width": "128px"}),
                        ]),
                        html.Div([
                            *bracket_label("Upper", "setting-default-time-p-label", className=None),
                            dbc.Input(id="setting-default-time-p", type="number",
                                      min=0, step=1, style={"width": "128px"}),
                        ]),
                    ], className="d-flex gap-3"),
                ], width=True),
            ], className="mt-1"),

        ], className="p-2")
    ])


def _build_misc_tab():
    return dbc.Tab(label="Misc", tab_id="tab-misc", children=[
        html.Div([
            # --- Now Cap section ---
            html.H5("Maximum Now Nodes", className="mt-2 mb-1"),
            html.Small(
                "Maximum number of nodes that can be flagged Now at once.",
                className="text-muted d-block mb-2"),
            dbc.Label("Maximum Now Nodes", html_for="setting-now-node-cap",
                      className="visually-hidden"),
            dbc.Input(id="setting-now-node-cap", type="number",
                      min=1, max=50, step=1,
                      style={"width": "128px"}),

            # --- Reflection section ---
            html.Hr(className="my-2"),
            html.H5("Reflection", className="mt-2 mb-1"),
            html.Small(
                "When a node is marked Done, prompt for actuals — time, "
                "value, interest, and effort.",
                className="text-muted d-block mb-2"),
            dbc.Checklist(
                id="setting-time-calibration-enabled",
                options=[{"label": "Prompt on Completion",
                          "value": "enabled"}],
                value=["enabled"],
                switch=True,
                className="mb-1",
            ),
        ], className="p-2")
    ])


def _build_paths_tab():
    return dbc.Tab(label="Paths", tab_id="tab-paths", children=[
        html.Div([
            html.Div([
                dbc.Label("Obsidian Vault Root Path", className="mt-2"),
                dbc.Input(id="setting-obsidian-path", type="text", className="mb-2"),

                dbc.Label("Google Drive Root Path"),
                dbc.Input(id="setting-gdrive-path", type="text"),
            ], style={"width": "100%", "maxWidth": "640px"}),
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
                _build_misc_tab(),
            ]),
        ),
    ], id="settings-modal", dialog_style={"maxWidth": "900px"},
       is_open=False, scrollable=True)
