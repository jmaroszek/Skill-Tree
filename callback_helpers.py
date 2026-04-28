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
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from scoring import (
    build_adjacency as build_scoring_adjacency,
    total_value,
    perceived_cost,
    _get_goal_subtree_from_adjacency,
)


SECTION_TITLE_STYLE = {"fontSize": "1.3rem", "fontWeight": "600"}


def build_context_weight_rows(contexts, ctx_weights):
    """Build the per-context weight input rows for the Contexts settings tab."""
    rows = []
    for ctx_name in contexts:
        rows.append(dbc.Row([
            dbc.Col(dbc.Label(ctx_name, className="mb-0"), width=4,
                    className="d-flex align-items-center"),
            dbc.Col(dbc.Input(
                id={"type": "setting-context-weight", "index": ctx_name},
                type="number", min=0, max=10, step=0.1,
                value=float(ctx_weights.get(ctx_name, 1.0)),
            ), width=4),
        ], className="mb-2"))
    return rows


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
            # Case-insensitive resolve so 'alias:mathnotes' finds 'MathNotes'.
            resolved = _mgr.resolve_alias(alias_key)
            return resolved if resolved is not None else search_val
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
    filters = {}

    contexts = []
    if f_context and f_context != "All":
        if isinstance(f_context, list):
            contexts = f_context
        elif f_context != "None":
            contexts = [f_context]
        else:
            contexts = [None]

    # Subcontext dropdown values are encoded as "ctx::sub" composites by
    # update_filter_subcontexts so the (value -> context) mapping is explicit.
    # Plain strings (legacy state / test fixtures that haven't adopted composites)
    # are accepted as context-agnostic subcontext names.
    ctx_to_subs: dict = {}
    plain_subs: list = []
    if f_subcontext and f_subcontext != "All":
        values = f_subcontext if isinstance(f_subcontext, list) else [f_subcontext]
        for v in values:
            if not v or not isinstance(v, str):
                continue
            v = v.strip()
            if not v:
                continue
            if "::" in v:
                c, s = v.split("::", 1)
                ctx_to_subs.setdefault(c, []).append(s)
            else:
                plain_subs.append(v)

    if contexts and ctx_to_subs:
        # Selective union: for each selected context, use the subcontexts the user
        # explicitly tagged to that context. Contexts with no selection fall back
        # to "include all nodes of that context" (per UX introduced in 58b4866:
        # "show all Mind, but only specific STEM").
        pairs = [(c, ctx_to_subs.get(c) or None) for c in contexts]
        filters['context_subcontext_union'] = pairs
    elif contexts and plain_subs:
        # Legacy path: plain subcontext names with contexts selected — apply the
        # bare list against every selected context (pre-composite behavior).
        filters['context_subcontext_union'] = [(c, plain_subs) for c in contexts]
    elif contexts:
        filters['context'] = contexts
    elif ctx_to_subs or plain_subs:
        flat = [s for subs in ctx_to_subs.values() for s in subs] + plain_subs
        filters['subcontext'] = flat
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


# --- Editor Dirty-State Check (snapshot-based) ---


def _norm_str(s):
    return (s or '').strip()


def _norm_list(lst):
    """Canonicalize a list: drop empty strings, sort."""
    return sorted([v for v in (lst or []) if v])


# Pristine snapshot for the new-node form — mirrors the def_out defaults
# emitted by populate_editor when the user clicks "+ New Node".
NEW_NODE_SNAPSHOT = {
    'name': '', 'n_type': 'Learn', 'desc': '',
    'context': '', 'subctx': '',
    'status_done': [],
    'val': 5, 'interest': 5, 'diff': 5,
    'time_o': 2, 'time_m': 4, 'time_p': 6, 'time_unit': 'weeks',
    'e_needs_h': [], 'e_needs_s': [],
    'e_supp_h': [], 'e_supp_s': [], 'e_helps': [],
    'obs_links': [''], 'drive_links': [''], 'website_links': [''],
    'time_mode': [],
    'priority_rank': 'none', 'competence': '',
    'aliases': [''],
}


