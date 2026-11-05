"""The node editor's alias rows.

Whatever writes aliases-store draws the rows in the same answer: this, a node
load (view.editor_view) and the post-save sync. A callback that drew them from
the store came a pass later, so a load showed its alias rows after the rest of
the form.
"""
from dash import ALL, Input, Output, State, ctx, no_update

from skilltree.features.editor.layout import (
    alias_rows_label,
    render_alias_rows,
    update_alias_rows,
)


def register_alias_callbacks(app, services):
    # --- Aliases Add/Remove ---
    @app.callback(
        [Output('aliases-store', 'data', allow_duplicate=True),
         Output('collapse-aliases', 'is_open', allow_duplicate=True),
         Output('aliases-container', 'children', allow_duplicate=True),
         Output('aliases-label', 'children', allow_duplicate=True)],
        [Input('btn-alias-add', 'n_clicks'),
         Input({'type': 'btn-alias-remove', 'index': ALL}, 'n_clicks')],
        [State({'type': 'alias-input', 'index': ALL}, 'value'),
         State('aliases-store', 'data'),
         State('collapse-aliases', 'is_open')],
        prevent_initial_call=True,
    )
    def modify_aliases(add_clicks, remove_clicks, current_values, store_data,
                       aliases_open):
        # Each rebuilt row's remove button fires with no click. Taken for one, it
        # emptied the store and closed the section on every load.
        if isinstance(ctx.triggered_id, dict) and not ctx.triggered[0].get('value'):
            return no_update, no_update, no_update, no_update
        aliases, collapse = update_alias_rows(
            ctx.triggered_id, current_values, store_data, aliases_open,
            'btn-alias-add', 'btn-alias-remove',
        )
        return aliases, collapse, render_alias_rows(aliases), alias_rows_label(aliases)
