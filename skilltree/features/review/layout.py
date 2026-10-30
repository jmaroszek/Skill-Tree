"""Layout for the Reflection modal.

The hub is the entry point for the Reflection feature. The journal icon in the
top toolbar opens this modal; the user picks an action (start the focused
queue, browse history, manage excluded nodes) from within.

Two tabs:
  - Reflect         — the queue (count of un-reflected completed nodes + a
                      launch button), then the "Don't ask again" list under it
  - History         — searchable/filterable table of already-reflected nodes

All container IDs (`hub-pending-count`, `hub-history-table-container`,
`hub-excluded-list`, the filter inputs) must exist at initial render — Dash
does not suppress callback exceptions, so any State or Input that references
them needs the component present from the first paint.
"""

from dash import dcc, html
import dash_bootstrap_components as dbc

from skilltree.ui.kit import hint
from skilltree.ui.components.context_picker import build_multi_context_picker
from skilltree.ui.kit import Tooltip
from skilltree.ui.kit import node_type_color
from skilltree.features.review.values import PROJECT_NOTES_PLACEHOLDER
from skilltree.store import settings
from skilltree.ui import tokens
from skilltree.ui.components.duration import unit_select
from skilltree.ui.components.duration import work_time_tooltip
from skilltree.ui.components.ratings_table import (
    HEADER_CELL_STYLE,
)
from skilltree.ui.components.ratings_table import build_popup_table_rows
from skilltree.ui.kit import edit_button
from skilltree.ui.kit import info_button
from skilltree.ui.kit import panel_close_button


# History sort criteria, in dropdown order. "Completed" has no column, so the
# dropdown is the only way back to the default order once a header is clicked.
HISTORY_SORT_CRITERIA = {
    "completed": "Completed",
    "name": "Name",
    "estimated": "Est Time",
    "actual": "Actual",
    "delta_time": "Δ Time",
    "delta_ratings": "Δ Ratings",
}
# Direction each criterion starts in when chosen: the order you most likely want.
HISTORY_SORT_DEFAULT_DIRECTION = {
    "completed": "desc",
    "name": "asc",
    "estimated": "asc",
    "actual": "asc",
    "delta_time": "desc",
    "delta_ratings": "desc",
}
# The direction button's tooltip names the order in the criterion's own terms,
# since "ascending Δ Time" says nothing about what comes first.
HISTORY_SORT_DIRECTION_LABELS = {
    "completed": {"desc": "Newest first", "asc": "Oldest first"},
    "name": {"asc": "A to Z", "desc": "Z to A"},
    "estimated": {"asc": "Shortest estimate first", "desc": "Longest estimate first"},
    "actual": {"asc": "Least time first", "desc": "Most time first"},
    "delta_time": {"desc": "Most over estimate first", "asc": "Most under estimate first"},
    "delta_ratings": {"desc": "Biggest rating change first",
                      "asc": "Smallest rating change first"},
}
HISTORY_SORT_DEFAULT = {"key": "completed", "direction": "desc"}


def history_sort_key_class(sort):
    """The default order reads like the row's placeholders; a chosen one
    reads as a value, so a changed order stands out."""
    return "is-default" if sort == HISTORY_SORT_DEFAULT else ""


def history_sort_direction_icon(direction):
    return "bi bi-sort-up" if direction == "asc" else "bi bi-sort-down"


def _build_pager(prefix):
    """ "Showing 20 of 73 reflections · show more" between two rules.

    Styled as the Events list's triggered divider: small gray text, the dot as
    plain text in the sentence, and a soft action that brightens on hover.
    """
    return html.Div([
        html.Span(className="events-triggered-rule"),
        html.Span([
            html.Span(id=f"{prefix}-page-status"),
            html.Span([
                " · ",
                html.Button("show more", id=f"{prefix}-show-more",
                            type="button", className="events-triggered-toggle"),
            ], id=f"{prefix}-more-wrap"),
        ]),
        html.Span(className="events-triggered-rule"),
    ], id=f"{prefix}-pager", className="events-triggered-divider review-hub-pager")


# The queue card names this many pending nodes, then "+N more".
PENDING_PREVIEW_LIMIT = 8


