"""
Shared helper functions for Dash callback modules.

Contains stateless utility functions extracted from callbacks.py to keep
the callback registration files focused on Dash I/O wiring.
"""

import json
from collections import defaultdict

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from config import ConfigManager
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from scoring import build_adjacency as build_scoring_adjacency, total_value


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


# --- Editor Dirty-State Check ---

_EDITOR_NEW_NODE_DEFAULTS = {
    'name': '', 'n_type': 'Learn', 'desc': '',
    'context': '', 'subctx': '', 'done': False,
    'val': 5, 'interest': 5, 'diff': 5,
    'time_o': 2, 'time_m': 4, 'time_p': 6, 'time_unit': 'weeks',
    'time_mode_inherited': False,
    'priority_rank': 'none', 'competence': '',
}


def _norm_str(s):
    return (s or '').strip()


def _norm_list(lst):
    """Canonicalize a list: drop empty strings, sort."""
    return sorted([v for v in (lst or []) if v])


def has_editor_unsaved_changes(
    manager, original_name,
    name, n_type, desc, context, subctx, status_done,
    val, interest, diff,
    time_o, time_m, time_p, time_unit,
    e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
    obs_link_values, drive_link_values, website_link_values,
    time_mode_val, priority_rank_val, competence_val,
    alias_values,
):
    """Check whether the node editor's form state differs from the last saved state.

    If ``original_name`` resolves to a DB node, compares form state vs DB (covers
    every editable field: scalars, edges, links, aliases, priority rank, and
    time values after converting back to hours). Otherwise treats it as a
    new-node form and compares against the blank-form defaults.
    """
    form_done = 'Done' in (status_done or [])
    form_time_mode_inherited = 'inherited' in (time_mode_val or [])
    form_priority_rank = priority_rank_val or 'none'

    # Compare time in the form's current display unit to avoid false positives
    # from the 2-decimal rounding in _friendly_time_estimates: a DB value like
    # 63 hours rendered as 1.58 weeks cannot round-trip back to 63.0 exactly.
    form_unit = time_unit or 'hours'
    multiplier = ConfigManager.get_time_multiplier(form_unit) or 1.0
    form_t_o = round(float(time_o or 0), 2)
    form_t_m = round(float(time_m or 0), 2)
    form_t_p = round(float(time_p or 0), 2)

    form_needs_h = _norm_list(e_needs_h)
    form_needs_s = _norm_list(e_needs_s)
    form_supp_h = _norm_list(e_supp_h)
    form_supp_s = _norm_list(e_supp_s)
    form_helps = _norm_list(e_helps)
    form_obs = _norm_list(obs_link_values)
    form_drive = _norm_list(drive_link_values)
    form_website = _norm_list(website_link_values)
    form_aliases = _norm_list(alias_values)

    old_node = manager.get_node(original_name) if original_name else None

    if old_node is None:
        # New-node form: any deviation from the blank defaults is "dirty".
        d = _EDITOR_NEW_NODE_DEFAULTS
        return (
            _norm_str(name) != d['name'] or
            (n_type or d['n_type']) != d['n_type'] or
            _norm_str(desc) != d['desc'] or
            _norm_str(context) != d['context'] or
            _norm_str(subctx) != d['subctx'] or
            form_done != d['done'] or
            int(val or d['val']) != d['val'] or
            int(interest or d['interest']) != d['interest'] or
            int(diff or d['diff']) != d['diff'] or
            float(time_o or 0) != d['time_o'] or
            float(time_m or 0) != d['time_m'] or
            float(time_p or 0) != d['time_p'] or
            (time_unit or d['time_unit']) != d['time_unit'] or
            form_time_mode_inherited != d['time_mode_inherited'] or
            form_priority_rank != d['priority_rank'] or
            _norm_str(competence_val) != d['competence'] or
            bool(form_needs_h) or bool(form_needs_s) or
            bool(form_supp_h) or bool(form_supp_s) or bool(form_helps) or
            bool(form_obs) or bool(form_drive) or bool(form_website) or
            bool(form_aliases)
        )

    # Existing-node form: compare against DB state.
    edges = manager.get_edges()
    db_needs_h = sorted({e['source'] for e in edges
                         if e['target'] == original_name and e['type'] == EDGE_NEEDS_HARD})
    db_needs_s = sorted({e['source'] for e in edges
                         if e['target'] == original_name and e['type'] == EDGE_NEEDS_SOFT})
    db_supp_h = sorted({e['target'] for e in edges
                        if e['source'] == original_name and e['type'] == EDGE_NEEDS_HARD})
    db_supp_s = sorted({e['target'] for e in edges
                        if e['source'] == original_name and e['type'] == EDGE_NEEDS_SOFT})
    db_helps_set = {e['target'] for e in edges
                    if e['source'] == original_name and e['type'] == EDGE_HELPS}
    db_helps_set |= {e['source'] for e in edges
                     if e['target'] == original_name and e['type'] == EDGE_HELPS}
    db_helps = sorted(db_helps_set)

    priority_goals = ConfigManager.get_priority_goals()
    if old_node.type == 'Goal' and old_node.name in priority_goals:
        db_priority_rank = str(priority_goals.index(old_node.name) + 1)
    else:
        db_priority_rank = 'none'

    db_aliases = _norm_list(manager.get_aliases(original_name))
    db_obs = _norm_list(parse_links(old_node.obsidian_path))
    db_drive = _norm_list(parse_links(old_node.google_drive_path))
    db_website = _norm_list(parse_links(old_node.website))

    db_t_o = round(float(old_node.time_o or 0) / multiplier, 2)
    db_t_m = round(float(old_node.time_m or 0) / multiplier, 2)
    db_t_p = round(float(old_node.time_p or 0) / multiplier, 2)

    # Type-specific fields: `priority_rank` only applies to Goal nodes, so
    # comparing it otherwise would pick up leftover form state from a
    # previously-edited Goal and produce a false "dirty" flag.
    current_type = n_type or old_node.type
    priority_matches = (current_type != 'Goal') or (form_priority_rank == db_priority_rank)

    return (
        _norm_str(name) != _norm_str(old_node.name) or
        (n_type or '') != (old_node.type or '') or
        _norm_str(desc) != _norm_str(old_node.description) or
        _norm_str(context) != _norm_str(old_node.context) or
        _norm_str(subctx) != _norm_str(old_node.subcontext) or
        form_done != (old_node.status == 'Done') or
        int(val or 5) != int(old_node.value or 5) or
        int(interest or 5) != int(old_node.interest or 5) or
        int(diff or 5) != int(old_node.difficulty or 5) or
        form_t_o != db_t_o or form_t_m != db_t_m or form_t_p != db_t_p or
        form_needs_h != db_needs_h or form_needs_s != db_needs_s or
        form_supp_h != db_supp_h or form_supp_s != db_supp_s or
        form_helps != db_helps or
        form_obs != db_obs or form_drive != db_drive or form_website != db_website or
        form_time_mode_inherited != (old_node.time_mode == 'inherited') or
        not priority_matches or
        _norm_str(competence_val) != _norm_str(old_node.competence) or
        form_aliases != db_aliases
    )


