"""Layout for the Review Hub modal.

The hub is the entry point for the calibration-review feature. It replaces the
former direct-launch behavior of the clock-history toolbar icon: clicking that
icon now opens this modal, and the user picks an action (start the focused
queue, browse history, manage excluded nodes) from within.

Three tabs:
  - Pending Queue   — count of uncalibrated completed nodes + a launch button
  - Review History  — searchable/filterable table of already-rated nodes
  - Excluded Nodes  — the "Don't ask again" list (moved here from Settings)

All container IDs (`hub-pending-count`, `hub-history-table`, `hub-history-store`,
`hub-excluded-list`) must exist at initial render — Dash does not suppress
callback exceptions, so any State or Input that references them needs the
component present from the first paint.
"""

from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc


_TABLE_HEADER_STYLE = {
    "backgroundColor": "#2b3035",
    "color": "#dee2e6",
    "border": "1px solid #495057",
    "fontWeight": "600",
}

_TABLE_DATA_STYLE = {
    "backgroundColor": "#212529",
    "color": "#dee2e6",
    "border": "1px solid #343a40",
}

_TABLE_FILTER_STYLE = {
    "backgroundColor": "#2b3035",
    "color": "#dee2e6",
}


def _build_pending_tab():
    return dbc.Tab(label="Pending Queue", tab_id="tab-review-pending", children=[
        html.Div([
            html.P(
                "Walk through completed nodes that haven't been rated yet — "
                "one at a time, capturing actual time, value, interest, and "
                "effort.",
                className="text-muted mb-3",
            ),
            html.Div([
                html.Span("Nodes pending review: ", className="text-muted"),
                html.Span(id="hub-pending-count", className="fw-bold ms-1",
                          children="0"),
            ], className="mb-3"),
            dbc.Button("Start review", id="btn-hub-pending-launch",
                       color="primary"),
        ], className="p-3")
    ])


def _build_history_tab():
    return dbc.Tab(label="Review History", tab_id="tab-review-history", children=[
        html.Div([
            html.P(
                "Already-rated nodes. Click the pencil on any row to edit its "
                "actuals. Sort and filter using the column headers.",
                className="text-muted mb-3",
            ),
            dcc.Store(id="hub-history-store", data={}),
            dash_table.DataTable(
                id="hub-history-table",
                data=[],
                columns=[],
                page_size=20,
                sort_action="native",
                filter_action="native",
                page_action="native",
                style_as_list_view=True,
                style_header=_TABLE_HEADER_STYLE,
                style_data=_TABLE_DATA_STYLE,
                style_filter=_TABLE_FILTER_STYLE,
                style_cell={
                    "backgroundColor": "#212529",
                    "color": "#dee2e6",
                    "textAlign": "left",
                    "padding": "8px",
                    "fontFamily": "inherit",
                },
            ),
        ], className="p-3")
    ])


def _build_excluded_tab():
    return dbc.Tab(label="Excluded", tab_id="tab-review-excluded", children=[
        html.Div([
            html.P(
                "Nodes marked \"Don't ask again\" during a review. Restore one "
                "to make it eligible for the review queue again.",
                className="text-muted mb-3",
            ),
            html.Div(id="hub-excluded-list"),
        ], className="p-3")
    ])


def build_review_hub_modal():
    """The Review Hub modal — opened by the clock-history button in the toolbar."""
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Review Hub")),
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
