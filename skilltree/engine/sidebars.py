"""The left sidebars (editor, Goals, Events), which share one slot.

left-panel-store says which is open. assets/sidebars/left_panel.js is its only
writer: clicks reach it directly, so a sidebar moves without waiting for the
server. What the server adds is the one decision it can't make there: a close
that depends on the unsaved-changes check. populate_editor sends that as a
request (ui.left_panel), which closes the editor only if the editor is still
what's open.
"""
from dash import ClientsideFunction, Input, Output, State

from skilltree.features.goals.callbacks import GOAL_LIST_SOURCES


def _panel_callback(app, *inputs, allow_duplicate=False):
    app.clientside_callback(
        ClientsideFunction(namespace='left_panel', function_name='advance'),
        Output('sidebar-editor-container', 'className', allow_duplicate=allow_duplicate),
        Output('details-goal-sidebar', 'className', allow_duplicate=allow_duplicate),
        Output('events-sidebar-container', 'className', allow_duplicate=allow_duplicate),
        Output('events-tab-inner', 'className', allow_duplicate=allow_duplicate),
        Output('left-panel-store', 'data', allow_duplicate=allow_duplicate),
        Output('editor-close-ask', 'data', allow_duplicate=allow_duplicate),
        *inputs,
        State('left-panel-store', 'data'),
        State('selected-event-store', 'data'),
        State('event-detail-empty', 'style'),
        State('details-selected-node-store', 'data'),
        *GOAL_LIST_SOURCES,
        prevent_initial_call=True,
    )


def register_left_panel_callbacks(app):
    """One reducer with two doors, because Dash holds a callback back while
    anything that writes one of its Inputs is running.

    Clicks come through the first, so a sidebar never waits on the server. Nothing
    a server callback writes may join them: with left-panel-request here, every
    click would wait for the core engine to finish rendering.
    """
    _panel_callback(
        app,
        Input('btn-add', 'n_clicks'),
        Input('btn-goals-toggle', 'n_clicks'),
        Input('btn-details-goals-close', 'n_clicks'),
        Input('btn-events-sidebar-toggle', 'n_clicks'),
        Input('btn-events-sidebar-close', 'n_clicks'),
        Input('btn-goals-sidebar-new', 'n_clicks'),
        Input('btn-bridge-create', 'n_clicks'),
        Input('edit-trigger-input', 'value'),
        Input('details-edit-trigger-input', 'value'),
        Input('details-add-choice-input', 'value'),
        Input('dormant-add-choice-input', 'value'),
    )
    _panel_callback(
        app,
        Input('main-tabs', 'active_tab'),
        Input('left-panel-request', 'data'),
        allow_duplicate=True,
    )