# --- Node CRUD Helpers ---

def handle_save(manager, name, n_type, desc, val, time_o, time_m, time_p, interest, diff,
                status_done, context, subctx, obs_path, drive_path, website_path,
                e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                time_mode='manual', competence=None):
    """Create or update a node and sync its edges. Returns a status message."""
    from models import Node

    target_status = "Done" if (status_done and "Done" in status_done) else "Open"

    node = Node(
        name=name, type=n_type, description=desc or "",
        value=val, time_o=time_o or 0, time_m=time_m or 0, time_p=time_p or 0,
        interest=interest, difficulty=diff,
        status=target_status, context=context or None, subcontext=(subctx or '').strip() or None,
        obsidian_path=(obs_path or '').strip() or None,
        google_drive_path=(drive_path or '').strip() or None,
        website=(website_path or '').strip() or None,
        time_mode=time_mode,
        competence=competence or None,
    )
    existing = manager.get_node(name)
    if existing:
        # Preserve fields that aren't represented in the editor form, otherwise
        # update_node would overwrite them with the Node dataclass defaults.
        node.dormant = existing.dormant
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
    # Clear override if parent was in the deleted set
    if names:
        override = ConfigManager.get_override()
        if override.get("parent") in names:
            ConfigManager.clear_override()
    return f"Deleted {len(names)} node(s)" if names else ""


