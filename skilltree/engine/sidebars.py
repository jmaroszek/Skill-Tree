"""The left sidebars (editor, Goals, Events), which share one slot.

left-panel-store says which is open. assets/sidebars/left_panel.js is its only
writer: clicks reach it directly, so a sidebar moves without waiting for the
server. What the server adds is the one decision it can't make there: a close
that depends on the unsaved-changes check. That goes out as a request, which
closes the editor only if the editor is still what's open.
"""
import time

from dash import ClientsideFunction, Input, Output, State, no_update

from skilltree.features.editor.form import (
    is_form_dirty_vs_snapshot, editor_form_values_from,
)
from skilltree.features.goals.callbacks import GOAL_LIST_SOURCES


def close_editor():
    """The request that closes the editor. The stamp makes a repeat a new value."""
    return {'close': 'editor', 'ts': int(time.time() * 1000)}


def editor_close_request(trigger_id, open_panel, pending_nav_store, form_state):
    """close_editor() when ``trigger_id`` should close the editor, or no_update.

    `form_state` is the editor form (editor form.EDITOR_FORM's values) plus its
    'pristine_snapshot', for the unsaved-changes check and the name and type a
    save needs. For triggers that need neither, pass an empty dict.
    """
    if trigger_id in ('btn-unsaved-save', 'btn-unsaved-discard'):
        # A canvas click closes once it's answered. Anywhere else the dialog was
        # going loads into the open editor.
        if pending_nav_store == '__background__':
            return close_editor()
        if pending_nav_store:
            return no_update
        # A save without these is refused, and the form stays up.
        if trigger_id == 'btn-unsaved-save' and not (form_state.get('name')
                                                     and form_state.get('n_type')):
            return no_update
        return close_editor()
    if trigger_id == 'btn-node-delete-confirm':
        return close_editor()
    # The toolbar icon toggles, and left_panel.js handles its opening half. These
    # close silently only with nothing to lose. Otherwise the dialog asks
    # (toggle_unsaved_modal).
    if trigger_id == 'btn-close-editor' or (trigger_id == 'btn-add' and open_panel == 'editor'):
        dirty = is_form_dirty_vs_snapshot(form_state.get('pristine_snapshot'),
                                          editor_form_values_from(form_state))
        return no_update if dirty else close_editor()
    return no_update


def _panel_callback(app, *inputs, allow_duplicate=False):
    app.clientside_callback(
        ClientsideFunction(namespace='left_panel', function_name='advance'),
        Output('sidebar-editor-container', 'className', allow_duplicate=allow_duplicate),
        Output('details-goal-sidebar', 'className', allow_duplicate=allow_duplicate),
        Output('events-sidebar-container', 'className', allow_duplicate=allow_duplicate),
        Output('events-tab-inner', 'className', allow_duplicate=allow_duplicate),
        Output('left-panel-store', 'data', allow_duplicate=allow_duplicate),
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
