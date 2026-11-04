"""The node editor's Revert and its confirmations for reopening and deleting.
"""
import dash
from dash import Input, Output, State

from skilltree.ui.dash_tools import get_trigger_id
from skilltree.ui.notices import info


def register_dialog_callbacks(app, services):
    manager = services.graph

    # --- Revert: populate_editor reloads the loaded node from the database,
    # discarding any unsaved edits. Disabled when no node is loaded. It used
    # to go through the context menu's Edit trigger, whose payload it got
    # wrong, so it reloaded nothing while saying it had, and from Details or
    # Events it also switched to the Nodes tab.
    app.clientside_callback(
        "function(name) { return !name; }",
        Output('btn-revert', 'disabled'),
        Input('node-original-name', 'data'),
    )

    @app.callback(
        Output('notice-store', 'data', allow_duplicate=True),
        Input('btn-revert', 'n_clicks'),
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def revert_message(n_clicks, name):
        if not n_clicks or not name:
            return dash.no_update
        if manager.get_node(name) is None:
            return info(f"Couldn't revert: '{name}' no longer exists.")
        return info("Changes reverted.")

    # Either answer closes the reopen confirmation. The core engine reads the
    # held Save from the store on a yes, so only a no clears it.
    app.clientside_callback(
        """
        function(confirm, cancel) {
            var NO = window.dash_clientside.no_update;
            var ctx = window.dash_clientside.callback_context;
            var cancelled = (ctx.triggered || []).some(function (t) {
                return t.prop_id.indexOf('btn-editor-reopen-cancel') === 0;
            });
            if (!confirm && !cancel) return [NO, NO];
            return [false, cancelled ? null : NO];
        }
        """,
        Output('modal-editor-reopen-confirm', 'is_open', allow_duplicate=True),
        Output('editor-reopen-pending-store', 'data', allow_duplicate=True),
        Input('btn-editor-reopen-confirm', 'n_clicks'),
        Input('btn-editor-reopen-cancel', 'n_clicks'),
        prevent_initial_call=True,
    )

    # --- Delete Confirmation Modal ---
    @app.callback(
        Output('modal-node-delete-confirm', 'is_open'),
        Output('node-delete-confirm-body', 'children'),
        [Input('btn-delete', 'n_clicks'),
         Input('btn-node-delete-cancel', 'n_clicks'),
         Input('btn-node-delete-confirm', 'n_clicks')],
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def toggle_delete_modal(_delete, _cancel, _confirm, original_name):
        if get_trigger_id() != 'btn-delete':
            return False, dash.no_update
        # Name the node the confirm will delete: the one the editor loaded,
        # which is not always what the Name field says by now.
        loaded = (original_name or '').strip()
        if not loaded:
            return True, "This node hasn't been saved yet. Deleting it just closes the editor."
        return True, f'Are you sure you want to delete "{loaded}"? This action cannot be undone.'
