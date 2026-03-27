"""
Callback definitions for the Skill Tree Dash application.
"""

import logging
import dash
import os
import subprocess
import urllib.parse
from dash import html, Input, Output, State, ALL, ctx
import dash_bootstrap_components as dbc
from graph_manager import GraphManager
from config import ConfigManager
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, EDGE_RESOURCE

logger = logging.getLogger(__name__)

manager = GraphManager()

SECTION_TITLE_STYLE = {"fontSize": "1.3rem", "fontWeight": "600"}


def _parse_links(db_value):
    """Parse a DB field that may contain a JSON array or a plain string into a list."""
    import json as _json
    if not db_value:
        return ['']
    try:
        parsed = _json.loads(db_value)
        if isinstance(parsed, list):
            return parsed if parsed else ['']
    except (ValueError, TypeError):
        pass
    return [db_value]


def _serialize_links(values_list):
    """Serialize a list of link input values into a JSON string for DB storage."""
    import json as _json
    if not values_list:
        return None
    links = [v.strip() for v in values_list if v and v.strip()]
    if not links:
        return None
    return _json.dumps(links)


def _get_trigger_id():
    """Return the component ID that triggered the current callback, or '' if none."""
    ctx = dash.callback_context
    return ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ""


def _node_options(nodes, exclude=None):
    """Build dropdown options from a list of nodes, optionally excluding one by name."""
    return [{'label': n.name, 'value': n.name} for n in nodes if n.name != exclude]


def _spawn_local_file_picker(initial_dir, title, filetypes_list):
    """Helper to launch a non-blocking Windows file picker via a temporary Python script."""
    import tempfile
    import sys
    import subprocess
    import os
    
    # Format the filetypes list as a string to inject into the script
    filetypes_str = str(filetypes_list)
    
    script = f'''import tkinter as tk
from tkinter import filedialog
import ctypes

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)

abs_path = filedialog.askopenfilename(
    initialdir=r"{initial_dir}",
    title="{title}",
    filetypes={filetypes_str}
)

if abs_path:
    print(os.path.normpath(abs_path), end="")
'''
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(script)
            tmp_path = f.name
            
        result = subprocess.run([sys.executable, tmp_path], capture_output=True, text=True)
        os.remove(tmp_path)
        
        return result.stdout.strip()
        
    except Exception as e:
        logger.error(f"Error launching file picker: {e}")
        return ""


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
    priority_goals = ConfigManager.get_priority_goals()
    scored = manager.calculate_priority_scores(filtered_nodes, priority_goals=priority_goals)
    valid = [n for n in scored if getattr(n, 'priority_score', -1) >= 0]
    return valid[:count]


def _build_filters(f_context, f_subcontext, f_done, f_value=1, f_interest=1, f_time=None, f_difficulty="All", f_node_types=None, f_goal=None):
    """Build a filter dict from sidebar filter component values for use with GraphManager.filter_nodes()."""
    filters = {}
    if f_context and f_context != "All":
        filters['context'] = f_context if f_context != "None" else None
    if f_subcontext and f_subcontext != "All" and f_subcontext.strip():
        filters['subcontext'] = f_subcontext.strip()
    if f_node_types and f_node_types != "All":
        filters['node_types'] = [f_node_types]
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
    if f_goal and f_goal != "All":
        filters['goal'] = f_goal
    return filters


