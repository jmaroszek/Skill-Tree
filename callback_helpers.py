"""
Shared helper functions for Dash callback modules.

Contains stateless utility functions extracted from callbacks.py to keep
the callback registration files focused on Dash I/O wiring.
"""

import json
import dash
from dash import html
import dash_bootstrap_components as dbc
from config import ConfigManager
from models import EDGE_RESOURCE, EDGE_HELPS


SECTION_TITLE_STYLE = {"fontSize": "1.3rem", "fontWeight": "600"}


# --- Serialization Helpers ---

def parse_links(db_value):
    """Parse a DB field that may contain a JSON array or a plain string into a list."""
    if not db_value:
        return ['']
    try:
        parsed = json.loads(db_value)
        if isinstance(parsed, list):
            return parsed if parsed else ['']
    except (ValueError, TypeError):
        pass
    return [db_value]


def serialize_links(values_list):
    """Serialize a list of link input values into a JSON string for DB storage."""
    if not values_list:
        return None
    links = [v.strip() for v in values_list if v and v.strip()]
    if not links:
        return None
    return json.dumps(links)


# --- Callback Utilities ---

def get_trigger_id():
    """Return the component ID that triggered the current callback, or '' if none."""
    triggered = dash.callback_context.triggered
    return triggered[0]['prop_id'].split('.')[0] if triggered else ""


def node_options(nodes, exclude=None):
    """Build dropdown options from a list of nodes, optionally excluding one by name."""
    return [{'label': n.name, 'value': n.name} for n in nodes if n.name != exclude]


def build_filters(f_context, f_subcontext, f_done, f_value=1, f_interest=1,
                  f_time=None, f_difficulty="All", f_node_types=None, f_goal=None):
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


# --- Node CRUD Helpers ---

def handle_save(manager, name, n_type, desc, val, time_o, time_m, time_p, interest, diff,
                status_done, context, subctx, obs_path, drive_path, website_path,
                e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps, e_res,
                habit_status_val=None, habit_freq=None, sess_lower=None,
                sess_expected=None, sess_upper=None, progress_val=None):
    """Create or update a node and sync its edges. Returns a status message."""
    from models import Node

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


def handle_delete(manager, name):
    """Delete a single node by name. Returns a status message."""
    manager.delete_node(name)
    return f"Deleted node '{name}'"


def handle_toggle_done(manager, tapped_node):
    """Toggle a node's status between Done and Open. Returns a status message."""
    node = manager.get_node(tapped_node.get('id'))
    if node:
        node.status = "Open" if node.status == "Done" else "Done"
        manager.update_node(node)
        return f"Toggled status of '{node.name}' to {node.status}"
    return ""


def handle_group_delete(manager, group_delete_data):
    """Delete multiple nodes from a JSON-encoded list. Returns a status message."""
    # JS sends '["name1","name2"]|timestamp' — strip the timestamp suffix
    raw = group_delete_data.split('|')[0] if isinstance(group_delete_data, str) else ''
    names = json.loads(raw) if raw else []
    for node_name in names:
        manager.delete_node(node_name)
    return f"Deleted {len(names)} node(s)" if names else ""


# --- UI Formatting Helpers ---

def format_suggestions_table(suggs, manager, selected_node_id=None):
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
            html.Td(ConfigManager.format_time_friendly(s.time) if hasattr(s, 'time') and s.time else "0h"),
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


def format_traversal_ui(tapped_node, active_node_id, manager):
    """Build the dependency chains and synergies display for the selected node."""
    traversal_ui = html.Div(className="text-muted", children="Select a node to see dependencies.")
    synergies_ui = html.Div(className="text-muted", children="Select a node to see synergies.")

    if not tapped_node:
        return traversal_ui, synergies_ui

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
