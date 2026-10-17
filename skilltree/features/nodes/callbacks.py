"""The Nodes tab's callbacks: its empty state and node count, Clear focus, the
graph settings panel, and switching to the tab when a node is edited."""
import dash
from dash import Input, Output, State, no_update

from skilltree.features.nodes.layout import empty_canvas_detail
from skilltree.store import settings
from skilltree.store.settings import DEFAULT_GRAPH_LAYOUT
from skilltree.ui import payloads as bridge_payloads
from skilltree.ui.filters import build_filters


def register_nodes_callbacks(app, services):
    manager = services.graph

    # The count is read in the browser from the payload's stamp, as Details
    # counts its own.
    app.clientside_callback(
        """
        function(stamp) {
            var n = (stamp && stamp.nodes) || 0;
            return n + (n === 1 ? ' node' : ' nodes');
        }
        """,
        Output('canvas-node-count', 'children'),
        Input('canvas-payload-stamp', 'data'),
        prevent_initial_call=True,
    )

    # --- The empty canvas: why, and the way back ---
    # An empty render over a graph that has nodes means the filters hid them
    # all. Done and Dormant nodes are hidden by default, so a search for a
    # finished node looks like a bug. The message counts what those two
    # switches hide and offers the switches. With a Community selected the
    # count would describe other communities, so it says only to widen.
    @app.callback(
        Output('canvas-empty-state', 'className'),
        Output('canvas-empty-detail', 'children'),
        Output('btn-empty-show-done', 'style'),
        Output('btn-empty-show-dormant', 'style'),
        Input('canvas-payload-stamp', 'data'),
        State('filter-context', 'value'), State('filter-subcontext', 'value'),
        State('filter-done', 'value'), State('filter-dormant', 'value'),
        State('filter-value', 'value'), State('filter-interest', 'value'),
        State('filter-time', 'value'), State('filter-time-unit', 'value'),
        State('filter-difficulty', 'value'), State('filter-node-type', 'value'),
        State('filter-time-min', 'value'), State('filter-search-query', 'data'),
        State('filter-community', 'value'), State('community-method', 'value'),
        prevent_initial_call=True,
    )
    def update_canvas_empty_state(stamp, f_context, f_subcontext, f_done,
                                  f_show_dormant, f_value, f_interest, f_time,
                                  f_time_unit, f_difficulty, f_node_types,
                                  f_time_min, f_search, f_community,
                                  community_method):
        closed = 'canvas-empty-state', no_update, no_update, no_update
        if (stamp or {}).get('nodes') != 0:
            return closed
        nodes = manager.get_all_nodes(include_dormant=True)
        if not nodes:
            return closed  # A graph with nothing in it is the welcome's business.
        shown, away = {}, {"display": "none"}
        hidden = {'hidden': 0, 'done': 0, 'dormant': 0}
        if not f_community or f_community == "All":
            filters = build_filters(
                f_context, f_subcontext, f_done, f_value, f_interest, f_time,
                f_difficulty, f_node_types, f_time_unit=f_time_unit,
                f_show_dormant=f_show_dormant, f_time_min=f_time_min,
                f_search=f_search)
            if community_method != "orphans":
                hidden = manager.hidden_by_status(nodes, filters)
            elif manager.filter_nodes(nodes, filters):
                # Orphans, and nodes match: every one of them has a link.
                return ('canvas-empty-state is-open',
                        "No orphans: every matching node has a link.", away, away)
        return ('canvas-empty-state is-open', empty_canvas_detail(hidden),
                shown if hidden['done'] else away,
                shown if hidden['dormant'] else away)

    @app.callback(
        Output('focus-goal-store', 'data', allow_duplicate=True),
        Input('btn-clear-focus', 'n_clicks'),
        prevent_initial_call=True,
    )
    def clear_focus(n_clicks):
        if n_clicks:
            return None
        return dash.no_update

    # --- Edit Trigger: switch to canvas tab ---
    # NOTE: short-circuit when already on canvas. Writing the same value to
    # main-tabs.active_tab with allow_duplicate=True still re-fires any Input
    # depending on it (notably core_engine). That second core_engine run had
    # trigger_id='main-tabs', which doesn't match any editor-open branch, so
    # it returned the State-cached ed_style — racing with the open-editor
    # output from the Edit-trigger run and sometimes clobbering it back to
    # the closed translateX. Only writing when the tab actually needs to change
    # avoids the spurious re-fire.
    @app.callback(
        Output('main-tabs', 'active_tab', allow_duplicate=True),
        Input('edit-trigger-input', 'value'),
        State('main-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    def handle_edit_trigger(value, current_tab):
        if not value:
            return dash.no_update
        node_name = bridge_payloads.strip_stamp(value)
        if not node_name:
            return dash.no_update
        if current_tab == 'tab-canvas':
            return dash.no_update
        return 'tab-canvas'

    # --- Graph Layout: Toggle Panel ---
    @app.callback(
        Output('graph-settings-panel', 'style'),
        Input('btn-graph-settings', 'n_clicks'),
        Input('btn-close-graph-settings', 'n_clicks'),
        State('graph-settings-panel', 'style'),
        prevent_initial_call=True,
    )
    def toggle_graph_settings(_n_open, _n_close, current_style):
        style = dict(current_style) if current_style else {}
        style['display'] = 'none' if style.get('display') != 'none' else 'block'
        return style

    # --- Graph Layout: Reset to Stored Defaults ---
    @app.callback(
        Output('graph-settings-animate', 'value', allow_duplicate=True),
        Output('graph-settings-edge-length', 'value', allow_duplicate=True),
        Output('graph-settings-gravity', 'value', allow_duplicate=True),
        Output('graph-settings-repulsion', 'value', allow_duplicate=True),
        Output('graph-settings-freeze-rerender', 'value', allow_duplicate=True),
        Input('btn-reset-graph-settings', 'n_clicks'),
        prevent_initial_call=True,
    )
    def reset_graph_settings(n_clicks):
        if not n_clicks:
            return (dash.no_update,) * 5
        gl = settings.GRAPH_LAYOUT_DEFAULTS.get()
        return (
            True,
            gl.get('edge_length', DEFAULT_GRAPH_LAYOUT['edge_length']),
            gl.get('gravity', DEFAULT_GRAPH_LAYOUT['gravity']),
            gl.get('repulsion', DEFAULT_GRAPH_LAYOUT['repulsion']),
            False,
        )
