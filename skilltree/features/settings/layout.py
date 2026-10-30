"""
Layout definitions for the Settings modal.

Every page has the same anatomy: a title and a one-sentence description,
then sections, each with its own title and description, divided by hairlines.
`_titled` adds the page header and `_section` builds a section; the styles
live under `.settings-body` in theme.css.
"""

from dash import dcc, html
import dash_bootstrap_components as dbc
from skilltree.ui.kit import hint
from skilltree.store.settings import DEFAULT_TITLECASE_LINTER
from skilltree.domain.contexts import (
    SUBCONTEXT_SORT_DEFINITION, SUBCONTEXT_SORT_ALPHABETICAL, CONTEXT_SORT_DEFINITION,
    CONTEXT_SORT_ALPHABETICAL,
)
from skilltree.domain.names import (
    NAME_FORMAT_NONE, NAME_FORMAT_TITLE, NAME_FORMAT_SENTENCE,
)
from skilltree.ui import tokens
from skilltree.store.resources import get_sections
from skilltree.store import backup
from skilltree.runtime.version import __version__
from skilltree.ui.kit import (cancel_action, danger_action, hover_label,
                    panel_close_button, quiet_action, restore_button)


# One line under each page's title, saying what the page is for.
_PAGE_DESCRIPTIONS = {
    "tab-recommendations": "How Skill Tree decides what to suggest next.",
    "tab-editing": "Name formatting, time units, and what happens when you "
                   "finish a node.",
    "tab-contexts": "Contexts sort your nodes into areas of your life, and "
                    "subcontexts divide each area. Drag a row or a chip to "
                    "reorder it.",
    "tab-resources": "Links to your notes and materials: files on this computer "
                     "or web pages. Each resource gets its own field in the Node "
                     "Editor, a labeled dot on Home, and an Open item in the "
                     "right-click menu.",
    "tab-appearance": "How nodes look on every canvas.",
    "tab-data": "Updates, backups, and moving your graph to another computer.",
}

# The profiles, in menu order, with what each does to your recommendations.
# The description sits under each choice, so picking one needs no reference.
# Sage, the balanced default, comes first. The rest run from tight focus to
# loose and light, so the list reads as how much energy you have today.
_PROFILES = [
    ("Sage",
     "Balances importance, interest, effort, time, and future benefits without "
     "strongly favoring any one of them. Choose this when you want the graph to "
     "speak for itself or do not have a particular working mode in mind."),
    ("Pragmatist",
     "Stays closely focused on what you marked as valuable and on your priority "
     "goal. Interesting detours and loosely related opportunities are much less "
     "likely to displace the work you have said matters most."),
    ("Investor",
     "Looks for foundational work that unlocks later steps. This profile is more "
     "willing to recommend a substantial investment now when the graph suggests "
     "it will pay off in the future."),
    ("Creator",
     "Favors work that connects and combines different areas, especially when "
     "those areas make one another more useful. Choose this when writing, "
     "designing, or building something that draws from several domains."),
    ("Explorer",
     "Gives curiosity more influence. Interesting work, connections between "
     "different areas, and parts of your life that have not surfaced recently "
     "get a better chance—even when they are outside your current priority goal."),
    ("Glider",
     "Brings shorter, easier work forward and gives non-priority tasks more room "
     "to appear. Choose this for low-energy days, maintenance periods, or when "
     "you want useful small wins without beginning something demanding."),
]


def _section(title, description, *children, title_extra=None):
    """A titled block of related settings, with one line saying what it does.

    ``title_extra`` sits beside the title, for a restore button.
    """
    heading = html.H5(title, className="settings-section-title")
    if title_extra is not None:
        heading = html.Div([heading, title_extra], className="settings-section-head")
    return html.Section([
        heading,
        description if not isinstance(description, str)
        else html.P(description, className="settings-section-desc"),
        *children,
    ], className="settings-section")


def _field(label, control, html_for=None):
    """A small label over its control, for fields that sit in a row."""
    return html.Div([
        dbc.Label(label, html_for=html_for, className="settings-field-label"),
        control,
    ], className="settings-field")


def _switch_help(text):
    """Help under a switch, indented to the switch's label.

    The wrapper keeps the switch's font size, so its ``em`` indent matches the
    ``.form-switch`` padding; only the text inside is small.
    """
    return html.Div(html.Small(text), className="settings-switch-help")


