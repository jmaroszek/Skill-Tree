"""The Events tab's graph: an event's nodes and what they wait on, its filter
chip and its graph settings."""
import time

from dash import Input, Output, State, no_update

from skilltree.store import settings
from skilltree.ui.canvas.elements import (
    build_edge_element,
    build_node_element,
    canvas_node_styles,
)
from skilltree.ui.filters import (
    FILTER_INPUTS,
    filter_chip_state,
    filter_chip_updates,
    filter_summary,
    filters_from,
)
from skilltree.ui.prerender import prerendered


def register_event_graph_callbacks(app, services):
    event_manager = services.events
    graph_manager = services.graph

    # --- Event Graph: render dormant nodes + immediate neighbors ---
    # The Nodes outside event switch drops the neighbors, leaving the event's own
    # nodes and the links between them. The sidebar filters narrow only the
    # neighbors: the event's own nodes are the list the user loaded, and are
    # dormant, so the Show Dormant gate alone would hide them all.
    # Outputs to events-elements-pending-store; freeze bypass applied by a
    # clientside callback in callbacks.py.
    # Any change to the graph can change the neighbors, such as a new node
    # linked to one in the event, so a graph change redraws it as on Details.
    # The refresh trigger covers the roster, which the graph doesn't hold.
    @app.callback(
        Output("events-elements-pending-store", "data"),
        Input("selected-event-store", "data"),
        Input("events-refresh-trigger", "data"),
        Input("events-outside-nodes", "value"),
        Input("graph-version-store", "data"),
        FILTER_INPUTS,
    )
    def render_event_graph(selected_event, _refresh, show_outside=True,
                           _graph_version=None, sidebar_filters=None):
        if not selected_event:
            return []

        event_nodes_data = event_manager.get_event_nodes(selected_event)
        dormant_names = {en['node'].name for en in event_nodes_data}
        if not dormant_names:
            return []

        all_edges = graph_manager.get_edges()
        neighbor_names = set()
        for e in (all_edges if show_outside is not False else []):
            if e['source'] in dormant_names and e['target'] not in dormant_names:
                neighbor_names.add(e['target'])
            if e['target'] in dormant_names and e['source'] not in dormant_names:
                neighbor_names.add(e['source'])

        neighbors = [node for node in map(graph_manager.get_node, neighbor_names)
                     if node]
        neighbors = graph_manager.filter_nodes(
            neighbors, filters_from(sidebar_filters))
        nodes = [node for node in map(graph_manager.get_node, dormant_names)
                 if node] + neighbors
        all_names = {node.name for node in nodes}
        styles = canvas_node_styles(event_manager)

        elements = []
        for node in nodes:
            name = node.name
            # "Dormant" on this canvas means attached to the selected event,
            # whatever the node's own flag says. The context menu routes Edit
            # on those nodes to the dormant-node editor.
            elements.append(build_node_element(
                node, styles, dormant=name in dormant_names))

        for e in all_edges:
            if e['source'] in all_names and e['target'] in all_names:
                elements.append(build_edge_element(e))

        return elements

    # --- Event Graph: single-click populates the editor only if it's already open ---
    # Why: the user wants tapping a node to re-populate an open editor the way it
    # does on other canvases, but never to open the editor from a closed state.
    # Right-click -> Edit (via context_menu.js) remains the explicit open path.
    @app.callback(
        Output("details-edit-trigger-input", "value", allow_duplicate=True),
        Input("events-detail-graph", "tapNodeData"),
        State("sidebar-editor-container", "style"),
        prevent_initial_call=True,
    )
    def populate_editor_from_event_graph(tap_data, editor_style):
        if not tap_data or not tap_data.get("id"):
            return no_update
        editor_open = bool(editor_style) and editor_style.get("transform", "") == "translateX(0px)"
        if not editor_open:
            return no_update
        return f"{tap_data['id']}|{int(time.time())}"

    # --- Events Tab: Node Count Canvas Overlay ---
    # Counted in the browser from the payload on its way to Cytoscape, as on
    # Details. Reading the canvas's elements sent the whole graph to the
    # server twice per selection: once for the payload and once for
    # dash-cytoscape's positional echo.
    app.clientside_callback(
        """
        function(pending) {
            if (!Array.isArray(pending)) return window.dash_clientside.no_update;
            var n = 0;
            for (var i = 0; i < pending.length; i++) {
                var data = pending[i] && pending[i].data;
                if (data && data.source === undefined) n += 1;
            }
            return n + (n === 1 ? ' node' : ' nodes');
        }
        """,
        Output('events-canvas-node-count', 'children'),
        Input('events-elements-pending-store', 'data'),
    )

    # --- Events Tab: Filtered chip ---
    # As on Details: the filters that narrow this canvas, which leave out
    # Community. They hide only the nodes outside the event.
    @app.callback(
        Output('events-filter-chip-text', 'children'),
        Output('events-filter-chip', 'title'),
        Output('events-filter-chip', 'hidden'),
        Input('filter-node-type', 'value'),
        Input('filter-context', 'value'),
        Input('filter-subcontext', 'value'),
        Input('filter-value', 'value'),
        Input('filter-interest', 'value'),
        Input('filter-difficulty', 'value'),
        Input('filter-time', 'value'),
        Input('filter-time-min', 'value'),
        Input('filter-search-query', 'data'),
        Input('filter-time-unit', 'value'),
        State('events-filter-chip-text', 'children'),
        State('events-filter-chip', 'title'),
        State('events-filter-chip', 'hidden'),
        prevent_initial_call=True,
    )
    @prerendered
    def update_events_filter_chip(f_type, f_ctx, f_sub, f_val, f_int, f_diff,
                                  f_time, f_time_min, f_search, f_time_unit,
                                  chip_text, chip_title, chip_hidden):
        chip = filter_chip_state(filter_summary(
            node_type=f_type, context=f_ctx, subcontext=f_sub, value=f_val,
            interest=f_int, difficulty=f_diff, time=f_time,
            time_min=f_time_min, search=f_search, time_unit=f_time_unit))
        return filter_chip_updates(chip, (chip_text, chip_title, chip_hidden))

    # --- Events Graph Layout: Toggle Panel ---
    @app.callback(
        Output('events-graph-settings-panel', 'style'),
        Input('btn-events-graph-settings', 'n_clicks'),
        Input('btn-close-events-graph-settings', 'n_clicks'),
        State('events-graph-settings-panel', 'style'),
        prevent_initial_call=True,
    )
    def toggle_events_graph_settings(_n_open, _n_close, current_style):
        style = dict(current_style) if current_style else {}
        style['display'] = 'none' if style.get('display') != 'none' else 'block'
        return style

    # --- Events Graph Layout: Reset to Stored Defaults ---
    @app.callback(
        Output('events-graph-settings-animate', 'value', allow_duplicate=True),
        Output('events-graph-settings-edge-length', 'value', allow_duplicate=True),
        Output('events-graph-settings-gravity', 'value', allow_duplicate=True),
        Output('events-graph-settings-repulsion', 'value', allow_duplicate=True),
        Output('events-graph-settings-freeze-rerender', 'value', allow_duplicate=True),
        Input('btn-reset-events-graph-settings', 'n_clicks'),
        prevent_initial_call=True,
    )
    def reset_events_graph_settings(n_clicks):
        if not n_clicks:
            return no_update, no_update, no_update, no_update, no_update
        gl = settings.EVENTS_GRAPH_LAYOUT_DEFAULTS.get()
        return (
            True,
            gl.get('edge_length', 50),
            gl.get('gravity', 0.25),
            gl.get('repulsion', 4500),
            False,
        )
