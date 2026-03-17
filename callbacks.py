"""
Callback definitions for the Skill Tree Dash application.
Contains all Dash callbacks and their helper functions.
"""

import dash
from dash import html, Input, Output, State
import dash_bootstrap_components as dbc
from graph_manager import GraphManager
from models import Node
from constants import NODE_COLORS, NODE_SHAPES, DEFAULT_WN, DEFAULT_WH

manager = GraphManager()


# --- Helper Functions ---

def generate_elements(filters=None, active_node_id=None, community_names=None):
    """Generates Cytoscape elements from the database, applying optional filters."""
    if filters is None:
        filters = {}

    nodes = manager.get_all_nodes()
    filtered_nodes = manager.filter_nodes(nodes, filters)

    if community_names is not None:
        filtered_nodes = [n for n in filtered_nodes if n.name in community_names]

    valid_names = {n.name for n in filtered_nodes}
    edges = manager.get_edges()

    elements = []

    for n in filtered_nodes:
        node_data = {
            'data': {
                'id': n.name,
                'label': n.name,
                'color': NODE_COLORS.get(n.status, '#888'),
                'shape': NODE_SHAPES.get(n.type, 'rectangle'),
                **n.to_dict()
            },
            'selected': n.name == active_node_id if active_node_id else False
        }
        elements.append(node_data)

    for e in edges:
        if e['source'] in valid_names and e['target'] in valid_names:
            elements.append({
                'data': {
                    'id': f"{e['source']}_{e['target']}_{e['type']}",
                    'source': e['source'],
                    'target': e['target'],
                    'type': e['type']
                }
            })

    return elements


def get_suggestions(filters=None, Wn=DEFAULT_WN, Wh=DEFAULT_WH):
    """Returns top 5 prioritized nodes based on filters, using given hyperparameters."""
    if filters is None:
        filters = {}
    nodes = manager.get_all_nodes()
    filtered_nodes = manager.filter_nodes(nodes, filters)
    scored = manager.calculate_priority_scores(filtered_nodes, Wn=Wn, Wh=Wh)
    valid = [n for n in scored if getattr(n, 'priority_score', -1) >= 0]
    return valid[:5]


def _build_filters(f_context, f_done):
    """Builds a filter dictionary from UI state."""
    filters = {}
    if f_context and f_context != "All":
        filters['context'] = f_context if f_context != "None" else None
    if f_done and "hide_done" in f_done:
        filters['hide_done'] = True
    return filters


def _format_suggestions_table(suggs):
    """Formats the suggestion list into a Dash table component with scores normalized to 0-100."""
    if not suggs:
        return html.P("No suggestions found based on current filters and graph state.", className="text-muted")

    # Normalize scores to 0-100 range using min-max normalization
    raw_scores = [getattr(s, 'priority_score', 0) for s in suggs]
    min_score = min(raw_scores)
    max_score = max(raw_scores)
    score_range = max_score - min_score

    def normalize(score):
        if score_range == 0:
            return 100.0 if len(suggs) == 1 else 50.0
        return round(((score - min_score) / score_range) * 100, 1)

    table_header = [html.Thead(html.Tr([
        html.Th("Task"), html.Th("Context"), html.Th("Type"),
        html.Th("Priority Score"), html.Th("Unlocks")
    ]))]
    row_data = [html.Tr([
        html.Td(s.name),
        html.Td(str(s.context)),
        html.Td(s.type),
        html.Td(f"{normalize(getattr(s, 'priority_score', 0)):.1f}"),
        html.Td(", ".join(manager.get_directly_unlocked_nodes(s.name)) or "None")
    ]) for s in suggs]
    table_body = [html.Tbody(row_data)]
    return dbc.Table(table_header + table_body, bordered=True, hover=True, size="sm")