# --- UI Formatting Helpers ---

def _bool_icon(val):
    """Render a boolean as a styled checkmark or cross."""
    if val:
        return html.Span("\u2713", style={"color": "#198754", "fontWeight": "bold"})
    return html.Span("\u2717", style={"color": "#dc3545"})


def format_suggestions_table(suggs, manager, selected_node_id=None, override_set=None):
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

    header_cells = [
        html.Th("Name"), html.Th("Type"), html.Th("Context"), html.Th("Subcontext"),
        html.Th("Priority"), html.Th("Value"), html.Th("Interest"), html.Th("Effort"), html.Th("Time"),
        html.Th("Hard Unlocks"), html.Th("Soft Unlocks"), html.Th("Synergies"),
        html.Th("Resources"), html.Th("Obsidian"), html.Th("Drive")
    ]
    if override_set:
        header_cells.append(html.Th("Override"))
    table_header = [html.Thead(html.Tr(header_cells))]

    override_color = ConfigManager.get_node_colors().get('Override', '#e83e8c') if override_set else None

    row_data = []
    for s in suggs:
        is_selected = (s.name == selected_node_id)
        row_class = "table-active" if is_selected else ""

        eff_time = manager.get_effective_time(s.name)
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

        row_cells = [
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
            html.Td(ConfigManager.format_time_friendly(eff_time) if eff_time > 0 else "0h"),
            html.Td(str(len(unlocks['hard']))),
            html.Td(str(len(unlocks['soft']))),
            html.Td(str(synergy_count)),
            html.Td(_bool_icon(has_resource)),
            html.Td(_bool_icon(getattr(s, 'obsidian_path', None))),
            html.Td(_bool_icon(getattr(s, 'google_drive_path', None))),
        ]
        if override_set:
            row_cells.append(html.Td(_bool_icon(s.name in override_set)))

        row_style = {"cursor": "pointer"}
        if override_set and s.name in override_set:
            row_style["borderLeft"] = f"3px solid {override_color}"
            row_style["backgroundColor"] = "rgba(232, 62, 140, 0.08)"
        row_data.append(html.Tr(row_cells, id={"type": "suggestion-row", "index": s.name}, className=row_class, style=row_style))

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
    ], style={"flex": "1", "minWidth": "200px", "maxWidth": "800px"})

    table_row = html.Div([table, desc_area], style={
        "display": "flex", "alignItems": "flex-start", "gap": "3rem",
    })

    return [table_row]


# --- Next-tab chain visualization helpers ---

_PILL_BG = '#2b3035'
_PILL_BORDER = '#495057'


