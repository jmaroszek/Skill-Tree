"""Layout for the Reflection Hub modal.

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

from dash import html, dcc
import dash_bootstrap_components as dbc

from config import ConfigManager, sort_contexts


def _build_pending_tab():
    return dbc.Tab(label="Pending Queue", tab_id="tab-review-pending", children=[
        html.Div([
            html.P(
                "Walk through completed nodes that haven't been "
                "reflected on yet — one at a time, capturing actual "
                "value, interest, effort, and time.",
                className="text-muted mb-3",
            ),
            html.Div([
                html.Span("Nodes pending reflection: ", className="text-muted"),
                html.Span(id="hub-pending-count", className="fw-bold ms-1",
                          children="0"),
            ], className="mb-3"),
            dbc.Button("Start Reflection", id="btn-hub-pending-launch",
                       color="primary"),
        ], className="p-3")
    ])


def _build_history_tab():
    contexts = sort_contexts(ConfigManager.get_contexts())
    return dbc.Tab(label="Review History", tab_id="tab-review-history", children=[
        html.Div([
            html.P(
                "Already-reflected nodes. Click the pencil on any row to edit "
                "its actuals.",
                className="text-muted mb-2",
            ),
            dbc.Row([
                dbc.Col(
                    dbc.Input(id="hub-history-search", type="search",
                              placeholder="Search by name…",
                              style={"width": "100%"}),
                    width=4,
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id="hub-history-filter-context",
                        options=[{"label": c, "value": c} for c in contexts],
                        value=[], multi=True,
                        placeholder="All contexts",
                        style={"color": "#212529"},
                    ),
                    width=4,
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id="hub-history-filter-subcontext",
                        options=[], value=[], multi=True,
                        placeholder="All subcontexts",
                        style={"color": "#212529"},
                    ),
                    width=4,
                ),
            ], className="mb-2 g-2"),
            html.Div(id="hub-history-table-container"),
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
    """The Reflection Hub modal — opened by the journal button in the toolbar."""
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Reflection Hub")),
        dbc.ModalBody(
            dbc.Tabs(id="review-hub-tabs", active_tab="tab-review-pending",
                     children=[
                         _build_pending_tab(),
                         _build_history_tab(),
                         _build_excluded_tab(),
                     ]),
        ),
    ], id="modal-review-hub", dialog_style={"maxWidth": "1100px"},
       is_open=False, scrollable=True)