def build_editor_snapshot(manager, node_name):
    """Build a snapshot of the editor form state for an existing node.

    The snapshot dict mirrors exactly what populate_editor writes into the form
    fields, *including* any post-display transformations (e.g. Drive paths after
    strip_gdrive_prefix). The dirty check compares form State against this
    snapshot so display transformations don't produce false-positives.

    Returns None if the node doesn't exist.
    """
    # Local import — _friendly_time_estimates lives in callbacks.py which
    # imports from this module, so we defer to avoid a circular import.
    from callbacks import _friendly_time_estimates

    node = manager.get_node(node_name) if node_name else None
    if node is None:
        return None

    edges = manager.get_edges()
    # The editor's edge dropdowns get their options from manager.get_all_nodes(),
    # which excludes dormant nodes. A dcc.Dropdown silently filters its `value`
    # to entries present in `options`, so any edge to/from a dormant node is
    # invisible to the form's State. The snapshot must mirror this filter, or
    # the dirty check fires every X-close on nodes with dormant prerequisites.
    non_dormant_names = {n.name for n in manager.get_all_nodes()}
    needs_h = sorted({e['source'] for e in edges
                      if e['target'] == node_name and e['type'] == EDGE_NEEDS_HARD
                      and e['source'] in non_dormant_names})
    needs_s = sorted({e['source'] for e in edges
                      if e['target'] == node_name and e['type'] == EDGE_NEEDS_SOFT
                      and e['source'] in non_dormant_names})
    supp_h = sorted({e['target'] for e in edges
                     if e['source'] == node_name and e['type'] == EDGE_NEEDS_HARD
                     and e['target'] in non_dormant_names})
    supp_s = sorted({e['target'] for e in edges
                     if e['source'] == node_name and e['type'] == EDGE_NEEDS_SOFT
                     and e['target'] in non_dormant_names})
    helps_set = {e['target'] for e in edges
                 if e['source'] == node_name and e['type'] == EDGE_HELPS
                 and e['target'] in non_dormant_names}
    helps_set |= {e['source'] for e in edges
                  if e['target'] == node_name and e['type'] == EDGE_HELPS
                  and e['source'] in non_dormant_names}
    helps = sorted(helps_set)

    priority_goals = ConfigManager.get_priority_goals()
    if node.type == 'Goal' and node.name in priority_goals:
        priority_rank = str(priority_goals.index(node.name) + 1)
    else:
        priority_rank = 'none'

    friendly_o, friendly_m, friendly_p, friendly_unit = _friendly_time_estimates(
        node.time_o, node.time_m, node.time_p
    )

    aliases = manager.get_aliases(node_name) or ['']

    return {
        'name': node.name,
        'n_type': node.type,
        'desc': node.description or '',
        'context': node.context or '',
        'subctx': node.subcontext or '',
        'status_done': [STATUS_DONE] if node.status == STATUS_DONE else [],
        'val': node.value or 5,
        'interest': node.interest or 5,
        'diff': node.difficulty or 5,
        'time_o': friendly_o,
        'time_m': friendly_m,
        'time_p': friendly_p,
        'time_unit': friendly_unit,
        'e_needs_h': needs_h,
        'e_needs_s': needs_s,
        'e_supp_h': supp_h,
        'e_supp_s': supp_s,
        'e_helps': helps,
        # Drive paths are stripped of the configured GDrive root prefix in
        # render_drive_links before display, so the form's State value is the
        # stripped form. Snapshot must match.
        'obs_links': parse_links(node.obsidian_path),
        'drive_links': strip_gdrive_prefix(parse_links(node.google_drive_path)),
        'website_links': parse_links(node.website),
        'time_mode': ['inherited'] if node.time_mode == 'inherited' else [],
        'priority_rank': priority_rank,
        'competence': node.competence or '',
        'aliases': aliases,
    }


def snapshot_from_form_state(form_values, linted_name, linted_aliases):
    """Build a pristine snapshot directly from the form State just saved.

    Unlike build_editor_snapshot (DB round-trip + display transforms),
    this snapshots what the form actually holds — so the post-save dirty
    check can't trip on heuristic drift (e.g. _friendly_time_estimates
    picking a different time_unit from DB hours than the user selected).

    linted_name / linted_aliases are the only values the app legitimately
    rewrites in the form after save (via the title-case linter). Pass them
    in so the snapshot agrees with the form's post-save rewritten state.
    """
    return {
        'name': linted_name,
        'n_type': form_values.get('n_type'),
        'desc': form_values.get('desc') or '',
        'context': form_values.get('context') or '',
        'subctx': form_values.get('subctx') or '',
        'status_done': form_values.get('status_done') or [],
        'val': form_values.get('val', 5),
        'interest': form_values.get('interest', 5),
        'diff': form_values.get('diff', 5),
        'time_o': form_values.get('time_o'),
        'time_m': form_values.get('time_m'),
        'time_p': form_values.get('time_p'),
        'time_unit': form_values.get('time_unit'),
        'e_needs_h': form_values.get('e_needs_h') or [],
        'e_needs_s': form_values.get('e_needs_s') or [],
        'e_supp_h': form_values.get('e_supp_h') or [],
        'e_supp_s': form_values.get('e_supp_s') or [],
        'e_helps': form_values.get('e_helps') or [],
        'obs_links': form_values.get('obs_links') or [''],
        'drive_links': form_values.get('drive_links') or [''],
        'website_links': form_values.get('website_links') or [''],
        'time_mode': form_values.get('time_mode') or [],
        'priority_rank': form_values.get('priority_rank') or 'none',
        'competence': form_values.get('competence') or '',
        'aliases': linted_aliases or [''],
    }