def _build_reflect_tab():
    """The queue and the nodes excluded from it, one above the other.

    They are two halves of one question (which completed nodes get reflected
    on), and each alone is too short to fill a fixed-size modal. The queue is
    the reason to open the tab, so it is a card led by its count; Excluded is
    rarely needed, so it sits quietly at the bottom.
    """
    return dbc.Tab(label="Reflect", tab_id="tab-review-reflect", children=[
        html.Div([
            html.Section([
                html.Div([
                    html.Div([
                        html.Div(id="hub-pending-count",
                                 className="reflect-queue-count", children="0"),
                        html.Div(id="hub-pending-label",
                                 className="reflect-queue-label",
                                 children="completed nodes waiting"),
                    ]),
                    dbc.Button("Start Reflection", id="btn-hub-pending-launch",
                               color="primary"),
                ], className="reflect-queue-head"),
                html.P(
                    "Walk through completed nodes that haven't been "
                    "reflected on yet.",
                    className="reflect-caption mb-0",
                ),
                html.Ul(id="hub-pending-list", className="reflect-node-list"),
            ], id="hub-pending-summary", className="reflect-queue-card"),
            html.Section([
                html.I(className="bi bi-check-circle reflect-empty-icon",
                       **{"aria-hidden": "true"}),
                html.Div("All caught up", className="reflect-empty-title"),
                html.P("Nodes you complete will show up here.",
                       className="reflect-caption mb-0"),
            ], id="hub-pending-empty", className="reflect-queue-card reflect-queue-empty",
                style={"display": "none"}),
            # Collapsed behind one line, the Events list's triggered divider,
            # so the queue leads however many nodes pile up here.
            html.Section([
                html.Div([
                    html.Span(className="events-triggered-rule"),
                    html.Span([
                        html.Span(id="hub-excluded-summary"),
                        " · ",
                        html.Button("show", id="hub-excluded-toggle", type="button",
                                    className="events-triggered-toggle",
                                    **{"aria-expanded": "false",
                                       "aria-controls": "hub-excluded-body"}),
                    ]),
                    html.Span(className="events-triggered-rule"),
                ], className="events-triggered-divider"),
                html.Div([
                    html.P(
                        "Marked \"Don't ask again\" during reflection. "
                        "Restore one to queue it again.",
                        className="reflect-caption mb-2",
                    ),
                    dcc.Store(id="hub-excluded-visible-count", data=20),
                    html.Div(id="hub-excluded-list"),
                    _build_pager("hub-excluded"),
                ], id="hub-excluded-body", style={"display": "none"}),
            ], id="hub-excluded-section", className="reflect-excluded",
                style={"display": "none"}),
        ], className="reflect-pane")
    ])


def _type_dot(node_type):
    return html.Span(className="reflect-type-dot", **hint(node_type),
                     style={"backgroundColor": node_type_color(node_type)})


def build_pending_preview(nodes, limit=PENDING_PREVIEW_LIMIT):
    """The queue card's list: the first few pending nodes, each with its
    type's dot, then how many more there are. `nodes` arrive in queue order."""
    rows = [html.Li([_type_dot(node.type),
                     html.Span(node.name, className="text-truncate")],
                    className="reflect-node-row")
            for node in nodes[:limit]]
    if len(nodes) > limit:
        rows.append(html.Li(f"+{len(nodes) - limit} more",
                            className="reflect-node-row reflect-node-more"))
    return rows


def pending_label(count):
    return "completed node waiting" if count == 1 else "completed nodes waiting"


def excluded_summary(count):
    return f"{count} excluded {'node' if count == 1 else 'nodes'}"