def _format_traversal_ui(tapped_node, active_node_id):
    """Formats the dependency chains and synergies views for a selected node."""
    traversal_ui = html.Div(className="text-muted", children="Select a node to see dependencies.")
    synergies_ui = html.Div(className="text-muted", children="Select a node to see synergies.")

    if not tapped_node:
        return traversal_ui, synergies_ui

    node_id = tapped_node.get('id')
    chains = manager.get_prerequisite_chains(node_id)

    # Gather synergies
    edges = manager.get_edges()
    synergies = [e['target'] for e in edges if e['source'] == node_id and e['type'] == 'Helps']
    synergies += [e['source'] for e in edges if e['target'] == node_id and e['type'] == 'Helps']
    synergies = list(set(synergies))

    # Format dependency chains
    if not chains:
        traversal_ui = html.P("None", className="text-dark")
    else:
        chain_items = []
        for c in chains:
            display_chain = c[:-1] if c and c[-1] == active_node_id else c
            if display_chain:
                chain_items.append(html.Div(" → ".join(display_chain)))
        traversal_ui = html.Div(chain_items) if chain_items else html.P("None", className="text-dark")

    # Format synergies
    if synergies:
        synergies_ui = html.Div([html.Div(s) for s in synergies])
    else:
        synergies_ui = html.P("None", className="text-dark")

    return traversal_ui, synergies_ui


# --- Callback Registration ---