def _build_recommendations_tab():
    return dbc.Tab(label="Recommendations", tab_id="tab-recommendations", children=[
        _section(
            "Scoring Profile",
            "Each profile weighs your ratings differently. Pick the one that "
            "fits how you are working right now.",
            dbc.RadioItems(
                id="setting-hp-profile",
                options=[{
                    "label": html.Span([
                        html.Span(name, className="settings-choice-name"),
                        html.Span(text, className="settings-choice-desc"),
                    ]),
                    "value": name,
                } for name, text in _PROFILES],
                value="Sage",
                className="settings-choice-list",
            ),
        ),
        _section(
            "Maximum Now Nodes",
            "Set the maximum number of active projects you can have at once.",
            dbc.Label("Maximum Now Nodes", html_for="setting-now-node-cap",
                      className="visually-hidden"),
            dbc.Input(id="setting-now-node-cap", type="number",
                      min=1, max=50, step=1, className="settings-input-num"),
        ),
    ])


def _build_editing_tab():
    """What happens when a node is entered or finished."""
    return dbc.Tab(label="Editing", tab_id="tab-editing", children=[
        _section(
            "Name Formatting",
            "Choose how node names and aliases are capitalized when saved. "
            "Changing this setting will not affect existing nodes.",
            dbc.RadioItems(
                id="setting-name-format-mode",
                options=[
                    {"label": "Keep as entered", "value": NAME_FORMAT_NONE},
                    {"label": "Title Case", "value": NAME_FORMAT_TITLE},
                    {"label": "Sentence case", "value": NAME_FORMAT_SENTENCE},
                ],
                value=DEFAULT_TITLECASE_LINTER['mode'],
                inline=True,
            ),
            dbc.Collapse(html.Div([
                dbc.Label("Lowercase exceptions", html_for="setting-linter-exclusions",
                          className="settings-field-label"),
                dbc.Textarea(id="setting-linter-exclusions", rows=2,
                             placeholder="e.g. a, an, the, and, or, of"),
                html.Small(
                    "Comma-separated words that stay lowercase unless they begin a name.",
                    className="settings-help",
                ),
            ], className="settings-subblock"), id="setting-titlecase-options",
               is_open=DEFAULT_TITLECASE_LINTER['mode'] == NAME_FORMAT_TITLE),
        ),

        # The hour rates convert durations entered in days, weeks, months, or
        # years, so they sit with the editor's other settings.
        _section(
            "Time Estimates",
            "The hours of work in a day, week, month, and year. An estimate "
            "of one week means that many hours of work, not seven calendar days.",
            html.Div([
                _field("Hours per day", dbc.Input(
                    id="setting-hpd", type="number", min=0.01, step="any",
                    className="settings-input-num"), "setting-hpd"),
                _field("Hours per week", dbc.Input(
                    id="setting-hpw", type="number", min=1, step="any",
                    className="settings-input-num"), "setting-hpw"),
                _field("Hours per month", dbc.Input(
                    id="setting-hpm", type="number", min=1, step="any",
                    className="settings-input-num"), "setting-hpm"),
                _field("Hours per year", dbc.Input(
                    id="setting-hpy", type="number", min=1, step="any",
                    className="settings-input-num"), "setting-hpy"),
            ], className="settings-field-row"),
            html.Div([
                dbc.Checklist(
                    id="setting-show-hour-equivalents",
                    options=[{"label": "Show hour equivalents", "value": "enabled"}],
                    value=["enabled"],
                    switch=True,
                ),
                _switch_help("Under each estimate in the Node Editor, show how "
                             "many hours it comes to."),
            ], className="settings-subblock"),
        ),

        _section(
            "Reflection",
            "When a node is marked Done, prompt for actuals — time, value, "
            "interest, and effort.",
            dbc.Checklist(
                id="setting-time-calibration-enabled",
                options=[{"label": "Prompt on Done", "value": "enabled"}],
                value=["enabled"],
                switch=True,
            ),
        ),
    ])


