"""The node editor following what changes outside it: a
context renamed in Settings, a new hours per week. What it leaves alone is
the user's unsaved edits.
"""
import dash
from dash import Input, Output, State, no_update

from skilltree.features.editor.form import (
    EDITOR_FORM,
    follow_context,
    follow_estimate,
)


def register_follow_callbacks(app, services):
    manager = services.graph

    # --- Editor follows a context renamed or moved in Settings ---
    # A Settings save carries a renamed context, or a subcontext moved to
    # another, onto every node, and the taxonomy store refreshes after it.
    # The editor's pickers were filled when it loaded. They take the stored
    # names while they still show the loaded ones; a context the user picked
    # stays. The snapshot takes the stored names either way. Save resolves the
    # same way (form.resolve_context_intent), so it never depends on this
    # having run, and a changed snapshot checks again for that save's sake.
    @app.callback(
        Output('node-context', 'value', allow_duplicate=True),
        Output('node-subcontext', 'value', allow_duplicate=True),
        Output('editor-pristine-snapshot', 'data', allow_duplicate=True),
        Input('context-taxonomy-store', 'data'),
        Input('editor-pristine-snapshot', 'data'),
        State('node-original-name', 'data'),
        State('node-context', 'value'),
        State('node-subcontext', 'value'),
        prevent_initial_call=True,
    )
    def follow_editor_taxonomy(_taxonomy, snapshot, name, context, subctx):
        node = manager.get_node(name) if name else None
        fields, stored = follow_context(node, context, subctx, snapshot)
        if stored is None:
            return (no_update,) * 3
        patch = dash.Patch()
        patch['context'], patch['subctx'] = stored
        return (*(fields or (no_update, no_update)), patch)

    # --- Editor follows a new hours per week ---
    # The estimate shows in days or weeks at the hours per week Settings held
    # when the node loaded. After Settings changes that, the same numbers mean
    # other hours, and editing one of them converted all three at the new
    # rate, rescaling the two left alone. The fields show the stored hours at
    # the new rate while they still show what was loaded; an estimate being
    # edited stays. The snapshot takes them either way. Settings is a modal,
    # so no other node can load while this is in flight.
    @app.callback(
        Output('node-time-o', 'value', allow_duplicate=True),
        Output('node-time-m', 'value', allow_duplicate=True),
        Output('node-time-p', 'value', allow_duplicate=True),
        Output('editor-pristine-snapshot', 'data', allow_duplicate=True),
        Input('settings-version-store', 'data'),
        [State('node-original-name', 'data'),
         State('editor-pristine-snapshot', 'data'),
         {key: EDITOR_FORM[key] for key in ('time_o', 'time_m', 'time_p', 'time_unit')}],
        prevent_initial_call=True,
    )
    def follow_editor_estimate(_version, name, snapshot, form):
        node = manager.get_node(name) if name else None
        fields, stored = follow_estimate(node, form, snapshot)
        if stored is None:
            return (no_update,) * 4
        patch = dash.Patch()
        patch['time_o'], patch['time_m'], patch['time_p'] = stored
        return (*(fields or (no_update,) * 3), patch)
