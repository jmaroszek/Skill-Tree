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
from resource_links import get_sections
import about
import backup
from app_paths import get_data_dir, get_log_dir
from version import __version__
from ui_kit import (Tooltip, cancel_action, danger_action, info_button,
                    primary_action, restore_button)



def _build_recommendations_tab():
    return dbc.Tab(label="Recommendations", tab_id="tab-recommendations", children=[
        html.Div([
            # --- Scoring Profile section ---
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.H5("Scoring Profile", className="mb-0"),
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
                    ], className="d-flex align-items-center mt-2 mb-1"),
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

            # --- Now Cap section ---
            html.H5("Maximum Now Nodes", className="mt-4 mb-1"),
            html.Small(
                "Set the maximum number of active projects you can have at once.",
                className="text-muted d-block mb-2",
            ),
            dbc.Label("Maximum Now Nodes", html_for="setting-now-node-cap",
                      className="visually-hidden"),
            dbc.Input(id="setting-now-node-cap", type="number",
                      min=1, max=50, step=1,
                      style={"width": "128px"}),

            # The Home tab's stats readout: how big the graph is and how long
            # scoring it took. Named for what you get rather than for when it
            # runs -- "Startup Analysis" described the timing and left the
            # content to be guessed at.
            html.H5("Graph Statistics", className="mt-4 mb-1"),
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


def _build_editing_tab():
    """What happens when a node is entered or finished."""
    return dbc.Tab(label="Editing", tab_id="tab-editing", children=[
        html.Div([
            # --- Name Formatting section ---
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

            # --- Time Estimates section ---
            # The hour rates convert durations entered in days, weeks,
            # months, or years, so they sit with the new-node defaults.
            html.Hr(className="my-3"),
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

            # --- Reflection section ---
            html.Hr(className="my-3"),
            html.H5("Reflection", className="mt-2 mb-1"),
            html.Small(
                "When a node is marked Done, prompt for actuals — time, "
                "value, interest, and effort.",
                className="text-muted d-block mb-2"),
            dbc.Checklist(
                id="setting-time-calibration-enabled",
                options=[{"label": "Prompt on Done",
                          "value": "enabled"}],
                value=["enabled"],
                switch=True,
                className="mb-1",
            ),
        ], className="p-2")
    ])


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
        ], className="p-2")
    ])


