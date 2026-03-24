"""
Callback definitions for the Skill Tree Dash application.
"""

import logging
import math
import dash
import os
import subprocess
import urllib.parse
from dash import html, Input, Output, State
import dash_bootstrap_components as dbc
from graph_manager import GraphManager
from config import ConfigManager
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, EDGE_RESOURCE

logger = logging.getLogger(__name__)

manager = GraphManager()


def _get_trigger_id():
    """Return the component ID that triggered the current callback, or '' if none."""
    ctx = dash.callback_context
    return ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ""


def _node_options(nodes, exclude=None):
    """Build dropdown options from a list of nodes, optionally excluding one by name."""
    return [{'label': n.name, 'value': n.name} for n in nodes if n.name != exclude]

def generate_elements(filters=None, active_node_id=None, community_names=None):
    """Convert nodes and edges from the database into Cytoscape-compatible element dicts."""
    if filters is None: filters = {}
    nodes = manager.get_all_nodes()
    filtered_nodes = manager.filter_nodes(nodes, filters)

    if community_names is not None:
        filtered_nodes = [n for n in filtered_nodes if n.name in community_names]

    valid_names = {n.name for n in filtered_nodes}
    edges = manager.get_edges()

    colors = ConfigManager.get_node_colors()
    shapes = ConfigManager.get_node_shapes()

    elements = []
    for node in filtered_nodes:
        node_data = {
            'data': {
                'id': node.name,
                'label': node.name,
                'color': colors.get(node.status, '#888'),
                'shape': shapes.get(node.type, 'rectangle'),
                **node.to_dict()
            },
            'selected': node.name == active_node_id if active_node_id else False
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


def get_suggestions(filters=None, count=5):
    if filters is None: filters = {}
    nodes = manager.get_all_nodes()
    filtered_nodes = manager.filter_nodes(nodes, filters)
    scored = manager.calculate_priority_scores(filtered_nodes)
    valid = [n for n in scored if getattr(n, 'priority_score', -1) >= 0]
    return valid[:count]


def _build_filters(f_context, f_subcontext, f_done, f_value=1, f_interest=1, f_time=None, f_difficulty="All"):
    """Build a filter dict from sidebar filter component values for use with GraphManager.filter_nodes()."""
    filters = {}
    if f_context and f_context != "All":
        filters['context'] = f_context if f_context != "None" else None
    if f_subcontext and f_subcontext != "All" and f_subcontext.strip():
        filters['subcontext'] = f_subcontext.strip()
    if f_done and "hide_done" in f_done:
        filters['hide_done'] = True
    if f_value and f_value > 1:
        filters['min_value'] = f_value
    if f_interest and f_interest > 1:
        filters['min_interest'] = f_interest
    if f_time is not None and f_time != "" and f_time != 0:
        try: filters['max_time'] = float(f_time)
        except (ValueError, TypeError): pass
    if f_difficulty and f_difficulty != "All":
        try: filters['max_difficulty'] = int(f_difficulty)
        except (ValueError, TypeError): pass
    return filters


def _format_suggestions_table(suggs):
    """Render the top-scored nodes as an HTML table with normalized priority scores (0-100)."""
    if not suggs:
        return html.P("No suggestions found based on current filters and graph state.", className="text-muted")

    raw_scores = [getattr(s, 'priority_score', 0) for s in suggs]
    max_score = max(raw_scores)

    def normalize(score):
        if max_score == 0:
            return 0.0
        return round((score / max_score) * 100, 1)

    table_header = [html.Thead(html.Tr([
        html.Th("Task"), html.Th("Priority"), html.Th("Type"), html.Th("Context"),
        html.Th("Subcontext"), html.Th("Value"), html.Th("Difficulty"), html.Th("Time"),
        html.Th("Unlocks")
    ]))]
    row_data = [html.Tr([
        html.Td(s.name),
        html.Td(f"{normalize(getattr(s, 'priority_score', 0)):.1f}"),
        html.Td(s.type),
        html.Td(str(s.context)),
        html.Td(str(s.subcontext) if s.subcontext else "None"),
        html.Td(str(s.value)),
        html.Td(str(s.difficulty)),
        html.Td(f"{round(s.time)}h"),
        html.Td(", ".join(manager.get_directly_unlocked_nodes(s.name)) or "None")
    ]) for s in suggs]
    return dbc.Table(table_header + [html.Tbody(row_data)], bordered=True, hover=True,
                     style={"width": "fit-content", "minWidth": "50%", "tableLayout": "auto"})


def _format_traversal_ui(tapped_node, active_node_id):
    """Build the dependency chains and synergies display for the selected node."""
    traversal_ui = html.Div(className="text-muted", children="Select a node to see dependencies.")
    synergies_ui = html.Div(className="text-muted", children="Select a node to see synergies.")

    if not tapped_node: return traversal_ui, synergies_ui

    node_id = tapped_node.get('id')
    chains = manager.get_prerequisite_chains(node_id)

    edges = manager.get_edges()
    synergies = [e['target'] for e in edges if e['source'] == node_id and e['type'] == EDGE_HELPS]
    synergies += [e['source'] for e in edges if e['target'] == node_id and e['type'] == EDGE_HELPS]
    synergies = list(set(synergies))

    if not chains:
        traversal_ui = html.P("None", className="text-dark")
    else:
        chain_items = []
        for c in chains:
            display_chain = c[:-1] if c and c[-1] == active_node_id else c
            if display_chain:
                chain_items.append(html.Div(" → ".join(display_chain), style={"overflowWrap": "break-word"}))
        traversal_ui = html.Div(chain_items) if chain_items else html.P("None", className="text-dark")

    synergies_ui = html.Div([html.Div(s) for s in synergies]) if synergies else html.P("None", className="text-dark")

    return traversal_ui, synergies_ui


def _handle_save(name, n_type, desc, val, time_o, time_m, time_p, interest, diff,
                  status_done, context, subctx, obs_path, drive_path,
                  e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps, e_res):
    """Create or update a node and sync its edges. Returns a status message."""
    # target_status: what the user selected in the form (Done or Open).
    # graph_manager may override to "Blocked" after sync_edges if hard prerequisites aren't met.
    target_status = "Done" if (status_done and "Done" in status_done) else "Open"
    node = Node(
        name=name, type=n_type, description=desc or "",
        value=val, time_o=time_o, time_m=time_m, time_p=time_p,
        interest=interest, difficulty=diff,
        status=target_status, context=context, subcontext=(subctx or '').strip() or None,
        obsidian_path=(obs_path or '').strip() or None,
        google_drive_path=(drive_path or '').strip() or None
    )
    if manager.get_node(name):
        manager.update_node(node)
        msg = f"Updated node '{name}'"
    else:
        manager.add_node(node)
        msg = f"Added node '{name}'"
    manager.sync_edges(name, e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps, e_res)
    return msg


def _handle_delete(name):
    """Delete a single node by name. Returns a status message."""
    manager.delete_node(name)
    return f"Deleted node '{name}'"


def _handle_toggle_done(tapped_node):
    """Toggle a node's status between Done and Open. Returns a status message."""
    node = manager.get_node(tapped_node.get('id'))
    if node:
        node.status = "Open" if node.status == "Done" else "Done"
        manager.update_node(node)
        return f"Toggled status of '{node.name}' to {node.status}"
    return ""


def _handle_group_delete(group_delete_data):
    """Delete multiple nodes from a JSON-encoded list. Returns a status message."""
    import json
    # JS sends "["name1","name2"]|timestamp" — strip the timestamp suffix
    raw = group_delete_data.split('|')[0] if isinstance(group_delete_data, str) else ''
    names = json.loads(raw) if raw else []
    for node_name in names:
        manager.delete_node(node_name)
    return f"Deleted {len(names)} node(s)" if names else ""


def register_callbacks(app):
    """Register all Dash callbacks for the application."""

    # --- Tooltip Formatting ---
    @app.callback(
        Output('hover-tooltip', 'children'),
        Input('cytoscape-graph', 'mouseoverNodeData')
    )
    def display_hover_data(data):
        if not data: return ""

        o = float(data.get('time_o', 0))
        m = float(data.get('time_m', 0))
        p = float(data.get('time_p', 0))
        final_time = data.get('time', 0)
        
        # Standard deviation (PERT method)
        std_dev = 0.0
        if m > 0 and o > 0 and p > 0 and not (o == m == p):
            std_dev = round((p - o) / 6.0, 2)
            
        std_str = f" ±{std_dev}" if std_dev > 0 else ""
        time_str = f"{final_time}h{std_str}"

        lines = [
            html.Div(html.Strong(data.get('label', data.get('id', ''))),
                     style={"fontSize": "0.95rem", "marginBottom": "4px", "borderBottom": "1px solid #495057", "paddingBottom": "4px"}),
            html.Div([html.Strong("Type: "), data.get('type', '')]),
            html.Div([html.Strong("Status: "), data.get('status', '')]),
            html.Div([html.Strong("Context: "), data.get('context', '')]),
            html.Div([html.Strong("Value: "), str(data.get('value', ''))]),
            html.Div([html.Strong("Difficulty: "), str(data.get('difficulty', ''))]),
            html.Div([html.Strong("Time: "), time_str]),
        ]

        if data.get('description'):
            lines.append(html.Div([html.Strong("Desc: "), html.Span(data.get('description'), style={'whiteSpace': 'normal'})]))

        return lines

    # --- Editor Form Population ---
    @app.callback(
        [Output('node-name', 'value'), Output('node-type', 'value'), Output('node-desc', 'value'),
         Output('node-context', 'value'), Output('node-subcontext', 'value'),
         Output('node-value', 'value'), Output('node-interest', 'value'), Output('node-difficulty', 'value'),
         Output('node-time-o', 'value'), Output('node-time-m', 'value'), Output('node-time-p', 'value'),
         Output('auto-status-display', 'children'), Output('node-status-done', 'value'),
         Output('edge-needs-hard', 'value'), Output('edge-needs-soft', 'value'),
         Output('edge-supports-hard', 'value'), Output('edge-supports-soft', 'value'),
         Output('edge-helps', 'value'), Output('edge-resources', 'value'),
         Output('edge-needs-hard', 'options'), Output('edge-needs-soft', 'options'),
         Output('edge-supports-hard', 'options'), Output('edge-supports-soft', 'options'),
         Output('edge-helps', 'options'), Output('edge-resources', 'options'),
         Output('node-obsidian-path', 'value'), Output('node-google-drive-path', 'value')],
        [Input('cytoscape-graph', 'tapNodeData'),
         Input('btn-add', 'n_clicks'),
         Input('btn-clear', 'n_clicks'),
         Input('search-node', 'value'),
         Input('cytoscape-graph', 'elements')]
    )
    def populate_editor(data, add_clicks, clear_clicks, search_val, elements):
        """Populate the editor sidebar form fields when a node is selected, searched, or cleared."""
        trigger_id = _get_trigger_id()

        all_nodes = manager.get_all_nodes()
        options = _node_options(all_nodes)

        def_out = [
            "", "Topic", "", "None", "", 5, 5, 5, 1.0, 1.0, 1.0, "Open", [],
            [], [], [], [], [], [],
            options, options, options, options, options, options,
            "", ""
        ]

        if trigger_id in ['btn-add', 'btn-clear']:
            return def_out

        name = None
        if trigger_id == 'search-node' and search_val:
            node = manager.get_node(search_val)
            if node:
                name = node.name
                data = node.to_dict()
                data['id'] = name
            else:
                return [dash.no_update] * 19 + [options]*6 + [dash.no_update]*2
        elif data:
            name = data.get('id')

        if not name or not data:
            return [dash.no_update] * 19 + [options]*6 + [dash.no_update]*2
            
        edges = manager.get_edges()

        # In/Out Edges mapping
        needs_hard_vals = [e['source'] for e in edges if e['target'] == name and e['type'] == EDGE_NEEDS_HARD]
        needs_soft_vals = [e['source'] for e in edges if e['target'] == name and e['type'] == EDGE_NEEDS_SOFT]
        supp_hard_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == EDGE_NEEDS_HARD]
        supp_soft_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == EDGE_NEEDS_SOFT]

        helps_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == EDGE_HELPS]
        helps_vals += [e['source'] for e in edges if e['target'] == name and e['type'] == EDGE_HELPS]
        helps_vals = list(set(helps_vals))
        res_vals = [e['source'] for e in edges if e['target'] == name and e['type'] == EDGE_RESOURCE]

        filtered_options = _node_options(all_nodes, exclude=name)

        # actual_status: the authoritative status from the DB (may be Blocked/Open/Done),
        # as opposed to the Cytoscape data dict which may be stale after state cascades.
        db_node = manager.get_node(name)
        actual_status = db_node.status if db_node else data.get('status', 'Open')
        done_val = ["Done"] if actual_status == "Done" else []

        return [
            name, data.get('type'), data.get('description'),
            data.get('context'), data.get('subcontext', ''),
            data.get('value', 5), data.get('interest', 5), data.get('difficulty', 5),
            data.get('time_o', 1.0), data.get('time_m', 1.0), data.get('time_p', 1.0),
            actual_status, done_val,
            needs_hard_vals, needs_soft_vals, supp_hard_vals, supp_soft_vals,
            helps_vals, res_vals,
            filtered_options, filtered_options, filtered_options, filtered_options, filtered_options, filtered_options,
            data.get('obsidian_path', ''), data.get('google_drive_path', '')
        ]

    # --- Core State: Save, Delete, Render ---
    @app.callback(
        [Output('cytoscape-graph', 'elements'), Output('save-output', 'children'),
         Output('suggestions-table', 'children'), Output('traversal-chains', 'children'),
         Output('synergies-list', 'children'),
         Output('clear-interval', 'disabled'), Output('clear-interval', 'n_intervals'),
         Output('filter-community', 'options'), Output('search-node', 'options'),
         Output('sidebar-editor-container', 'style'), Output('sidebar-filters-container', 'style'),
         Output('filter-context', 'options'), Output('node-context', 'options'),
         Output('node-type', 'options')],
        
        [Input('btn-save', 'n_clicks'), Input('btn-delete', 'n_clicks'),
         Input('filter-context', 'value'), Input('filter-subcontext', 'value'), Input('filter-done', 'value'),
         Input('search-node', 'value'),
         Input('cytoscape-graph', 'tapNodeData'),
         Input('filter-community', 'value'), Input('community-method', 'value'),
         Input('filter-value', 'value'), Input('filter-interest', 'value'),
         Input('filter-time', 'value'), Input('filter-difficulty', 'value'),
         Input('suggestion-count-store', 'data'),
         Input('btn-edit-node', 'n_clicks'), Input('btn-add', 'n_clicks'),
         Input('btn-close-editor', 'n_clicks'),
         Input('btn-filters-toggle', 'n_clicks'), Input('btn-close-filters', 'n_clicks'),
         Input('modal-settings', 'is_open'),
         Input('btn-toggle-done-node', 'n_clicks'),
         Input('group-delete-input', 'value')],
        
        [State('node-name', 'value'), State('node-type', 'value'), State('node-desc', 'value'),
         State('node-context', 'value'), State('node-subcontext', 'value'), State('node-status-done', 'value'),
         State('node-value', 'value'), State('node-interest', 'value'), State('node-difficulty', 'value'),
         State('node-time-o', 'value'), State('node-time-m', 'value'), State('node-time-p', 'value'),
         State('edge-needs-hard', 'value'), State('edge-needs-soft', 'value'),
         State('edge-supports-hard', 'value'), State('edge-supports-soft', 'value'),
         State('edge-helps', 'value'), State('edge-resources', 'value'),
         State('node-obsidian-path', 'value'), State('node-google-drive-path', 'value'),
         State('cytoscape-graph', 'elements'),
         State('sidebar-editor-container', 'style'), State('sidebar-filters-container', 'style')]
    )
    def core_engine(save_clicks, delete_clicks, f_context, f_subcontext, f_done, search_val,
                     tapped_node,  # Cytoscape tapNodeData dict (not a Node object)
                     f_community, community_method, f_value, f_interest, f_time, f_difficulty, sugg_count,
                     btn_edit, btn_add, btn_close_ed, btn_filters, btn_close_fil, settings_open, btn_toggle_done,
                     group_delete_data,
                     name, n_type, desc, context, subctx, status_done, val, interest, diff,
                     time_o, time_m, time_p,
                     e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps, e_res,
                     obs_path, drive_path, current_elements, ed_style, fil_style):
        """Central state callback handling node CRUD, filtering, and UI updates.

        This is intentionally a single large callback because Dash requires each Output
        to belong to exactly one callback. Since save/delete/filter operations all need
        to refresh the graph elements and sidebar state, they must share one callback.
        """
                     
        trigger_id = _get_trigger_id()
        msg = ""

        filters = _build_filters(f_context, f_subcontext, f_done, f_value, f_interest, f_time, f_difficulty)

        # Editor Sidebar State (380px matches sidebar_content width in layout.py)
        next_ed_style = ed_style or {"width": "380px", "minWidth": "380px", "marginLeft": "-380px", "overflowX": "hidden", "overflowY": "auto", "borderRight": "1px solid #495057", "transition": "margin-left 0.3s ease", "backgroundColor": "#212529"}
        if trigger_id in ('btn-edit-node', 'btn-add') or (trigger_id == 'search-node' and search_val):
            next_ed_style['marginLeft'] = "0px"
        elif trigger_id in ('btn-save', 'btn-clear', 'btn-delete', 'btn-close-editor'):
            next_ed_style['marginLeft'] = "-380px"

        # Filters Sidebar State (320px matches filters_content width in layout.py)
        next_fil_style = fil_style or {"width": "320px", "minWidth": "320px", "marginRight": "-320px", "overflowX": "hidden", "overflowY": "auto", "borderLeft": "1px solid #495057", "transition": "margin-right 0.3s ease", "backgroundColor": "#212529"}
        if trigger_id == 'btn-filters-toggle':
            next_fil_style['marginRight'] = "0px" if next_fil_style.get('marginRight', '-320px') == "-320px" else "-320px"
        elif trigger_id == 'btn-close-filters':
            next_fil_style['marginRight'] = "-320px"

        active_node_id = None
        if trigger_id == 'search-node' and search_val: active_node_id = search_val
        elif trigger_id == 'cytoscape-graph' and tapped_node: active_node_id = tapped_node.get('id')
        else: active_node_id = name

        # --- Action Routing ---
        if trigger_id in ('btn-save', 'btn-close-editor') and name and n_type:
            try:
                msg = _handle_save(name, n_type, desc, val, time_o, time_m, time_p,
                                   interest, diff, status_done, context, subctx,
                                   obs_path, drive_path, e_needs_h, e_needs_s,
                                   e_supp_h, e_supp_s, e_helps, e_res)
            except (ValueError, TypeError):
                msg = "Error: Please check your mathematical inputs."
                return current_elements, msg, dash.no_update, dash.no_update, dash.no_update, False, 0, dash.no_update, dash.no_update, next_ed_style, next_fil_style, dash.no_update, dash.no_update, dash.no_update
            except Exception as e:
                msg = str(e)

        elif trigger_id == 'btn-delete' and name:
            try:
                msg = _handle_delete(name)
            except Exception as e:
                msg = str(e)

        elif trigger_id == 'btn-toggle-done-node' and tapped_node:
            try:
                msg = _handle_toggle_done(tapped_node)
            except Exception as e:
                msg = str(e)

        elif trigger_id == 'group-delete-input' and group_delete_data:
            try:
                msg = _handle_group_delete(group_delete_data)
            except Exception as e:
                msg = str(e)

        # --- Visual Generation ---
        community_method = community_method or "components"
        communities = manager.detect_communities(method=community_method, filters=filters)
        community_options = [{"label": "All", "value": "All"}]
        for i, comm in enumerate(communities):
            community_options.append({"label": f"Community {i+1} ({len(comm)} nodes)", "value": str(i)})

        community_names = None
        if f_community and f_community != "All":
            try:
                idx = int(f_community)
                if 0 <= idx < len(communities):
                    community_names = communities[idx]
            except (ValueError, IndexError): pass

        elements = generate_elements(filters, active_node_id, community_names=community_names)

        count = sugg_count if sugg_count else 5
        sugg_ui = _format_suggestions_table(get_suggestions(filters, count=count))
        traversal_ui, synergies_ui = _format_traversal_ui(tapped_node, active_node_id)

        all_nodes = manager.get_all_nodes()
        search_options = _node_options(all_nodes)
        
        # Populate dynamic contexts datalists from DB + Config preserving defined order
        base_ctx = ConfigManager.get_contexts()
        
        ctx_list = [{"label": c, "value": c} for c in base_ctx]
        f_ctx_list = [{"label": "All", "value": "All"}] + ctx_list

        base_types = ConfigManager.get_node_types()
        type_list = [{"label": t, "value": t} for t in base_types]

        return elements, msg, sugg_ui, traversal_ui, synergies_ui, False if msg else True, 0, community_options, search_options, next_ed_style, next_fil_style, f_ctx_list, ctx_list, type_list

    @app.callback(
        Output('save-output', 'children', allow_duplicate=True),
        Output('clear-interval', 'disabled', allow_duplicate=True),
        Input('clear-interval', 'n_intervals'),
        prevent_initial_call=True
    )
    def clear_message(n):
        if n > 0: return "", True
        return dash.no_update, dash.no_update

    @app.callback(
        Output('node-subcontext', 'options'),
        Input('node-context', 'value')
    )
    def update_node_subcontexts(ctx):
        if not ctx or ctx == "None": return []
        subs = ConfigManager.get_subcontexts().get(ctx, [])
        return [{"label": s, "value": s} for s in subs]

    @app.callback(
        Output('filter-subcontext', 'options'),
        Input('filter-context', 'value')
    )
    def update_filter_subcontexts(ctx):
        base = [{"label": "All", "value": "All"}]
        if not ctx or ctx == "All": return base
        subs = ConfigManager.get_subcontexts().get(ctx, [])
        return base + [{"label": s, "value": s} for s in subs]

    # --- Suggestion Count +/- Callbacks ---
    @app.callback(
        Output('suggestion-count-store', 'data'),
        Output('suggestion-count-display', 'children'),
        Input('btn-sugg-plus', 'n_clicks'),
        Input('btn-sugg-minus', 'n_clicks'),
        State('suggestion-count-store', 'data'),
        prevent_initial_call=True
    )
    def update_suggestion_count(plus, minus, current_count):
        trigger_id = _get_trigger_id()
        count = current_count or 5
        if trigger_id == 'btn-sugg-plus': count = min(15, count + 1)
        elif trigger_id == 'btn-sugg-minus': count = max(1, count - 1)
        return count, str(count)

    # --- Settings Modal ---
    @app.callback(
        Output('modal-settings', 'is_open'),
        [Output('hp-wv', 'value'), Output('hp-wi', 'value'),
         Output('hp-dh', 'value'), Output('hp-ds', 'value'), Output('hp-dsyn', 'value'),
         Output('hp-we', 'value'), Output('hp-wt', 'value'), Output('hp-beta', 'value'),
         Output('setting-node-types', 'value'),
         Output('setting-contexts', 'value'),
         Output('setting-subcontexts', 'value'),
         Output('setting-hp-profile', 'value'),
         Output('setting-obsidian-path', 'value')],
        [Input('btn-settings-toggle', 'n_clicks'),
         Input('btn-settings-cancel', 'n_clicks'),
         Input('btn-settings-save', 'n_clicks'),
         Input('setting-hp-profile', 'value')],
        [State('hp-wv', 'value'), State('hp-wi', 'value'),
         State('hp-dh', 'value'), State('hp-ds', 'value'), State('hp-dsyn', 'value'),
         State('hp-we', 'value'), State('hp-wt', 'value'), State('hp-beta', 'value'),
         State('setting-node-types', 'value'),
         State('setting-contexts', 'value'),
         State('setting-subcontexts', 'value'),
         State('setting-obsidian-path', 'value')],
        prevent_initial_call=True
    )
    def manage_settings_modal(open_cm, cancel_cm, save_cm, profile_val,
                              wv, wi, dh, ds, dsyn, we, wt, beta, n_types_val, contexts_val, subcontexts_val, obs_path):
        trigger_id = _get_trigger_id()

        if trigger_id == 'btn-settings-toggle':
            # Load stored config
            hp = ConfigManager.get_hyperparams()
            obs = ConfigManager.get_obsidian_vault()
            ntypes = ", ".join(ConfigManager.get_node_types())
            ctxts = ", ".join(ConfigManager.get_contexts())
            s_dict = ConfigManager.get_subcontexts()
            subctxts_lines = []
            for k, v in s_dict.items():
                if v:
                    subctxts_lines.append(f"{k}: {', '.join(v)}")
            subctxts = "\n".join(subctxts_lines)
            return True, hp.get('w_v'), hp.get('w_i'), hp.get('d_H'), hp.get('d_S'), hp.get('d_Syn'), hp.get('w_e'), hp.get('w_t'), hp.get('beta'), ntypes, ctxts, subctxts, "Custom", obs
            
        if trigger_id == 'setting-hp-profile':
            from config import PROFILES
            if profile_val in PROFILES:
                p = PROFILES[profile_val]
                return True, p['w_v'], p['w_i'], p['d_H'], p['d_S'], p['d_Syn'], p['w_e'], p['w_t'], p['beta'], dash.no_update, dash.no_update, dash.no_update, profile_val, dash.no_update
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
            
        if trigger_id == 'btn-settings-save':
            try:
                new_hp = {
                    'w_v': float(wv), 'w_i': float(wi),
                    'd_H': float(dh), 'd_S': float(ds), 'd_Syn': float(dsyn),
                    'w_e': float(we), 'w_t': float(wt), 'beta': float(beta)
                }
                ConfigManager.set_hyperparams(new_hp)
                ConfigManager.set_obsidian_vault(obs_path)
                
                # Parse comma-separated lists
                if n_types_val is not None:
                    n_list = [c.strip() for c in n_types_val.split(',') if c.strip()]
                    ConfigManager.set_node_types(n_list)
                if contexts_val is not None:
                    c_list = [c.strip() for c in contexts_val.split(',') if c.strip()]
                    ConfigManager.set_contexts(c_list)

                # Parse subcontexts: one context per line, comma-separated subs
                # Format: "Mind: Rational, Sensory\nBody: Stress, Sleep"
                if subcontexts_val is not None:
                    s_dict = {}
                    for line in subcontexts_val.split('\n'):
                        line = line.strip()
                        if ':' in line:
                            ctx_name, subs_str = line.split(':', 1)
                            ctx_name = ctx_name.strip()
                            subs = [s.strip() for s in subs_str.split(',') if s.strip()]
                            if ctx_name and subs:
                                # Merge if same context appears on multiple lines
                                if ctx_name in s_dict:
                                    s_dict[ctx_name].extend(subs)
                                else:
                                    s_dict[ctx_name] = subs
                    ConfigManager.set_subcontexts(s_dict)
                
            except Exception:
                logger.exception("Failed to save settings")
            return False, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        if trigger_id == 'btn-settings-cancel':
            return False, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
            
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    # --- Subcontext Collapse Toggle ---
    @app.callback(
        Output("collapse-subcontext", "is_open"),
        [Input("btn-subcontext-toggle", "n_clicks")],
        [State("collapse-subcontext", "is_open")],
    )
    def toggle_subcontext(n, is_open):
        if n: return not is_open
        return is_open

    # --- Obsidian Integration Callbacks ---
    @app.callback(
        Output('node-obsidian-path', 'value', allow_duplicate=True),
        Input('btn-obsidian-browse', 'n_clicks'),
        prevent_initial_call=True
    )
    def handle_obsidian_browse(n_clicks):
        if not n_clicks:
            return dash.no_update
        vault = ConfigManager.get_obsidian_vault()
        try:
            import tempfile
            import sys
            
            script = f'''import tkinter as tk
            from tkinter import filedialog
            import os
            import ctypes

            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)

            abs_path = filedialog.askopenfilename(
                initialdir=r"{vault}",
                title="Select Obsidian File",
                filetypes=[("Markdown files", "*.md"), ("All files", "*.*")]
            )

            if abs_path:
                print(os.path.normpath(abs_path), end="")
            '''
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
                f.write(script)
                tmp_path = f.name
                
            result = subprocess.run([sys.executable, tmp_path], capture_output=True, text=True)
            os.remove(tmp_path)
            
            abs_path = result.stdout.strip()
            
            if not abs_path:
                return dash.no_update

            vault_norm = os.path.normpath(vault)
            if abs_path.startswith(vault_norm):
                rel = abs_path[len(vault_norm):].lstrip(os.sep)
            else:
                rel = abs_path
                
            return rel
        except Exception as e:
            logger.error(f"Error browsing obsidian: {e}")
            return dash.no_update

    @app.callback(
        Output('save-output', 'children', allow_duplicate=True),
        Input('btn-obsidian-open', 'n_clicks'),
        State('node-obsidian-path', 'value'),
        prevent_initial_call=True
    )
    def handle_obsidian_open(n_clicks, rel_path):
        if not n_clicks:
            return dash.no_update
        if not rel_path or not rel_path.strip():
            return "No Obsidian file path set for this node."
        
        vault = ConfigManager.get_obsidian_vault()
        abs_path = os.path.join(vault, rel_path.strip())
        encoded = urllib.parse.quote(abs_path, safe='')
        uri = f'obsidian://open?path={encoded}'
        try:
            subprocess.Popen(['cmd', '/c', 'start', '', uri], shell=False)
            return dash.no_update
        except Exception as e:
            return f"Error opening Obsidian: {str(e)}"

    @app.callback(
        Output('save-output', 'children', allow_duplicate=True),
        [Input('btn-drive-open', 'n_clicks'),
         Input('btn-website-open', 'n_clicks')],
        [State('node-google-drive-path', 'value'),
         State('node-website-path', 'value')],
        prevent_initial_call=True
    )
    def handle_external_links(drive_clicks, web_clicks, drive_path, web_path):
        trigger_id = _get_trigger_id()
        if not trigger_id:
            return dash.no_update
        
        # Grab the correct URL based on the button clicked
        url = None
        if trigger_id == 'btn-drive-open' and drive_path:
            url = drive_path.strip()
        elif trigger_id == 'btn-website-open' and web_path:
            url = web_path.strip()
            
        if not url:
            return "No URL set for this specific link."
            
        # Ensure it has a protocol so it doesn't route internally
        if not url.startswith('http://') and not url.startswith('https://'):
            url = 'https://' + url
            
        import webbrowser
        try:
            webbrowser.open_new_tab(url)
            return dash.no_update
        except Exception as e:
            return f"Error opening URL: {str(e)}"