def _build_appearance_tab():
    return dbc.Tab(label="Appearance", tab_id="tab-appearance", children=[
        # Shapes and colors are separate callback outputs, so they stay two
        # columns; their rows share one height and line up across.
        _section(
            "Node Types",
            "The shape of each type, and its color while the node is open. "
            "A Done or Blocked node takes its status color instead.",
            html.Div([
                html.Div([
                    html.Div([
                        html.Span("Shape", className="settings-col-head"),
                        restore_button("btn-restore-shapes", "Restore default shapes"),
                    ], className="settings-col-head-row"),
                    html.Div(id="setting-node-shapes-container"),
                ]),
                html.Div([
                    html.Div([
                        html.Span("Color", className="settings-col-head"),
                        restore_button("btn-restore-type-colors", "Restore default colors"),
                    ], className="settings-col-head-row"),
                    html.Div(id="setting-node-type-colors-container"),
                ]),
            ], className="settings-appearance-grid"),
        ),
        _section(
            "Status Colors",
            "Done and Blocked replace a node's type color. Now outlines the "
            "node in its color, whatever its fill.",
            html.Div(id="setting-node-status-colors-container"),
            title_extra=restore_button("btn-restore-status-colors",
                                       "Restore default colors"),
        ),
    ])


def _build_contexts_tab():
    return dbc.Tab(label="Contexts", tab_id="tab-contexts", children=[
        html.Section([
            # Column headings. The trailing spacer stands in for each row's
            # remove button, so "Priority" sits over its input.
            html.Div([
                html.Span("Context", className="ctx-head-name"),
                html.Span("Subcontexts", className="ctx-head-subs"),
                html.Span(hover_label(
                    "Priority", "ctx-head-priority",
                    "Priority scales a context's tasks in the rankings: 1 is "
                    "normal, 2 doubles, 0.5 halves.",
                    component=html.Span), className="ctx-head-weight"),
                html.Span(className="ctx-head-btn"),
            ], className="ctx-head"),

            # The rows are rendered from context-editor-store; the adder is
            # static because a callback Input must be in the initial layout.
            html.Div([
                html.Div(id="setting-context-editor"),
                dbc.Button([html.I(className="bi bi-plus"), " Add context"],
                           id="btn-ctx-row-add", className="ctx-row-adder"),
            ], className="ctx-editor-box"),
            html.Div(id="ctx-editor-summary"),

            # Hidden input: assets/settings/context_editor_sortable.js writes the DOM
            # order here after a drag so Dash can fold it into the store.
            dcc.Input(id="ctx-editor-drag-input", type="text", value="",
                      style={"display": "none"}),
            dcc.Store(id="context-editor-store", data=None),
        ], className="settings-section"),

        _section(
            "Dropdown Order",
            "Use the order defined above, or sort alphabetically.",
            html.Div([
                dbc.Label("Contexts", className="settings-field-label"),
                dbc.RadioItems(
                    id="setting-context-sort-mode",
                    options=[
                        {"label": "Defined order", "value": CONTEXT_SORT_DEFINITION},
                        {"label": "Alphabetical", "value": CONTEXT_SORT_ALPHABETICAL},
                    ],
                    value=CONTEXT_SORT_DEFINITION,
                    inline=True,
                ),
                dbc.Label("Subcontexts", className="settings-field-label"),
                dbc.RadioItems(
                    id="setting-subcontext-sort-mode",
                    options=[
                        {"label": "Defined order", "value": SUBCONTEXT_SORT_DEFINITION},
                        {"label": "Alphabetical", "value": SUBCONTEXT_SORT_ALPHABETICAL},
                    ],
                    value=SUBCONTEXT_SORT_DEFINITION,
                    inline=True,
                ),
            ], className="settings-label-grid"),
        ),
    ])


def _build_resources_tab():
    return dbc.Tab(label="Resources", tab_id="tab-resources", children=[
        html.Section([
            # Column headings over the rows, as on the Contexts page.
            html.Div([
                html.Span("Name", className="resource-head-name"),
                html.Span(hover_label(
                    "Root folder", "resource-head-root",
                    "Links to files under this folder are saved with paths "
                    "relative to it. Web links ignore it.", component=html.Span)),
                html.Span(),
            ], className="resource-head"),
            dcc.Store(id="resource-section-settings-store", data=get_sections()),
            html.Div(id="resource-section-settings-rows"),
            # Static: a callback Input with a string id must be in the
            # initial layout, so the adder sits outside the rendered rows.
            dbc.Button([html.I(className="bi bi-plus"), " Add resource"],
                       id="btn-resource-section-add", className="resource-adder"),
            html.Small(id="resource-section-limit-msg", className="text-warning d-block mt-2"),
        ], className="settings-section"),
    ])


