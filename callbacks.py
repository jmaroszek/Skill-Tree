"""
Callback definitions for the Skill Tree Dash application.
"""

import logging
import dash
import os
import subprocess
import urllib.parse
from dash import html, Input, Output, State, ALL, ctx, no_update
import dash_bootstrap_components as dbc
from graph_manager import GraphManager
from config import ConfigManager
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from next_callbacks import get_suggestions, get_override_set
from callback_helpers import (
    parse_links, serialize_links, get_trigger_id, get_all_triggered_ids,
    node_options, build_filters,
    handle_save, handle_delete, handle_toggle_done, handle_group_delete,
    format_suggestions_table, format_next_visualizations, format_traversal_ui,
    render_link_rows, spawn_local_file_picker,
    strip_gdrive_prefix, expand_gdrive_prefix,
    should_open_editor, resolve_active_node_id,
    normalize_name_for_comparison,
)

logger = logging.getLogger(__name__)

manager = GraphManager()


def _friendly_time_estimates(time_o, time_m, time_p):
    """Convert stored hour values for display in the node editor.

    Uses weeks as the maximum unit — never months — so the editor always
    shows values in hours or weeks regardless of magnitude.  Returns (o, m, p, unit_string).
    """
    max_hours = max(time_o or 0, time_m or 0, time_p or 0)
    _, unit = ConfigManager.hours_to_friendly_unit(max_hours)
    # Cap at weeks: months is too coarse for direct editing
    if unit == 'months':
        unit = 'weeks'
    multiplier = ConfigManager.get_time_multiplier(unit)
    def _convert(h):
        v = round((h or 0) / multiplier, 2)
        if v == int(v):
            v = int(v)
        return v
    return _convert(time_o), _convert(time_m), _convert(time_p), unit




def generate_elements(filters=None, active_node_id=None, community_names=None,
                      max_depth=0, neighbor_links=True):
    """Convert nodes and edges from the database into Cytoscape-compatible element dicts.

    Args:
        max_depth: 0 = show all nodes; 1-5 = only show nodes within this many
                   hops of *active_node_id*.  Ignored when no node is active.
        neighbor_links: When False, hide edges between non-active nodes
                        (only show edges that touch the active node).
    """
    if filters is None: filters = {}
    nodes = manager.get_all_nodes()
    filtered_nodes = manager.filter_nodes(nodes, filters)

    if community_names is not None:
        filtered_nodes = [n for n in filtered_nodes if n.name in community_names]

    valid_names = {n.name for n in filtered_nodes}

    # --- Max Depth filtering (BFS from active node) ---
    if max_depth and max_depth > 0 and active_node_id and active_node_id in valid_names:
        edges = manager.get_edges()
        # Build adjacency from edges within the valid set
        adj = {}
        for e in edges:
            s, t = e['source'], e['target']
            if s in valid_names and t in valid_names:
                adj.setdefault(s, set()).add(t)
                adj.setdefault(t, set()).add(s)
        # BFS
        visited = {active_node_id}
        frontier = {active_node_id}
        for _ in range(max_depth):
            next_frontier = set()
            for n in frontier:
                for nb in adj.get(n, set()):
                    if nb not in visited:
                        visited.add(nb)
                        next_frontier.add(nb)
            frontier = next_frontier
            if not frontier:
                break
        valid_names = valid_names & visited
        filtered_nodes = [n for n in filtered_nodes if n.name in valid_names]

    edges = manager.get_edges()
    colors = ConfigManager.get_node_colors()
    shapes = ConfigManager.get_node_shapes()
    override_set = ConfigManager.get_override_node_set(manager)
    override_color = colors.get('Override', '#e83e8c')

    elements = []
    for node in filtered_nodes:
        if node.name in override_set:
            node_color = override_color
        elif node.status == 'Done':
            node_color = colors.get('Done', '#198754')
        elif node.status == 'Blocked':
            node_color = colors.get('Blocked', '#dc3545')
        else:
            node_color = colors.get(node.type, colors.get('Open', '#0d6efd'))

        node_data = {
            'data': {
                'id': node.name,
                'label': node.name,
                'color': node_color,
                'shape': shapes.get(node.type, 'rectangle'),
                **node.to_dict()
            },
            'selected': node.name == active_node_id if active_node_id else False
        }
        elements.append(node_data)

    for e in edges:
        if e['source'] in valid_names and e['target'] in valid_names:
            # Neighbor links filter: when off, only show edges touching active node
            if not neighbor_links and active_node_id:
                if e['source'] != active_node_id and e['target'] != active_node_id:
                    continue
            elements.append({
                'data': {
                    'id': f"{e['source']}_{e['target']}_{e['type']}",
                    'source': e['source'],
                    'target': e['target'],
                    'type': e['type']
                }
            })

    return elements






