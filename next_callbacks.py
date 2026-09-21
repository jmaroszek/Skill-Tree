"""
Callback definitions for the Home tab (priority suggestions).
"""

from next_view import (
    _components_by_id,
    _initial_next_view,
    NextRows,
    get_suggestions as _get_suggestions,
)

import database
from collections import namedtuple
from copy import deepcopy

from dash import Input, Output, State, ALL, ClientsideFunction
from graph_manager import GraphManager
from config import ConfigManager
from callback_helpers import get_trigger_id, format_now_nodes_section, format_suggestions_table, build_filters

manager = GraphManager()


#: What the Next table renders: the ordered rows, plus a map from a pinned
#: step's name to the Now target it unblocks (empty for an ordinary row).


def get_suggestions(filters=None, count=5):
    return _get_suggestions(filters, count, manager=manager)


def register_next_callbacks(app, services=None):
    manager = services.graph if services is not None else globals()['manager']

    # --- Suggestion Count +/- ---
    @app.callback(
        Output('suggestion-count-store', 'data'),
        Output('suggestion-count-display', 'children'),
        Input('btn-sugg-plus', 'n_clicks'),
        Input('btn-sugg-minus', 'n_clicks'),
        State('suggestion-count-store', 'data'),
        prevent_initial_call=True
    )
    def update_suggestion_count(plus, minus, current_count):
        trigger_id = get_trigger_id()
        count = current_count or 10
        if trigger_id == 'btn-sugg-plus':
            count = count + 1
        elif trigger_id == 'btn-sugg-minus':
            count = max(1, count - 1)
        return count, str(count)

    # Selection uses descriptions already shipped with the visible rows.
    # No Python request or graph/table refresh is needed for a click.
    app.clientside_callback(
        ClientsideFunction(namespace='skillTreeNext', function_name='select'),
        Output('selected-suggestion-store', 'data'),
        Output('next-description-text', 'children'),
        Output({'type': 'suggestion-row', 'index': ALL}, 'style'),
        Output({'type': 'now-row', 'index': ALL}, 'style'),
        Output('next-description-text', 'style'),
        Input({'type': 'suggestion-row', 'index': ALL}, 'n_clicks'),
        Input({'type': 'now-row', 'index': ALL}, 'n_clicks'),
        Input('suggestions-table', 'children'),
        Input('now-nodes-table', 'children'),
        State('selected-suggestion-store', 'data'),
    )

    # Not on page load. The layout already carries this table, built from the
    # same snapshot and filters (next_view._initial_next_view), and rebuilding
    # it there cost more than the request. Dash held the core engine behind
    # it, because the table feeds selected-suggestion-store, one of the core
    # engine's States, and so the whole startup waited on a copy of what was
    # already on screen.
    @app.callback(
        Output('suggestions-table', 'children'),
        Input('graph-version-store', 'data'),
        Input('suggestion-count-store', 'data'),
        Input('filter-context', 'value'), Input('filter-subcontext', 'value'),
        Input('filter-done', 'value'), Input('filter-value', 'value'),
        Input('filter-interest', 'value'), Input('filter-time', 'value'),
        Input('filter-time-unit', 'value'), Input('filter-difficulty', 'value'),
        Input('filter-node-type', 'value'), Input('filter-dormant', 'value'),
        Input('settings-save-status', 'children'),
        prevent_initial_call=True,
    )
    @database.snapshot_read
    def populate_suggestions(_version, count, context, subcontext, done, value,
                             interest, time, time_unit, difficulty, types, dormant, _settings):
        filters = build_filters(context, subcontext, done, value, interest, time,
                                difficulty, types, f_time_unit=time_unit,
                                f_show_dormant=dormant)
        next_rows = get_suggestions(filters, count=count or 10)
        return format_suggestions_table(next_rows.rows, manager,
                                        pinned_steps=next_rows.pinned_steps)

    # --- Now Section: populate now-nodes-table ---
    # Listens to graph-version-store so the section refreshes whenever any
    # node mutates (including a flip of the Now flag, which goes through
    # update_node and bumps graph_version). Not on page load, for the same
    # reason as the table above: the layout already carries it.
    @app.callback(
        Output('now-nodes-table', 'children'),
        Input('graph-version-store', 'data'),
        State('selected-suggestion-store', 'data'),
        prevent_initial_call=True,
    )
    def populate_now_section(_version, selected_node_id):
        now_nodes = manager.get_now_nodes()
        return format_now_nodes_section(
            now_nodes,
            cap=ConfigManager.get_now_node_cap(),
            manager=manager,
            selected_node_id=selected_node_id,
        )