def _render_chain_pills(chain, node_info=None, chain_id="chain", empty_msg="No chain found."):
    """Render a list of node names as styled pills with arrow separators.

    Args:
        chain: List of node names.
        node_info: Optional dict mapping node name -> {'subtasks': list[str]}.
            Badge shown on pills with remaining prereqs; click reveals the list.
        chain_id: Prefix for unique popover target IDs.
        empty_msg: Shown when chain is empty.
    """
    if not chain:
        return html.P(empty_msg, className="text-muted small")

    items = []
    for i, name in enumerate(chain):
        info = node_info.get(name, {}) if node_info else {}
        subtasks = info.get('subtasks', [])

        pill_style = {
            "padding": "2px 8px", "borderRadius": "4px",
            "fontSize": "0.82rem", "whiteSpace": "nowrap",
            "backgroundColor": _PILL_BG, "border": f"1px solid {_PILL_BORDER}",
        }

        pill = html.Span(name, style=pill_style)

        if subtasks:
            badge_id = f"{chain_id}-badge-{i}"
            badge = html.Span(str(len(subtasks)), id=badge_id, style={
                "position": "absolute", "top": "-7px", "right": "-7px",
                "backgroundColor": "#6c757d", "color": "#fff",
                "borderRadius": "8px", "fontSize": "0.6rem", "fontWeight": "600",
                "minWidth": "15px", "height": "15px", "lineHeight": "15px",
                "textAlign": "center", "padding": "0 3px", "cursor": "pointer",
            })
            prereq_list = html.Div(
                [html.Div(s, style={"padding": "1px 0"}) for s in subtasks],
                style={"maxHeight": "200px", "overflowY": "auto",
                       "fontSize": "0.8rem", "lineHeight": "1.4"},
            )
            popover = dbc.Popover([
                dbc.PopoverHeader("Hard Needs"),
                dbc.PopoverBody(prereq_list),
            ], target=badge_id, trigger="legacy", placement="bottom")
            wrapper = html.Span([pill, badge, popover], style={
                "position": "relative", "display": "inline-block",
            })
            items.append(wrapper)
        else:
            items.append(pill)

        if i < len(chain) - 1:
            items.append(html.Span(" \u2192 ", className="text-muted",
                                   style={"fontSize": "0.82rem"}))
    return html.Div(items, style={
        "padding": "8px 0", "overflowX": "auto", "whiteSpace": "nowrap",
        "display": "flex", "alignItems": "center", "gap": "2px",
        "justifyContent": "flex-start",
    })


def _build_hard_dag(manager):
    """Build a hard-edge DAG among non-Done nodes. Returns (non_done_names, dag_fwd, dag_rev)."""
    nodes = manager.get_all_nodes()
    edges = manager.get_edges()
    non_done_names = {n.name for n in nodes if n.status != 'Done'}

    dag_fwd = defaultdict(list)   # source -> targets that depend on source
    dag_rev = defaultdict(list)   # target -> sources (prerequisites of target)
    for e in edges:
        s, t = e['source'], e['target']
        if e['type'] == EDGE_NEEDS_HARD and s in non_done_names and t in non_done_names:
            dag_fwd[s].append(t)
            dag_rev[t].append(s)

    return nodes, edges, non_done_names, dag_fwd, dag_rev


def _topo_sort(non_done_names, dag_fwd):
    """Kahn's topological sort on the hard-edge DAG."""
    in_degree = defaultdict(int)
    for name in non_done_names:
        for tgt in dag_fwd.get(name, []):
            in_degree[tgt] += 1

    queue = [n for n in non_done_names if in_degree[n] == 0]
    topo = []
    while queue:
        node = queue.pop(0)
        topo.append(node)
        for nxt in dag_fwd.get(node, []):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
    return topo


def _compute_longest_prereq_chain(manager):
    """Find the longest hard-dependency chain among non-Done nodes."""
    _nodes, _edges, non_done_names, dag_fwd, _dag_rev = _build_hard_dag(manager)
    if not non_done_names:
        return []

    topo = _topo_sort(non_done_names, dag_fwd)

    dist = {n: 0 for n in non_done_names}
    parent = {n: None for n in non_done_names}
    for node in topo:
        for nxt in dag_fwd.get(node, []):
            if dist[node] + 1 > dist[nxt]:
                dist[nxt] = dist[node] + 1
                parent[nxt] = node

    if not dist:
        return []
    end = max(dist, key=dist.get)
    if dist[end] == 0:
        return []

    chain = []
    cur = end
    while cur is not None:
        chain.append(cur)
        cur = parent[cur]
    chain.reverse()
    return chain


