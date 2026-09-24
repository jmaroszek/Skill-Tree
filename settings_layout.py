"""
Layout definitions for the Settings modal.
"""

from duration_ui import bracket_label, unit_select
from dash import dcc, html
import dash_bootstrap_components as dbc
from config import (
    SUBCONTEXT_SORT_DEFINITION,
    SUBCONTEXT_SORT_ALPHABETICAL,
    CONTEXT_SORT_DEFINITION,
    CONTEXT_SORT_ALPHABETICAL,
    NAME_FORMAT_NONE,
    NAME_FORMAT_TITLE,
    NAME_FORMAT_SENTENCE,
)
import style_tokens as tokens
from ui_kit import Tooltip, info_button, restore_button



def _build_appearance_tab():
    return dbc.Tab(label="Appearance", tab_id="tab-appearance", children=[
        html.Div([
            # --- Node Appearance group ---
            html.H5("Node Appearance", className="mt-2 mb-1"),
            dbc.Row([
                dbc.Col([
                    html.Div([
                        dbc.Label("Shapes", className="mb-0"),
                        restore_button("btn-restore-shapes"),
                    ], className="d-flex align-items-center mt-2 mb-1"),
                    html.Small("Shape for each node type.", className="text-muted d-block mb-2"),
                    html.Div(id="setting-node-shapes-container"),
                ], width=4),
                dbc.Col([
                    html.Div([
                        dbc.Label("Type Colors", className="mb-0"),
                        restore_button("btn-restore-type-colors"),
                    ], className="d-flex align-items-center mt-2 mb-1"),
                    html.Small("Open color for each node type.", className="text-muted d-block mb-2"),
                    html.Div(id="setting-node-type-colors-container"),
                ], width=3),
                dbc.Col([
                    html.Div([
                        dbc.Label("Status Colors", className="mb-0"),
                        restore_button("btn-restore-status-colors"),
                    ], className="d-flex align-items-center mt-2 mb-1"),
                    html.Small("Color for Done, Blocked, and Now.", className="text-muted d-block mb-2"),
                    html.Div(id="setting-node-status-colors-container"),
                ], width=5),
            ]),

            # --- Name Formatting group ---
            html.Hr(className="my-3"),
            html.H5("Name Formatting", className="mt-2 mb-1"),
            html.Small(
                "Choose how node names and aliases are capitalized when saved. "
                "Changing this setting will not affect existing nodes.",
                className="text-muted d-block mb-2",
            ),
            dbc.RadioItems(
                id="setting-name-format-mode",
                options=[
                    {"label": "Keep as entered", "value": NAME_FORMAT_NONE},
                    {"label": "Title Case", "value": NAME_FORMAT_TITLE},
                    {"label": "Sentence case", "value": NAME_FORMAT_SENTENCE},
                ],
                value=NAME_FORMAT_TITLE,
                inline=True,
                className="mb-2",
            ),
            dbc.Collapse([
                dbc.Label("Lowercase exceptions", className="mt-1"),
                dbc.Textarea(id="setting-linter-exclusions", rows=2,
                             placeholder="e.g. a, an, the, and, or, of"),
                html.Small(
                    "Comma-separated words that stay lowercase unless they begin a name.",
                    className="text-muted d-block mb-1",
                ),
            ], id="setting-titlecase-options", is_open=True),

        ], className="p-2")
    ])


