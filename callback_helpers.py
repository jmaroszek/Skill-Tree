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
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS


SECTION_TITLE_STYLE = {"fontSize": "1.3rem", "fontWeight": "600"}

def _get_duplicate_stop_words():
    """Get stop words for duplicate comparison from linter settings."""
    linter = ConfigManager.get_titlecase_linter()
    exclusions = linter.get('exclusions', [])
    if exclusions:
        return {w.lower() for w in exclusions}
    # Fallback defaults
    return {
        "a", "an", "or", "not", "with", "the", "but", "and", "vs", "vs.",
        "at", "of", "are", "as", "is", "in", "to", "for", "on", "from",
        "by", "about", "into", "it",
    }


def normalize_name_for_comparison(name):
    """Strip stop/connector words and lowercase for fuzzy duplicate comparison.

    Uses the linter exclusion list from Settings so the user controls which
    words are ignored during duplicate detection.
    """
    if not name:
        return ""
    stop_words = _get_duplicate_stop_words()
    words = name.lower().split()
    return " ".join(w for w in words if w not in stop_words)


# --- Google Drive Path Helpers ---

def _gdrive_prefix():
    """Return the configured Google Drive root path, normalized with a trailing separator."""
    import os
    prefix = (ConfigManager.get_gdrive_path() or '').strip()
    if prefix and not prefix.endswith(os.sep) and not prefix.endswith('/'):
        prefix += os.sep
    return prefix


def strip_gdrive_prefix(links):
    """Strip the configured GDrive root prefix from each path in a list."""
    prefix = _gdrive_prefix()
    if not prefix:
        return links
    result = []
    for p in (links or []):
        if p and p.startswith(prefix):
            result.append(p[len(prefix):])
        else:
            result.append(p)
    return result


def expand_gdrive_prefix(path):
    """Prepend the configured GDrive root prefix to a relative path if it lacks one."""
    import os
    if not path or not path.strip():
        return path
    path = path.strip()
    prefix = _gdrive_prefix()
    if not prefix:
        return path
    # Already absolute — don't double-prefix
    if os.path.isabs(path) or path.startswith('http://') or path.startswith('https://'):
        return path
    return prefix + path


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


def get_all_triggered_ids(triggered_props=None):
    """Return the set of ALL component IDs that fired in this callback cycle.

    When multiple Dash Inputs change within the same update cycle (e.g. a
    double-click fires both tapNodeData and edit-trigger-input), only
    ``triggered[0]`` is returned by :func:`get_trigger_id`.  This helper
    exposes the full set so callers can detect batched triggers.
    """
    if triggered_props is None:
        triggered_props = dash.callback_context.triggered
    return {t['prop_id'].split('.')[0] for t in triggered_props}


def should_open_editor(all_triggered_ids, trigger_id, search_val):
    """Decide whether the sidebar editor should slide open.

    Checks ALL triggered IDs (not just the primary) so that an edit trigger
    batched with tapNodeData in the same Dash cycle still opens the sidebar.
    """
    return bool(all_triggered_ids & {'btn-edit-node', 'edit-trigger-input', 'details-edit-trigger-input'}) or \
           (trigger_id == 'search-node' and bool(search_val))


def resolve_active_node_id(all_triggered_ids, trigger_id, edit_trigger_data,
                           search_val, tapped_node, current_name):
    """Determine which node the editor should display.

    Prefers ``edit-trigger-input`` (carries the node ID explicitly) even when
    it is batched with another trigger like tapNodeData.
    """
    if ('edit-trigger-input' in all_triggered_ids or 'details-edit-trigger-input' in all_triggered_ids) and edit_trigger_data:
        return edit_trigger_data.split('|')[0]
    if trigger_id in ('background-click-input', 'btn-add'):
        return None
    if trigger_id == 'search-node' and search_val:
        if search_val.startswith('alias:'):
            from graph_manager import GraphManager
            _mgr = GraphManager()
            alias_key = search_val[6:]
            all_aliases = _mgr.get_all_aliases()
            return all_aliases.get(alias_key, search_val)
        return search_val
    if trigger_id == 'cytoscape-graph' and tapped_node:
        return tapped_node.get('id')
    return current_name


def node_options(nodes, exclude=None):
    """Build dropdown options from a list of nodes, optionally excluding one by name."""
    return [{'label': n.name, 'value': n.name} for n in nodes if n.name != exclude]