def is_form_dirty_vs_snapshot(snapshot, form_values):
    """Compare current editor form State to the pristine snapshot.

    snapshot:    dict from build_editor_snapshot / NEW_NODE_SNAPSHOT, or None.
    form_values: dict of current State values keyed the same as the snapshot.

    Returns False if snapshot is None — no baseline means we can't tell, and
    treating as not-dirty lets the X button always close in that edge case.
    """
    if snapshot is None:
        return False

    # Scalar string fields — strip whitespace before comparing.
    for k in ('name', 'desc', 'context', 'subctx', 'competence'):
        if _norm_str(form_values.get(k)) != _norm_str(snapshot.get(k)):
            return True

    # Type / time_unit / priority_rank — direct equality with empty-coercion.
    if (form_values.get('n_type') or '') != (snapshot.get('n_type') or ''):
        return True
    if (form_values.get('time_unit') or '') != (snapshot.get('time_unit') or ''):
        return True
    if (form_values.get('priority_rank') or 'none') != (snapshot.get('priority_rank') or 'none'):
        return True

    # Integer fields with a default-of-5 convention.
    for k in ('val', 'interest', 'diff'):
        if int(form_values.get(k) or 5) != int(snapshot.get(k) or 5):
            return True

    # Time fields — compare with 2-decimal rounding to match form display.
    for k in ('time_o', 'time_m', 'time_p'):
        if round(float(form_values.get(k) or 0), 2) != round(float(snapshot.get(k) or 0), 2):
            return True

    # Checkbox-list fields — set comparison.
    for k in ('status_done', 'time_mode'):
        if set(form_values.get(k) or []) != set(snapshot.get(k) or []):
            return True

    # Multi-value list fields — drop empties, sort, compare.
    for k in ('e_needs_h', 'e_needs_s', 'e_supp_h', 'e_supp_s', 'e_helps',
              'obs_links', 'drive_links', 'website_links', 'aliases'):
        if _norm_list(form_values.get(k)) != _norm_list(snapshot.get(k)):
            return True

    return False


# --- Node CRUD Helpers ---

def handle_save(manager, name, n_type, desc, val, time_o, time_m, time_p, interest, diff,
                status_done, context, subctx, obs_path, drive_path, website_path,
                e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                time_mode='manual', competence=None):
    """Create or update a node and sync its edges. Returns a status message."""
    from models import Node

    target_status = STATUS_DONE if (status_done and STATUS_DONE in status_done) else STATUS_OPEN

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
        node.status = STATUS_OPEN if node.status == STATUS_DONE else STATUS_DONE
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

    if not selected_node_id:
        desc_content = "Click a row to see its description"
    else:
        desc_content = node.description.strip() if node and node.description and node.description.strip() else "None"

    desc_area = html.Div([
        html.H6("Description", className="text-muted mb-2", style=SECTION_TITLE_STYLE),
        html.Div(desc_content, style={"color": "#dee2e6", "whiteSpace": "pre-wrap", "fontSize": "0.95rem"})
    ], style={"flex": "1", "minWidth": "200px", "maxWidth": "800px"})

    table_row = html.Div([table, desc_area], style={
        "display": "flex", "alignItems": "flex-start", "gap": "3rem",
    })

    return [table_row, *format_value_chain_section(manager)]


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
    non_done_names = {n.name for n in nodes if n.status != STATUS_DONE}

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


