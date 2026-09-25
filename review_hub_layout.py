"""Layout for the Reflection modal.

The hub is the entry point for the Reflection feature. The journal icon in the
top toolbar opens this modal; the user picks an action (start the focused
queue, browse history, manage excluded nodes) from within.

Three tabs:
  - Queue           — count of un-reflected completed nodes + a launch button
  - History         — searchable/filterable table of already-reflected nodes
  - Excluded        — the "Don't ask again" list (moved here from Settings)

All container IDs (`hub-pending-count`, `hub-history-table-container`,
`hub-excluded-list`, the filter inputs) must exist at initial render — Dash
does not suppress callback exceptions, so any State or Input that references
them needs the component present from the first paint.
"""

from dash import dcc, html
import dash_bootstrap_components as dbc

from context_picker import build_multi_context_picker
from ui_kit import Tooltip


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
    """ "Showing 20 of 73 reflections · Show 20 more" between two rules.

    Styled as the Events list's triggered divider: small gray text, the dot as
    plain text in the sentence, and a soft action that brightens on hover.
    """
    return html.Div([
        html.Span(className="events-triggered-rule"),
        html.Span([
            html.Span(id=f"{prefix}-page-status"),
            html.Span([
                " · ",
                html.Button("Show 20 more", id=f"{prefix}-show-more",
                            type="button", className="events-triggered-toggle"),
            ], id=f"{prefix}-more-wrap"),
        ]),
        html.Span(className="events-triggered-rule"),
    ], id=f"{prefix}-pager", className="events-triggered-divider review-hub-pager")


def _build_pending_tab():
    return dbc.Tab(label="Queue", tab_id="tab-review-pending", children=[
        html.Div([
            html.P(
                "Walk through completed nodes that haven't been "
                "reflected on yet",
                className="text-muted mb-3",
            ),
            html.Div([
                html.Span("Nodes pending reflection: ", className="text-muted"),
                html.Span(id="hub-pending-count", className="fw-bold ms-1",
                          children="0"),
            ], id="hub-pending-summary", className="mb-3"),
            html.P([
                html.I(className="bi bi-check-circle text-success me-2",
                       **{"aria-hidden": "true"}),
                "All caught up",
            ], id="hub-pending-empty",
                   className="mb-0", style={"display": "none"}),
            dbc.Button("Start Reflection", id="btn-hub-pending-launch",
                       color="primary"),
        ], className="p-3")
    ])


def _build_history_tab():
    return dbc.Tab(label="History", tab_id="tab-review-history", children=[
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
            _build_pager("hub-history"),
        ], className="p-3")
    ])


def _build_excluded_tab():
    return dbc.Tab(label="Excluded", tab_id="tab-review-excluded", children=[
        html.Div([
            html.P(
                "Nodes marked \"Don't ask again\" during reflection. "
                "Restore one to make it eligible for the queue again.",
                className="text-muted mb-3",
            ),
            dcc.Store(id="hub-excluded-visible-count", data=20),
            html.Div(id="hub-excluded-list"),
            _build_pager("hub-excluded"),
        ], className="p-3")
    ])


def build_review_hub_modal():
    """The Reflection modal — opened by the journal button in the toolbar."""
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Reflection")),
        dbc.ModalBody(
            dbc.Tabs(id="review-hub-tabs", active_tab="tab-review-pending",
                     children=[
                         _build_pending_tab(),
                         _build_history_tab(),
                         _build_excluded_tab(),
                     ]),
        ),
    ], id="modal-review-hub", dialog_style={"maxWidth": "940px"},
       is_open=False, centered=True, scrollable=True)
