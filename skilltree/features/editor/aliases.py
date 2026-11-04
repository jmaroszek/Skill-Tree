"""The node editor's alias rows.
"""
from dash import ALL, Input, Output, State, ctx, no_update

from skilltree.features.editor.layout import (
    alias_rows_label,
    render_alias_rows,
    update_alias_rows,
)
from skilltree.ui.prerender import prerendered


def register_alias_callbacks(app, services):
    # --- Aliases Render ---
    @app.callback(
        [Output('aliases-container', 'children'),
         Output('aliases-label', 'children')],
        Input('aliases-store', 'data'),
        prevent_initial_call=True,
    )
    @prerendered
    def render_aliases(aliases):
        return render_alias_rows(aliases), alias_rows_label(aliases)

    # --- Aliases Add/Remove ---
    @app.callback(
        [Output('aliases-store', 'data', allow_duplicate=True),
         Output('collapse-aliases', 'is_open', allow_duplicate=True)],
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
            return no_update, no_update
        return update_alias_rows(
            ctx.triggered_id, current_values, store_data, aliases_open,
            'btn-alias-add', 'btn-alias-remove',
        )