def _compute_highest_value_path(manager):
    """Find the hard-edge chain whose cumulative total_value is maximized."""
    nodes, edges, non_done_names, dag_fwd, _dag_rev = _build_hard_dag(manager)
    if not non_done_names:
        return []

    # Compute total_value for each non-Done node
    hp = ConfigManager.get_hyperparams()
    w_v, w_i = hp.get('w_v', 1.0), hp.get('w_i', 1.0)
    d_H, d_S, d_Syn = hp.get('d_H', 0.6), hp.get('d_S', 0.25), hp.get('d_Syn', 0.35)
    all_nodes_dict = {n.name: n for n in nodes}
    node_names = set(all_nodes_dict.keys())
    H_out, S_out, Syn, Hard_in = build_scoring_adjacency(edges, node_names)

    tv = {}
    for name in non_done_names:
        tv[name] = total_value(name, set(), all_nodes_dict, H_out, S_out, Syn,
                               w_v, w_i, d_H, d_S, d_Syn)

    # DP: longest-weight path in DAG
    topo = _topo_sort(non_done_names, dag_fwd)
    dp = {n: tv.get(n, 0) for n in non_done_names}
    parent = {n: None for n in non_done_names}
    for node in topo:
        for nxt in dag_fwd.get(node, []):
            candidate = dp[node] + tv.get(nxt, 0)
            if candidate > dp[nxt]:
                dp[nxt] = candidate
                parent[nxt] = node

    if not dp:
        return []
    end = max(dp, key=dp.get)
    # Only return a chain if it has more than one node
    if parent[end] is None:
        return []

    chain = []
    cur = end
    while cur is not None:
        chain.append(cur)
        cur = parent[cur]
    chain.reverse()
    return chain


def _compute_unlock_path(manager):
    """Find the most valuable Blocked node and trace the critical prereq path to unlock it."""
    nodes, edges, non_done_names, dag_fwd, _dag_rev = _build_hard_dag(manager)
    blocked = [n for n in nodes if n.status == 'Blocked']
    if not blocked:
        return []

    # Score each blocked node
    hp = ConfigManager.get_hyperparams()
    w_v, w_i = hp.get('w_v', 1.0), hp.get('w_i', 1.0)
    d_H, d_S, d_Syn = hp.get('d_H', 0.6), hp.get('d_S', 0.25), hp.get('d_Syn', 0.35)
    all_nodes_dict = {n.name: n for n in nodes}
    node_names = set(all_nodes_dict.keys())
    H_out, S_out, Syn, Hard_in = build_scoring_adjacency(edges, node_names)

    best_node = None
    best_tv = -1
    for n in blocked:
        tv = total_value(n.name, set(), all_nodes_dict, H_out, S_out, Syn,
                         w_v, w_i, d_H, d_S, d_Syn)
        if tv > best_tv:
            best_tv = tv
            best_node = n.name

    if not best_node:
        return []

    # Trace backward: find longest chain of unsatisfied hard prereqs to the target
    # dag_fwd[node] = nodes that 'node' depends on (hard)
    # We want the chain: root_prereq -> ... -> prereq -> best_node
    # BFS/DP to find longest path ending at best_node within its prereq subgraph
    # First collect reachable unsatisfied prereqs
    reachable = set()
    stack = [best_node]
    while stack:
        cur = stack.pop()
        for dep in dag_fwd.get(cur, []):
            if dep not in reachable:
                reachable.add(dep)
                stack.append(dep)

    if not reachable:
        return [best_node]

    # Build sub-DAG of reachable prereqs + best_node
    sub_nodes = reachable | {best_node}
    sub_fwd = defaultdict(list)
    for s in sub_nodes:
        for t in dag_fwd.get(s, []):
            if t in sub_nodes:
                sub_fwd[s].append(t)

    # Longest path ending at a root (no further prereqs) starting from best_node
    # Reverse: find longest path in sub-DAG from any root to best_node
    sub_rev = defaultdict(list)
    for s in sub_nodes:
        for t in sub_fwd.get(s, []):
            sub_rev[t].append(s)

    # Topo sort on sub_rev direction (reverse edges: prereq -> dependent)
    in_deg = defaultdict(int)
    for s in sub_nodes:
        for t in sub_rev.get(s, []):
            in_deg[t] += 1
    queue = [n for n in sub_nodes if in_deg[n] == 0]
    topo = []
    while queue:
        nd = queue.pop(0)
        topo.append(nd)
        for nxt in sub_rev.get(nd, []):
            in_deg[nxt] -= 1
            if in_deg[nxt] == 0:
                queue.append(nxt)

    # DP longest path in reversed direction (prereq -> dependent)
    dist = {n: 0 for n in sub_nodes}
    parent = {n: None for n in sub_nodes}
    for nd in topo:
        for nxt in sub_rev.get(nd, []):
            if dist[nd] + 1 > dist[nxt]:
                dist[nxt] = dist[nd] + 1
                parent[nxt] = nd

    # Reconstruct chain: start from the most actionable prereq, end at blocked target
    chain = []
    cur = best_node
    while cur is not None:
        chain.append(cur)
        cur = parent[cur]
    # chain is already [blocked_target, ..., root_prereq] — keep this order
    # so the display reads: start here → ... → unlock this
    return chain