def _build_data_tab():
    """Application preferences, followed by data backup and transfer controls.

    These act at once, unlike the other tabs, so their buttons sit in the tab
    rather than behind the Settings save. data_callbacks.py handles them.
    """
    return dbc.Tab(label="App", tab_id="tab-data", children=[
        _section(
            "Application",
            html.P(f"Skill Tree {__version__}", id="about-version",
                   className="settings-section-desc"),
            html.Div([
                dbc.Switch(id="about-update-auto", value=True,
                           label="Check for updates at startup"),
                dcc.Store(id="about-update-sink"),
            ], id="about-updates", style={"display": "none"}),

            # The Home tab's stats readout: how big the graph is and how long
            # scoring it took. It sits with the app's own preferences because
            # it changes no recommendation.
            dbc.Checklist(
                id="setting-show-scoring-perf",
                options=[{"label": "Show graph statistics on Home",
                          "value": "enabled"}],
                value=[],
                switch=True,
            ),
            _switch_help("Node and edge counts, and how long scoring took."),
        ),

        _section(
            "Backups",
            "When automatic backup is on, Skill Tree copies your graph once a day "
            f"when it has changed, and keeps the last {backup.KEEP['daily']} copies. "
            "Turn it off to save disk space.",
            dbc.Switch(id="setting-auto-backup", value=True,
                       label="Back up automatically"),
            html.Div([
                quiet_action("Back up now", "btn-backup-now", standalone=True, size="sm",
                             className="me-2"),
                quiet_action("Open backups folder", "btn-open-backup-folder", standalone=True,
                             size="sm"),
            ], className="d-flex align-items-center settings-subblock"),
            html.Div([
                dbc.Label("Also copy each backup to", html_for="setting-backup-extra-dir",
                          className="settings-field-label"),
                dbc.Input(id="setting-backup-extra-dir", type="text",
                          className="settings-input-path",
                          placeholder="Optional: a synced folder, such as Dropbox or OneDrive"),
                html.Small("A second copy in a synced folder survives the loss of this "
                           "computer. Saved with the other settings.",
                           className="settings-help"),
            ], className="settings-subblock"),
        ),

        _section(
            "Restore",
            "Replace your current graph with a backup. Your current graph "
            "is backed up first, so a restore can itself be undone.",
            html.Div([
                html.Div(dcc.Dropdown(id="restore-backup-select", options=[],
                                      clearable=False, placeholder="Choose a backup"),
                         className="text-dark", style={"minWidth": "340px"}),
                danger_action("Restore…", "btn-restore-backup", standalone=True, size="sm",
                              className="ms-2"),
            ], className="d-flex align-items-center"),
            dbc.Collapse(html.Div([
                html.Div(id="restore-confirm-text", className="mb-2"),
                cancel_action("Cancel", "btn-restore-cancel", size="sm", className="me-2"),
                danger_action("Restore", "btn-restore-confirm", commit=True, size="sm"),
            ], className="mt-2"), id="restore-confirm", is_open=False),
        ),

        _section(
            "Export & Import",
            "An export is one file holding your whole graph and its "
            "settings. Use it to move to another computer, or to keep a "
            "copy outside Skill Tree.",
            html.Div([
                quiet_action("Export graph (.json)", "btn-export-json", standalone=True, size="sm",
                             className="me-2 data-graph-btn"),
                quiet_action("Export database file", "btn-export-db", standalone=True, size="sm"),
            ], className="d-flex align-items-center mb-2"),
            dcc.Download(id="download-export-json"),
            dcc.Download(id="download-export-db"),
            dcc.Upload(
                quiet_action("Import graph (.json)…", "btn-import-json", standalone=True, size="sm",
                             className="data-graph-btn"),
                id="upload-import", accept=".json,application/json", multiple=False),
            html.Small("Import fills an empty graph, such as a new installation.",
                       className="settings-help"),

            html.Div(id="data-status", className="mt-3"),
            dcc.Store(id="data-reload-trigger"),
            dcc.Store(id="data-reload-sink"),
        ),
    ])