def _format_suggestions_table(suggs, selected_node_id=None):
    """Render the top-scored nodes as an HTML table with normalized priority scores (0-100)."""
    if not suggs:
        return html.P("No suggestions found based on current filters and graph state.", className="text-muted")

    raw_scores = [getattr(s, 'priority_score', 0) for s in suggs]
    max_score = max(raw_scores)

    def normalize(score):
        if max_score == 0:
            return 0.0
        return round((score / max_score) * 100, 1)

    edges = manager.get_edges()

    table_header = [html.Thead(html.Tr([
        html.Th("Name"), html.Th("Priority"), html.Th("Type"), html.Th("Context"),
        html.Th("Subcontext"), html.Th("Value"), html.Th("Effort"), html.Th("Time"),
        html.Th("Unlocks"), html.Th("Resources")
    ]))]

    row_data = []
    for s in suggs:
        is_selected = (s.name == selected_node_id)
        # Subtle highlight for the selected row
        row_class = "table-active" if is_selected else ""

        node_res = [e['source'] for e in edges if e['target'] == s.name and e['type'] == EDGE_RESOURCE]
        res_str = ", ".join(node_res) if node_res else "None"

        row_data.append(html.Tr([
            html.Td(html.Span(
                s.name,
                id={"type": "suggestion-name-link", "index": s.name},
                title="Go to this node in the Nodes tab",
                style={"cursor": "pointer"},
            )),
            html.Td(str(round(normalize(getattr(s, 'priority_score', 0))))),
            html.Td(s.type),
            html.Td(str(s.context)),
            html.Td(str(s.subcontext) if s.subcontext else "None"),
            html.Td(str(s.value)),
            html.Td(str(s.difficulty)),
            html.Td(f"{round(s.time)}h"),
            html.Td(", ".join(manager.get_directly_unlocked_nodes(s.name)) or "None"),
            html.Td(res_str)
        ], id={"type": "suggestion-row", "index": s.name}, className=row_class, style={"cursor": "pointer"}))
        
    table = dbc.Table(table_header + [html.Tbody(row_data)], bordered=True, hover=True,
                     style={"width": "fit-content", "minWidth": "50%", "tableLayout": "auto"})

    node = None
    if selected_node_id:
        node = next((n for n in suggs if n.name == selected_node_id), None)
        if not node:
            node = manager.get_node(selected_node_id)
    
    desc_content = node.description.strip() if node and node.description and node.description.strip() else "None"
    
    desc_area = html.Div([
        html.H6("Description", className="text-muted mb-2", style=SECTION_TITLE_STYLE),
        html.Div(desc_content, style={"color": "#dee2e6", "whiteSpace": "pre-wrap", "fontSize": "0.95rem"})
    ], className="mt-4", style={"maxWidth": "800px"})

    return [table, desc_area]


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
                  status_done, context, subctx, obs_path, drive_path, website_path,
                  e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps, e_res,
                  habit_status_val=None, habit_freq=None, sess_lower=None, sess_expected=None, sess_upper=None, progress_val=None):
    """Create or update a node and sync its edges. Returns a status message."""
    # target_status: what the user selected in the form (Done or Open).
    # graph_manager may override to "Blocked" after sync_edges if hard prerequisites aren't met.
    target_status = "Done" if (status_done and "Done" in status_done) else "Open"

    # Auto-set progress to 100% when resource is marked Done
    if n_type == 'Resource' and target_status == 'Done':
        progress_val = 100

    node = Node(
        name=name, type=n_type, description=desc or "",
        value=val, time_o=time_o or 0, time_m=time_m or 0, time_p=time_p or 0,
        interest=interest, difficulty=diff,
        status=target_status, context=context or None, subcontext=(subctx or '').strip() or None,
        obsidian_path=(obs_path or '').strip() or None,
        google_drive_path=(drive_path or '').strip() or None,
        website=(website_path or '').strip() or None,
        frequency=habit_freq if n_type == 'Habit' else None,
        session_lower=sess_lower if n_type == 'Habit' else None,
        session_expected=sess_expected if n_type == 'Habit' else None,
        session_upper=sess_upper if n_type == 'Habit' else None,
        habit_status=habit_status_val if n_type == 'Habit' else None,
        progress=int(progress_val) if n_type == 'Resource' and progress_val is not None else None,
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
        Input('cytoscape-graph', 'mouseoverNodeData'),
        Input('goal-mini-graph', 'mouseoverNodeData'),
    )
    def display_hover_data(data, goal_data):
        trigger = _get_trigger_id()
        if trigger == 'goal-mini-graph':
            data = goal_data
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

        node_type = data.get('type', '')
        lines = [
            html.Div(html.Strong(data.get('label', data.get('id', ''))),
                     style={"fontSize": "0.95rem", "marginBottom": "4px", "borderBottom": "1px solid #495057", "paddingBottom": "4px"}),
            html.Div([html.Strong("Type: "), node_type]),
        ]

        if node_type == 'Habit':
            lines.append(html.Div([html.Strong("Habit Status: "), data.get('habit_status', 'Active')]))
            freq = data.get('frequency')
            if freq:
                lines.append(html.Div([html.Strong("Frequency: "), freq]))
        else:
            lines.append(html.Div([html.Strong("Status: "), data.get('status', '')]))

        lines.extend([
            html.Div([html.Strong("Context: "), data.get('context', '')]),
            html.Div([html.Strong("Value: "), str(data.get('value', ''))]),
            html.Div([html.Strong("Effort: "), str(data.get('difficulty', ''))]),
        ])

        if node_type != 'Habit':
            lines.append(html.Div([html.Strong("Time: "), time_str]))

        if node_type == 'Resource' and data.get('progress') is not None:
            lines.append(html.Div([html.Strong("Progress: "), f"{data.get('progress', 0)}%"]))

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
         Output('obsidian-links-store', 'data'), Output('drive-links-store', 'data'),
         Output('website-links-store', 'data'),
         # Type-specific outputs
         Output('habit-status', 'value'), Output('habit-frequency', 'value'),
         Output('session-lower', 'value'), Output('session-expected', 'value'), Output('session-upper', 'value'),
         Output('node-progress', 'value')],
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
            "", "Learn", "", "", "", 5, 5, 5, 1.0, 1.0, 1.0, "Open", [],
            [], [], [], [], [], [],
            options, options, options, options, options, options,
            [''], [''], [''],
            # Type-specific defaults
            "Active", "Daily", None, None, None, 0
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
                return [dash.no_update] * 19 + [options]*6 + [dash.no_update]*9
        elif data:
            name = data.get('id')

        if not name or not data:
            return [dash.no_update] * 19 + [options]*6 + [dash.no_update]*9

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
            data.get('context') or '', data.get('subcontext') or '',
            data.get('value', 5), data.get('interest', 5), data.get('difficulty', 5),
            data.get('time_o', 1.0), data.get('time_m', 1.0), data.get('time_p', 1.0),
            actual_status, done_val,
            needs_hard_vals, needs_soft_vals, supp_hard_vals, supp_soft_vals,
            helps_vals, res_vals,
            filtered_options, filtered_options, filtered_options, filtered_options, filtered_options, filtered_options,
            _parse_links(data.get('obsidian_path', '')),
            _parse_links(data.get('google_drive_path', '')),
            _parse_links(data.get('website', '')),
            # Type-specific fields
            data.get('habit_status') or 'Active',
            data.get('frequency') or 'Daily',
            data.get('session_lower'), data.get('session_expected'), data.get('session_upper'),
            data.get('progress') or 0,
        ]

    # --- Type-adaptive field visibility ---
    @app.callback(
        [Output('section-done-time', 'style'),
         Output('section-time-estimates', 'style'),
         Output('section-habit', 'style'),
         Output('section-resource', 'style')],
        Input('node-type', 'value')
    )
    def toggle_type_fields(node_type):
        show = {}
        hide = {'display': 'none'}
        if node_type == 'Habit':
            return hide, hide, show, hide
        elif node_type == 'Resource':
            return show, show, hide, show
        elif node_type == 'Goal':
            return show, hide, hide, hide
        else:  # Learn, Action
            return show, show, hide, hide

    # --- Priority Badge in Node Editor ---
    @app.callback(
        Output('node-priority-badge', 'children'),
        Output('node-priority-badge', 'style'),
        Input('node-name', 'value'),
        Input('node-type', 'value'),
    )
    def update_node_priority_badge(node_name, node_type):
        hidden = {"display": "none", "fontSize": "0.75rem"}
        visible = {"display": "inline-block", "fontSize": "0.75rem"}
        if not node_name or node_type != "Goal":
            return "", hidden
        priority_goals = ConfigManager.get_priority_goals()
        if node_name in priority_goals:
            rank = priority_goals.index(node_name) + 1
            return f"#{rank} Priority", visible
        return "", hidden

    # --- Core State: Save, Delete, Render ---
    @app.callback(
        [Output('cytoscape-graph', 'elements'), Output('save-output', 'children'),
         Output('suggestions-table', 'children'), Output('traversal-chains', 'children'),
         Output('synergies-list', 'children'),
         Output('clear-interval', 'disabled'), Output('clear-interval', 'n_intervals'),
         Output('filter-community', 'options'), Output('search-node', 'options'),
         Output('sidebar-editor-container', 'style'), Output('sidebar-filters-container', 'style'),
         Output('filter-context', 'options'), Output('node-context', 'options'),
         Output('node-type', 'options'),
         Output('filter-node-type', 'options'),
         Output('filter-goal', 'options'),
         Output('cytoscape-graph', 'stylesheet'),
         Output('btn-clear-focus', 'style'),
         Output('node-completion-events-store', 'data')],

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
         Input('btn-filters-toggle', 'n_clicks'), Input('btn-suggestions-filters-toggle', 'n_clicks'), Input('btn-close-filters', 'n_clicks'),
         Input('btn-settings-save', 'n_clicks'),
         Input('modal-migration', 'is_open'),
         Input('btn-toggle-done-node', 'n_clicks'),
         Input('group-delete-input', 'value'),
         Input('filter-node-type', 'value'),
         Input('selected-suggestion-store', 'data'),
         Input('filter-goal', 'value'),
         Input('focus-goal-store', 'data'),
         Input('edit-trigger-input', 'value'),
         Input('toggle-done-trigger-input', 'value')],

        [State('node-name', 'value'), State('node-type', 'value'), State('node-desc', 'value'),
         State('node-context', 'value'), State('node-subcontext', 'value'), State('node-status-done', 'value'),
         State('node-value', 'value'), State('node-interest', 'value'), State('node-difficulty', 'value'),
         State('node-time-o', 'value'), State('node-time-m', 'value'), State('node-time-p', 'value'),
         State('edge-needs-hard', 'value'), State('edge-needs-soft', 'value'),
         State('edge-supports-hard', 'value'), State('edge-supports-soft', 'value'),
         State('edge-helps', 'value'), State('edge-resources', 'value'),
         State({'type': 'obsidian-link', 'index': ALL}, 'value'),
         State({'type': 'drive-link', 'index': ALL}, 'value'),
         State({'type': 'website-link', 'index': ALL}, 'value'),
         State('habit-status', 'value'), State('habit-frequency', 'value'),
         State('session-lower', 'value'), State('session-expected', 'value'), State('session-upper', 'value'),
         State('node-progress', 'value'),
         State('cytoscape-graph', 'elements'),
         State('sidebar-editor-container', 'style'), State('sidebar-filters-container', 'style')]
    )
    def core_engine(save_clicks, delete_clicks, f_context, f_subcontext, f_done, search_val,
                     tapped_node,  # Cytoscape tapNodeData dict (not a Node object)
                     f_community, community_method, f_value, f_interest, f_time, f_difficulty, sugg_count,
                     btn_edit, btn_add, btn_close_ed, btn_filters, btn_sugg_filters, btn_close_fil, settings_open, migration_open, btn_toggle_done,
                     group_delete_data, f_node_types,
                     active_suggestion_id,
                     f_goal, focus_goal,
                     edit_trigger_data, toggle_done_trigger_data,
                     name, n_type, desc, context, subctx, status_done, val, interest, diff,
                     time_o, time_m, time_p,
                     e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps, e_res,
                     obs_link_values, drive_link_values, website_link_values,
                     habit_status_val, habit_freq, sess_lower, sess_expected, sess_upper, progress_val,
                     current_elements, ed_style, fil_style):
        """Central state callback handling node CRUD, filtering, and UI updates.

        This is intentionally a single large callback because Dash requires each Output
        to belong to exactly one callback. Since save/delete/filter operations all need
        to refresh the graph elements and sidebar state, they must share one callback.
        """
                     
        trigger_id = _get_trigger_id()
        msg = ""
        completion_check_node = None  # Set when a node transitions to Done

        # Check for any delayed event nodes or scheduled events that are due
        from event_manager import EventManager
        _event_mgr = EventManager()
        _event_mgr.check_pending_activations()
        _event_mgr.check_scheduled_triggers()

        filters = _build_filters(f_context, f_subcontext, f_done, f_value, f_interest, f_time, f_difficulty, f_node_types, f_goal=f_goal)

        # Editor Sidebar State (380px matches sidebar_content width in layout.py)
        next_ed_style = ed_style or {"width": "380px", "minWidth": "380px", "marginLeft": "-380px", "overflowX": "hidden", "overflowY": "auto", "borderRight": "1px solid #495057", "transition": "margin-left 0.3s ease", "backgroundColor": "#212529"}
        if trigger_id in ('btn-edit-node', 'btn-add', 'edit-trigger-input') or (trigger_id == 'search-node' and search_val):
            next_ed_style['marginLeft'] = "0px"
        elif trigger_id in ('btn-save', 'btn-clear', 'btn-delete', 'btn-close-editor'):
            next_ed_style['marginLeft'] = "-380px"

        # Filters Sidebar State (overlay, shared between Canvas + Suggestions tabs)
        next_fil_style = fil_style or {"position": "absolute", "top": "0", "right": "-320px", "width": "320px", "height": "100%", "zIndex": 100, "overflowX": "hidden", "overflowY": "auto", "borderLeft": "1px solid #495057", "transition": "right 0.3s ease", "backgroundColor": "#212529"}
        if trigger_id in ('btn-filters-toggle', 'btn-suggestions-filters-toggle'):
            next_fil_style['right'] = "0px" if next_fil_style.get('right', '-320px') == "-320px" else "-320px"
        elif trigger_id == 'btn-close-filters':
            next_fil_style['right'] = "-320px"

        active_node_id = None
        if trigger_id == 'edit-trigger-input' and edit_trigger_data:
            active_node_id = edit_trigger_data.split('|')[0] if edit_trigger_data else None
        elif trigger_id == 'search-node' and search_val: active_node_id = search_val
        elif trigger_id == 'cytoscape-graph' and tapped_node: active_node_id = tapped_node.get('id')
        else: active_node_id = name

        # Serialize multi-link arrays for storage
        obs_path = _serialize_links(obs_link_values)
        drive_path = _serialize_links(drive_link_values)
        website_path = _serialize_links(website_link_values)

        # --- Action Routing ---
        if trigger_id in ('btn-save', 'btn-close-editor') and name and n_type:
            try:
                # Track if this save marks the node Done (for event completion check)
                if status_done and "done" in (status_done or []):
                    completion_check_node = name
                msg = _handle_save(name, n_type, desc, val, time_o, time_m, time_p,
                                   interest, diff, status_done, context, subctx,
                                   obs_path, drive_path, website_path,
                                   e_needs_h, e_needs_s,
                                   e_supp_h, e_supp_s, e_helps, e_res,
                                   habit_status_val, habit_freq, sess_lower, sess_expected, sess_upper, progress_val)
            except (ValueError, TypeError):
                msg = "Error: Please check your mathematical inputs."
                return current_elements, msg, dash.no_update, dash.no_update, dash.no_update, False, 0, dash.no_update, dash.no_update, next_ed_style, next_fil_style, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
            except Exception as e:
                msg = str(e)

        elif trigger_id == 'btn-delete' and name:
            try:
                msg = _handle_delete(name)
            except Exception as e:
                msg = str(e)

        elif trigger_id == 'btn-toggle-done-node' and tapped_node:
            try:
                node_id = tapped_node.get('id')
                _pre_node = manager.get_node(node_id)
                if _pre_node and _pre_node.status != "Done":
                    completion_check_node = node_id
                msg = _handle_toggle_done(tapped_node)
            except Exception as e:
                msg = str(e)

        elif trigger_id == 'toggle-done-trigger-input' and toggle_done_trigger_data:
            try:
                node_name = toggle_done_trigger_data.split('|')[0]
                node = manager.get_node(node_name)
                if node:
                    if node.status != "Done":
                        completion_check_node = node_name
                    node.status = "Open" if node.status == "Done" else "Done"
                    manager.update_node(node)
                    msg = f"Toggled status of '{node.name}' to {node.status}"
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
        sugg_ui = _format_suggestions_table(get_suggestions(filters, count=count), active_suggestion_id)
        traversal_ui, synergies_ui = _format_traversal_ui(tapped_node, active_node_id)

        all_nodes = manager.get_all_nodes()
        search_options = _node_options(all_nodes)
        
        # Populate dynamic contexts datalists from DB + Config preserving defined order
        base_ctx = ConfigManager.get_contexts()
        
        ctx_list = [{"label": "None", "value": ""}] + [{"label": c, "value": c} for c in base_ctx]
        f_ctx_list = [{"label": "All", "value": "All"}] + [{"label": c, "value": c} for c in base_ctx]

        base_types = ConfigManager.get_node_types()
        type_list = [{"label": t, "value": t} for t in base_types]

        f_type_list = [{"label": "All", "value": "All"}] + [{"label": t, "value": t} for t in base_types]

        # Goal filter options (dbc.Select — needs "All" option first)
        goal_nodes = [n for n in all_nodes if n.type == "Goal"]
        goal_opts = [{"label": "All", "value": "All"}] + [{"label": g.name, "value": g.name} for g in goal_nodes]

        # Focus mode stylesheet: highlight subtree, dim others
        from layout import stylesheet as base_stylesheet
        active_stylesheet = list(base_stylesheet)
        if focus_goal:
            focus_subtree = manager.get_goal_subtree(focus_goal)
            focus_subtree.add(focus_goal)
            active_stylesheet.append({
                'selector': 'node',
                'style': {'opacity': 0.15}
            })
            active_stylesheet.append({
                'selector': 'edge',
                'style': {'opacity': 0.08}
            })
            for node_name in focus_subtree:
                safe_id = node_name.replace("'", "\\'")
                active_stylesheet.append({
                    'selector': f'node[id = "{safe_id}"]',
                    'style': {'opacity': 1}
                })
            active_stylesheet.append({
                'selector': 'node:selected',
                'style': {'opacity': 1}
            })

        clear_focus_style = {"display": "inline-block"} if focus_goal else {"display": "none"}

        # Check for events triggered by node completion
        node_completion_events = dash.no_update
        if completion_check_node:
            try:
                triggered_events = _event_mgr.get_events_triggered_by_node(completion_check_node)
                if triggered_events:
                    node_completion_events = [e.name for e in triggered_events]
            except Exception:
                pass

        return elements, msg, sugg_ui, traversal_ui, synergies_ui, False if msg else True, 0, community_options, search_options, next_ed_style, next_fil_style, f_ctx_list, ctx_list, type_list, f_type_list, goal_opts, active_stylesheet, clear_focus_style, node_completion_events

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
        base = [{"label": "None", "value": ""}]
        if not ctx:
            return base
        subs = ConfigManager.get_subcontexts().get(ctx, [])
        return base + [{"label": s, "value": s} for s in subs]

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

    # --- Settings: Load when Settings tab activates ---
    @app.callback(
        Output('hp-wv', 'value'),
        Output('hp-wi', 'value'),
        Output('hp-dh', 'value'),
        Output('hp-ds', 'value'),
        Output('hp-dsyn', 'value'),
        Output('hp-we', 'value'),
        Output('hp-wt', 'value'),
        Output('hp-beta', 'value'),
        Output('hp-goal-boost', 'value'),
        Output('setting-node-types', 'value'),
        Output('setting-contexts', 'value'),
        Output('setting-subcontexts', 'value'),
        Output('setting-hp-profile', 'value'),
        Output('setting-obsidian-path', 'value'),
        Output('setting-node-shapes-container', 'children'),
        Output('setting-node-colors-container', 'children'),
        Input('main-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    def load_settings(active_tab):
        if active_tab != 'tab-settings':
            return (dash.no_update,) * 16

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

        # Build shapes editor
        node_types = ConfigManager.get_node_types()
        shapes = ConfigManager.get_node_shapes()
        shape_options = [
            {"label": s.title(), "value": s}
            for s in ["ellipse", "triangle", "rectangle", "star", "pentagon", "hexagon",
                       "diamond", "octagon", "round-rectangle", "vee"]
        ]
        shape_rows = []
        for t in node_types:
            shape_rows.append(dbc.Row([
                dbc.Col(dbc.Label(t, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Select(
                    id={"type": "setting-shape", "index": t},
                    options=shape_options,
                    value=shapes.get(t, "ellipse"),
                ), width=8),
            ], className="mb-2"))

        # Build colors editor
        colors = ConfigManager.get_node_colors()
        status_list = ["Open", "Blocked", "Done"]
        color_rows = []
        for status in status_list:
            color_rows.append(dbc.Row([
                dbc.Col(dbc.Label(status, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Input(
                    id={"type": "setting-color", "index": status},
                    type="color",
                    value=colors.get(status, "#6c757d"),
                    style={"height": "38px", "padding": "2px"},
                ), width=4),
                dbc.Col(html.Small(
                    colors.get(status, "#6c757d"),
                    className="text-muted d-flex align-items-center",
                    style={"fontSize": "0.8rem"},
                ), width=4),
            ], className="mb-2"))

        return (hp.get('w_v'), hp.get('w_i'), hp.get('d_H'), hp.get('d_S'), hp.get('d_Syn'),
                hp.get('w_e'), hp.get('w_t'), hp.get('beta'), hp.get('goal_boost', 1.5),
                ntypes, ctxts, subctxts, "Custom", obs, shape_rows, color_rows)

    # --- Settings: Profile selector ---
    @app.callback(
        Output('hp-wv', 'value', allow_duplicate=True),
        Output('hp-wi', 'value', allow_duplicate=True),
        Output('hp-dh', 'value', allow_duplicate=True),
        Output('hp-ds', 'value', allow_duplicate=True),
        Output('hp-dsyn', 'value', allow_duplicate=True),
        Output('hp-we', 'value', allow_duplicate=True),
        Output('hp-wt', 'value', allow_duplicate=True),
        Output('hp-beta', 'value', allow_duplicate=True),
        Output('hp-goal-boost', 'value', allow_duplicate=True),
        Input('setting-hp-profile', 'value'),
        prevent_initial_call=True,
    )
    def apply_profile(profile_val):
        from config import PROFILES
        if profile_val in PROFILES:
            p = PROFILES[profile_val]
            return (p['w_v'], p['w_i'], p['d_H'], p['d_S'], p['d_Syn'],
                    p['w_e'], p['w_t'], p['beta'], p.get('goal_boost', 1.5))
        return (dash.no_update,) * 9

    # --- Settings: Save ---
    @app.callback(
        Output('settings-save-status', 'children'),
        Output('pending-settings-store', 'data'),
        Input('btn-settings-save', 'n_clicks'),
        State('hp-wv', 'value'), State('hp-wi', 'value'),
        State('hp-dh', 'value'), State('hp-ds', 'value'), State('hp-dsyn', 'value'),
        State('hp-we', 'value'), State('hp-wt', 'value'), State('hp-beta', 'value'),
        State('hp-goal-boost', 'value'),
        State('setting-node-types', 'value'),
        State('setting-contexts', 'value'),
        State('setting-subcontexts', 'value'),
        State('setting-obsidian-path', 'value'),
        State({"type": "setting-shape", "index": ALL}, "value"),
        State({"type": "setting-shape", "index": ALL}, "id"),
        State({"type": "setting-color", "index": ALL}, "value"),
        State({"type": "setting-color", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def save_settings(n_clicks, wv, wi, dh, ds, dsyn, we, wt, beta, goal_boost,
                      n_types_val, contexts_val, subcontexts_val, obs_path,
                      shape_values, shape_ids, color_values, color_ids):
        if not n_clicks:
            return dash.no_update, dash.no_update

        try:
            new_hp = {
                'w_v': float(wv), 'w_i': float(wi),
                'd_H': float(dh), 'd_S': float(ds), 'd_Syn': float(dsyn),
                'w_e': float(we), 'w_t': float(wt), 'beta': float(beta),
                'goal_boost': float(goal_boost) if goal_boost is not None else 1.5,
            }

            # Parse new values
            new_types = [c.strip() for c in (n_types_val or '').split(',') if c.strip()]
            new_contexts = [c.strip() for c in (contexts_val or '').split(',') if c.strip()]
            new_subcontexts = {}
            if subcontexts_val is not None:
                for line in subcontexts_val.split('\n'):
                    line = line.strip()
                    if ':' in line:
                        ctx_name, subs_str = line.split(':', 1)
                        ctx_name = ctx_name.strip()
                        subs = [s.strip() for s in subs_str.split(',') if s.strip()]
                        if ctx_name and subs:
                            if ctx_name in new_subcontexts:
                                new_subcontexts[ctx_name].extend(subs)
                            else:
                                new_subcontexts[ctx_name] = subs

            # Load old values
            old_types = ConfigManager.get_node_types()
            old_contexts = ConfigManager.get_contexts()
            old_subcontexts = ConfigManager.get_subcontexts()

            # Flatten old/new subcontexts for comparison
            old_sub_flat = [s for subs in old_subcontexts.values() for s in subs]
            new_sub_flat = [s for subs in new_subcontexts.values() for s in subs]

            # Detect orphans
            orphans = {}
            type_orphans = manager.find_orphaned_nodes('type', old_types, new_types)
            if type_orphans:
                orphans['type'] = {k: [n.name for n in v] for k, v in type_orphans.items()}
            ctx_orphans = manager.find_orphaned_nodes('context', old_contexts, new_contexts)
            if ctx_orphans:
                orphans['context'] = {k: [n.name for n in v] for k, v in ctx_orphans.items()}
            sub_orphans = manager.find_orphaned_nodes('subcontext', old_sub_flat, new_sub_flat)
            if sub_orphans:
                orphans['subcontext'] = {k: [n.name for n in v] for k, v in sub_orphans.items()}

            if orphans:
                # Defer save — store pending data and open migration modal
                pending = {
                    'hp': new_hp,
                    'obs_path': obs_path,
                    'types': new_types,
                    'contexts': new_contexts,
                    'subcontexts': new_subcontexts,
                    'orphans': orphans,
                    'new_values': {
                        'type': new_types,
                        'context': new_contexts,
                        'subcontext': new_sub_flat,
                    }
                }
                return "Migration required — check the migration dialog.", pending

            # No orphans — save immediately
            ConfigManager.set_hyperparams(new_hp)
            ConfigManager.set_obsidian_vault(obs_path)
            if new_types:
                ConfigManager.set_node_types(new_types)
                ConfigManager.sync_shapes_to_types(new_types)
            if new_contexts:
                ConfigManager.set_contexts(new_contexts)
            ConfigManager.set_subcontexts(new_subcontexts)

            # Save shapes
            if shape_ids and shape_values:
                new_shapes = {}
                for sid, sval in zip(shape_ids, shape_values):
                    if sval:
                        new_shapes[sid["index"]] = sval
                if new_shapes:
                    ConfigManager.set_node_shapes(new_shapes)

            # Save colors
            if color_ids and color_values:
                new_colors = {}
                for cid, cval in zip(color_ids, color_values):
                    if cval:
                        new_colors[cid["index"]] = cval
                if new_colors:
                    ConfigManager.set_node_colors(new_colors)

            return "Settings saved.", dash.no_update

        except Exception:
            logger.exception("Failed to save settings")
            return "Error saving settings.", dash.no_update

    # --- Migration Modal ---
    @app.callback(
        Output('modal-migration', 'is_open'),
        Output('migration-modal-body', 'children'),
        Output('migration-mapping-store', 'data'),
        Input('pending-settings-store', 'data'),
        Input('btn-migration-apply', 'n_clicks'),
        Input('btn-migration-skip', 'n_clicks'),
        State({"type": "migration-dropdown", "index": dash.ALL}, "value"),
        State('migration-mapping-store', 'data'),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True
    )
    def handle_migration(pending_data, apply_clicks, skip_clicks,
                         dropdown_values, mapping_data, pending_state):
        from layout import build_migration_content

        trigger_id = _get_trigger_id()

        if trigger_id == 'pending-settings-store' and pending_data:
            orphans = pending_data.get('orphans', {})
            new_values = pending_data.get('new_values', {})

            # Create lightweight objects with .name for the UI builder
            orphans_for_ui = {}
            for field, val_map in orphans.items():
                orphans_for_ui[field] = {}
                for old_val, node_names in val_map.items():
                    orphans_for_ui[field][old_val] = [type('N', (), {'name': n})() for n in node_names]

            children, mapping = build_migration_content(orphans_for_ui, new_values)
            return True, children, mapping

        if trigger_id in ('btn-migration-apply', 'btn-migration-skip') and pending_state:
            # Save the pending settings
            try:
                ConfigManager.set_hyperparams(pending_state['hp'])
                ConfigManager.set_obsidian_vault(pending_state['obs_path'])
                new_types = pending_state.get('types', [])
                if new_types:
                    ConfigManager.set_node_types(new_types)
                    ConfigManager.sync_shapes_to_types(new_types)
                new_contexts = pending_state.get('contexts', [])
                if new_contexts:
                    ConfigManager.set_contexts(new_contexts)
                ConfigManager.set_subcontexts(pending_state.get('subcontexts', {}))
            except Exception:
                logger.exception("Failed to save pending settings")

            # Apply migrations if user clicked Apply
            if trigger_id == 'btn-migration-apply' and mapping_data and dropdown_values:
                new_subcontexts = pending_state.get('subcontexts', {})
                remaps = {}  # field -> {old_val: new_val}
                for i, entry in enumerate(mapping_data):
                    if i < len(dropdown_values) and dropdown_values[i]:
                        field = entry['field']
                        old_val = entry['old_value']
                        if field not in remaps:
                            remaps[field] = {}
                        remaps[field][old_val] = dropdown_values[i]

                for field, remap in remaps.items():
                    manager.apply_migration(field, remap, new_subcontexts=new_subcontexts)

            return False, [], None

        return dash.no_update, dash.no_update, dash.no_update

    # --- Subcontext Collapse Toggle ---
    @app.callback(
        Output("collapse-subcontext", "is_open"),
        [Input("btn-subcontext-toggle", "n_clicks")],
        [State("collapse-subcontext", "is_open")],
    )
    def toggle_subcontext(n, is_open):
        if n: return not is_open
        return is_open

    # --- Multi-Link Render Callbacks ---
    def _render_link_rows(links, link_type, has_browse=False):
        """Build a list of input rows for a resource type.
        link_type: 'obsidian-link', 'drive-link', or 'website-link'
        """
        from dash import html as _html
        link_list = links or ['']
        add_btn_id = f"btn-{link_type.replace('-link', '')}-add"
        rows = []
        for i, path in enumerate(link_list):
            is_last = (i == len(link_list) - 1)
            buttons = []
            if has_browse:
                browse_type = 'btn-obsidian-browse' if 'obsidian' in link_type else 'btn-drive-browse'
                buttons.append(dbc.Button(
                    "\U0001f4c1", id={"type": browse_type, "index": i},
                    color="secondary", size="sm", title="Browse",
                    className="me-1", style={"minWidth": "32px"}
                ))
            buttons.append(dbc.Button(
                "\U0001f517", id={"type": f"btn-{link_type.replace('-link','')}-open", "index": i},
                color="secondary", size="sm", title="Open",
                className="me-1", style={"minWidth": "32px"}
            ))
            if len(link_list) > 1:
                buttons.append(dbc.Button(
                    "\u00d7", id={"type": f"btn-{link_type}-remove", "index": i},
                    color="danger", size="sm", outline=True,
                    className="me-1", style={"minWidth": "28px", "padding": "2px 6px"}
                ))
            # Add "+" button on last row only
            if is_last:
                buttons.append(dbc.Button(
                    "+", id=add_btn_id,
                    color="secondary", size="sm", outline=True,
                    title="Add another",
                    style={"minWidth": "28px", "padding": "2px 6px", "color": "#6c757d"}
                ))
            rows.append(_html.Div([
                dbc.Input(id={"type": link_type, "index": i}, type="text",
                          value=path or '', placeholder="Enter path or URL...",
                          className="me-1", style={"flex": "1", "fontSize": "0.85rem"}),
                *buttons
            ], className="d-flex mb-1"))
        return rows

    @app.callback(
        Output('obsidian-links-container', 'children'),
        Input('obsidian-links-store', 'data'),
    )
    def render_obsidian_links(links):
        return _render_link_rows(links, 'obsidian-link', has_browse=True)

    @app.callback(
        Output('drive-links-container', 'children'),
        Input('drive-links-store', 'data'),
    )
    def render_drive_links(links):
        return _render_link_rows(links, 'drive-link', has_browse=True)

    @app.callback(
        Output('website-links-container', 'children'),
        Input('website-links-store', 'data'),
    )
    def render_website_links(links):
        return _render_link_rows(links, 'website-link', has_browse=False)

    # --- Multi-Link Add/Remove Callbacks ---
    def _handle_link_modify(add_clicks, remove_clicks, current_values, store_data, browse_clicks=None, browse_result=None):
        """Shared logic for add/remove/browse on a link list. Returns updated list."""
        trigger = ctx.triggered_id
        # Capture current input values (they may have been edited by the user)
        links = list(current_values) if current_values else list(store_data or [''])
        if isinstance(trigger, str):
            # Add button
            links.append('')
        elif isinstance(trigger, dict):
            if 'remove' in trigger.get('type', ''):
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
            elif 'browse' in trigger.get('type', '') and browse_result:
                idx = trigger['index']
                if 0 <= idx < len(links):
                    links[idx] = browse_result
        return links

    @app.callback(
        Output('obsidian-links-store', 'data', allow_duplicate=True),
        [Input('btn-obsidian-add', 'n_clicks'),
         Input({'type': 'btn-obsidian-link-remove', 'index': ALL}, 'n_clicks'),
         Input({'type': 'btn-obsidian-browse', 'index': ALL}, 'n_clicks')],
        [State({'type': 'obsidian-link', 'index': ALL}, 'value'),
         State('obsidian-links-store', 'data')],
        prevent_initial_call=True,
    )
    def modify_obsidian_links(add_clicks, remove_clicks, browse_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-obsidian-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-obsidian-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
            elif trigger.get('type') == 'btn-obsidian-browse':
                idx = trigger['index']
                if not any(browse_clicks):
                    return dash.no_update
                vault = ConfigManager.get_obsidian_vault()
                abs_path = _spawn_local_file_picker(
                    initial_dir=vault,
                    title="Select Obsidian File",
                    filetypes_list=[("Markdown files", "*.md"), ("All files", "*.*")]
                )
                if abs_path:
                    vault_norm = os.path.normpath(vault)
                    if abs_path.startswith(vault_norm):
                        rel = abs_path[len(vault_norm):].lstrip(os.sep)
                    else:
                        rel = abs_path
                    if 0 <= idx < len(links):
                        links[idx] = rel
                else:
                    return dash.no_update
        return links

    @app.callback(
        Output('drive-links-store', 'data', allow_duplicate=True),
        [Input('btn-drive-add', 'n_clicks'),
         Input({'type': 'btn-drive-link-remove', 'index': ALL}, 'n_clicks'),
         Input({'type': 'btn-drive-browse', 'index': ALL}, 'n_clicks')],
        [State({'type': 'drive-link', 'index': ALL}, 'value'),
         State('drive-links-store', 'data')],
        prevent_initial_call=True,
    )
    def modify_drive_links(add_clicks, remove_clicks, browse_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-drive-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-drive-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
            elif trigger.get('type') == 'btn-drive-browse':
                idx = trigger['index']
                if not any(browse_clicks):
                    return dash.no_update
                abs_path = _spawn_local_file_picker(
                    initial_dir=r"G:\\My Drive",
                    title="Select Google Drive File",
                    filetypes_list=[("All files", "*.*")]
                )
                if abs_path:
                    if 0 <= idx < len(links):
                        links[idx] = abs_path
                else:
                    return dash.no_update
        return links

    @app.callback(
        Output('website-links-store', 'data', allow_duplicate=True),
        [Input('btn-website-add', 'n_clicks'),
         Input({'type': 'btn-website-link-remove', 'index': ALL}, 'n_clicks')],
        [State({'type': 'website-link', 'index': ALL}, 'value'),
         State('website-links-store', 'data')],
        prevent_initial_call=True,
    )
    def modify_website_links(add_clicks, remove_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-website-add':
            links.append('')
        elif isinstance(trigger, dict) and trigger.get('type') == 'btn-website-link-remove':
            idx = trigger['index']
            if 0 <= idx < len(links) and len(links) > 1:
                links.pop(idx)
        return links

    # --- Multi-Link Open Callbacks ---
    def _open_url_or_path(url):
        """Open a URL or local file path. Returns error message or no_update."""
        import webbrowser
        if not url or not url.strip():
            return "No URL/Path set for this link."
        url = url.strip()
        if os.path.exists(url) or url.startswith(('G:\\', 'C:\\', 'D:\\', '\\\\')):
            try:
                os.startfile(url)
                return dash.no_update
            except Exception as e:
                return f"Error opening local file: {str(e)}"
        else:
            if not url.startswith('http://') and not url.startswith('https://'):
                url = 'https://' + url
            try:
                webbrowser.open_new_tab(url)
                return dash.no_update
            except Exception as e:
                return f"Error opening URL: {str(e)}"

    @app.callback(
        Output('save-output', 'children', allow_duplicate=True),
        Input({'type': 'btn-obsidian-open', 'index': ALL}, 'n_clicks'),
        State({'type': 'obsidian-link', 'index': ALL}, 'value'),
        prevent_initial_call=True,
    )
    def open_obsidian_link(n_clicks_list, values):
        if not any(n_clicks_list):
            return dash.no_update
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return dash.no_update
        idx = trigger['index']
        if 0 <= idx < len(values):
            rel_path = values[idx]
            if not rel_path or not rel_path.strip():
                return "No Obsidian file path set."
            vault = ConfigManager.get_obsidian_vault()
            abs_path = os.path.join(vault, rel_path.strip())
            encoded = urllib.parse.quote(abs_path, safe='')
            uri = f'obsidian://open?path={encoded}'
            try:
                subprocess.Popen(['cmd', '/c', 'start', '', uri], shell=False)
                return dash.no_update
            except Exception as e:
                return f"Error opening Obsidian: {str(e)}"
        return dash.no_update

    @app.callback(
        Output('save-output', 'children', allow_duplicate=True),
        Input({'type': 'btn-drive-open', 'index': ALL}, 'n_clicks'),
        State({'type': 'drive-link', 'index': ALL}, 'value'),
        prevent_initial_call=True,
    )
    def open_drive_link(n_clicks_list, values):
        if not any(n_clicks_list):
            return dash.no_update
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return dash.no_update
        idx = trigger['index']
        if 0 <= idx < len(values):
            return _open_url_or_path(values[idx])
        return dash.no_update

    @app.callback(
        Output('save-output', 'children', allow_duplicate=True),
        Input({'type': 'btn-website-open', 'index': ALL}, 'n_clicks'),
        State({'type': 'website-link', 'index': ALL}, 'value'),
        prevent_initial_call=True,
    )
    def open_website_link(n_clicks_list, values):
        if not any(n_clicks_list):
            return dash.no_update
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return dash.no_update
        idx = trigger['index']
        if 0 <= idx < len(values):
            return _open_url_or_path(values[idx])
        return dash.no_update

    # --- Edit/Toggle Done Trigger from Goal Graph ---
    @app.callback(
        Output('main-tabs', 'active_tab', allow_duplicate=True),
        Output('search-node', 'value', allow_duplicate=True),
        Input('edit-trigger-input', 'value'),
        prevent_initial_call=True,
    )
    def handle_edit_trigger(value):
        if not value:
            return dash.no_update, dash.no_update
        node_name = value.split('|')[0]
        if not node_name:
            return dash.no_update, dash.no_update
        return 'tab-canvas', node_name


    @app.callback(
        Output('goals-refresh-trigger', 'data', allow_duplicate=True),
        Input('toggle-done-trigger-input', 'value'),
        prevent_initial_call=True,
    )
    def refresh_goals_on_toggle(value):
        if not value:
            return dash.no_update
        import time
        return time.time()

    # --- Suggestion Row Selection ---
    @app.callback(
        Output('selected-suggestion-store', 'data'),
        Input({'type': 'suggestion-row', 'index': ALL}, 'n_clicks'),
        prevent_initial_call=True
    )
    def update_selected_suggestion(n_clicks_list):
        if not any(n_clicks_list): return dash.no_update
        trigger_id = ctx.triggered_id
        if trigger_id and isinstance(trigger_id, dict) and 'index' in trigger_id:
            return trigger_id['index']
        return dash.no_update

    # --- Suggestion Name Click → Navigate to Nodes Tab ---
    @app.callback(
        Output('main-tabs', 'active_tab', allow_duplicate=True),
        Output('search-node', 'value', allow_duplicate=True),
        Input({'type': 'suggestion-name-link', 'index': ALL}, 'n_clicks'),
        prevent_initial_call=True,
    )
    def navigate_to_suggestion_node(n_clicks_list):
        if not any(n_clicks_list):
            return dash.no_update, dash.no_update
        trigger = ctx.triggered_id
        if trigger and isinstance(trigger, dict) and 'index' in trigger:
            return 'tab-canvas', trigger['index']
        return dash.no_update, dash.no_update

    # --- Settings: Restore Default Shapes ---
    @app.callback(
        Output('setting-node-shapes-container', 'children', allow_duplicate=True),
        Input('btn-restore-shapes', 'n_clicks'),
        prevent_initial_call=True,
    )
    def restore_default_shapes(n_clicks):
        if not n_clicks:
            return dash.no_update
        from config import DEFAULT_NODE_SHAPES
        node_types = ConfigManager.get_node_types()
        shape_options = [
            {"label": s.title(), "value": s}
            for s in ["ellipse", "triangle", "rectangle", "star", "pentagon", "hexagon",
                       "diamond", "octagon", "round-rectangle", "vee"]
        ]
        shape_rows = []
        for t in node_types:
            shape_rows.append(dbc.Row([
                dbc.Col(dbc.Label(t, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Select(
                    id={"type": "setting-shape", "index": t},
                    options=shape_options,
                    value=DEFAULT_NODE_SHAPES.get(t, "ellipse"),
                ), width=8),
            ], className="mb-2"))
        return shape_rows

    # --- Settings: Restore Default Colors ---
    @app.callback(
        Output('setting-node-colors-container', 'children', allow_duplicate=True),
        Input('btn-restore-colors', 'n_clicks'),
        prevent_initial_call=True,
    )
    def restore_default_colors(n_clicks):
        if not n_clicks:
            return dash.no_update
        from config import DEFAULT_NODE_COLORS
        status_list = ["Open", "Blocked", "Done"]
        color_rows = []
        for status in status_list:
            color_rows.append(dbc.Row([
                dbc.Col(dbc.Label(status, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Input(
                    id={"type": "setting-color", "index": status},
                    type="color",
                    value=DEFAULT_NODE_COLORS.get(status, "#6c757d"),
                    style={"height": "38px", "padding": "2px"},
                ), width=4),
                dbc.Col(html.Small(
                    DEFAULT_NODE_COLORS.get(status, "#6c757d"),
                    className="text-muted d-flex align-items-center",
                    style={"fontSize": "0.8rem"},
                ), width=4),
            ], className="mb-2"))
        return color_rows