def build_filters(f_context, f_subcontext, f_done, f_value=1, f_interest=1,
                  f_time=None, f_difficulty="All", f_node_types=None, f_goal=None):
    """Build a filter dict from sidebar filter component values for use with GraphManager.filter_nodes()."""
    from config import ConfigManager
    filters = {}

    contexts = []
    if f_context and f_context != "All":
        if isinstance(f_context, list):
            contexts = f_context
        elif f_context != "None":
            contexts = [f_context]
        else:
            contexts = [None]

    subs = []
    if f_subcontext and f_subcontext != "All":
        if isinstance(f_subcontext, list):
            subs = f_subcontext
        elif f_subcontext.strip():
            subs = [f_subcontext.strip()]

    if contexts and subs:
        # Selective union: for each context, restrict to the selected subcontexts
        # that belong to it. If none of the selected subcontexts belong to a context,
        # include all nodes in that context (no subcontext restriction).
        sub_map = ConfigManager.get_subcontexts()  # {context: [subcontext, ...]}
        pairs = []
        for ctx in contexts:
            ctx_subs = sub_map.get(ctx, [])
            matching = [s for s in subs if s in ctx_subs]
            pairs.append((ctx, matching if matching else None))
        filters['context_subcontext_union'] = pairs
    elif contexts:
        filters['context'] = contexts
    elif subs:
        filters['subcontext'] = subs
    if f_node_types:
        if isinstance(f_node_types, list):
            if f_node_types:
                filters['node_types'] = f_node_types
        elif f_node_types != "All":
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
    if f_goal:
        if isinstance(f_goal, list):
            if f_goal:
                filters['goal'] = f_goal
        elif f_goal != "All":
            filters['goal'] = [f_goal]
    return filters


# --- Node CRUD Helpers ---

def handle_save(manager, name, n_type, desc, val, time_o, time_m, time_p, interest, diff,
                status_done, context, subctx, obs_path, drive_path, website_path,
                e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                progress_val=None, time_mode='manual', competence=None):
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
        progress=int(progress_val) if n_type == 'Resource' and progress_val is not None else None,
        time_mode=time_mode,
        competence=competence or None,
    )
    if manager.get_node(name):
        manager.update_node(node)
        msg = f"Updated node '{name}'"
    else:
        manager.add_node(node)
        msg = f"Added node '{name}'"
    manager.sync_edges(name, e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps)
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

