"""The ratings popup's definitions, and editing them.
"""
from dash import ALL, ClientsideFunction, Input, Output, State, ctx, no_update

from skilltree.store import settings
from skilltree.ui.components.ratings_table import (
    build_editor_table,
    build_popup_table_rows,
)


def register_ratings_callbacks(app, services):
    # --- Ratings Editor ---

    app.clientside_callback(
        ClientsideFunction(namespace='ratings_popup', function_name='reopen_after_edit'),
        Output('ratings-popup', 'data-reopened'),  # dummy output
        Input('modal-ratings-editor', 'is_open'),
        State('ratings-popup', 'id'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("modal-ratings-editor", "is_open"),
        Output("ratings-editor-body", "children"),
        Input("btn-ratings-edit", "n_clicks"),
        Input("btn-ratings-editor-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_ratings_editor(edit_clicks, cancel_clicks):
        if ctx.triggered_id == "btn-ratings-edit":
            defs = settings.RATINGS_DEFINITIONS.get()
            return True, build_editor_table(defs)
        return False, no_update

    @app.callback(
        Output("ratings-popup-table-body", "children"),
        Output("modal-ratings-editor", "is_open", allow_duplicate=True),
        Input("btn-ratings-editor-save", "n_clicks"),
        State({"type": "ratings-edit-value", "index": ALL}, "value"),
        State({"type": "ratings-edit-interest", "index": ALL}, "value"),
        State({"type": "ratings-edit-effort", "index": ALL}, "value"),
        prevent_initial_call=True,
    )
    def save_ratings_definitions(n_clicks, values, interests, efforts):
        defs = settings.RATINGS_DEFINITIONS.get()
        new_defs = []
        for i, d in enumerate(defs):
            new_defs.append({
                "rating": d["rating"],
                "value": values[i] if i < len(values) else d["value"],
                "interest": interests[i] if i < len(interests) else d["interest"],
                "effort": efforts[i] if i < len(efforts) else d["effort"],
            })
        settings.RATINGS_DEFINITIONS.set(new_defs)
        return build_popup_table_rows(new_defs), False
