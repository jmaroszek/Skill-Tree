"""The reflection modal's rating definitions and its actual-time hour hints."""
from dash import ALL, ClientsideFunction, Input, Output, State, ctx, no_update

from skilltree.store.settings import ConfigManager
from skilltree.ui.components.ratings_table import (
    build_editor_table,
    build_popup_table_rows,
)


def register_reflection_ratings_callbacks(app, services=None):
    # The reflection modal's actual-time inputs get the same hints.
    app.clientside_callback(
        ClientsideFunction(namespace='time_hour_hints', function_name='render_actual'),
        [Output(f'time-calibration-{field}-hours', 'children')
         for field in ('lower', 'point', 'upper')],
        [Output(f'time-calibration-{field}-hours', 'style')
         for field in ('lower', 'point', 'upper')],
        Input('time-calibration-lower', 'value'),
        Input('time-calibration-point', 'value'),
        Input('time-calibration-upper', 'value'),
        Input('time-calibration-unit', 'value'),
        Input('editor-time-settings', 'data'),
    )

    # --- Reflection Ratings Editor ---
    # Mirrors the estimation editor above but reads/writes the decoupled
    # REFLECTION_RATINGS_DEFINITIONS so the Reflection modal's rubric can be
    # tuned independently of the node-editor/Add-Subtask rubric.

    @app.callback(
        Output("modal-reflection-ratings-editor", "is_open"),
        Output("reflection-ratings-editor-body", "children"),
        Input("btn-reflection-ratings-edit", "n_clicks"),
        Input("btn-reflection-ratings-editor-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_reflection_ratings_editor(edit_clicks, cancel_clicks):
        if ctx.triggered_id == "btn-reflection-ratings-edit":
            defs = ConfigManager.get_reflection_ratings_definitions()
            return True, build_editor_table(defs, id_prefix="reflection-ratings-edit")
        return False, no_update

    @app.callback(
        Output("reflection-ratings-popup-table-body", "children"),
        Output("modal-reflection-ratings-editor", "is_open", allow_duplicate=True),
        Input("btn-reflection-ratings-editor-save", "n_clicks"),
        State({"type": "reflection-ratings-edit-value", "index": ALL}, "value"),
        State({"type": "reflection-ratings-edit-interest", "index": ALL}, "value"),
        State({"type": "reflection-ratings-edit-effort", "index": ALL}, "value"),
        prevent_initial_call=True,
    )
    def save_reflection_ratings_definitions(n_clicks, values, interests, efforts):
        defs = ConfigManager.get_reflection_ratings_definitions()
        new_defs = []
        for i, d in enumerate(defs):
            new_defs.append({
                "rating": d["rating"],
                "value": values[i] if i < len(values) else d["value"],
                "interest": interests[i] if i < len(interests) else d["interest"],
                "effort": efforts[i] if i < len(efforts) else d["effort"],
            })
        ConfigManager.set_reflection_ratings_definitions(new_defs)
        return build_popup_table_rows(new_defs), False