def _compute_highest_priority_path(manager):
    """Find the hard-edge chain whose cumulative priority score is maximized.

    Mirrors the full scoring formula from `score_nodes` (TV / cost, goal boost,
    context weight, density normalization) but skips the eligibility gate so
    Blocked nodes contribute their would-be priority to chain weight. Goals
    score 0 — they're terminal endpoints, not work.
    """
    nodes, edges, non_done_names, dag_fwd, _dag_rev = _build_hard_dag(manager)
    if not non_done_names:
        return []

    hp = ConfigManager.get_hyperparams()
    w_v, w_i = hp.get('w_v', 1.0), hp.get('w_i', 1.0)
    d_H, d_S = hp.get('d_H', 0.6), hp.get('d_S', 0.25)
    d_Syn_pair = hp.get('d_Syn_pair', 0.10)
    d_Syn_mul = hp.get('d_Syn_mul', 0.40)
    w_e, w_t, beta = hp.get('w_e', 2.5), hp.get('w_t', 1.0), hp.get('beta', 0.85)
    goal_boost = hp.get('goal_boost', 1.5)
    alpha = hp.get('alpha', 0.0)
    context_weights = ConfigManager.get_context_weights() or {}

    all_nodes_dict = {n.name: n for n in nodes}
    H_out, S_out, Syn, Hard_in = build_scoring_adjacency(edges, set(all_nodes_dict.keys()))

    n_active_map = {}
    for n in nodes:
        if n.type == 'Goal' or n.status in (STATUS_DONE, STATUS_BLOCKED):
            continue
        if n.context is None:
            continue
        key = (n.context, n.subcontext)
        n_active_map[key] = n_active_map.get(key, 0) + 1

    rank_multipliers = [
        goal_boost,
        1 + (goal_boost - 1) * 0.66,
        1 + (goal_boost - 1) * 0.33,
    ]
    priority_goals = ConfigManager.get_priority_goals()
    node_to_boost = {}
    if priority_goals:
        for rank_idx, g in enumerate(priority_goals[:3]):
            multiplier = rank_multipliers[rank_idx]
            subtree = _get_goal_subtree_from_adjacency(g, Hard_in)
            for n_name in subtree:
                if n_name not in node_to_boost or multiplier > node_to_boost[n_name]:
                    node_to_boost[n_name] = multiplier

    score_map = {}
    for name in non_done_names:
        node = all_nodes_dict.get(name)
        if not node or node.type == 'Goal':
            score_map[name] = 0.0
            continue
        t_override = 0.0 if node.time_mode == 'inherited' else None
        cost = perceived_cost(node, w_e, w_t, beta, time_override=t_override)
        tv = total_value(name, set(), all_nodes_dict, H_out, S_out, Syn,
                         w_v, w_i, d_H, d_S, d_Syn_pair, d_Syn_mul)
        score = tv / cost
        if name in node_to_boost:
            score *= node_to_boost[name]
        weight = context_weights.get(node.context, 1.0) if node.context else 1.0
        n_bucket = max(1, n_active_map.get((node.context, node.subcontext), 1))
        density_mult = (1.0 / (n_bucket ** alpha)) if alpha > 0 else 1.0
        score_map[name] = score * weight * density_mult

    topo = _topo_sort(non_done_names, dag_fwd)
    dp = {n: score_map.get(n, 0) for n in non_done_names}
    parent = {n: None for n in non_done_names}
    for node in topo:
        for nxt in dag_fwd.get(node, []):
            candidate = dp[node] + score_map.get(nxt, 0)
            if candidate > dp[nxt]:
                dp[nxt] = candidate
                parent[nxt] = node

    if not dp:
        return []
    end = max(dp, key=dp.get)
    if parent[end] is None:
        return []

    chain = []
    cur = end
    while cur is not None:
        chain.append(cur)
        cur = parent[cur]
    chain.reverse()
    return chain