def register_callbacks(app):
    """Register all Dash callbacks for the application."""

    # --- Clear Filters ---
    @app.callback(
        Output('filter-node-type', 'value'),
        Output('filter-context', 'value'),
        Output('filter-subcontext', 'value', allow_duplicate=True),
        Output('filter-goal', 'value'),
        Output('community-method', 'value'),
        Output('filter-community', 'value'),
        Output('filter-value', 'value'),
        Output('filter-interest', 'value'),
        Output('filter-difficulty', 'value'),
        Output('filter-time', 'value'),
        Output('filter-done', 'value'),
        Input('btn-clear-filters', 'n_clicks'),
        prevent_initial_call=True,
    )
    def clear_filters(_):
        return [], [], [], [], 'components', 'All', 1, 1, 10, None, ['hide_done']

    # --- Tooltip Formatting ---
    @app.callback(
        Output('hover-tooltip', 'children'),
        Input('cytoscape-graph', 'mouseoverNodeData'),
        Input('details-mini-graph', 'mouseoverNodeData'),
    )
    def display_hover_data(data, details_data):
        trigger = get_trigger_id()
        if trigger == 'details-mini-graph':
            data = details_data
        if not data: return ""

        node_type = data.get('type', '')
        node_id = data.get('id', data.get('label', ''))

        header = html.Div(
            html.Strong(data.get('label', node_id)),
            style={"fontSize": "0.95rem", "marginBottom": "4px",
                   "borderBottom": "1px solid #495057", "paddingBottom": "4px"}
        )

        if node_type == 'Goal':
            completion = manager.get_goal_completion(node_id)
            total = completion.get('total', 0)
            done = completion.get('done', 0)
            pct = completion.get('pct', 0)
            remaining = completion.get('remaining_time', 0)

            if total > 0:
                if pct == 100:
                    effective_status = "Done"
                elif completion.get('is_blocked', False):
                    effective_status = "Blocked"
                else:
                    effective_status = data.get('status', 'Open')
            else:
                effective_status = data.get('status', 'Open')

            status_color = {"Done": "#198754", "Blocked": "#dc3545"}.get(effective_status, "#dee2e6")

            lines = [header]

            if total > 0:
                bar_color = "#198754" if pct == 100 else "#0d6efd"
                lines += [
                    html.Hr(style={"margin": "6px 0", "borderColor": "#495057"}),
                    html.Div([html.Strong("Progress: "), f"{done}/{total} subtasks ({pct}%)"]),
                    html.Div(
                        html.Div(style={
                            "width": f"{pct}%", "height": "6px",
                            "backgroundColor": bar_color, "borderRadius": "3px",
                            "transition": "width 0.3s ease"
                        }),
                        style={"backgroundColor": "#495057", "borderRadius": "3px",
                               "margin": "4px 0", "overflow": "hidden"}
                    ),
                    html.Div([html.Strong("Remaining: "),
                              ConfigManager.format_time_friendly(remaining)]),
                ]
            else:
                lines.append(html.Div("No subtasks yet", style={"color": "#6c757d", "fontStyle": "italic"}))

            ctx_val = data.get('context', '')
            sub_val = data.get('subcontext', '')
            if ctx_val or sub_val:
                subctx_str = f"{ctx_val} > {sub_val}" if ctx_val and sub_val else ctx_val or sub_val
                lines.append(html.Div(subctx_str, style={"color": "#adb5bd"}))

        else:
            final_time = data.get('time', 0)
            time_str = ConfigManager.format_time_friendly(final_time)

            lines = [
                header,
                html.Div([html.Strong("Value: "), str(data.get('value', ''))]),
                html.Div([html.Strong("Effort: "), str(data.get('difficulty', ''))]),
                html.Div([html.Strong("Time: "), time_str]),
            ]

            ctx_val = data.get('context', '')
            sub_val = data.get('subcontext', '')
            if ctx_val or sub_val:
                subctx_str = f"{ctx_val} > {sub_val}" if ctx_val and sub_val else ctx_val or sub_val
                lines.append(html.Div(subctx_str, style={"color": "#adb5bd"}))

        return lines

    # --- Scroll editor to top on New Node / Add ---
    app.clientside_callback(
        """function(n1, n2) {
            var el = document.getElementById('sidebar-editor-container');
            if (el) el.scrollTop = 0;
            return window.dash_clientside.no_update;
        }""",
        Output('btn-new-node', 'title'),
        Input('btn-new-node', 'n_clicks'),
        Input('btn-add', 'n_clicks'),
        prevent_initial_call=True,
    )

    # --- Editor Form Population ---
    @app.callback(
        [Output('node-name', 'value'), Output('node-type', 'value'), Output('node-desc', 'value'),
         Output('node-context', 'value'), Output('node-subcontext', 'value'),
         Output('node-value', 'value'), Output('node-interest', 'value'), Output('node-difficulty', 'value'),
         Output('node-time-o', 'value'), Output('node-time-m', 'value'), Output('node-time-p', 'value'),
         Output('auto-status-display', 'children'), Output('node-status-done', 'value'),
         Output('edge-needs-hard', 'value'), Output('edge-needs-soft', 'value'),
         Output('edge-supports-hard', 'value'), Output('edge-supports-soft', 'value'),
         Output('edge-helps', 'value'),
         Output('edge-needs-hard', 'options'), Output('edge-needs-soft', 'options'),
         Output('edge-supports-hard', 'options'), Output('edge-supports-soft', 'options'),
         Output('edge-helps', 'options'),
         Output('obsidian-links-store', 'data'), Output('drive-links-store', 'data'),
         Output('website-links-store', 'data'),
         # Type-specific outputs
         Output('node-progress', 'value'), Output('node-time-unit', 'value'),
         Output('node-time-unit-prev', 'data', allow_duplicate=True),
         Output('node-original-name', 'data', allow_duplicate=True),
         Output('search-node', 'value', allow_duplicate=True),
         Output('node-priority-rank', 'value'),
         Output('node-time-mode', 'value'),
         Output('node-competence', 'value'),
         Output('aliases-store', 'data'),
         Output('pending-navigation-store', 'data'),
         Output('modal-unsaved-changes', 'is_open', allow_duplicate=True)],
        [Input('cytoscape-graph', 'tapNodeData'),
         Input('btn-add', 'n_clicks'),
         Input('btn-clear-yes', 'n_clicks'),
         Input('btn-unsaved-discard', 'n_clicks'),
         Input('btn-unsaved-save', 'n_clicks'),
         Input('search-node', 'value'),
         Input('background-click-input', 'value'),
         Input('btn-new-node', 'n_clicks'),
         Input('edit-trigger-input', 'value'),
         Input('details-edit-trigger-input', 'value')],
        [State('cytoscape-graph', 'elements'),
         State('sidebar-editor-container', 'style'),
         State('node-original-name', 'data'),
         State('node-name', 'value'), State('node-desc', 'value'),
         State('node-value', 'value'), State('node-interest', 'value'),
         State('node-difficulty', 'value'),
         State('pending-navigation-store', 'data')],
        prevent_initial_call='initial_duplicate'
    )
    def populate_editor(data, add_clicks, clear_yes_clicks, discard_clicks, unsaved_save_clicks, search_val, _bg_click, new_node_clicks, edit_trigger_val,
                        details_edit_trigger_val,
                        elements, ed_style, original_name, cur_name, cur_desc, cur_val, cur_interest, cur_diff,
                        pending_nav):
        """Populate the editor sidebar form fields when a node is selected, searched, or cleared."""
        trigger_id = get_trigger_id()

        all_nodes = manager.get_all_nodes()
        options = node_options(all_nodes)

        def_out = [
            "", "Learn", "", "", "", 5, 5, 5, 2, 4, 6, "Open", [],
            [], [], [], [], [],
            options, options, options, options, options,
            [''], [''], [''],
            # Type-specific defaults
            0, "weeks", "weeks",
            None,  # node-original-name
            dash.no_update,  # search-node — don't change; avoids retriggering core_engine
            "none",  # node-priority-rank
            [],  # node-time-mode
            "",  # node-competence
            [''],  # aliases-store
            None,  # pending-navigation-store
            False,  # modal-unsaved-changes
        ]

        # Helper: check if editor has unsaved changes
        def _has_unsaved_changes():
            if original_name:
                old_node = manager.get_node(original_name)
                if old_node:
                    return any([
                        (cur_name or "").strip() != (old_node.name or "").strip(),
                        (cur_desc or "").strip() != (old_node.description or "").strip(),
                        float(cur_val or 5) != float(old_node.value or 5),
                        float(cur_interest or 5) != float(old_node.interest or 5),
                        float(cur_diff or 5) != float(old_node.difficulty or 5),
                    ])
            # New node: check if any content has been entered
            return bool(cur_name and cur_name.strip()) or bool(cur_desc and cur_desc.strip()) or any([
                cur_val not in (None, 5), cur_interest not in (None, 5), cur_diff not in (None, 5),
            ])

        if trigger_id == 'btn-new-node':
            editor_open = ed_style and ed_style.get('transform', '') == 'translateX(0px)'
            if editor_open and _has_unsaved_changes():
                # Show unsaved modal; store 'new-node' as pending action
                no_change = [dash.no_update] * 18 + [options]*5 + [dash.no_update]*14
                no_change[35] = '__new_node__'  # pending-navigation-store (special sentinel)
                no_change[36] = True            # modal-unsaved-changes
                return no_change
            # No unsaved changes — clear and reset (don't clear search-node;
            # that would re-trigger core_engine and overwrite the editor-open state)
            return def_out

        if trigger_id in ['btn-add', 'btn-clear-yes', 'background-click-input']:
            # Clear search bar on reset triggers — but NOT for btn-add, because
            # setting search-node to None re-triggers core_engine via the callback
            # chain, and the second invocation reads stale editor state and
            # overwrites the first invocation's "open editor" output.
            if trigger_id != 'btn-add':
                def_out[30] = None  # search-node value position
            return def_out

        # Handle unsaved-discard / unsaved-save with pending navigation
        if trigger_id in ('btn-unsaved-discard', 'btn-unsaved-save'):
            if pending_nav:
                if pending_nav == '__new_node__':
                    # Discard/save done — reset to blank new-node form
                    def_out[30] = None  # clear search bar
                    return def_out
                # Navigate to the pending node after discarding/saving
                node = manager.get_node(pending_nav)
                if node:
                    data = node.to_dict()
                    data['id'] = pending_nav
                    # Fall through to populate logic below with this data
                else:
                    return def_out
            else:
                return def_out

        # Intercept node tap when editor has unsaved changes
        if trigger_id == 'cytoscape-graph' and data:
            editor_open = ed_style and ed_style.get('transform', '') == 'translateX(0px)'
            tapped_id = data.get('id')
            if editor_open and tapped_id and tapped_id != original_name and _has_unsaved_changes():
                # Store the pending target and show unsaved modal instead of populating
                # 18 form fields + 5 edge options + 14 remaining = 37 total outputs
                no_change = [dash.no_update] * 18 + [options]*5 + [dash.no_update]*14
                no_change[35] = tapped_id  # pending-navigation-store (index 35)
                no_change[36] = True       # modal-unsaved-changes (index 36)
                return no_change

        name = None
        if trigger_id in ('edit-trigger-input', 'details-edit-trigger-input'):
            # Context menu / dormant-node Edit: node ID carried in the trigger value
            edit_val = edit_trigger_val if trigger_id == 'edit-trigger-input' else details_edit_trigger_val
            if edit_val:
                edit_node_name = edit_val.split('|')[0]
                node = manager.get_node(edit_node_name)
                if node:
                    name = node.name
                    data = node.to_dict()
                    data['id'] = name
                else:
                    return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*14
        elif trigger_id == 'search-node':
            if not search_val:
                # User cleared the search bar — reset form to defaults
                return def_out
            # Resolve alias: prefix to actual node name
            resolved_name = search_val
            if search_val.startswith('alias:'):
                alias_key = search_val[6:]
                all_aliases = manager.get_all_aliases()
                resolved_name = all_aliases.get(alias_key, search_val)
            node = manager.get_node(resolved_name)
            if node:
                name = node.name
                data = node.to_dict()
                data['id'] = name
            else:
                return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*13
        elif data:
            name = data.get('id')
            # Always read fresh data from DB on tap (Cytoscape data may be stale)
            if name:
                db_node = manager.get_node(name)
                if db_node:
                    data = db_node.to_dict()
                    data['id'] = name

        if not name or not data:
            return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*13

        edges = manager.get_edges()

        # In/Out Edges mapping
        needs_hard_vals = [e['source'] for e in edges if e['target'] == name and e['type'] == EDGE_NEEDS_HARD]
        needs_soft_vals = [e['source'] for e in edges if e['target'] == name and e['type'] == EDGE_NEEDS_SOFT]
        supp_hard_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == EDGE_NEEDS_HARD]
        supp_soft_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == EDGE_NEEDS_SOFT]

        helps_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == EDGE_HELPS]
        helps_vals += [e['source'] for e in edges if e['target'] == name and e['type'] == EDGE_HELPS]
        helps_vals = list(set(helps_vals))
        filtered_options = node_options(all_nodes, exclude=name)

        actual_status = data.get('status', 'Open')
        done_val = ["Done"] if actual_status == "Done" else []

        friendly_o, friendly_m, friendly_p, friendly_unit = _friendly_time_estimates(
            data.get('time_o', 1.0), data.get('time_m', 1.0), data.get('time_p', 1.0)
        )

        # Priority rank for Goal nodes
        priority_goals = ConfigManager.get_priority_goals()
        if data.get('type') == 'Goal' and name in priority_goals:
            rank_value = str(priority_goals.index(name) + 1)
        else:
            rank_value = "none"

        # Time mode
        time_mode_val = ["inherited"] if data.get('time_mode') == 'inherited' else []

        return [
            name, data.get('type'), data.get('description'),
            data.get('context') or '', data.get('subcontext') or '',
            data.get('value', 5), data.get('interest', 5), data.get('difficulty', 5),
            friendly_o, friendly_m, friendly_p,
            actual_status, done_val,
            needs_hard_vals, needs_soft_vals, supp_hard_vals, supp_soft_vals,
            helps_vals,
            filtered_options, filtered_options, filtered_options, filtered_options, filtered_options,
            parse_links(data.get('obsidian_path', '')),
            parse_links(data.get('google_drive_path', '')),
            parse_links(data.get('website', '')),
            # Type-specific fields
            data.get('progress') or 0, friendly_unit, friendly_unit,
            name,  # node-original-name — track what was loaded
            name if (trigger_id in ('edit-trigger-input', 'details-edit-trigger-input') or (ed_style and ed_style.get('transform', '') == 'translateX(0px)')) else dash.no_update,  # search-node — update when editor is open or edit-trigger
            rank_value,  # node-priority-rank
            time_mode_val,  # node-time-mode
            data.get('competence') or '',  # node-competence
            manager.get_aliases(name) or [''],  # aliases-store
            None,  # pending-navigation-store — clear on successful populate
            False,  # modal-unsaved-changes — close on successful populate
        ]

    # --- Type-adaptive field visibility ---
    @app.callback(
        [Output('section-done-time', 'style'),
         Output('section-time-estimates', 'style'),
         Output('section-resource', 'style'),
         Output('section-priority-rank', 'style')],
        Input('node-type', 'value')
    )
    def toggle_type_fields(node_type):
        show = {}
        hide = {'display': 'none'}
        if node_type == 'Resource':
            return show, show, hide, hide
        elif node_type == 'Goal':
            return show, show, hide, show  # Show time estimates (for time_mode toggle) + priority rank
        else:  # Learn, Action
            return show, show, hide, hide

    # --- Toggle O/M/P fields based on time_mode ---
    @app.callback(
        Output('section-time-omp', 'style'),
        Output('node-time-unit', 'style'),
        Input('node-time-mode', 'value'),
    )
    def toggle_time_omp_visibility(time_mode_val):
        if time_mode_val and 'inherited' in time_mode_val:
            return {'display': 'none'}, {'display': 'none', 'width': '100px'}
        return {}, {'width': '100px'}

    # --- Auto-convert time estimates when unit dropdown changes ---
    @app.callback(
        Output('node-time-o', 'value', allow_duplicate=True),
        Output('node-time-m', 'value', allow_duplicate=True),
        Output('node-time-p', 'value', allow_duplicate=True),
        Output('node-time-unit-prev', 'data'),
        Input('node-time-unit', 'value'),
        State('node-time-o', 'value'),
        State('node-time-m', 'value'),
        State('node-time-p', 'value'),
        State('node-time-unit-prev', 'data'),
        prevent_initial_call=True,
    )
    def convert_time_unit(new_unit, val_o, val_m, val_p, prev_unit):
        """Re-express time values when the unit selector changes."""
        old_unit = prev_unit or 'hours'
        no_change = dash.no_update, dash.no_update, dash.no_update, new_unit
        if not new_unit or new_unit == old_unit:
            return no_change
        old_mult = ConfigManager.get_time_multiplier(old_unit)
        new_mult = ConfigManager.get_time_multiplier(new_unit)
        if new_mult == 0:
            return no_change
        def _reexpress(v):
            if v is None:
                return v
            hours = float(v) * old_mult
            result = round(hours / new_mult, 2)
            return int(result) if result == int(result) else result
        return _reexpress(val_o), _reexpress(val_m), _reexpress(val_p), new_unit

    # --- Time Estimate Validation ---
    @app.callback(
        Output('time-validation-error', 'children'),
        Output('time-validation-error', 'style'),
        Output('btn-save', 'disabled'),
        Output('btn-save-close', 'disabled'),
        Input('node-time-o', 'value'),
        Input('node-time-m', 'value'),
        Input('node-time-p', 'value'),
        prevent_initial_call=True,
    )
    def validate_time_estimates(time_o, time_m, time_p):
        """Enforce Optimistic <= Expected <= Pessimistic and disable Save on violation."""
        o = float(time_o or 0)
        m = float(time_m or 0)
        p = float(time_p or 0)
        hidden = {"display": "none", "color": "#dc3545", "fontSize": "0.85rem"}
        visible = {"display": "block", "color": "#dc3545", "fontSize": "0.85rem"}

        # Skip validation when all fields are empty/zero
        if o == 0 and m == 0 and p == 0:
            return "", hidden, False, False

        errors = []
        if o > 0 and m > 0 and o > m:
            errors.append("Optimistic must be ≤ Expected")
        if m > 0 and p > 0 and m > p:
            errors.append("Expected must be ≤ Pessimistic")
        if o > 0 and p > 0 and o > p:
            errors.append("Optimistic must be ≤ Pessimistic")

        if errors:
            return "; ".join(errors), visible, True, True
        return "", hidden, False, False

    # --- Duplicate Node Detection (fires on blur, no auto-fill) ---
    @app.callback(
        Output('node-name-duplicate-warning', 'children'),
        Output('node-name-duplicate-warning', 'style'),
        Input('node-name', 'n_blur'),
        State('node-name', 'value'),
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def check_duplicate_name(_blur, typed_name, original_name):
        """Check if typed name matches an existing node (exact or fuzzy). Shows a temporary warning."""
        hidden = {"display": "none"}
        if not typed_name or not typed_name.strip():
            return "", hidden
        typed_stripped = typed_name.strip()
        # Skip if editing the same node
        if original_name and typed_stripped == original_name:
            return "", hidden

        all_nodes = manager.get_all_nodes(include_dormant=True)
        typed_normalized = normalize_name_for_comparison(typed_stripped)

        matches = []
        for node in all_nodes:
            if node.name == original_name:
                continue
            if node.name.lower() == typed_stripped.lower():
                matches.append(node.name)
            elif typed_normalized and normalize_name_for_comparison(node.name) == typed_normalized:
                matches.append(node.name)

        if matches:
            names_str = ", ".join(matches)
            warning = html.Div(f"Possible duplicate: {names_str}",
                               style={"color": "#dc3545", "fontSize": "0.85rem"})
            return warning, {"display": "block"}

        return "", hidden

    # Auto-hide duplicate warning after 3 seconds
    app.clientside_callback(
        """function(children) {
            if (children && children !== '') {
                setTimeout(function() {
                    var el = document.getElementById('node-name-duplicate-warning');
                    if (el) el.style.display = 'none';
                }, 3000);
            }
            return window.dash_clientside.no_update;
        }""",
        Output('node-name-duplicate-warning', 'title'),  # dummy output
        Input('node-name-duplicate-warning', 'children'),
        prevent_initial_call=True,
    )

    # --- Priority Badge in Node Editor ---
    @app.callback(
        Output('node-priority-badge', 'children'),
        Output('node-priority-badge', 'style'),
        Input('node-name', 'value'),
        Input('node-type', 'value'),
        Input('override-store', 'data'),
    )
    def update_node_priority_badge(node_name, node_type, _override_data):
        hidden = {"display": "none"}
        visible = {"display": "flex", "gap": "4px", "flexWrap": "wrap", "marginBottom": "8px"}
        if not node_name:
            return [], hidden

        badges = []

        # Override badge (always first)
        override = ConfigManager.get_override()
        if override.get("parent"):
            override_set = ConfigManager.get_override_node_set(manager)
            if node_name in override_set:
                is_parent = (node_name == override["parent"])
                override_label = "Override" if is_parent else "Override (Dependent)"
                _ov_color = ConfigManager.get_node_colors().get('Override', '#e83e8c')
                badges.append(html.Span(override_label, className="badge",
                                        style={"fontSize": "0.75rem", "backgroundColor": _ov_color, "color": "#fff"}))

        # Priority goal badges
        priority_goals = ConfigManager.get_priority_goals()
        if priority_goals:
            if node_type == "Goal" and node_name in priority_goals:
                rank = priority_goals.index(node_name) + 1
                badges.append(dbc.Badge(f"#{rank} Priority", color="warning", style={"fontSize": "0.75rem"}))
            else:
                for rank_idx, goal_name in enumerate(priority_goals[:3]):
                    full_subtree = manager.get_goal_subtree(goal_name)
                    if node_name not in full_subtree:
                        continue
                    rank = rank_idx + 1
                    hard_subtree = manager.get_goal_subtree(goal_name, edge_types=(EDGE_NEEDS_HARD,))
                    rel_type = "Hard" if node_name in hard_subtree else "Soft"
                    rel_color = "primary" if rel_type == "Hard" else "info"
                    badges.append(dbc.Badge(f"{rel_type} #{rank}", color=rel_color, style={"fontSize": "0.75rem"}))

        if not badges:
            return [], hidden
        return badges, visible

    # --- Core State: Save, Delete, Render ---
    @app.callback(
        [Output('cytoscape-graph', 'elements'), Output('save-output', 'children'),
         Output('suggestions-table', 'children'),
         Output('traversal-chains-hard', 'children'), Output('traversal-chains-soft', 'children'),
         Output('synergies-list', 'children'), Output('node-info-description', 'children'),
         Output('clear-interval', 'disabled'), Output('clear-interval', 'n_intervals'),
         Output('filter-community', 'options'), Output('search-node', 'options'),
         Output('sidebar-editor-container', 'style'), Output('sidebar-filters-container', 'style'),
         Output('filter-context', 'options'), Output('node-context', 'options'),
         Output('node-type', 'options'),
         Output('filter-node-type', 'options'),
         Output('filter-goal', 'options'),
         Output('cytoscape-graph', 'stylesheet'),
         Output('btn-clear-focus', 'style'),
         Output('filter-node-count', 'children'),
         Output('details-goal-sidebar', 'style', allow_duplicate=True),
         Output('events-sidebar-container', 'style', allow_duplicate=True)],

        [Input('btn-save', 'n_clicks'), Input('btn-save-close', 'n_clicks'), Input('btn-node-delete-confirm', 'n_clicks'),
         Input('filter-context', 'value'), Input('filter-subcontext', 'value'), Input('filter-done', 'value'),
         Input('search-node', 'value'),
         Input('cytoscape-graph', 'tapNodeData'),
         Input('filter-community', 'value'), Input('community-method', 'value'),
         Input('filter-value', 'value'), Input('filter-interest', 'value'),
         Input('filter-time', 'value'), Input('filter-difficulty', 'value'),
         Input('suggestion-count-store', 'data'),
         Input('btn-edit-node', 'n_clicks'), Input('btn-add', 'n_clicks'), Input('btn-new-node', 'n_clicks'),
         Input('btn-close-editor', 'n_clicks'), Input('btn-goals-toggle', 'n_clicks'),
         Input('btn-unsaved-save', 'n_clicks'), Input('btn-unsaved-discard', 'n_clicks'), Input('btn-clear-yes', 'n_clicks'),
         Input('btn-filters-toggle', 'n_clicks'), Input('btn-close-filters', 'n_clicks'),
         Input('btn-settings-save', 'n_clicks'),
         Input('modal-migration', 'is_open'),
         Input('btn-toggle-done-node', 'n_clicks'),
         Input('group-delete-input', 'value'),
         Input('filter-node-type', 'value'),
         Input('selected-suggestion-store', 'data'),
         Input('filter-goal', 'value'),
         Input('focus-goal-store', 'data'),
         Input('edit-trigger-input', 'value'),
         Input('details-edit-trigger-input', 'value'),
         Input('toggle-done-trigger-input', 'value'),
         Input('events-refresh-trigger', 'data'),
         Input('details-refresh-trigger', 'data'),
         Input('background-click-input', 'value'),
         Input('graph-settings-max-depth', 'value'),
         Input('graph-settings-neighbor-links', 'value'),
         Input('main-tabs', 'active_tab')],

        [State('node-name', 'value'), State('node-type', 'value'), State('node-desc', 'value'),
         State('node-context', 'value'), State('node-subcontext', 'value'), State('node-status-done', 'value'),
         State('node-value', 'value'), State('node-interest', 'value'), State('node-difficulty', 'value'),
         State('node-time-o', 'value'), State('node-time-m', 'value'), State('node-time-p', 'value'),
         State('node-time-unit', 'value'),
         State('edge-needs-hard', 'value'), State('edge-needs-soft', 'value'),
         State('edge-supports-hard', 'value'), State('edge-supports-soft', 'value'),
         State('edge-helps', 'value'),
         State({'type': 'obsidian-link', 'index': ALL}, 'value'),
         State({'type': 'drive-link', 'index': ALL}, 'value'),
         State({'type': 'website-link', 'index': ALL}, 'value'),
         State('node-progress', 'value'),
         State('cytoscape-graph', 'elements'),
         State('sidebar-editor-container', 'style'), State('sidebar-filters-container', 'style'),
         State('node-original-name', 'data'),
         State('node-time-mode', 'value'),
         State('node-priority-rank', 'value'),
         State('node-competence', 'value'),
         State('details-goal-sidebar', 'style'),
         State('events-sidebar-container', 'style'),
         State('pending-navigation-store', 'data'),
         State({'type': 'alias-input', 'index': ALL}, 'value')],
        prevent_initial_call='initial_duplicate'
    )
    def core_engine(save_clicks, save_close_clicks, delete_confirm_clicks, f_context, f_subcontext, f_done, search_val,
                     tapped_node,  # Cytoscape tapNodeData dict (not a Node object)
                     f_community, community_method, f_value, f_interest, f_time, f_difficulty, sugg_count,
                     btn_edit, btn_add, btn_new_node, btn_close_ed, btn_goals_toggle, btn_unsaved_save, btn_unsaved_discard, btn_clear_yes, btn_filters, btn_close_fil, settings_open, migration_open, btn_toggle_done,
                     group_delete_data, f_node_types,
                     active_suggestion_id,
                     f_goal, focus_goal,
                     edit_trigger_data, details_edit_trigger_data, toggle_done_trigger_data, _events_refresh, _details_refresh, _bg_click,
                     gs_max_depth, gs_neighbor_links, active_tab,
                     name, n_type, desc, context, subctx, status_done, val, interest, diff,
                     time_o, time_m, time_p, time_unit,
                     e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                     obs_link_values, drive_link_values, website_link_values,
                     progress_val,
                     current_elements, ed_style, fil_style, original_name,
                     time_mode_val, priority_rank_val, competence_val,
                     goal_sidebar_style, events_sidebar_style, pending_nav_store, alias_values):
        """Central state callback handling node CRUD, filtering, and UI updates.

        This is intentionally a single large callback because Dash requires each Output
        to belong to exactly one callback. Since save/delete/filter operations all need
        to refresh the graph elements and sidebar state, they must share one callback.
        """
                     
        trigger_id = get_trigger_id()
        all_triggered_ids = get_all_triggered_ids()
        msg = ""
        completion_check_node = None  # Set when a node transitions to Done

        # Check for any delayed event nodes or scheduled events that are due
        from event_manager import EventManager
        _event_mgr = EventManager()
        _event_mgr.check_pending_activations()
        _event_mgr.check_scheduled_triggers()

        filters = build_filters(f_context, f_subcontext, f_done, f_value, f_interest, f_time, f_difficulty, f_node_types, f_goal=f_goal)

        # Editor Sidebar State (380px matches sidebar_content width in layout.py)
        next_ed_style = ed_style or {"position": "absolute", "top": "0", "left": "0", "width": "380px", "minWidth": "380px", "height": "100%", "zIndex": 1000, "overflowX": "hidden", "overflowY": "auto", "borderRight": "1px solid #495057", "transition": "transform 0.3s ease", "transform": "translateX(-380px)", "willChange": "transform", "backgroundColor": "#212529"}
        if trigger_id == 'btn-add':
            # Always open the editor
            next_ed_style['transform'] = "translateX(0px)"
        elif trigger_id == 'btn-new-node':
            # Always open the editor (populate_editor handles unsaved-changes modal)
            next_ed_style['transform'] = "translateX(0px)"
        elif trigger_id == 'search-node' and not search_val:
            # Search bar was cleared (e.g. by populate_editor resetting after btn-add) — don't
            # touch the editor state. Without this guard, a race condition causes core_engine to
            # read a stale "closed" ed_style and immediately close an editor that btn-add just opened.
            next_ed_style = dash.no_update
        elif should_open_editor(all_triggered_ids, trigger_id, search_val):
            next_ed_style['transform'] = "translateX(0px)"
        elif trigger_id == 'btn-goals-toggle':
            next_ed_style['transform'] = "translateX(-380px)"
        elif trigger_id == 'btn-save':
            # Save only — keep editor open, don't change transform
            next_ed_style['transform'] = "translateX(0px)"
        elif trigger_id in ('btn-save-close', 'btn-clear-yes', 'btn-node-delete-confirm', 'btn-close-editor', 'btn-unsaved-discard', 'btn-unsaved-save'):
            # btn-save-close and unsaved-save close it after saving.
            # btn-clear-yes and btn-unsaved-discard close without saving.
            # btn-close-editor only silently closes if the form is blank (otherwise modal handles it).
            if trigger_id in ('btn-unsaved-save', 'btn-unsaved-discard') and pending_nav_store:
                pass  # Keep editor open — pending navigation will load the next node
            elif trigger_id in ('btn-save-close', 'btn-unsaved-save') and (not name or not n_type):
                pass  # Keep sidebar open — validation error shown below
            elif trigger_id == 'btn-close-editor':
                form_has_content = False
                if original_name:
                    old_node = manager.get_node(original_name)
                    if old_node:
                        form_has_content = any([
                            (name or "").strip() != (old_node.name or "").strip(),
                            (desc or "").strip() != (old_node.description or "").strip(),
                            float(val or 5) != float(old_node.value or 5),
                            float(interest or 5) != float(old_node.interest or 5),
                            float(diff or 5) != float(old_node.difficulty or 5)
                        ])
                if not original_name or not manager.get_node(original_name):
                    form_has_content = bool(name and name.strip()) or bool(desc and desc.strip()) or any([
                        val not in (None, 5), interest not in (None, 5), diff not in (None, 5),
                    ])
                if not form_has_content:
                    next_ed_style['transform'] = "translateX(-380px)"
            else:
                next_ed_style['transform'] = "translateX(-380px)"

        # Goal / Events Sidebar Mutex: close them when editor opens
        next_goal_style = dash.no_update
        next_events_sidebar_style = dash.no_update
        if isinstance(next_ed_style, dict) and next_ed_style.get('transform', '') == 'translateX(0px)' and trigger_id != 'btn-goals-toggle':
            # Editor is opening — ensure goal sidebar is closed
            if goal_sidebar_style and goal_sidebar_style.get('left', '-380px') == '0px':
                next_goal_style = dict(goal_sidebar_style)
                next_goal_style['left'] = '-380px'
            if events_sidebar_style and events_sidebar_style.get('left', '-380px') == '0px':
                next_events_sidebar_style = dict(events_sidebar_style)
                next_events_sidebar_style['left'] = '-380px'

        # Filters Sidebar State (overlay, shared between Canvas + Suggestions tabs)
        next_fil_style = fil_style or {"position": "absolute", "top": "0", "right": "-320px", "width": "320px", "height": "100%", "zIndex": 100, "overflowX": "hidden", "overflowY": "auto", "borderLeft": "1px solid #495057", "transition": "right 0.3s ease", "backgroundColor": "#212529"}
        if trigger_id == 'btn-filters-toggle':
            next_fil_style['right'] = "0px" if next_fil_style.get('right', '-320px') == "-320px" else "-320px"
        elif trigger_id == 'btn-close-filters':
            next_fil_style['right'] = "-320px"

        # Use whichever edit trigger fired (details tab or main)
        _edit_trigger = details_edit_trigger_data if trigger_id == 'details-edit-trigger-input' else edit_trigger_data
        active_node_id = resolve_active_node_id(
            all_triggered_ids, trigger_id, _edit_trigger,
            search_val, tapped_node, name)

        # When entering focus mode, clear the selected node so only the
        # goal's subtree is highlighted (not a previously-tapped node).
        # focus_goal may be a dict {"node": str, "subtree": list} or a plain string.
        focus_subtree_override = None
        if isinstance(focus_goal, dict):
            focus_subtree_override = set(focus_goal.get("subtree", []))
            focus_goal = focus_goal.get("node")
        if trigger_id == 'focus-goal-store' and focus_goal:
            active_node_id = None

        # Serialize multi-link arrays for storage
        obs_path = serialize_links(obs_link_values)
        drive_path = serialize_links(drive_link_values)
        website_path = serialize_links(website_link_values)

        # --- Action Routing ---
        if trigger_id in ('btn-save', 'btn-save-close', 'btn-unsaved-save'):
            if name and name.strip():
                name = ConfigManager.apply_titlecase_linter(name.strip())
            if not name or not name.strip():
                # Only show the error if the user has filled in something meaningful.
                # If the form is blank (no desc, all ratings at default), they just
                # changed their mind after clicking New Node — silently close.
                form_has_content = any([
                    desc and desc.strip(),
                    val not in (None, 5),
                    interest not in (None, 5),
                    diff not in (None, 5),
                ])
                if form_has_content:
                    msg = "Error: Node name is required."
                    return current_elements, msg, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, False, 0, dash.no_update, dash.no_update, next_ed_style, next_fil_style, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, next_goal_style
                else:
                    next_ed_style['transform'] = "translateX(-380px)"
                    return current_elements, "", dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, False, 0, dash.no_update, dash.no_update, next_ed_style, next_fil_style, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, next_goal_style
            if not n_type:
                msg = "Error: Node type is required."
                return current_elements, msg, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, False, 0, dash.no_update, dash.no_update, next_ed_style, next_fil_style, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, next_goal_style
            try:
                # Track if this save marks the node Done (for event completion check)
                if status_done and "Done" in (status_done or []):
                    completion_check_node = name

                multiplier = ConfigManager.get_time_multiplier(time_unit)
                t_o = float(time_o or 0) * multiplier
                t_m = float(time_m or 0) * multiplier
                t_p = float(time_p or 0) * multiplier

                # Intercept rename: if original name differs from current name, rename node atomically
                if (trigger_id in ('btn-save', 'btn-save-close', 'btn-unsaved-save') and
                        original_name and original_name.strip() and
                        name.strip() != original_name.strip() and
                        manager.get_node(original_name.strip())):
                    manager.rename_node(original_name.strip(), name.strip())
                    # Update override reference on rename
                    _ov = ConfigManager.get_override()
                    if _ov.get("parent") == original_name.strip():
                        _ov["parent"] = name.strip()
                        ConfigManager.set_override(_ov)

                time_mode = 'inherited' if (time_mode_val and 'inherited' in time_mode_val) else 'manual'
                msg = handle_save(manager, name, n_type, desc, val, t_o, t_m, t_p,
                                  interest, diff, status_done, context, subctx,
                                  obs_path, drive_path, website_path,
                                  e_needs_h, e_needs_s,
                                  e_supp_h, e_supp_s, e_helps,
                                  progress_val, time_mode=time_mode,
                                  competence=competence_val)

                # Save aliases
                clean_aliases = [a for a in (alias_values or []) if a and a.strip()]
                manager.set_aliases(name, clean_aliases)

                # Update priority goals for Goal nodes
                if n_type == 'Goal':
                    priority_goals = ConfigManager.get_priority_goals()
                    if name in priority_goals:
                        priority_goals.remove(name)
                    if priority_rank_val and priority_rank_val != "none":
                        rank_idx = int(priority_rank_val) - 1
                        rank_idx = min(rank_idx, len(priority_goals))
                        priority_goals.insert(rank_idx, name)
                    ConfigManager.set_priority_goals(priority_goals)
            except (ValueError, TypeError):
                msg = "Error: Please check your mathematical inputs."
                return current_elements, msg, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, False, 0, dash.no_update, dash.no_update, next_ed_style, next_fil_style, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, next_goal_style
            except Exception as e:
                msg = f"Error: {e}"
        elif trigger_id == 'btn-node-delete-confirm' and name:
            try:
                msg = handle_delete(manager, name)
                # Clear override if deleted node was the override parent
                _ov = ConfigManager.get_override()
                if _ov.get("parent") == name:
                    ConfigManager.clear_override()
            except Exception as e:
                msg = f"Error: {e}"
        elif trigger_id == 'btn-toggle-done-node' and tapped_node:
            try:
                node_id = tapped_node.get('id')
                _pre_node = manager.get_node(node_id)
                if _pre_node and _pre_node.status != "Done":
                    completion_check_node = node_id
                msg = handle_toggle_done(manager, tapped_node)
            except Exception as e:
                msg = f"Error: {e}"
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
                msg = f"Error: {e}"
        elif trigger_id == 'group-delete-input' and group_delete_data:
            try:
                msg = handle_group_delete(manager, group_delete_data)
            except Exception as e:
                msg = f"Error: {e}"
        # --- Visual Generation ---
        ui_only_triggers = ('btn-edit-node', 'btn-add', 'btn-new-node', 'edit-trigger-input', 'details-edit-trigger-input', 'cytoscape-graph', 'btn-close-editor')
        if trigger_id in ui_only_triggers:
            # We bypass full graph recreation and list evaluation
            elements = dash.no_update
            community_options = dash.no_update
            search_options = dash.no_update
            f_ctx_list = dash.no_update
            ctx_list = dash.no_update
            type_list = dash.no_update
            f_type_list = dash.no_update
            goal_opts = dash.no_update
            active_stylesheet = dash.no_update
            clear_focus_style = dash.no_update
            node_count_text = dash.no_update
            
            # Still format sidebar traversal UI
            count = sugg_count if sugg_count else 10
            sugg_ui = format_suggestions_table(get_suggestions(filters, count=count), manager, active_suggestion_id, override_set=get_override_set())
            sugg_ui = sugg_ui + format_next_visualizations(manager)
            effective_tapped_node = None if trigger_id in ('background-click-input', 'btn-add') else tapped_node
            hard_chains_ui, soft_chains_ui, synergies_ui, description_ui = format_traversal_ui(effective_tapped_node, active_node_id, manager)

        else:
            community_method = community_method or "components"
            communities = manager.detect_communities(method=community_method, filters=filters)
            community_options = [{"label": "All", "value": "All"}]
            name_counts: dict[str, int] = {}
            for i, comm in enumerate(communities):
                base_name = manager.name_community(comm)
                name_counts[base_name] = name_counts.get(base_name, 0) + 1
                if name_counts[base_name] > 1:
                    label = f"{base_name} #{name_counts[base_name]} ({len(comm)} nodes)"
                else:
                    label = f"{base_name} ({len(comm)} nodes)"
                community_options.append({"label": label, "value": str(i)})
            # Fix labels retroactively when the first occurrence also needs a number
            for key, count in name_counts.items():
                if count > 1:
                    for opt in community_options:
                        if opt["label"].startswith(f"{key} (") and opt["value"] != "All":
                            opt["label"] = opt["label"].replace(f"{key} (", f"{key} #1 (", 1)
                            break

            community_names = None
            if f_community and f_community != "All":
                try:
                    idx = int(f_community)
                    if 0 <= idx < len(communities):
                        community_names = communities[idx]
                except (ValueError, IndexError): pass
            elif community_method == "orphans" and communities:
                # "All" in orphans mode still means "only orphan nodes", not every node
                community_names = set().union(*communities)

            elements = generate_elements(filters, active_node_id,
                                        community_names=community_names,
                                        max_depth=gs_max_depth or 0,
                                        neighbor_links=gs_neighbor_links if gs_neighbor_links is not None else True)

            count = sugg_count if sugg_count else 10
            sugg_ui = format_suggestions_table(get_suggestions(filters, count=count), manager, active_suggestion_id, override_set=get_override_set())
            sugg_ui = sugg_ui + format_next_visualizations(manager)
            effective_tapped_node = None if trigger_id in ('background-click-input', 'btn-add') else tapped_node
            hard_chains_ui, soft_chains_ui, synergies_ui, description_ui = format_traversal_ui(effective_tapped_node, active_node_id, manager)

            all_nodes = manager.get_all_nodes()
            search_options = node_options(manager.get_all_nodes(include_dormant=True))

            # Append alias entries to search options (use alias: prefix for unique values)
            for alias, node_name in manager.get_all_aliases().items():
                search_options.append({'label': f"{alias} \u2192 {node_name}", 'value': f"alias:{alias}"})

            # Populate dynamic contexts datalists from DB + Config preserving defined order
            base_ctx = ConfigManager.get_contexts()
            
            ctx_list = [{"label": "None", "value": ""}] + [{"label": c, "value": c} for c in base_ctx]
            f_ctx_list = [{"label": c, "value": c} for c in base_ctx]

            base_types = ConfigManager.get_node_types()
            type_list = [{"label": t, "value": t} for t in base_types]

            f_type_list = [{"label": t, "value": t} for t in base_types]

            # Goal filter options
            goal_nodes = [n for n in all_nodes if n.type == "Goal"]
            goal_opts = [{"label": g.name, "value": g.name} for g in goal_nodes]

            # Focus mode stylesheet: highlight subtree, dim others
            from layout import stylesheet as base_stylesheet
            active_stylesheet = list(base_stylesheet)
            if focus_goal:
                if focus_subtree_override is not None:
                    focus_subtree = focus_subtree_override
                else:
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
                # Highlight edges between focus subtree nodes
                edges = manager.get_edges()
                for e in edges:
                    if e['source'] in focus_subtree and e['target'] in focus_subtree:
                        eid = f"{e['source']}_{e['target']}_{e['type']}".replace("'", "\\'")
                        active_stylesheet.append({
                            'selector': f'edge[id = "{eid}"]',
                            'style': {'opacity': 1}
                        })

            clear_focus_style = {"display": "inline-block"} if focus_goal else {"display": "none"}

            # Silently auto-trigger events tied to this node's completion.
            # The user is notified on next app load via the announcement modal.
            if completion_check_node:
                try:
                    _event_mgr.auto_trigger_by_node_completion(completion_check_node)
                except Exception:
                    pass

            if active_tab in ('tab-settings', 'tab-events', 'tab-analyze'):
                node_count_text = ""
            elif active_tab == 'tab-details':
                node_count_text = dash.no_update  # Owned by update_details_node_count in details_callbacks
            else:
                node_count = sum(1 for el in elements if 'source' not in el.get('data', {}))
                node_count_text = f"{node_count} node{'s' if node_count != 1 else ''} displayed"

        return elements, msg, sugg_ui, hard_chains_ui, soft_chains_ui, synergies_ui, description_ui, False if msg else True, 0, community_options, search_options, next_ed_style, next_fil_style, f_ctx_list, ctx_list, type_list, f_type_list, goal_opts, active_stylesheet, clear_focus_style, node_count_text, next_goal_style, next_events_sidebar_style

    @app.callback(
        Output('modal-unsaved-changes', 'is_open'),
        [Input('btn-close-editor', 'n_clicks'),
         Input('btn-unsaved-cancel', 'n_clicks'),
         Input('btn-unsaved-save', 'n_clicks'),
         Input('btn-unsaved-discard', 'n_clicks')],
        [State('node-name', 'value'), State('node-desc', 'value'),
         State('node-value', 'value'), State('node-interest', 'value'),
         State('node-difficulty', 'value'), State('node-original-name', 'data')],
        prevent_initial_call=True
    )
    def toggle_unsaved_modal(_close, _cancel, _save, _discard, name, desc, val, interest, diff, original_name):
        trigger_id = get_trigger_id()
        if trigger_id == 'btn-close-editor':
            if original_name:
                old_node = manager.get_node(original_name)
                if old_node:
                    name_changed = (name or "").strip() != (old_node.name or "").strip()
                    desc_changed = (desc or "").strip() != (old_node.description or "").strip()
                    val_changed = float(val or 5) != float(old_node.value or 5)
                    interest_changed = float(interest or 5) != float(old_node.interest or 5)
                    diff_changed = float(diff or 5) != float(old_node.difficulty or 5)
                    return any([name_changed, desc_changed, val_changed, interest_changed, diff_changed])
            has_content = bool(name and name.strip()) or bool(desc and desc.strip()) or any([
                val not in (None, 5), interest not in (None, 5), diff not in (None, 5),
            ])
            return has_content
        return False

    # --- Delete Confirmation Modal ---
    @app.callback(
        Output('modal-node-delete-confirm', 'is_open'),
        [Input('btn-delete', 'n_clicks'),
         Input('btn-node-delete-cancel', 'n_clicks'),
         Input('btn-node-delete-confirm', 'n_clicks')],
        prevent_initial_call=True,
    )
    def toggle_delete_modal(_delete, _cancel, _confirm):
        trigger_id = get_trigger_id()
        return trigger_id == 'btn-delete'

    # --- Clear Confirmation Modal ---
    @app.callback(
        Output('modal-clear-confirm', 'is_open'),
        [Input('btn-cancel', 'n_clicks'),
         Input('btn-clear-no', 'n_clicks'),
         Input('btn-clear-yes', 'n_clicks')],
        prevent_initial_call=True,
    )
    def toggle_clear_modal(_cancel, _no, _yes):
        trigger_id = get_trigger_id()
        return trigger_id == 'btn-cancel'

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
        Output('focus-goal-store', 'data', allow_duplicate=True),
        Input('btn-clear-focus', 'n_clicks'),
        prevent_initial_call=True,
    )
    def clear_focus(n_clicks):
        if n_clicks:
            return None
        return dash.no_update



    @app.callback(
        Output("modal-error", "is_open"),
        Output("error-modal-body", "children"),
        Input("save-output", "children"),
        Input("btn-close-error", "n_clicks"),
        State("modal-error", "is_open"),
        prevent_initial_call=True
    )
    def toggle_error_modal(save_msg, close_clicks, is_open):
        ctx = dash.callback_context
        trigger = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else ""
        if trigger == "btn-close-error":
            return False, dash.no_update
        if trigger == "save-output" and save_msg and isinstance(save_msg, str) and save_msg.startswith("Error:"):
            return True, save_msg
        return is_open, dash.no_update

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
        Output('filter-subcontext', 'value'),
        Input('filter-context', 'value')
    )
    def update_filter_subcontexts(ctx):
        if not ctx or ctx == "All" or (isinstance(ctx, list) and not ctx):
            return [], []
        contexts = ctx if isinstance(ctx, list) else [ctx]
        all_subs = ConfigManager.get_subcontexts()
        multi_context = len(contexts) > 1
        seen = set()  # tracks (context, subcontext) pairs to avoid duplicates
        opts = []
        for c in contexts:
            for s in all_subs.get(c, []):
                key = (c, s) if multi_context else s
                if key not in seen:
                    seen.add(key)
                    label = f"{c} > {s}" if multi_context else s
                    opts.append({"label": label, "value": s})
        return opts, []



    # --- Subcontext Collapse Toggle ---
    @app.callback(
        Output("collapse-subcontext", "is_open"),
        [Input("btn-subcontext-toggle", "n_clicks")],
        [State("collapse-subcontext", "is_open")],
    )
    def toggle_subcontext(n, is_open):
        if n: return not is_open
        return is_open

    # --- Aliases Collapse Toggle ---
    @app.callback(
        Output("collapse-aliases", "is_open"),
        Input("btn-aliases-toggle", "n_clicks"),
        State("collapse-aliases", "is_open"),
    )
    def toggle_aliases(n, is_open):
        if n: return not is_open
        return is_open

    # --- Aliases Render ---
    @app.callback(
        Output('aliases-container', 'children'),
        Input('aliases-store', 'data'),
    )
    def render_aliases(aliases):
        if not aliases:
            aliases = ['']
        rows = []
        for i, val in enumerate(aliases):
            rows.append(html.Div([
                dbc.Input(
                    id={'type': 'alias-input', 'index': i},
                    type='text', value=val or '',
                    placeholder='',
                    style={'flex': '1'},
                ),
                dbc.Button('\u00d7',
                    id={'type': 'btn-alias-remove', 'index': i},
                    color='link', className='p-0 ms-1 text-decoration-none text-muted',
                    style={'fontSize': '1.1rem', 'lineHeight': '1'}),
            ], className='d-flex align-items-center mb-1'))
        return rows

    # --- Aliases Add/Remove ---
    @app.callback(
        Output('aliases-store', 'data', allow_duplicate=True),
        [Input('btn-alias-add', 'n_clicks'),
         Input({'type': 'btn-alias-remove', 'index': ALL}, 'n_clicks')],
        [State({'type': 'alias-input', 'index': ALL}, 'value'),
         State('aliases-store', 'data')],
        prevent_initial_call=True,
    )
    def modify_aliases(add_clicks, remove_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        aliases = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-alias-add':
            aliases.append('')
        elif isinstance(trigger, dict) and trigger.get('type') == 'btn-alias-remove':
            idx = trigger['index']
            if 0 <= idx < len(aliases) and len(aliases) > 1:
                aliases.pop(idx)
        return aliases

    # --- Multi-Link Render Callbacks ---
    @app.callback(
        Output('obsidian-links-container', 'children'),
        Input('obsidian-links-store', 'data'),
    )
    def render_obsidian_links(links):
        return render_link_rows(links, 'obsidian-link', has_browse=True)

    @app.callback(
        Output('drive-links-container', 'children'),
        Input('drive-links-store', 'data'),
    )
    def render_drive_links(links):
        return render_link_rows(strip_gdrive_prefix(links), 'drive-link', has_browse=True)

    @app.callback(
        Output('website-links-container', 'children'),
        Input('website-links-store', 'data'),
    )
    def render_website_links(links):
        return render_link_rows(links, 'website-link', has_browse=False)

    # --- Multi-Link Add/Remove Callbacks ---
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
                abs_path = spawn_local_file_picker(
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
                abs_path = spawn_local_file_picker(
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
            return _open_url_or_path(expand_gdrive_prefix(values[idx]))
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

    # --- Edit Trigger: switch to canvas tab ---
    @app.callback(
        Output('main-tabs', 'active_tab', allow_duplicate=True),
        Input('edit-trigger-input', 'value'),
        prevent_initial_call=True,
    )
    def handle_edit_trigger(value):
        if not value:
            return dash.no_update
        node_name = value.split('|')[0]
        if not node_name:
            return dash.no_update
        return 'tab-canvas'

    # --- Graph Settings: Toggle Panel ---
    @app.callback(
        Output('graph-settings-panel', 'style'),
        Input('btn-graph-settings', 'n_clicks'),
        State('graph-settings-panel', 'style'),
        prevent_initial_call=True,
    )
    def toggle_graph_settings(_n, current_style):
        style = dict(current_style) if current_style else {}
        style['display'] = 'none' if style.get('display') != 'none' else 'block'
        return style

    # --- Graph Settings: Reset to Stored Defaults ---
    @app.callback(
        Output('graph-settings-max-depth', 'value', allow_duplicate=True),
        Output('graph-settings-neighbor-links', 'value', allow_duplicate=True),
        Output('graph-settings-animate', 'value', allow_duplicate=True),
        Output('graph-settings-edge-length', 'value', allow_duplicate=True),
        Output('graph-settings-gravity', 'value', allow_duplicate=True),
        Output('graph-settings-repulsion', 'value', allow_duplicate=True),
        Input('btn-reset-graph-settings', 'n_clicks'),
        prevent_initial_call=True,
    )
    def reset_graph_settings(n_clicks):
        if not n_clicks:
            return (dash.no_update,) * 6
        gl = ConfigManager.get_graph_layout_defaults()
        return (
            0, True, True,
            gl.get('edge_length', 100),
            gl.get('gravity', 0.25),
            gl.get('repulsion', 4500),
        )

    # --- Graph Settings: Apply Layout Parameters ---
    @app.callback(
        Output('cytoscape-graph', 'layout'),
        Input('graph-settings-edge-length', 'value'),
        Input('graph-settings-gravity', 'value'),
        Input('graph-settings-repulsion', 'value'),
        Input('graph-settings-animate', 'value'),
        Input('graph-settings-relayout', 'n_clicks'),
        Input('btn-sidebar-relayout', 'n_clicks'),
        prevent_initial_call=True,
    )
    def update_graph_layout(edge_length, gravity, repulsion, animate, _relayout, _sidebar_relayout):
        randomize = ctx.triggered_id in ('graph-settings-relayout', 'btn-sidebar-relayout')
        return {
            'name': 'cose-bilkent',
            'fit': True,
            'animate': bool(animate),
            'randomize': randomize,
            'idealEdgeLength': edge_length or 100,
            'nodeRepulsion': repulsion or 4500,
            'gravity': gravity if gravity is not None else 0.25,
            'numIter': 2500,
        }

    # =====================================================================
    # Override callbacks
    # =====================================================================

    @app.callback(
        Output('override-toggle', 'value'),
        Input('node-original-name', 'data'),
        Input('override-store', 'data'),
        prevent_initial_call=True,
    )
    def sync_override_toggle(node_name, _override_data):
        """Sync override toggle state when the edited node or override state changes."""
        if not node_name:
            return []
        override = ConfigManager.get_override()
        if not override.get("parent"):
            return []
        override_set = ConfigManager.get_override_node_set(manager)
        return ["on"] if node_name in override_set else []

    @app.callback(
        Output('popover-override-mode', 'is_open'),
        Output('modal-override-conflict', 'is_open', allow_duplicate=True),
        Output('override-conflict-body', 'children'),
        Output('modal-override-untoggle', 'is_open', allow_duplicate=True),
        Output('override-untoggle-body', 'children'),
        Output('override-store', 'data', allow_duplicate=True),
        Output('details-refresh-trigger', 'data', allow_duplicate=True),
        Input('override-toggle', 'value'),
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def handle_override_toggle(toggle_val, node_name):
        """Handle override toggle interaction: open popover, show conflicts, or clear."""
        no_change = (False, False, dash.no_update, False, dash.no_update, dash.no_update, dash.no_update)
        if not node_name:
            return no_change

        toggle_on = bool(toggle_val and "on" in toggle_val)
        override = ConfigManager.get_override()
        current_parent = override.get("parent")

        if toggle_on:
            # Turning ON
            if current_parent:
                override_set = ConfigManager.get_override_node_set(manager)
                if node_name in override_set:
                    # Node is already in the override set (parent or dep) — sync triggered this
                    return no_change
            if current_parent:
                # Conflict: different override already active
                body = f'An override is already active for "{current_parent}". Do you want to keep the current override, or apply it to this new set?'
                return False, True, body, False, dash.no_update, dash.no_update, dash.no_update
            else:
                # No existing override: open popover for mode selection
                return True, False, dash.no_update, False, dash.no_update, dash.no_update, dash.no_update
        else:
            # Turning OFF
            if not current_parent:
                return no_change
            if node_name == current_parent:
                # Direct parent: clear override
                import time as _time
                ConfigManager.clear_override()
                return False, False, dash.no_update, False, dash.no_update, ConfigManager.get_override(), f"override-{_time.time()}"
            else:
                # Inherited dep: show untoggle modal
                override_set = ConfigManager.get_override_node_set(manager)
                if node_name in override_set:
                    body = f'This override was inherited from "{current_parent}".'
                    return False, False, dash.no_update, True, body, dash.no_update, dash.no_update
                else:
                    return no_change

    @app.callback(
        Output('popover-override-mode', 'is_open', allow_duplicate=True),
        Output('override-store', 'data', allow_duplicate=True),
        Output('details-refresh-trigger', 'data', allow_duplicate=True),
        Input('btn-override-apply', 'n_clicks'),
        State('override-mode-radio', 'value'),
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def apply_override(n_clicks, mode, node_name):
        """Apply override with selected mode from the popover."""
        if not n_clicks or not node_name:
            return dash.no_update, dash.no_update, dash.no_update
        ConfigManager.set_override({"parent": node_name, "mode": mode or "hard"})
        import time
        return False, ConfigManager.get_override(), f"override-{time.time()}"

    @app.callback(
        Output('modal-override-conflict', 'is_open', allow_duplicate=True),
        Output('override-store', 'data', allow_duplicate=True),
        Output('details-refresh-trigger', 'data', allow_duplicate=True),
        Input('btn-override-keep', 'n_clicks'),
        Input('btn-override-replace', 'n_clicks'),
        State('override-conflict-mode-radio', 'value'),
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def resolve_override_conflict(keep_clicks, replace_clicks, mode, node_name):
        """Resolve conflict when a new override is attempted while one is active."""
        import time
        trigger = get_trigger_id()
        if trigger == 'btn-override-keep':
            return False, dash.no_update, dash.no_update
        elif trigger == 'btn-override-replace' and node_name:
            ConfigManager.set_override({"parent": node_name, "mode": mode or "hard"})
            return False, ConfigManager.get_override(), f"override-{time.time()}"
        return dash.no_update, dash.no_update, dash.no_update

    @app.callback(
        Output('modal-override-untoggle', 'is_open', allow_duplicate=True),
        Output('override-store', 'data', allow_duplicate=True),
        Output('details-refresh-trigger', 'data', allow_duplicate=True),
        Input('btn-override-untoggle-cancel', 'n_clicks'),
        Input('btn-override-untoggle-all', 'n_clicks'),
        Input('btn-override-untoggle-hard', 'n_clicks'),
        Input('btn-override-untoggle-soft', 'n_clicks'),
        prevent_initial_call=True,
    )
    def resolve_override_untoggle(cancel, untoggle_all, hard_only, soft_only):
        """Resolve untoggling an inherited override dependency."""
        import time as _time
        trigger = get_trigger_id()
        if trigger == 'btn-override-untoggle-cancel':
            return False, dash.no_update, dash.no_update
        elif trigger == 'btn-override-untoggle-all':
            ConfigManager.clear_override()
            return False, ConfigManager.get_override(), f"override-{_time.time()}"
        elif trigger == 'btn-override-untoggle-hard':
            override = ConfigManager.get_override()
            override["mode"] = "hard"
            ConfigManager.set_override(override)
            return False, ConfigManager.get_override(), f"override-{_time.time()}"
        elif trigger == 'btn-override-untoggle-soft':
            override = ConfigManager.get_override()
            override["mode"] = "soft"
            ConfigManager.set_override(override)
            return False, ConfigManager.get_override(), f"override-{_time.time()}"
        return dash.no_update, dash.no_update, dash.no_update

    # --- Ratings Editor ---

    @app.callback(
        Output("modal-ratings-editor", "is_open"),
        Output("ratings-editor-body", "children"),
        Input("btn-ratings-edit", "n_clicks"),
        Input("btn-ratings-editor-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_ratings_editor(edit_clicks, cancel_clicks):
        from layout import build_editor_table
        if ctx.triggered_id == "btn-ratings-edit":
            defs = ConfigManager.get_ratings_definitions()
            return True, build_editor_table(defs)
        return False, no_update

    @app.callback(
        Output("ratings-popup-table-body", "children"),
        Output("modal-ratings-editor", "is_open", allow_duplicate=True),
        Input("btn-ratings-editor-save", "n_clicks"),
        State({"type": "ratings-edit-value", "index": ALL}, "value"),
        State({"type": "ratings-edit-interest", "index": ALL}, "value"),
        State({"type": "ratings-edit-effort", "index": ALL}, "value"),
        prevent_initial_call=True,
    )
    def save_ratings_definitions(n_clicks, values, interests, efforts):
        from layout import build_popup_table_rows
        defs = ConfigManager.get_ratings_definitions()
        new_defs = []
        for i, d in enumerate(defs):
            new_defs.append({
                "rating": d["rating"],
                "value": values[i] if i < len(values) else d["value"],
                "interest": interests[i] if i < len(interests) else d["interest"],
                "effort": efforts[i] if i < len(efforts) else d["effort"],
            })
        ConfigManager.set_ratings_definitions(new_defs)
        return build_popup_table_rows(new_defs), False