def register_callbacks(app):
    """Registers all Dash callbacks on the given app."""

    @app.callback(
        Output('hover-tooltip', 'children'),
        Input('cytoscape-graph', 'mouseoverNodeData')
    )
    def display_hover_data(data):
        if not data:
            return ""

        lines = [
            html.Div([html.Strong("Type: "), data.get('type', '')]),
            html.Div([html.Strong("Status: "), data.get('status', '')]),
            html.Div([html.Strong("Context: "), data.get('context', '')]),
            html.Div([html.Strong("Value: "), str(data.get('value', ''))]),
            html.Div([html.Strong("Effort: "), str(data.get('effort', ''))]),
            html.Div([html.Strong("Time: "), f"{data.get('time', '')}h"]),
        ]

        if data.get('description'):
            lines.append(html.Div([html.Strong("Description: "), html.Span(data.get('description'), style={'whiteSpace': 'normal'})]))

        return lines

    @app.callback(
        [Output('node-name', 'value'), Output('node-type', 'value'), Output('node-desc', 'value'),
         Output('node-context', 'value'), Output('node-status', 'value'),
         Output('node-value', 'value'), Output('node-interest', 'value'),
         Output('node-time', 'value'), Output('node-effort', 'value'),
         Output('edge-needs', 'value'), Output('edge-supports', 'value'), Output('edge-helps', 'value'), Output('edge-resources', 'value'),
         Output('edge-needs', 'options'), Output('edge-supports', 'options'), Output('edge-helps', 'options'), Output('edge-resources', 'options')],
        [Input('cytoscape-graph', 'tapNodeData'),
         Input('btn-add', 'n_clicks'),
         Input('btn-clear', 'n_clicks'),
         Input('search-node', 'value'),
         Input('cytoscape-graph', 'elements')]
    )
    def populate_editor(data, add_clicks, clear_clicks, search_val, elements):
        ctx = dash.callback_context
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ""

        all_nodes = manager.get_all_nodes()
        options = [{'label': n.name, 'value': n.name} for n in all_nodes]

        if trigger_id in ['btn-add', 'btn-clear']:
            return ["", "Goal", "", "None", "Open", 5, 5, 1.0, 2, [], [], [], [], options, options, options, options]

        name = None
        if trigger_id == 'search-node' and search_val:
            search_val_lower = search_val.lower()
            matched = [n for n in all_nodes if search_val_lower in n.name.lower()]
            if matched:
                node = matched[0]
                name = node.name
                data = node.to_dict()
                data['id'] = name
            else:
                return [dash.no_update] * 13 + [options, options, options, options]
        elif data:
            name = data.get('id')

        if not name or not data:
            return [dash.no_update] * 13 + [options, options, options, options]

        edges = manager.get_edges()

        needs_vals = [e['source'] for e in edges if e['target'] == name and e['type'] == 'Needs']
        supports_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == 'Needs']
        helps_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == 'Helps']
        helps_vals += [e['source'] for e in edges if e['target'] == name and e['type'] == 'Helps']
        helps_vals = list(set(helps_vals))

        res_vals = [e['source'] for e in edges if e['target'] == name and e['type'] == 'Resource']

        filtered_options = [{'label': n.name, 'value': n.name} for n in all_nodes if n.name != name]

        return [
            name, data.get('type'), data.get('description'),
            data.get('context'), data.get('status'),
            data.get('value', 5), data.get('interest', 5),
            data.get('time', 1), data.get('effort', 2),
            needs_vals, supports_vals, helps_vals, res_vals,
            filtered_options, filtered_options, filtered_options, filtered_options
        ]

    @app.callback(
        [Output('cytoscape-graph', 'elements'), Output('save-output', 'children'),
         Output('suggestions-table', 'children'), Output('traversal-chains', 'children'),
         Output('synergies-list', 'children'),
         Output('clear-interval', 'disabled'), Output('clear-interval', 'n_intervals'),
         Output('filter-community', 'options')],
        [Input('btn-save', 'n_clicks'), Input('btn-delete', 'n_clicks'),
         Input('filter-context', 'value'), Input('filter-done', 'value'),
         Input('suggestion-algo', 'value'),
         Input('search-node', 'value'),
         Input('cytoscape-graph', 'tapNodeData'),
         Input('filter-community', 'value'),
         Input('community-method', 'value'),
         Input('hyperparams-store', 'data')],
        [State('node-name', 'value'), State('node-type', 'value'), State('node-desc', 'value'),
         State('node-context', 'value'), State('node-status', 'value'),
         State('node-value', 'value'), State('node-interest', 'value'),
         State('node-time', 'value'), State('node-effort', 'value'),
         State('edge-needs', 'value'), State('edge-supports', 'value'), State('edge-helps', 'value'), State('edge-resources', 'value'),
         State('cytoscape-graph', 'elements')]
    )
    def update_graph(save_clicks, delete_clicks, f_context, f_done, algo_val, search_val, tapped_node,
                     f_community, community_method, hp_data,
                     name, n_type, desc, context, status, val, interest, time, effort,
                     e_needs, e_supports, e_helps, e_res, current_elements):
        ctx = dash.callback_context
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ""
        msg = ""

        filters = _build_filters(f_context, f_done)

        # Determine active node for selection highlight
        active_node_id = None
        if trigger_id == 'search-node' and search_val:
            all_nodes = manager.get_all_nodes()
            search_val_lower = search_val.lower()
            matched = [n for n in all_nodes if search_val_lower in n.name.lower()]
            if matched:
                active_node_id = matched[0].name
        elif trigger_id == 'cytoscape-graph' and tapped_node:
            active_node_id = tapped_node.get('id')
        else:
            active_node_id = name

        # --- Save ---
        if trigger_id == 'btn-save' and name and n_type:
            try:
                node = Node(
                    name=name, type=n_type, description=desc or "",
                    value=val, time=time, interest=interest, effort=effort,
                    status=status or "Open", context=context
                )
            except (ValueError, TypeError):
                msg = "Error: Please check your inputs."
                return current_elements, msg, dash.no_update, dash.no_update, dash.no_update, False, 0, dash.no_update

            try:
                if manager.get_node(name):
                    manager.update_node(node)
                    msg = f"Updated node '{name}'"
                else:
                    manager.add_node(node)
                    msg = f"Added node '{name}'"

                manager.sync_edges(name, e_needs, e_supports, e_helps, e_res)

            except Exception as e:
                msg = str(e)

        # --- Delete ---
        elif trigger_id == 'btn-delete' and name:
            try:
                manager.delete_node(name)
                msg = f"Deleted node '{name}'"
            except Exception as e:
                msg = str(e)

        # --- Community Detection ---
        community_method = community_method or "components"
        communities = manager.detect_communities(method=community_method)
        community_options = [{"label": "All", "value": "All"}]
        for i, comm in enumerate(communities):
            label = f"Community {i+1} ({len(comm)} nodes)"
            community_options.append({"label": label, "value": str(i)})

        community_names = None
        if f_community and f_community != "All":
            try:
                idx = int(f_community)
                if 0 <= idx < len(communities):
                    community_names = communities[idx]
            except (ValueError, IndexError):
                pass

        # --- Regenerate Visuals ---
        elements = generate_elements(filters, active_node_id, community_names=community_names)

        # Read hyperparameters from store
        hp = hp_data or {}
        wn = hp.get('Wn', DEFAULT_WN)
        wh = hp.get('Wh', DEFAULT_WH)
        sugg_ui = _format_suggestions_table(get_suggestions(filters, Wn=wn, Wh=wh))
        traversal_ui, synergies_ui = _format_traversal_ui(tapped_node, active_node_id)

        return elements, msg, sugg_ui, traversal_ui, synergies_ui, False if msg else True, 0, community_options

    @app.callback(
        Output('save-output', 'children', allow_duplicate=True),
        Output('clear-interval', 'disabled', allow_duplicate=True),
        Input('clear-interval', 'n_intervals'),
        prevent_initial_call=True
    )
    def clear_message(n):
        if n > 0:
            return "", True
        return dash.no_update, dash.no_update

    # --- Hyperparameters Modal Callbacks ---

    @app.callback(
        Output('modal-hyperparams', 'is_open'),
        Output('input-wn', 'value'),
        Output('input-wh', 'value'),
        Output('input-wn-feedback', 'children'),
        Output('input-wh-feedback', 'children'),
        Output('hyperparams-store', 'data'),
        Input('btn-algo-settings', 'n_clicks'),
        Input('btn-hp-cancel', 'n_clicks'),
        Input('btn-hp-apply', 'n_clicks'),
        State('input-wn', 'value'),
        State('input-wh', 'value'),
        State('hyperparams-store', 'data'),
        prevent_initial_call=True
    )
    def handle_hyperparams_modal(open_clicks, cancel_clicks, apply_clicks,
                                  wn_val, wh_val, current_hp):
        ctx = dash.callback_context
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ""
        hp = current_hp or {'Wn': DEFAULT_WN, 'Wh': DEFAULT_WH}

        if trigger_id == 'btn-algo-settings':
            # Open modal, populate with persisted values from DB
            hp = manager.get_hyperparams()
            return True, hp['Wn'], hp['Wh'], "", "", hp

        if trigger_id == 'btn-hp-cancel':
            # Close without saving
            return False, hp['Wn'], hp['Wh'], "", "", dash.no_update

        if trigger_id == 'btn-hp-apply':
            # Validate inputs
            wn_err, wh_err = "", ""
            valid = True

            try:
                wn_parsed = float(wn_val)
                if wn_parsed < 0:
                    wn_err = "Value must be ≥ 0."
                    valid = False
            except (TypeError, ValueError):
                wn_err = "Please enter a valid number."
                valid = False

            try:
                wh_parsed = float(wh_val)
                if wh_parsed < 0:
                    wh_err = "Value must be ≥ 0."
                    valid = False
            except (TypeError, ValueError):
                wh_err = "Please enter a valid number."
                valid = False

            if not valid:
                return True, dash.no_update, dash.no_update, wn_err, wh_err, dash.no_update

            # Save to database and close
            manager.save_hyperparams(wn_parsed, wh_parsed)
            new_hp = {'Wn': wn_parsed, 'Wh': wh_parsed}
            return False, wn_parsed, wh_parsed, "", "", new_hp

        return dash.no_update, dash.no_update, dash.no_update, "", "", dash.no_update