def _resource_root_field(section_id, root_path):
    """A root-folder input with a trailing folder browse, as in the node editor."""
    return html.Div([
        dbc.Input(id={"type": "resource-section-root", "index": section_id},
                  value=root_path, type="text", placeholder="Choose a folder..."),
        html.Button(html.I(className="bi bi-folder2-open"),
                   id={"type": "resource-section-root-browse", "index": section_id},
                   type="button", className="btn btn-primary editor-icon-btn", **hint("Browse", label=True)),
    ], className="d-flex editor-field-group")


def _removed_resource_card(section, link_count):
    """A removed resource, held until Save so it can be undone."""
    note = (f"removed — its {link_count} link{'s' if link_count != 1 else ''} "
            "will be deleted" if link_count else "removed")
    return html.Div([
        html.Span(section["name"], className="resource-card-name-removed"),
        html.Span(note, className="resource-card-note"),
        html.Button(html.I(className="bi bi-arrow-counterclockwise"),
                   id={"type": "resource-section-undelete", "index": section["id"]},
                   type="button", className="btn btn-primary ctx-row-btn", **hint("Keep this resource", label=True)),
    ], className="resource-row resource-card-removed")


def build_resource_setting_rows(sections, link_counts=None):
    """One row per Resource section, in order, under the page's column heads.

    A row holds the name, the Root folder switch with the folder field it
    reveals, and remove. A removed
    section stays as a struck row until Save, naming the links it will take
    along.
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
            dbc.Input(id={"type": "resource-section-name", "index": section_id},
                      value=section["name"], type="text", maxLength=60,
                      placeholder="Resource name", className="settings-name-input"),
            html.Div([
                dbc.Checklist(id={"type": "resource-section-root-enabled", "index": section_id},
                              options=[{"label": html.Span("Root folder",
                                                           className="visually-hidden"),
                                        "value": "enabled"}],
                              value=["enabled"] if use_root else [], switch=True),
                dbc.Collapse(
                    _resource_root_field(section_id, root_path),
                    id={"type": "resource-section-root-options", "index": section_id},
                    is_open=use_root),
            ], className="resource-root-cell"),
            html.Button(html.I(className="bi bi-x-lg"),
                       id={"type": "resource-section-remove", "index": section_id},
                       type="button", className="btn btn-primary ctx-row-btn ctx-row-btn-danger",
                       **hint("Remove resource", label=True)),
        ], className="resource-row"))
    return cards


def _titled(tabs):
    """Open each page with its nav label as the title and one line on its purpose.

    Every page then starts the same way, whatever its first section is.
    """
    for tab in tabs:
        tab.children = [
            html.Header([
                html.H4(tab.label, className="settings-page-title"),
                html.P(_PAGE_DESCRIPTIONS[tab.tab_id], className="settings-page-desc"),
            ], className="settings-page-header"),
            *tab.children,
        ]
    return tabs


def build_settings_modal():
    """The Settings modal — opened by the gear button in the top toolbar."""
    return dbc.Modal([
        dbc.ModalHeader([
            dbc.ModalTitle("Settings"),
            html.Span(id="settings-save-error", className="text-danger ms-3",
                      style={"fontSize": tokens.FS_BASE}, role="status"),
            panel_close_button("btn-settings-close", className_extra="ms-auto"),
        ], close_button=False),
        # The tabs run down the left of a modal whose size never changes, so
        # switching sections doesn't resize it; only the section pane scrolls.
        # The layout lives under .settings-body in theme.css.
        dbc.ModalBody(
            dbc.Tabs(id="settings-modal-tabs", active_tab="tab-recommendations",
                     class_name="settings-nav", children=_titled([
                _build_recommendations_tab(),
                _build_editing_tab(),
                _build_contexts_tab(),
                _build_resources_tab(),
                _build_appearance_tab(),
                _build_data_tab(),
            ])),
            class_name="settings-body",
        ),
        # Internal completion signal used to refresh other views after commit.
        # It must never appear during the modal's closing animation.
        html.Span(id="settings-save-status", style={"display": "none"}),
        dcc.Store(id="settings-close-request"),
        dcc.Store(id="settings-close-result"),
        dcc.Store(id="settings-close-sink"),
    ], id="settings-modal", dialog_class_name="settings-dialog",
       is_open=False, centered=True, scrollable=True, backdrop="static", keyboard=False)