def format_next_visualizations(manager):
    """Compute and render the three chain visualizations for the Next tab."""
    all_nodes = manager.get_all_nodes()
    edges = manager.get_edges()

    # Build reverse hard-edge DAG among non-Done nodes for subtask counting
    # Edge source → target means "source is prerequisite of target"
    # dag_rev[target] = [sources] = prerequisites of target
    non_done_names = {n.name for n in all_nodes if n.status != 'Done'}
    dag_rev = defaultdict(list)
    for e in edges:
        if e['type'] == EDGE_NEEDS_HARD:
            s, t = e['source'], e['target']
            if s in non_done_names and t in non_done_names:
                dag_rev[t].append(s)

    # Collect transitive non-Done hard prerequisites per node via BFS
    _subtask_cache = {}
    def _get_subtasks(name):
        if name in _subtask_cache:
            return _subtask_cache[name]
        visited = set()
        stack = list(dag_rev.get(name, []))
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            stack.extend(dag_rev.get(cur, []))
        _subtask_cache[name] = sorted(visited)
        return _subtask_cache[name]

    node_status = {n.name: n.status for n in all_nodes}
    node_info = {
        n.name: {'subtasks': _get_subtasks(n.name)}
        for n in all_nodes
    }

    def _trim_leading_blocked(chain):
        """Remove leading Blocked nodes so chains start with an actionable node."""
        for i, name in enumerate(chain):
            if node_status.get(name) != 'Blocked':
                return chain[i:]
        return chain

    sections = [
        html.H6("Chains", className="text-muted mb-1 mt-4", style=SECTION_TITLE_STYLE),
        html.P("Dependency paths through your graph, offering perspectives beyond individual task rankings.",
               className="text-muted small mb-0"),
    ]

    _sub_style = {"fontSize": "1rem", "fontWeight": "500"}
    _info_icon_style = {
        "fontSize": "1rem", "color": "#6c757d", "cursor": "pointer",
        "marginLeft": "6px",
    }

    def _sub_header(title, info_id, description):
        return html.Div([
            html.H6(title, className="text-muted mb-0 d-inline", style=_sub_style),
            html.Span(
                "\u24d8", id=info_id,
                style=_info_icon_style,
            ),
            dbc.Popover(
                dbc.PopoverBody(description),
                target=info_id, trigger="click", placement="right",
            ),
        ], className="mb-1")

    value_path = _trim_leading_blocked(_compute_highest_value_path(manager))
    sections.append(html.Div([
        _sub_header("Highest-Value Dependency Path", "chain-info-value",
                     "The connected chain of tasks (by hard edges) whose cumulative total value "
                     "is maximized. Shows which thread of work carries the most value."),
        _render_chain_pills(value_path, node_info, chain_id="value",
                            empty_msg="No multi-node dependency paths found."),
    ], className="mt-3"))

    unlock = _trim_leading_blocked(_compute_unlock_path(manager))
    sections.append(html.Div([
        _sub_header("Path to Most Valuable Blocked Task", "chain-info-blocked",
                     "Identifies the blocked task with the highest total value, then traces "
                     "the prerequisite chain you need to complete to unblock it."),
        _render_chain_pills(unlock, node_info, chain_id="blocked",
                            empty_msg="No blocked nodes found."),
    ], className="mt-3"))

    longest = _trim_leading_blocked(_compute_longest_prereq_chain(manager))
    sections.append(html.Div([
        _sub_header("Longest Prerequisite Chain", "chain-info-longest",
                     "The longest sequence of hard-dependency steps among incomplete tasks. "
                     "Shows the critical path bottleneck in your graph."),
        _render_chain_pills(longest, node_info, chain_id="longest",
                            empty_msg="No dependency chains found."),
    ], className="mt-3"))

    return sections


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


