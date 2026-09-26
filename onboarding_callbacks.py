"""The welcome dialog and the Getting Started card (onboarding.py decides what
they show)."""
import dash
from dash import ALL, Input, Output, html, no_update
import dash_bootstrap_components as dbc

import onboarding
from config import ConfigManager
from graph_manager import GraphManager


def register_onboarding_callbacks(app, services=None):
    @app.callback(
        Output("welcome-modal", "is_open"),
        Output("welcome-reload-trigger", "data"),
        Output("settings-modal", "is_open", allow_duplicate=True),
        Output("settings-modal-tabs", "active_tab", allow_duplicate=True),
        Input("btn-welcome-suggested", "n_clicks"),
        Input("btn-welcome-empty", "n_clicks"),
        Input("btn-welcome-import", "n_clicks"),
        prevent_initial_call=True,
    )
    def welcome_choice(_suggested, _empty, _import):
        choice = dash.ctx.triggered_id
        if choice not in ("btn-welcome-suggested", "btn-welcome-empty", "btn-welcome-import"):
            return no_update, no_update, no_update, no_update
        ConfigManager.set_welcome_done(True)
        if choice == "btn-welcome-empty":
            # Every node needs a context, so "none" is one plain one to rename.
            ConfigManager.set_contexts(["General"])
            ConfigManager.set_subcontexts({"General": []})
            # The context pickers were built with the old list.
            return False, "reload", no_update, no_update
        if choice == "btn-welcome-import":
            return False, no_update, True, "tab-data"
        return False, no_update, no_update, no_update

    app.clientside_callback(
        """function(trigger) {
            if (trigger) { window.location.reload(); }
            return window.dash_clientside.no_update;
        }""",
        Output("welcome-reload-sink", "data"),
        Input("welcome-reload-trigger", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("getting-started", "children"),
        Input("graph-version-store", "data"),
    )
    def render_getting_started(_version):
        if ConfigManager.get_getting_started_dismissed():
            return None
        steps = onboarding.getting_started(GraphManager())
        if all(step.done for step in steps):
            return None
        return _card(steps)

    # The button lives in the card, which isn't always there: pattern-matched.
    @app.callback(
        Output("getting-started", "children", allow_duplicate=True),
        Input({"type": "getting-started-dismiss", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def dismiss_getting_started(clicks):
        if not any(clicks or []):
            return no_update
        ConfigManager.set_getting_started_dismissed(True)
        return None


def _card(steps):
    items = [
        html.Li([
            html.I(className="bi bi-check-circle-fill text-success me-2" if step.done
                   else "bi bi-circle text-muted me-2", **{"aria-hidden": "true"}),
            html.Span(step.label, className="text-decoration-line-through text-muted"
                      if step.done else "fw-semibold"),
            html.Div(step.hint, className="small text-muted ms-4") if not step.done else None,
        ], className="mb-2")
        for step in steps
    ]
    return dbc.Card(dbc.CardBody([
        html.Div([
            html.H6("Getting started", className="mb-2"),
            dbc.Button("Hide", id={"type": "getting-started-dismiss", "index": 0},
                       color="link", size="sm",
                       className="p-0 ms-auto text-muted"),
        ], className="d-flex align-items-start"),
        html.Ol(items, className="list-unstyled mb-0"),
    ]), className="mb-3", style={"maxWidth": "640px"})