def format_value_chain_section(manager):
    """Render the highest-value dependency chain subsection."""
    all_nodes = manager.get_all_nodes()
    edges = manager.get_edges()

    # Build reverse hard-edge DAG among non-Done nodes for subtask counting
    # Edge source → target means "source is prerequisite of target"
    # dag_rev[target] = [sources] = prerequisites of target
    non_done_names = {n.name for n in all_nodes if n.status != STATUS_DONE}
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
            if node_status.get(name) != STATUS_BLOCKED:
                return chain[i:]
        return chain

    value_path = _trim_leading_blocked(_compute_highest_priority_path(manager))

    sub_style = {"fontSize": "1rem", "fontWeight": "500"}
    info_icon_style = {
        "fontSize": "1rem", "color": "#6c757d", "cursor": "pointer",
        "marginLeft": "6px",
    }

    return [
        html.Div([
            html.Div([
                html.H6("Highest-Priority Dependency Path",
                        className="text-muted mb-0 d-inline", style=sub_style),
                html.Span("\u24d8", id="chain-info-value", style=info_icon_style),
                dbc.Popover(
                    dbc.PopoverBody(
                        "The connected chain of tasks (by hard edges) whose cumulative priority "
                        "score is maximized."
                    ),
                    target="chain-info-value", trigger="click", placement="right",
                ),
            ], className="mb-1"),
            _render_chain_pills(value_path, node_info, chain_id="value",
                                empty_msg="No multi-node dependency paths found."),
        ], className="mt-3"),
    ]


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
# Cool & quiet palette. Hard is a darker rugged blue (matches subtasks-
# table Hard and the HardRelPri badge in the node-info stack); Soft
# neutral slate; Synergy cyan-teal (categorically different — mutual,
# multiplicative reinforcement, not a weaker prereq). Self is a warm
# sand off the cool axis entirely so it can't be confused with Soft.
_VIA_COLORS = {
    'Self':    '#685e52',  # warm sand — the node itself, off the edge axis
    'Hard':    '#2a4d6e',  # darker rugged blue (must-have)
    'Soft':    '#576068',  # neutral slate (should-have)
    'Synergy': '#466a78',  # cyan-teal (mutual, multiplicative — categorically different)
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

    # Synergy multiplier on intrinsic — kicks in only when at least one
    # synergy partner is Done. Hidden when inactive (multiplier == 1.0)
    # to keep the table tight.
    iv_multiplier = comp.get('iv_multiplier', 1.0)
    iv_mult_contribution = comp.get('iv_multiplier_contribution', 0.0)
    if iv_multiplier > 1.0 + 1e-9:
        done_count = comp.get('done_synergy_count', 0)
        partner_word = "partner" if done_count == 1 else "partners"
        label = f"Synergy multiplier (×{iv_multiplier:.2f}, {done_count} Done {partner_word})"
        rows.append(html.Tr([
            html.Td(label),
            _num_cell(iv_mult_contribution),
        ]))

    rows.append(html.Tr([html.Td("Downstream"), _num_cell(downstream)]))
    for label, value in (
        ("via Hard", comp['hard_cascade']),
        ("via Soft", comp['soft_cascade']),
        ("via Synergy (pair bonus)", comp['synergy']),
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
        cost_label.append(html.Span(" (container — inherited time treated as 0)",
                                    style={**muted_style, "marginLeft": "4px"}))
    rows.append(html.Tr([
        html.Td(cost_label),
        _num_cell(cost_info['cost']),
    ]))

    # --- Adjustments section (shown only if any multiplier is non-trivial) --
    ctx_adj = breakdown.get('context_adjustment') or {}
    ctx_weight = ctx_adj.get('weight', 1.0)
    density_mult = ctx_adj.get('density_mult', 1.0)
    n_bucket = ctx_adj.get('n_bucket', 1)
    alpha_val = ctx_adj.get('alpha', 0.0)
    has_boost = boost is not None
    has_weight = abs(ctx_weight - 1.0) > 1e-9
    has_density = abs(density_mult - 1.0) > 1e-9
    has_any_adjustment = has_boost or has_weight or has_density

    if has_any_adjustment:
        rows.append(html.Tr([html.Td("Adjustments", colSpan=2, style=header_style)]))
        combined = 1.0
        if has_boost:
            rows.append(html.Tr([
                html.Td([html.Span("Goal Boost"),
                         html.Span(f" (rank #{boost['rank']} · {boost['goal']})",
                                   style={**muted_style, "marginLeft": "4px"})]),
                html.Td(f"\u00d7{boost['multiplier']:.3f}", style=num_style),
            ]))
            combined *= boost['multiplier']
        if has_weight:
            rows.append(html.Tr([
                html.Td("Context Weight"),
                html.Td(f"\u00d7{ctx_weight:.3f}", style=num_style),
            ]))
            combined *= ctx_weight
        if has_density:
            rows.append(html.Tr([
                html.Td([html.Span("Density"),
                         html.Span(f" (n={n_bucket}, \u03b1={alpha_val:.2f})",
                                   style={**muted_style, "marginLeft": "4px"})]),
                html.Td(f"\u00d7{density_mult:.3f}", style=num_style),
            ]))
            combined *= density_mult
        rows.append(html.Tr([
            html.Td("Combined", style=total_style),
            html.Td(f"\u00d7{combined:.3f}", style={**num_style, **total_style}),
        ]))

    # --- Score section ------------------------------------------------
    rows.append(html.Tr([html.Td("Score", colSpan=2, style=header_style)]))
    if eligible:
        raw_label = [html.Span("Raw")]
        if has_any_adjustment:
            raw_label.append(html.Span(
                " (all adjustments applied)",
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