# ---------------------------------------------------------------------------
# Explain Score modal renderer
# ---------------------------------------------------------------------------

# Maps the `via` field from scoring.explain_score to a bar color.
_VIA_COLORS = {
    'Self':    '#6c757d',  # neutral grey — the node itself
    'Hard':    '#ffc107',  # amber — matches Goal/warning palette
    'Soft':    '#0d6efd',  # blue — matches Open/primary palette
    'Synergy': '#9d65c9',  # purple — distinct from the above
}


def _trunc(name: str, max_len: int = 25) -> str:
    """Truncate long names with an ellipsis; full name goes in hover."""
    return name if len(name) <= max_len else name[:max_len - 1] + '\u2026'


def _explain_summary_table(breakdown: dict, normalized):
    """Grouped summary table: Value / Cost / Score.

    Every row maps to a field in scoring.explain_score's output. Edge
    cases: ineligible nodes show '—' for Raw and Normalized and annotate
    with the block reason; leaf nodes show zero-valued downstream rows in
    muted style; inherited-time nodes annotate the Cost row; `normalized`
    may be None (displays '—') when the caller could not determine a
    normalization base.
    """
    comp = breakdown['composition']
    cost_info = breakdown['cost']
    boost = breakdown['goal_boost']
    eligible = breakdown['eligible']
    downstream = comp['hard_cascade'] + comp['soft_cascade'] + comp['synergy']

    header_style = {
        "fontWeight": "700",
        "letterSpacing": "0.06em",
        "textTransform": "uppercase",
        "fontSize": "1.05rem",
        "color": "#ffffff",
        "backgroundColor": "#212529",
        "borderTop": "1px solid #495057",
        "paddingTop": "10px",
        "paddingBottom": "8px",
    }
    total_style = {"fontWeight": "600", "borderTop": "1px solid #495057"}
    num_style = {"textAlign": "right", "fontVariantNumeric": "tabular-nums",
                 "whiteSpace": "nowrap"}
    muted_style = {"color": "#adb5bd", "fontSize": "0.88rem"}
    muted_num_style = {**num_style, **muted_style}
    zero_num_style = {**num_style, "color": "#6c757d"}

    def _fmt(v: float) -> str:
        return f"{v:.2f}"

    def _num_cell(v: float, style=None):
        s = dict(style) if style else dict(num_style)
        if abs(v) < 1e-9 and style is not total_style:
            s = dict(zero_num_style)
        return html.Td(_fmt(v), style=s)

    rows = []

    # --- Value section ------------------------------------------------
    rows.append(html.Tr([html.Td("Value", colSpan=2, style=header_style)]))
    rows.append(html.Tr([html.Td("Intrinsic"), _num_cell(comp['iv'])]))
    rows.append(html.Tr([html.Td("Downstream"), _num_cell(downstream)]))
    for label, value in (
        ("via Hard", comp['hard_cascade']),
        ("via Soft", comp['soft_cascade']),
        ("via Synergy", comp['synergy']),
    ):
        rows.append(html.Tr([
            html.Td(label, className="ps-4", style=muted_style),
            html.Td(_fmt(value),
                    style=muted_num_style if value > 1e-9 else zero_num_style),
        ]))
    rows.append(html.Tr([
        html.Td("Total", style=total_style),
        html.Td(_fmt(comp['total_value']), style={**num_style, **total_style}),
    ]))

    # --- Cost section -------------------------------------------------
    rows.append(html.Tr([html.Td("Cost", colSpan=2, style=header_style)]))
    cost_label = [html.Span("Perceived cost")]
    if cost_info['time_overridden']:
        cost_label.append(html.Span(" (time inherited)",
                                    style={**muted_style, "marginLeft": "4px"}))
    rows.append(html.Tr([
        html.Td(cost_label),
        _num_cell(cost_info['cost']),
    ]))

    # --- Score section ------------------------------------------------
    rows.append(html.Tr([html.Td("Score", colSpan=2, style=header_style)]))
    if eligible:
        raw_label = [html.Span("Raw")]
        if boost is not None:
            raw_label.append(html.Span(
                f" (includes goal boost ×{boost['multiplier']:.3f} · rank #{boost['rank']} · {boost['goal']})",
                style={**muted_style, "marginLeft": "4px"},
            ))
        rows.append(html.Tr([
            html.Td(raw_label),
            _num_cell(breakdown['score']),
        ]))
        norm_display = f"{normalized}" if normalized is not None else "—"
        rows.append(html.Tr([
            html.Td("Normalized"),
            html.Td(norm_display, style=num_style),
        ]))
    else:
        rows.append(html.Tr([
            html.Td([html.Span("Raw"),
                     html.Span(f" (ineligible: {breakdown['block_reason']})",
                               style={**muted_style, "marginLeft": "4px"})]),
            html.Td("—", style=num_style),
        ]))
        rows.append(html.Tr([
            html.Td("Normalized"),
            html.Td("—", style=num_style),
        ]))

    return dbc.Table(
        [html.Tbody(rows)],
        borderless=True, size="sm",
        className="mb-0",
        style={"color": "#dee2e6", "marginTop": "4px"},
    )