def _bool_icon(val):
    """Render a boolean as a styled checkmark or cross."""
    if val:
        return html.Span("\u2713", style={"color": "#198754", "fontWeight": "bold"})
    return html.Span("\u2717", style={"color": "#dc3545"})


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
    all_nodes = manager.get_all_nodes()
    resource_names = {n.name for n in all_nodes if n.type == 'Resource'}

    table_header = [html.Thead(html.Tr([
        html.Th("Name"), html.Th("Type"), html.Th("Context"), html.Th("Subcontext"),
        html.Th("Priority"), html.Th("Value"), html.Th("Interest"), html.Th("Effort"), html.Th("Time"),
        html.Th("Hard Unlocks"), html.Th("Soft Unlocks"), html.Th("Synergies"),
        html.Th("Resources"), html.Th("Obsidian"), html.Th("Drive")
    ]))]

    row_data = []
    for s in suggs:
        is_selected = (s.name == selected_node_id)
        row_class = "table-active" if is_selected else ""

        unlocks = manager.get_directly_unlocked_nodes_by_type(s.name)
        has_resource = s.type == 'Resource' or any(
            e['source'] in resource_names
            for e in edges
            if e['target'] == s.name and e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT)
        )
        synergy_count = sum(
            1 for e in edges
            if e['type'] == EDGE_HELPS and (e['source'] == s.name or e['target'] == s.name)
        )

        row_data.append(html.Tr([
            html.Td(html.Span(
                s.name,
                id={"type": "suggestion-name-link", "index": s.name},
                title="Open in Details tab",
                style={"cursor": "pointer"},
            )),
            html.Td(s.type),
            html.Td(str(s.context)),
            html.Td(str(s.subcontext) if s.subcontext else "None"),
            html.Td(str(round(normalize(getattr(s, 'priority_score', 0))))),
            html.Td(str(s.value)),
            html.Td(str(s.interest) if hasattr(s, 'interest') and s.interest is not None else "None"),
            html.Td(str(s.difficulty)),
            html.Td(ConfigManager.format_time_friendly(s.time) if hasattr(s, 'time') and s.time else "0h"),
            html.Td(str(len(unlocks['hard']))),
            html.Td(str(len(unlocks['soft']))),
            html.Td(str(synergy_count)),
            html.Td(_bool_icon(has_resource)),
            html.Td(_bool_icon(getattr(s, 'obsidian_path', None))),
            html.Td(_bool_icon(getattr(s, 'google_drive_path', None))),
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
    """Build the dependency chains (hard/soft) and synergies display for the selected node.

    Returns (hard_chains_ui, soft_chains_ui, synergies_ui, description).
    """
    empty_msg = "Select a node to see dependencies."
    hard_ui = html.Div(className="text-muted", children=empty_msg)
    soft_ui = html.Div(className="text-muted", children=empty_msg)
    synergies_ui = html.Div(className="text-muted", children="Select a node to see synergies.")
    description = ""

    node_id = active_node_id or (tapped_node.get('id') if tapped_node else None)

    if not node_id:
        return hard_ui, soft_ui, synergies_ui, description

    node = manager.get_node(node_id)
    if node:
        description = node.description.strip() if node.description else "No description available."
    else:
        description = ""

    typed_chains = manager.get_prerequisite_chains_typed(node_id)

    edges = manager.get_edges()
    synergies = [e['target'] for e in edges if e['source'] == node_id and e['type'] == EDGE_HELPS]
    synergies += [e['source'] for e in edges if e['target'] == node_id and e['type'] == EDGE_HELPS]
    synergies = list(set(synergies))

    hard_items, soft_items = [], []
    for chain, chain_type in typed_chains:
        display_chain = chain[:-1] if chain and chain[-1] == active_node_id else chain
        if display_chain:
            item = html.Div(" \u2192 ".join(display_chain), style={"overflowWrap": "break-word"})
            if chain_type == "Hard":
                hard_items.append(item)
            else:
                soft_items.append(item)

    hard_ui = html.Div(hard_items) if hard_items else html.P("None", className="text-dark")
    soft_ui = html.Div(soft_items) if soft_items else html.P("None", className="text-dark")

    synergies_ui = html.Div([html.Div(s) for s in synergies]) if synergies else html.P("None", className="text-dark")

    return hard_ui, soft_ui, synergies_ui, description


# --- Link Row UI Helper ---

def render_link_rows(links, link_type, has_browse=False, has_open=True):
    """Build a list of input rows for a resource type.

    link_type: e.g. 'obsidian-link', 'drive-link', 'goal-add-obsidian-link'
    The browse/open/remove button IDs are derived from link_type automatically.
    """
    link_list = links or ['']
    prefix = link_type.replace('-link', '')  # e.g. 'obsidian', 'goal-add-obsidian'
    rows = []
    for i, path in enumerate(link_list):
        buttons = []
        if has_browse:
            buttons.append(dbc.Button(
                "\U0001f4c1", id={"type": f"btn-{prefix}-browse", "index": i},
                color="secondary", title="Browse",
                className="me-1 d-flex justify-content-center align-items-center p-0",
                style={"width": "38px"},
            ))
        if has_open:
            buttons.append(dbc.Button(
                html.I(className="bi bi-box-arrow-up-right", style={"fontSize": "0.85rem"}),
                id={"type": f"btn-{prefix}-open", "index": i},
                color="secondary", title="Open",
                className="me-1 d-flex justify-content-center align-items-center p-0",
                style={"width": "38px"},
            ))
        if len(link_list) > 1:
            buttons.append(dbc.Button(
                "\u00d7", id={"type": f"btn-{link_type}-remove", "index": i},
                color="danger", outline=True,
                className="d-flex justify-content-center align-items-center p-0",
                style={"width": "38px", "fontSize": "1.5rem"},
            ))
        rows.append(html.Div([
            dbc.Input(
                id={"type": link_type, "index": i}, type="text",
                value=path or '', placeholder="Enter path or URL...",
                className="me-1", style={"flex": "1"},
            ),
            *buttons,
        ], className="d-flex mb-1"))
    return rows


def spawn_local_file_picker(initial_dir, title, filetypes_list):
    """Launch a blocking Windows file-picker dialog in a subprocess. Returns the selected path or ''."""
    import logging
    import tempfile
    import sys
    import subprocess
    import os

    _logger = logging.getLogger(__name__)
    filetypes_str = str(filetypes_list)
    script = f'''import os
import tkinter as tk
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
        _logger.error(f"Error launching file picker: {e}")
        return ""
