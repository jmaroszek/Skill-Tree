"""Layout for the Reflection modal.

The hub is the entry point for the Reflection feature. The journal icon in the
top toolbar opens this modal; the user picks an action (start the focused
queue, browse history, manage excluded nodes) from within.

Three tabs:
  - Pending Queue   — count of un-reflected completed nodes + a launch button
  - Review History  — searchable/filterable table of already-reflected nodes
  - Excluded        — the "Don't ask again" list (moved here from Settings)

All container IDs (`hub-pending-count`, `hub-history-table-container`,
`hub-excluded-list`, the filter inputs) must exist at initial render — Dash
does not suppress callback exceptions, so any State or Input that references
them needs the component present from the first paint.
"""

from dash import dcc, html
import dash_bootstrap_components as dbc

from context_picker import build_multi_context_picker


def _build_pending_tab():
    return dbc.Tab(label="Pending Queue", tab_id="tab-review-pending", children=[
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
            html.P("All caught up", id="hub-pending-empty",
                   className="mb-0", style={"display": "none"}),
            dbc.Button("Start Reflection", id="btn-hub-pending-launch",
                       color="primary"),
        ], className="p-3")
    ])


def _build_history_tab():
    return dbc.Tab(label="Review History", tab_id="tab-review-history", children=[
        html.Div([
            # No caption. "Already-reflected nodes" only restates the tab's own
            # name, and the pencil carries its own tooltip. The sibling tabs
            # keep theirs because they say something their names do not: the
            # queue identifies which completed nodes it handles, and Excluded
            # says what can be restored.
            #
            # Search takes the width: a name is long and you type into it,
            # while the context picker shows at most two contexts and a "+N".
            dbc.Row([
                dbc.Col(
                    dbc.Input(id="hub-history-search", type="search",
                              placeholder="Search by name...",
                              style={"width": "100%"}),
                    width=8,
                ),
                dbc.Col(
                    build_multi_context_picker(
                        "hub-history-context-picker",
                        "hub-history-filter-context",
                        "hub-history-filter-subcontext",
                    ),
                    width=4,
                ),
            ], className="mb-2 g-2"),
            dcc.Store(id="hub-history-visible-count", data=20),
            dcc.Store(id="hub-history-sort", data={"key": "completed", "direction": "desc"}),
            html.Div(id="hub-history-sort-reset-wrap", children=[
                dbc.Button("Newest completed first", id="hub-history-sort-reset",
                           color="link", size="sm", className="p-0"),
            ], className="mb-1", style={"display": "none"}),
            html.Div(id="hub-history-table-container",
                     className="review-history-table-wrap"),
            html.Div([
                html.Span(id="hub-history-page-status", className="text-muted small"),
                dbc.Button("Show 20 more", id="hub-history-show-more",
                           color="link", size="sm", className="ms-2"),
            ], id="hub-history-pager", className="review-history-pager"),
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
            html.Div(id="hub-excluded-list"),
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