def _build_history_tab():
    # The filters and table scroll; the "show more" pager stays below them, so
    # it is reachable however much of the list fits on screen.
    return dbc.Tab(label="History", tab_id="tab-review-history", children=[
        html.Div([
            html.Div([
                # No caption. "Already-reflected nodes" only restates the tab's own
                # name, and the pencil carries its own tooltip. The sibling tabs
                # keep theirs because they say something their names do not: the
                # queue identifies which completed nodes it handles, and Excluded
                # says what can be restored.
                #
                # Search takes the width: a name is long and you type into it,
                # while the context picker shows at most two contexts and a "+N".
                #
                # Sort is a visible dropdown rather than the sidebars' menu
                # button: the table's default order (Completed) has no column
                # header to click back to, so the current criterion must stay on
                # screen. Direction is its own button; column headers still sort.
                dbc.Row([
                    dbc.Col(
                        dbc.Input(id="hub-history-search", type="search",
                                  placeholder="Search by name...",
                                  style={"width": "100%"}),
                        width=6,
                    ),
                    dbc.Col(
                        build_multi_context_picker(
                            "hub-history-context-picker",
                            "hub-history-filter-context",
                            "hub-history-filter-subcontext",
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        html.Div([
                            html.Label("Sort by", htmlFor="hub-history-sort-key",
                                       className="visually-hidden"),
                            dbc.Select(
                                id="hub-history-sort-key",
                                options=[{"label": label, "value": key}
                                         for key, label in HISTORY_SORT_CRITERIA.items()],
                                value=HISTORY_SORT_DEFAULT["key"],
                                className=history_sort_key_class(HISTORY_SORT_DEFAULT),
                            ),
                            html.Button(
                                html.I(id="hub-history-sort-direction-icon",
                                       className=history_sort_direction_icon(
                                           HISTORY_SORT_DEFAULT["direction"]),
                                       **{"aria-hidden": "true"}),
                                id="hub-history-sort-direction",
                                type="button",
                                className="btn btn-secondary details-header-btn "
                                          "review-history-direction-btn",
                                **{"aria-label": "Reverse sort order"},
                            ),
                            Tooltip(
                                HISTORY_SORT_DIRECTION_LABELS["completed"]["desc"],
                                id="hub-history-sort-direction-tooltip",
                                target="hub-history-sort-direction",
                                placement="top",
                            ),
                        ], className="review-history-sort-controls"),
                        width=3,
                    ),
                ], className="mb-2 g-2"),
                dcc.Store(id="hub-history-visible-count", data=20),
                dcc.Store(id="hub-history-sort", data=dict(HISTORY_SORT_DEFAULT)),
                html.Div(id="hub-history-table-container",
                         className="review-history-table-wrap"),
            ], className="review-history-scroll"),
            _build_pager("hub-history"),
        ], className="review-history-pane")
    ])


def build_review_hub_modal():
    """The Reflection modal — opened by the journal button in the toolbar."""
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Reflection")),
        dbc.ModalBody(
            dbc.Tabs(id="review-hub-tabs", active_tab="tab-review-reflect",
                     children=[
                         _build_reflect_tab(),
                         _build_history_tab(),
                     ]),
            class_name="review-hub-body",
        ),
    ], id="modal-review-hub", dialog_class_name="review-hub-dialog",
       is_open=False, centered=True, scrollable=True)


def build_calibration_dismissed_view(dismissed, limit=None):
    """List of nodes marked "Don't ask again" during a calibration review,
    each row with a Restore button (pattern-matched id
    `{'type': 'calibration-restore', 'index': <name>}`). Returns a Dash
    component tree for the Reflect tab's Excluded section. Nodes arrive
    sorted by name."""
    if not dismissed:
        return (html.Small("No nodes excluded from reflection.",
                           className="reflect-caption d-block"), 0)
    rows = []
    for node in dismissed[:limit]:
        rows.append(html.Li([
            _type_dot(node.type),
            html.Span(node.name, className="text-truncate"),
            html.Button("Restore", id={'type': 'calibration-restore', 'index': node.name},
                        type="button", className="reflect-restore-btn",
                        **{"aria-label": f"Include {node.name} in future reflections"}),
        ], className="reflect-node-row"))
    return html.Ul(rows, className="reflect-node-list"), len(dismissed)