def _build_contexts_tab():
    return dbc.Tab(label="Contexts", tab_id="tab-contexts", children=[
        html.Div([
            # --- Context definitions ---
            html.H5("Definitions", className="mt-2 mb-1"),
            html.Small(
                "Drag to reorder. Priority scales a context's tasks in the "
                "rankings: 1 is normal, 2 doubles, 0.5 halves.",
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
            # No rule here: the outlined row editor already closes the
            # section above, so space alone separates the two.
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


def _build_resources_tab():
    return dbc.Tab(label="Resources", tab_id="tab-resources", children=[
        html.Div([
            html.Div([
                html.Small("Each resource gets its own field in the Node Editor, a labeled dot on Home, and an Open item in the right-click menu.",
                           className="text-muted d-block mt-2 mb-3"),
                dcc.Store(id="resource-section-settings-store", data=get_sections()),
                html.Div(id="resource-section-settings-rows"),
                # Static: a callback Input with a string id must be in the
                # initial layout, so the adder sits outside the rendered rows.
                dbc.Button([html.I(className="bi bi-plus"), " Add resource"],
                           id="btn-resource-section-add", className="resource-adder"),
                html.Small(id="resource-section-limit-msg", className="text-warning d-block mt-2"),
            ], style={"width": "100%", "maxWidth": "640px"}),
        ], className="p-2")
    ])


def _build_about_tab():
    """The version, where the data lives, and how to get help.

    about_callbacks.py fills in the diagnostics and the report link when the
    tab opens. The Updates block belongs to the desktop shell and stays hidden
    in a browser (the clientside callbacks in about_callbacks.py).
    """
    return dbc.Tab(label="About", tab_id="tab-about", children=[
        html.Div([
            html.H5("Skill Tree", className="mt-2 mb-1"),
            html.Div(f"Version {__version__}", id="about-version", className="mb-3"),

            # --- Where things are ---
            html.H5("Your data", className="mt-2 mb-1"),
            html.Small(["Your graph is kept on this computer, in ",
                        html.Code(str(get_data_dir())),
                        ", and never leaves it."],
                       className="text-muted d-block mb-2"),
            html.Div([
                cancel_action("Open data folder", "btn-open-data-folder", size="sm",
                              className="me-2"),
                cancel_action("Open logs folder", "btn-open-log-folder", size="sm"),
            ], className="d-flex align-items-center mb-1"),
            html.Small(["Logs are in ", html.Code(str(get_log_dir())), "."],
                       className="text-muted d-block mb-2"),
            html.Div(id="about-status", className="mb-2"),

            # --- Getting help ---
            html.Hr(className="my-3"),
            html.H5("Report a problem", className="mt-2 mb-1"),
            html.Small("The report form on GitHub opens with these details filled in. "
                       "Folders under your home folder show as ~, and your graph "
                       "itself is never included.",
                       className="text-muted d-block mb-2"),
            html.Div([
                html.Pre(id="about-diagnostics", className="small mb-0 flex-grow-1",
                         style={"whiteSpace": "pre-wrap"}),
                dcc.Clipboard(id="about-copy-diagnostics", target_id="about-diagnostics",
                              title="Copy diagnostics", className="ms-2"),
            ], className="d-flex align-items-start mb-2"),
            html.A("Report a problem on GitHub", id="about-report-link",
                   href=about.ISSUES_NEW_URL, target="_blank", rel="noopener"),

            # --- Updates (the desktop app only) ---
            html.Div([
                html.Hr(className="my-3"),
                html.H5("Updates", className="mt-2 mb-1"),
                dbc.Switch(id="about-update-auto", value=True,
                           label="Check for a new version when Skill Tree starts"),
                html.Small("The check asks GitHub for the newest release and sends "
                           "nothing about you or your graph.",
                           className="text-muted d-block mb-2"),
                cancel_action("Check now", "btn-check-updates", size="sm"),
                html.Div(id="about-update-status", className="mt-2"),
                html.A("Open the release page", id="about-update-link", target="_blank",
                       rel="noopener", style={"display": "none"}),
                dcc.Store(id="about-update-sink"),
            ], id="about-updates", style={"display": "none"}),

            # --- Where it comes from ---
            html.Hr(className="my-3"),
            html.Small(["Skill Tree is open source. Its code, license, release notes "
                        "and downloads are at ",
                        html.A("github.com/jmaroszek/Skill-Tree", href=about.REPO_URL,
                               target="_blank", rel="noopener"), "."],
                       className="text-muted d-block mb-2"),
            # The licenses of what it's built on. Only a build has the file.
            html.Div([
                cancel_action("Third-party notices", "btn-open-notices", size="sm"),
                html.Div(id="about-notices-status", className="mt-2"),
            ], id="about-notices",
               style={} if about.notices_path() else {"display": "none"}),
        ], style={"width": "100%", "maxWidth": "640px"}),
    ])


def _build_data_tab():
    """Backups, restore, export and import: everything about the data file.

    These act at once, unlike the other tabs, so their buttons sit in the tab
    rather than behind the Settings save. data_callbacks.py handles them.
    """
    return dbc.Tab(label="Data", tab_id="tab-data", children=[
        html.Div([
            # --- Backups ---
            html.H5("Backups", className="mt-2 mb-1"),
            html.Small([
                "Skill Tree copies your graph once a day when it has changed, "
                f"and keeps the last {backup.KEEP['daily']} copies in ",
                html.Code(str(backup.backup_dir())), "."],
                className="text-muted d-block mb-2"),
            html.Div([
                primary_action("Back up now", "btn-backup-now", size="sm", className="me-2"),
                cancel_action("Open backups folder", "btn-open-backup-folder", size="sm"),
            ], className="d-flex align-items-center mb-3"),
            dbc.Label("Also copy each backup to"),
            dbc.Input(id="setting-backup-extra-dir", type="text",
                      placeholder="Optional: a synced folder, such as Dropbox or OneDrive"),
            html.Small("A second copy in a synced folder survives the loss of this "
                       "computer. Saved with the other settings.",
                       className="text-muted d-block mt-1"),

            # --- Restore ---
            html.Hr(className="my-3"),
            html.H5("Restore", className="mt-2 mb-1"),
            html.Small("Replace your current graph with a backup. Your current graph "
                       "is backed up first, so a restore can itself be undone.",
                       className="text-muted d-block mb-2"),
            html.Div([
                html.Div(dcc.Dropdown(id="restore-backup-select", options=[],
                                      clearable=False, placeholder="Choose a backup"),
                         className="text-dark", style={"minWidth": "340px"}),
                danger_action("Restore…", "btn-restore-backup", size="sm", className="ms-2"),
            ], className="d-flex align-items-center"),
            dbc.Collapse(html.Div([
                html.Div(id="restore-confirm-text", className="mb-2"),
                cancel_action("Cancel", "btn-restore-cancel", size="sm", className="me-2"),
                danger_action("Restore", "btn-restore-confirm", size="sm"),
            ], className="mt-2"), id="restore-confirm", is_open=False),

            # --- Export & import ---
            html.Hr(className="my-3"),
            html.H5("Export & Import", className="mt-2 mb-1"),
            html.Small("An export is one file holding your whole graph and its "
                       "settings. Use it to move to another computer, or to keep a "
                       "copy outside Skill Tree.",
                       className="text-muted d-block mb-2"),
            html.Div([
                primary_action("Export graph (.json)", "btn-export-json", size="sm",
                               className="me-2"),
                cancel_action("Export database file", "btn-export-db", size="sm"),
            ], className="d-flex align-items-center mb-2"),
            dcc.Download(id="download-export-json"),
            dcc.Download(id="download-export-db"),
            dcc.Upload(
                cancel_action("Import graph (.json)…", "btn-import-json", size="sm"),
                id="upload-import", accept=".json,application/json", multiple=False),
            html.Small("Import fills an empty graph, such as a new installation.",
                       className="text-muted d-block mt-1"),

            html.Div(id="data-status", className="mt-3"),
            dcc.Store(id="data-reload-trigger"),
            dcc.Store(id="data-reload-sink"),
        ], className="p-2", style={"width": "100%", "maxWidth": "640px"}),
    ])


def _resource_root_field(section_id, root_path):
    """A root-folder input with a trailing folder browse, as in the node editor."""
    return html.Div([
        dbc.Input(id={"type": "resource-section-root", "index": section_id},
                  value=root_path, type="text", placeholder="Choose a folder..."),
        dbc.Button(html.I(className="bi bi-folder2-open"),
                   id={"type": "resource-section-root-browse", "index": section_id},
                   title="Browse", className="editor-icon-btn"),
    ], className="d-flex editor-field-group")


def _removed_resource_card(section, link_count):
    """A removed resource, held until Save so it can be undone."""
    note = (f"removed — its {link_count} link{'s' if link_count != 1 else ''} "
            "will be deleted" if link_count else "removed")
    return html.Div([
        html.Span(section["name"], className="resource-card-name-removed"),
        html.Span(note, className="resource-card-note"),
        dbc.Button(html.I(className="bi bi-arrow-counterclockwise"),
                   id={"type": "resource-section-undelete", "index": section["id"]},
                   title="Keep this resource", className="editor-icon-btn"),
    ], className="resource-card resource-card-removed")


def build_resource_setting_rows(sections, link_counts=None):
    """One outlined card per Resource section, in order.

    A card holds the name (with its remove) and two switches on one line:
    Root folder, which reveals the folder field, and Open in Obsidian, which
    sends the section's notes to the Obsidian app instead of the default one.
    A removed section stays as a struck card until Save, naming the links it
    will take along.
    """
    link_counts = link_counts or {}
    cards = []
    for section in sections:
        section_id = section["id"]
        if section.get("deleted"):
            cards.append(_removed_resource_card(section, link_counts.get(section_id, 0)))
            continue
        root_path = section.get("root_path") or ""
        use_root = section.get("use_root", bool(root_path))
        cards.append(html.Div([
            html.Div([
                dbc.Input(id={"type": "resource-section-name", "index": section_id},
                          value=section["name"], type="text", maxLength=60,
                          placeholder="Resource name"),
                dbc.Button(html.I(className="bi bi-x-lg"),
                           id={"type": "resource-section-remove", "index": section_id},
                           title="Remove", className="editor-icon-btn editor-icon-btn-danger"),
            ], className="d-flex editor-field-group"),
            html.Div([
                dbc.Checklist(id={"type": "resource-section-root-enabled", "index": section_id},
                              options=[{"label": "Root folder", "value": "enabled"}],
                              value=["enabled"] if use_root else [], switch=True),
                dbc.Checklist(id={"type": "resource-section-obsidian", "index": section_id},
                              options=[{"label": "Open in Obsidian", "value": "obsidian"}],
                              value=["obsidian"] if section.get("kind") == "obsidian" else [],
                              switch=True),
            ], className="resource-card-switches"),
            dbc.Collapse([
                _resource_root_field(section_id, root_path),
                html.Small("Files under this folder are saved with relative paths.",
                           className="text-muted d-block mt-1"),
            ], id={"type": "resource-section-root-options", "index": section_id},
               is_open=use_root),
        ], className="resource-card"))
    return cards


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
            dbc.Tabs(id="settings-modal-tabs", active_tab="tab-recommendations", children=[
                _build_recommendations_tab(),
                _build_contexts_tab(),
                _build_editing_tab(),
                _build_appearance_tab(),
                _build_resources_tab(),
                _build_data_tab(),
                _build_about_tab(),
            ]),
        ),
    ], id="settings-modal", dialog_style={"maxWidth": "900px"},
       is_open=False, centered=True, scrollable=True)