def _build_contexts_tab():
    return dbc.Tab(label="Contexts", tab_id="tab-contexts", children=[
        html.Div([
            # --- Context definitions ---
            html.H5("Definitions", className="mt-2 mb-1"),
            html.Small(
                "Drag to reorder. Priority 1 is normal; higher brings an "
                "area forward in what appears next, lower lets it recede.",
                className="text-muted d-block mb-2"),

            # Column headings. The trailing spacer stands in for each row's
            # remove button, so "Priority" sits over its input.
            html.Div([
                html.Span("Context", className="ctx-head-name"),
                html.Span("Subcontexts", className="ctx-head-subs"),
                html.Span("Priority", className="ctx-head-weight"),
                html.Span(className="ctx-head-btn"),
            ], className="ctx-head"),

            # The rows are rendered from context-editor-store; the adder is
            # static because a callback Input must be in the initial layout.
            html.Div([
                html.Div(id="setting-context-editor"),
                dbc.Button([html.I(className="bi bi-plus"), " Add context"],
                           id="btn-ctx-row-add", className="ctx-row-adder"),
            ], className="ctx-editor-box"),
            html.Div(id="ctx-editor-summary", className="mt-1"),

            # Hidden input: assets/context_editor_sortable.js writes the DOM
            # order here after a drag so Dash can fold it into the store.
            dcc.Input(id="ctx-editor-drag-input", type="text", value="",
                      style={"display": "none"}),
            dcc.Store(id="context-editor-store", data=None),

            # --- Dropdown order ---
            html.Hr(className="my-3"),
            html.H5("Dropdown Order", className="mt-2 mb-1"),
            html.Small(
                "Use the order defined above, or sort alphabetically.",
                className="text-muted d-block mb-2"),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Contexts"),
                    dbc.RadioItems(
                        id="setting-context-sort-mode",
                        options=[
                            {"label": "Defined order", "value": CONTEXT_SORT_DEFINITION},
                            {"label": "Alphabetical", "value": CONTEXT_SORT_ALPHABETICAL},
                        ],
                        value=CONTEXT_SORT_DEFINITION,
                        inline=True,
                    ),
                ], width=6),
                dbc.Col([
                    dbc.Label("Subcontexts"),
                    dbc.RadioItems(
                        id="setting-subcontext-sort-mode",
                        options=[
                            {"label": "Defined order", "value": SUBCONTEXT_SORT_DEFINITION},
                            {"label": "Alphabetical", "value": SUBCONTEXT_SORT_ALPHABETICAL},
                        ],
                        value=SUBCONTEXT_SORT_DEFINITION,
                        inline=True,
                    ),
                ], width=6),
            ]),
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
                        info_button("btn-hp-profile-info"),
                        dbc.Popover(
                            [
                                dbc.PopoverHeader("Scoring Profiles"),
                                dbc.PopoverBody(
                                    dbc.Table(
                                        [
                                            html.Thead(html.Tr([
                                                html.Th("Profile"),
                                                html.Th("How it changes your recommendations"),
                                            ])),
                                            html.Tbody([
                                                html.Tr([
                                                    html.Td(html.Strong("Sage")),
                                                    html.Td(
                                                        "Balances importance, interest, effort, time, and future benefits "
                                                        "without strongly favoring any one of them. Choose this when you "
                                                        "want the graph to speak for itself or do not have a particular "
                                                        "working mode in mind."
                                                    ),
                                                ]),
                                                html.Tr([
                                                    html.Td(html.Strong("Explorer")),
                                                    html.Td(
                                                        "Gives curiosity more influence. Interesting work, connections "
                                                        "between different areas, and parts of your life that have not "
                                                        "surfaced recently get a better chance—even when they are outside "
                                                        "your current priority goal."
                                                    ),
                                                ]),
                                                html.Tr([
                                                    html.Td(html.Strong("Compounder")),
                                                    html.Td(
                                                        "Looks for foundational work that will unlock many later steps. "
                                                        "It is more willing to recommend a substantial investment now "
                                                        "when the graph suggests it will pay off repeatedly in the future."
                                                    ),
                                                ]),
                                                html.Tr([
                                                    html.Td(html.Strong("Pragmatist")),
                                                    html.Td(
                                                        "Stays closely focused on what you marked as valuable and on your "
                                                        "priority goal. Interesting detours and loosely related opportunities "
                                                        "are much less likely to displace the work you have said matters most."
                                                    ),
                                                ]),
                                                html.Tr([
                                                    html.Td(html.Strong("Creator")),
                                                    html.Td(
                                                        "Favors work that connects and combines different areas, especially "
                                                        "when those areas make one another more useful. Choose this when "
                                                        "writing, designing, or building something that draws from several domains."
                                                    ),
                                                ]),
                                                html.Tr([
                                                    html.Td(html.Strong("Glider")),
                                                    html.Td(
                                                        "Brings shorter, easier work forward and gives non-priority tasks "
                                                        "more room to appear. Choose this for low-energy days, maintenance "
                                                        "periods, or when you want useful small wins without beginning "
                                                        "something demanding."
                                                    ),
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
            # The Home tab's stats readout: how big the graph is and how long
            # scoring it took. Named for what you get rather than for when it
            # runs -- "Startup Analysis" described the timing and left the
            # content to be guessed at.
            html.H5("Graph Statistics", className="mt-2 mb-1"),
            html.Small(
                "Shows node and edge counts, and how long scoring took, "
                "on the Home tab.",
                className="text-muted d-block mb-2",
            ),
            dbc.Checklist(
                id="setting-show-scoring-perf",
                options=[{"label": "Run on startup", "value": "enabled"}],
                value=[],
                switch=True,
                className="mb-1",
                labelStyle={"fontWeight": "normal", "fontSize": tokens.FS_MD},
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
                    dbc.Label("Hours per Day"),
                    dbc.Input(id="setting-hpd", type="number", min=0.01, step="any",
                              className="mb-2", style={"width": "128px"}),
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
                    unit_select("setting-default-time-unit", className="mb-2"),
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
                "Set the maximum number of active projects you can have at once.",
                className="text-muted d-block mb-2",
            ),
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


def _build_integrations_tab():
    return dbc.Tab(label="Integrations", tab_id="tab-integrations", children=[
        html.Div([
            html.Div([
                html.H5("Obsidian", className="mt-2 mb-1"),
                dbc.Checklist(id="setting-obsidian-enabled", switch=True,
                              options=[{"label": "Show Obsidian resources", "value": "enabled"}],
                              value=[], className="mb-1"),
                dbc.Label("Vault path", html_for="setting-obsidian-path"),
                dbc.Input(id="setting-obsidian-path", type="text", className="mb-2"),
                html.Small("A vault path is needed to open Obsidian notes.",
                           className="text-muted d-block mb-2"),
                html.Hr(className="my-2"),
                html.H5("Google Drive", className="mt-2 mb-1"),
                dbc.Checklist(id="setting-gdrive-enabled", switch=True,
                              options=[{"label": "Show Google Drive resources", "value": "enabled"}],
                              value=[], className="mb-1"),
                dbc.Label("Mounted Drive root path (optional)", html_for="setting-gdrive-path"),
                dbc.Input(id="setting-gdrive-path", type="text", className="mb-2"),
                html.Small("Google Drive resources accept a URL or a local path. "
                           "A root path helps browse mounted files and resolve relative paths.",
                           className="text-muted d-block"),
            ], style={"width": "100%", "maxWidth": "640px"}),
        ], className="p-2")
    ])


def build_settings_modal():
    """The Settings modal — opened by the gear button in the top toolbar."""
    save_group = html.Div([
        dbc.Button(html.I(className="bi bi-floppy2-fill"), id="btn-settings-save",
                   color="primary", size="sm",
                   style={"fontSize": tokens.FS_LG, "lineHeight": "1", "padding": "4px 7px"}),
        html.Span(id="settings-save-status", className="text-success ms-2",
                  style={"fontSize": tokens.FS_BASE}),
        Tooltip("Save settings", target="btn-settings-save", placement="bottom"),
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
                _build_integrations_tab(),
                _build_misc_tab(),
            ]),
        ),
    ], id="settings-modal", dialog_style={"maxWidth": "900px"},
       is_open=False, centered=True, scrollable=True)