# Time-calibration modal: pops after an explicit single-node completion to
# capture how long the work actually took. Submit persists the values onto the
# node; Skip leaves the actual_time_* fields NULL. The reference div is filled
# by core_engine with the node name and its original estimate. Input fields are
# static (the app doesn't suppress callback exceptions, so State-referenced IDs
# must exist in the initial layout); they are reset on close.
def build_time_calibration_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Reflection", id="time-calibration-title")),
        dbc.ModalBody([
            # Progress bar — shown in review + completion (chrome callback toggles).
            html.Div(id="calibration-review-progress-wrap", style={"display": "none"},
                     className="mb-3", children=[
                dbc.Progress(id="calibration-review-progress", value=0, label="",
                             style={"height": "20px"}),
            ]),
            # Active rating form — hidden on the completion screen.
            html.Div(id="time-calibration-active", children=[
                # V/I/E sliders — capture how the node *actually* felt now that
                # the work is done. Stored as reflect_value/interest/difficulty
                # (separate from the estimate columns value/interest/difficulty).
                # Ratings come first, as in the node editor. A callback sets
                # --est-value/-interest/-difficulty on this section's style, and
                # theme.css draws the "estimated" tick on each slider from them.
                html.Div(id="calibration-vie-section", children=[
                    html.Div([
                        html.H5("Actual ratings", className="mb-0"),
                        info_button("btn-reflection-ratings-info", "Ratings reference", placement="right"),
                    ], className="d-flex align-items-center mb-2"),
                    dbc.Label("Value", className="mt-3"),
                    dcc.Slider(min=1, max=10, step=1, value=5,
                               id="calibration-value", className="calibration-slider",
                               marks={i: str(i) for i in range(1, 11)}),
                    dbc.Label("Interest", className="mt-3"),
                    dcc.Slider(min=1, max=10, step=1, value=5,
                               id="calibration-interest", className="calibration-slider",
                               marks={i: str(i) for i in range(1, 11)}),
                    dbc.Label("Effort", className="mt-3"),
                    dcc.Slider(min=1, max=10, step=1, value=5,
                               id="calibration-difficulty", className="calibration-slider",
                               marks={i: str(i) for i in range(1, 11)}),
                ]),
                # A Milestone holds no work, so it reflects in notes alone: a
                # callback hides the ratings above and this time section.
                html.Div(id="calibration-time-section", children=[
                    html.Hr(className="my-4"),
                    # d-inline-block: the hover target is the words, not the whole
                    # row, so the tooltip opens beside them instead of off-screen.
                    html.H5("Actual time", id="time-calibration-heading",
                            className="mb-2 d-inline-block hover-hint"),
                    Tooltip(work_time_tooltip("actual"),
                            target="time-calibration-heading", placement="bottom",
                            id="time-calibration-heading-tooltip"),
                    html.Div(id="time-calibration-reference", className="text-muted small mb-2"),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Lower Bound"),
                            dbc.Input(id="time-calibration-lower", type="number", min=0),
                            html.Small(id="time-calibration-lower-hours",
                                       className="time-hour-hint text-muted mt-1",
                                       style={"display": "none"}),
                        ], width=3),
                        dbc.Col([
                            dbc.Label("Best Estimate"),
                            dbc.Input(id="time-calibration-point", type="number", min=0),
                            html.Small(id="time-calibration-point-hours",
                                       className="time-hour-hint text-muted mt-1",
                                       style={"display": "none"}),
                        ], width=3),
                        dbc.Col([
                            dbc.Label("Upper Bound"),
                            dbc.Input(id="time-calibration-upper", type="number", min=0),
                            html.Small(id="time-calibration-upper-hours",
                                       className="time-hour-hint text-muted mt-1",
                                       style={"display": "none"}),
                        ], width=3),
                        dbc.Col([
                            dbc.Label("Unit"),
                            unit_select("time-calibration-unit", value="hours"),
                        ], width=3),
                    ]),
                    html.Hr(className="my-4"),
                ]),
                # Written afterthoughts. The node's Description is the plan
                # made before starting; this is what the work taught.
                # A label, so it names the box for assistive tech, sized as an H5.
                dbc.Label("Reflection notes", html_for="calibration-notes",
                          className="h5 mb-2"),
                dbc.Textarea(
                    id="calibration-notes", rows=4,
                    placeholder=PROJECT_NOTES_PLACEHOLDER,
                    style={"resize": "vertical"}),
            ]),
            # Completion screen — shown only after the last node of a review cycle.
            html.Div(id="time-calibration-complete", style={"display": "none"},
                     className="text-center py-3"),
        ]),
        dbc.ModalFooter([
            # Dismiss / Done are shown contextually by the chrome callback.
            dbc.Button("Don't ask again", id="btn-time-calibration-dismiss",
                       color="secondary", className="flex-fill me-2",
                       style={"display": "none"}),
            dbc.Button("Skip", id="btn-time-calibration-skip",
                       color="secondary", className="flex-fill me-2"),
            dbc.Button("Submit", id="btn-time-calibration-submit",
                       color="primary", className="flex-fill"),
            dbc.Button("Done", id="btn-time-calibration-done",
                       color="primary", className="flex-fill",
                       style={"display": "none"}),
        ], className="d-flex"),
    ], id="modal-time-calibration", size="lg", is_open=False, centered=True)