def _explain_bar_chart(contributors: list, top_n: int):
    """Horizontal Plotly bar of top-N contributors, colored by `via`.

    Long node names are truncated for the y-axis tick labels (full name
    preserved in hover); `ticksuffix` adds breathing room between labels
    and bar starts — both patterns lifted from analyze_callbacks._trunc.
    """
    rows = list(reversed(contributors[:top_n]))  # Plotly stacks bottom-up
    full_names = [r['name'] for r in rows]
    display_names = [_trunc(n) for n in full_names]
    vals = [r['contribution'] for r in rows]
    colors = [_VIA_COLORS.get(r['via'], '#6c757d') for r in rows]
    bar_texts = [f"{r['contribution']:.2f}" for r in rows]
    customdata = [
        [full_names[i], rows[i]['via'], rows[i]['pct_of_tv'],
         rows[i]['depth'], rows[i]['weight'], rows[i]['iv']]
        for i in range(len(rows))
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=vals, y=display_names,
        orientation='h',
        marker_color=colors,
        text=bar_texts,
        textposition='outside',
        cliponaxis=False,
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Contribution: %{x:.2f} (%{customdata[2]:.1f}% of total value)<br>"
            "Via: %{customdata[1]}<br>"
            "Depth: %{customdata[3]}<br>"
            "Weight: %{customdata[4]:.3f}<br>"
            "Intrinsic value: %{customdata[5]:.2f}"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='#1a1d21',
        plot_bgcolor='#1a1d21',
        margin=dict(l=10, r=40, t=10, b=40),
        xaxis_title="Contribution to Total Value",
        yaxis=dict(automargin=True, ticksuffix="  "),
        showlegend=False,
        height=max(260, 30 * len(rows) + 80),
    )
    return fig


def build_explain_summary(breakdown: dict, normalized=None):
    """Dash component for the Value/Cost/Score summary table.

    `breakdown` is the dict from scoring.explain_score. `normalized` is
    the integer 0–100 score the Next tab would show, or None to render
    as '—'. Returns a single component; the caller slots it into the
    static modal body in details_layout.
    """
    if breakdown is None:
        return html.Div("Node not found.", className="text-muted",
                        style={"padding": "16px"})
    return _explain_summary_table(breakdown, normalized)


def build_explain_chart(contributors, top_n: int = 10):
    """Plotly figure for the Top Contributors bar chart.

    `contributors` is the sorted list from scoring.explain_score (or the
    serialized copy stored in dcc.Store). Returns a go.Figure; the
    callback assigns it to the static dcc.Graph's figure prop.
    """
    return _explain_bar_chart(contributors or [], top_n)
