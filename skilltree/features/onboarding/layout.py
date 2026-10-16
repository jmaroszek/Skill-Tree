"""The welcome dialog's layout."""
from dash import dcc
from dash import html
from skilltree.store.settings import DEFAULT_CONTEXTS
from skilltree.ui.kit import cancel_action
from skilltree.ui.kit import primary_action
import dash_bootstrap_components as dbc
from skilltree.features.onboarding import steps as onboarding


def build_welcome_modal():
    """The first launch, with an empty graph (onboarding.should_welcome).

    The layout is built per page load, so answering it once keeps it closed.
    onboarding_callbacks.py handles the choices.
    """
    return html.Div([
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Welcome to Skill Tree"), close_button=False),
            dbc.ModalBody([
                html.P("Skill Tree helps you decide what to work on next. You add your "
                       "goals and the things that lead to them, connect them, and it "
                       "ranks what's worth doing now."),
                html.P("Contexts are the areas of your life that nodes belong to, and "
                       "every node has one. Start with a suggested set "
                       f"({', '.join(DEFAULT_CONTEXTS)}), or with a single one "
                       "called General, and change them any time in "
                       "Settings > Contexts."),
                html.P(["Coming from another computer? Import your export in ",
                        html.Em("Settings > App"), "."], className="mb-0"),
            ]),
            dbc.ModalFooter([
                cancel_action("Import a graph…", "btn-welcome-import", className="me-auto"),
                cancel_action("Start with just General", "btn-welcome-empty"),
                primary_action("Use the suggested contexts", "btn-welcome-suggested"),
            ]),
        ], id="welcome-modal", is_open=onboarding.should_welcome(), centered=True,
            size="lg", backdrop="static", keyboard=False),
        dcc.Store(id="welcome-reload-trigger"),
        dcc.Store(id="welcome-reload-sink"),
    ])