# Brief notification shown when calibration review is launched but every
# completed node is already rated or dismissed.
def build_calibration_review_toast():
    return dbc.Toast(
        id="calibration-review-toast",
        header="Reflection",
        is_open=False,
        dismissable=True,
        duration=4000,
        icon="info",
        style={"position": "fixed", "top": 66, "right": 12,
               "width": 340, "zIndex": 1100},
    )


# Retrospective sibling of `ratings_popup`, opened only from the Reflection
# modal's info icon. It reads its own REFLECTION_RATINGS_DEFINITIONS so the
# wording can stay decoupled from the estimation rubric. The JS in
# assets/editor/ratings_popup.js wires btn-reflection-ratings-info to this popup.
def build_reflection_ratings_popup():
    return html.Div([
        html.Div([
            html.Span("Reflection Ratings Reference", style={"fontWeight": "600", "fontSize": tokens.FS_MD}),
            edit_button("btn-reflection-ratings-edit", "Edit definitions",
                        className_extra="ms-2"),
            panel_close_button("btn-reflection-ratings-close",
                               "Close reflection ratings reference",
                               style={"marginLeft": "auto"}),
        ], id="reflection-ratings-popup-header", className="d-flex align-items-center", style={
            "padding": "8px 10px",
            "backgroundColor": tokens.BG_RAISED,
            "borderBottom": f"1px solid {tokens.BORDER_PANEL}",
            "borderRadius": "6px 6px 0 0",
            "flexShrink": "0",
            "userSelect": "none",
        }),
        html.Div([
            html.Table([
                html.Thead(html.Tr([
                    html.Th("#", style={**HEADER_CELL_STYLE, "width": "36px"}),
                    html.Th("Value", style=HEADER_CELL_STYLE),
                    html.Th("Interest", style=HEADER_CELL_STYLE),
                    html.Th("Effort", style=HEADER_CELL_STYLE),
                ])),
                html.Tbody(
                    id="reflection-ratings-popup-table-body",
                    children=build_popup_table_rows(settings.REFLECTION_RATINGS_DEFINITIONS.get()),
                ),
            ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": tokens.FS_CAP, "color": tokens.TEXT_PRIMARY}),
        ], style={"overflow": "auto", "flex": "1", "padding": "4px"}),
    ], id="reflection-ratings-popup", style={
        "display": "none",
        "flexDirection": "column",
        "position": "fixed",
        "top": "120px",
        "left": "420px",
        "width": "960px",
        "height": "auto",
        "maxHeight": "calc(100vh - 160px)",
        "minWidth": "400px",
        "minHeight": "200px",
        "zIndex": 9998,
        "backgroundColor": tokens.BG_PANEL,
        "border": f"1px solid {tokens.BORDER_PANEL}",
        "borderRadius": "6px",
        "boxShadow": "0 4px 16px rgba(0,0,0,0.5)",
        "resize": "both",
        "overflow": "hidden",
    })


def build_reflection_ratings_editor_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Edit Reflection Ratings Definitions")),
        dbc.ModalBody(
            html.Div(id="reflection-ratings-editor-body"),
            style={"maxHeight": "70vh", "overflowY": "auto"},
        ),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-reflection-ratings-editor-cancel", color="secondary", className="me-auto"),
            dbc.Button("Save", id="btn-reflection-ratings-editor-save", color="primary"),
        ]),
    ], id="modal-reflection-ratings-editor", size="xl", is_open=False,
       centered=True, scrollable=True)
