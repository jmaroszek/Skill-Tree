"""The Create Bridge dialog.

A bridge puts a new node between two nodes you already have. The dialog only
asks which node comes first and how they relate; the node itself is made in
the ordinary node editor, which opens with those relationships filled in.
"""
from dash import html
import dash_bootstrap_components as dbc

from skilltree.ui import tokens
from skilltree.ui.kit import cancel_action, primary_action, swap_button


def _end_row(label, label_id, name_id):
    return html.Div([
        html.Div(label, id=label_id, className="text-muted",
                 style={"width": "4.5rem", "fontSize": tokens.FS_BASE}),
        html.Div(id=name_id, className="fw-semibold text-break"),
    ], className="d-flex align-items-baseline gap-2")


def build_bridge_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Create Bridge")),
        dbc.ModalBody([
            html.Div([
                html.Div([
                    _end_row("Start", "bridge-start-label", "bridge-start"),
                    html.Div(className="my-2"),
                    _end_row("End", "bridge-end-label", "bridge-end"),
                ], className="flex-grow-1"),
                html.Div(swap_button("btn-bridge-swap", "Swap Start and End"),
                         id="bridge-swap-wrap"),
            ], className="d-flex align-items-center mb-3"),
            dbc.Label("Relationship"),
            dbc.Select(
                id="bridge-type",
                options=[
                    {"label": "Hard", "value": "hard"},
                    {"label": "Soft", "value": "soft"},
                    {"label": "Synergy", "value": "synergy"},
                ],
                value="hard",
            ),
            html.Div(id="bridge-notice", className="mt-3",
                     style={"fontSize": tokens.FS_BASE, "minHeight": "1.2em"}),
        ]),
        dbc.ModalFooter([
            cancel_action("Cancel", "btn-bridge-cancel", className="me-2"),
            primary_action("Create", "btn-bridge-create"),
        ]),
    ], id="modal-bridge", is_open=False, centered=True)
