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
from typing import Tuple, Any
from callback_helpers import (
    parse_links, serialize_links, get_trigger_id, get_all_triggered_ids,
    node_options, build_filters,
    handle_save, handle_delete, handle_toggle_done, handle_group_delete,
    format_suggestions_table, format_traversal_ui, SECTION_TITLE_STYLE,
    render_link_rows, spawn_local_file_picker,
    strip_gdrive_prefix, expand_gdrive_prefix,
    should_open_editor, resolve_active_node_id,
)

logger = logging.getLogger(__name__)

manager = GraphManager()


# Backward-compatible aliases for helpers now in callback_helpers.py
_parse_links = parse_links
_serialize_links = serialize_links
_get_trigger_id = get_trigger_id
_node_options = node_options


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


_spawn_local_file_picker = spawn_local_file_picker  # backward-compat alias


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
                'color': (
                    colors.get('Done', '#198754') if node.type == 'Goal' and node.status == 'Done'
                    else colors.get('Blocked', '#dc3545') if node.type == 'Goal' and node.status == 'Blocked'
                    else colors.get('Goal', '#ffc107') if node.type == 'Goal'
                    else colors.get('Done', '#198754') if node.type == 'Resource' and node.status == 'Done'
                    else colors.get('Blocked', '#dc3545') if node.type == 'Resource' and node.status == 'Blocked'
                    else colors.get('Resource', '#9b59b6') if node.type == 'Resource'
                    else colors.get(node.status, '#888')
                ),
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


_build_filters = build_filters


def _format_suggestions_table(suggs, selected_node_id=None):
    """Render the top-scored nodes as an HTML table with normalized priority scores (0-100)."""
    return format_suggestions_table(suggs, manager, selected_node_id)


def _format_traversal_ui(tapped_node, active_node_id):
    """Build the dependency chains (hard/soft) and synergies display for the selected node."""
    return format_traversal_ui(tapped_node, active_node_id, manager)  # returns 4-tuple


def _handle_save(name, n_type, desc, val, time_o, time_m, time_p, interest, diff,
                  status_done, context, subctx, obs_path, drive_path, website_path,
                  e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                  progress_val=None):
    """Create or update a node and sync its edges. Returns a status message."""
    return handle_save(manager, name, n_type, desc, val, time_o, time_m, time_p, interest, diff,
                       status_done, context, subctx, obs_path, drive_path, website_path,
                       e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                       progress_val)


def _handle_delete(name):
    """Delete a single node by name. Returns a status message."""
    return handle_delete(manager, name)


def _handle_toggle_done(tapped_node):
    """Toggle a node's status between Done and Open. Returns a status message."""
    return handle_toggle_done(manager, tapped_node)


def _handle_group_delete(group_delete_data):
    """Delete multiple nodes from a JSON-encoded list. Returns a status message."""
    return handle_group_delete(manager, group_delete_data)


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
        Input('goal-mini-graph', 'mouseoverNodeData'),
    )
    def display_hover_data(data, goal_data):
        trigger = _get_trigger_id()
        if trigger == 'goal-mini-graph':
            data = goal_data
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

            lines = [
                header,
                html.Div([html.Strong("Type: "), node_type]),
                html.Div([html.Strong("Status: "),
                          html.Span(effective_status, style={"color": status_color})]),
            ]

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

            if data.get('context'):
                lines.append(html.Div([html.Strong("Context: "), data.get('context', '')]))
            if data.get('subcontext'):
                lines.append(html.Div([html.Strong("Subcontext: "), data.get('subcontext', '')]))

        else:
            final_time = data.get('time', 0)
            time_str = ConfigManager.format_time_friendly(final_time)

            lines = [
                header,
                html.Div([html.Strong("Type: "), node_type]),
                html.Div([html.Strong("Status: "), data.get('status', '')]),
                html.Div([html.Strong("Value: "), str(data.get('value', ''))]),
                html.Div([html.Strong("Effort: "), str(data.get('difficulty', ''))]),
                html.Div([html.Strong("Time: "), time_str]),
            ]

            if node_type == 'Resource' and data.get('progress') is not None:
                lines.append(html.Div([html.Strong("Progress: "), f"{data.get('progress', 0)}%"]))

            if data.get('context'):
                lines.append(html.Div([html.Strong("Context: "), data.get('context', '')]))
            if data.get('subcontext'):
                lines.append(html.Div([html.Strong("Subcontext: "), data.get('subcontext', '')]))

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
         Output('search-node', 'value', allow_duplicate=True)],
        [Input('cytoscape-graph', 'tapNodeData'),
         Input('btn-add', 'n_clicks'),
         Input('btn-cancel', 'n_clicks'),
         Input('btn-unsaved-discard', 'n_clicks'),
         Input('search-node', 'value'),
         Input('background-click-input', 'value')],
        [State('cytoscape-graph', 'elements')],
        prevent_initial_call='initial_duplicate'
    )
    def populate_editor(data, add_clicks, cancel_clicks, discard_clicks, search_val, _bg_click, elements):
        """Populate the editor sidebar form fields when a node is selected, searched, or cleared."""
        trigger_id = _get_trigger_id()

        all_nodes = manager.get_all_nodes()
        options = _node_options(all_nodes)

        def_out = [
            "", "Learn", "", "", "", 5, 5, 5, 2, 4, 6, "Open", [],
            [], [], [], [], [],
            options, options, options, options, options,
            [''], [''], [''],
            # Type-specific defaults
            0, "weeks", "weeks",
            None,  # node-original-name
            dash.no_update,  # search-node — don't change; avoids retriggering core_engine
        ]

        if trigger_id in ['btn-add', 'btn-cancel', 'btn-unsaved-discard', 'background-click-input']:
            return def_out

        name = None
        if trigger_id == 'search-node':
            if not search_val:
                # User cleared the search bar — reset form to defaults
                return def_out
            node = manager.get_node(search_val)
            if node:
                name = node.name
                data = node.to_dict()
                data['id'] = name
            else:
                return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*7
        elif data:
            name = data.get('id')
            # Always read fresh data from DB on tap (Cytoscape data may be stale)
            if name:
                db_node = manager.get_node(name)
                if db_node:
                    data = db_node.to_dict()
                    data['id'] = name

        if not name or not data:
            return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*7

        edges = manager.get_edges()

        # In/Out Edges mapping
        needs_hard_vals = [e['source'] for e in edges if e['target'] == name and e['type'] == EDGE_NEEDS_HARD]
        needs_soft_vals = [e['source'] for e in edges if e['target'] == name and e['type'] == EDGE_NEEDS_SOFT]
        supp_hard_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == EDGE_NEEDS_HARD]
        supp_soft_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == EDGE_NEEDS_SOFT]

        helps_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == EDGE_HELPS]
        helps_vals += [e['source'] for e in edges if e['target'] == name and e['type'] == EDGE_HELPS]
        helps_vals = list(set(helps_vals))
        filtered_options = _node_options(all_nodes, exclude=name)

        actual_status = data.get('status', 'Open')
        done_val = ["Done"] if actual_status == "Done" else []

        friendly_o, friendly_m, friendly_p, friendly_unit = _friendly_time_estimates(
            data.get('time_o', 1.0), data.get('time_m', 1.0), data.get('time_p', 1.0)
        )

        return [
            name, data.get('type'), data.get('description'),
            data.get('context') or '', data.get('subcontext') or '',
            data.get('value', 5), data.get('interest', 5), data.get('difficulty', 5),
            friendly_o, friendly_m, friendly_p,
            actual_status, done_val,
            needs_hard_vals, needs_soft_vals, supp_hard_vals, supp_soft_vals,
            helps_vals,
            filtered_options, filtered_options, filtered_options, filtered_options, filtered_options,
            _parse_links(data.get('obsidian_path', '')),
            _parse_links(data.get('google_drive_path', '')),
            _parse_links(data.get('website', '')),
            # Type-specific fields
            data.get('progress') or 0, friendly_unit, friendly_unit,
            name,  # node-original-name — track what was loaded
            dash.no_update,  # search-node — don't change; avoids retriggering core_engine
        ]

    # --- Type-adaptive field visibility ---
    @app.callback(
        [Output('section-done-time', 'style'),
         Output('section-time-estimates', 'style'),
         Output('section-resource', 'style')],
        Input('node-type', 'value')
    )
    def toggle_type_fields(node_type):
        show = {}
        hide = {'display': 'none'}
        if node_type == 'Resource':
            return show, show, show
        elif node_type == 'Goal':
            return show, hide, hide
        else:  # Learn, Action
            return show, show, hide

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

    # --- Priority Badge in Node Editor ---
    @app.callback(
        Output('node-priority-badge', 'children'),
        Output('node-priority-badge', 'style'),
        Input('node-name', 'value'),
        Input('node-type', 'value'),
    )
    def update_node_priority_badge(node_name, node_type):
        hidden = {"display": "none"}
        visible = {"display": "flex", "gap": "4px", "flexWrap": "wrap", "marginBottom": "8px"}
        if not node_name:
            return [], hidden

        priority_goals = ConfigManager.get_priority_goals()
        if not priority_goals:
            return [], hidden

        badges = []

        if node_type == "Goal" and node_name in priority_goals:
            rank = priority_goals.index(node_name) + 1
            badges.append(dbc.Badge(f"#{rank} Priority", color="warning", style={"fontSize": "0.75rem"}))
        else:
            # Check if this node is in any priority goal's subtree
            for rank_idx, goal_name in enumerate(priority_goals[:3]):
                full_subtree = manager.get_goal_subtree(goal_name)
                if node_name not in full_subtree:
                    continue
                rank = rank_idx + 1
                hard_subtree = manager.get_goal_subtree(goal_name, edge_types=(EDGE_NEEDS_HARD,))
                rel_type = "Hard" if node_name in hard_subtree else "Soft"
                rel_color = "primary" if rel_type == "Hard" else "info"
                badges.append(dbc.Badge(f"#{rank} Priority", color="warning", style={"fontSize": "0.75rem"}))
                badges.append(dbc.Badge(rel_type, color=rel_color, style={"fontSize": "0.75rem"}))

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
         Output('node-completion-events-store', 'data'),
         Output('filter-node-count', 'children')],

        [Input('btn-save', 'n_clicks'), Input('btn-save-close', 'n_clicks'), Input('btn-delete', 'n_clicks'),
         Input('filter-context', 'value'), Input('filter-subcontext', 'value'), Input('filter-done', 'value'),
         Input('search-node', 'value'),
         Input('cytoscape-graph', 'tapNodeData'),
         Input('filter-community', 'value'), Input('community-method', 'value'),
         Input('filter-value', 'value'), Input('filter-interest', 'value'),
         Input('filter-time', 'value'), Input('filter-difficulty', 'value'),
         Input('suggestion-count-store', 'data'),
         Input('btn-edit-node', 'n_clicks'), Input('btn-add', 'n_clicks'),
         Input('btn-close-editor', 'n_clicks'),
         Input('btn-unsaved-save', 'n_clicks'), Input('btn-unsaved-discard', 'n_clicks'),
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
         Input('toggle-done-trigger-input', 'value'),
         Input('events-refresh-trigger', 'data'),
         Input('goals-refresh-trigger', 'data'),
         Input('background-click-input', 'value')],

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
         State('node-original-name', 'data')]
    )
    def core_engine(save_clicks, save_close_clicks, delete_clicks, f_context, f_subcontext, f_done, search_val,
                     tapped_node,  # Cytoscape tapNodeData dict (not a Node object)
                     f_community, community_method, f_value, f_interest, f_time, f_difficulty, sugg_count,
                     btn_edit, btn_add, btn_close_ed, btn_unsaved_save, btn_unsaved_discard, btn_filters, btn_sugg_filters, btn_close_fil, settings_open, migration_open, btn_toggle_done,
                     group_delete_data, f_node_types,
                     active_suggestion_id,
                     f_goal, focus_goal,
                     edit_trigger_data, toggle_done_trigger_data, _events_refresh, _goals_refresh, _bg_click,
                     name, n_type, desc, context, subctx, status_done, val, interest, diff,
                     time_o, time_m, time_p, time_unit,
                     e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                     obs_link_values, drive_link_values, website_link_values,
                     progress_val,
                     current_elements, ed_style, fil_style, original_name):
        """Central state callback handling node CRUD, filtering, and UI updates.

        This is intentionally a single large callback because Dash requires each Output
        to belong to exactly one callback. Since save/delete/filter operations all need
        to refresh the graph elements and sidebar state, they must share one callback.
        """
                     
        trigger_id = _get_trigger_id()
        all_triggered_ids = get_all_triggered_ids()
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
        if should_open_editor(all_triggered_ids, trigger_id, search_val):
            next_ed_style['marginLeft'] = "0px"
        elif trigger_id in ('btn-save', 'btn-save-close', 'btn-cancel', 'btn-delete', 'btn-close-editor', 'btn-unsaved-discard', 'btn-unsaved-save'):
            # btn-save keeps the editor open; btn-save-close and unsaved-save close it after saving.
            # btn-cancel and btn-unsaved-discard close without saving.
            # btn-close-editor only silently closes if the form is blank (otherwise modal handles it).
            if trigger_id in ('btn-save-close', 'btn-unsaved-save') and (not name or not n_type):
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
                    next_ed_style['marginLeft'] = "-380px"
            elif trigger_id not in ('btn-save',):
                next_ed_style['marginLeft'] = "-380px"

        # Filters Sidebar State (overlay, shared between Canvas + Suggestions tabs)
        next_fil_style = fil_style or {"position": "absolute", "top": "0", "right": "-320px", "width": "320px", "height": "100%", "zIndex": 100, "overflowX": "hidden", "overflowY": "auto", "borderLeft": "1px solid #495057", "transition": "right 0.3s ease", "backgroundColor": "#212529"}
        if trigger_id in ('btn-filters-toggle', 'btn-suggestions-filters-toggle'):
            next_fil_style['right'] = "0px" if next_fil_style.get('right', '-320px') == "-320px" else "-320px"
        elif trigger_id == 'btn-close-filters':
            next_fil_style['right'] = "-320px"

        active_node_id = resolve_active_node_id(
            all_triggered_ids, trigger_id, edit_trigger_data,
            search_val, tapped_node, name)

        # When entering focus mode, clear the selected node so only the
        # goal's subtree is highlighted (not a previously-tapped node).
        if trigger_id == 'focus-goal-store' and focus_goal:
            active_node_id = None

        # Serialize multi-link arrays for storage
        obs_path = _serialize_links(obs_link_values)
        drive_path = _serialize_links(drive_link_values)
        website_path = _serialize_links(website_link_values)

        # --- Action Routing ---
        if trigger_id in ('btn-save', 'btn-save-close', 'btn-unsaved-save'):
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
                    return current_elements, msg, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, False, 0, dash.no_update, dash.no_update, next_ed_style, next_fil_style, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
                else:
                    next_ed_style['marginLeft'] = "-380px"
                    return current_elements, "", dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, False, 0, dash.no_update, dash.no_update, next_ed_style, next_fil_style, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
            if not n_type:
                msg = "Error: Node type is required."
                return current_elements, msg, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, False, 0, dash.no_update, dash.no_update, next_ed_style, next_fil_style, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
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

                msg = _handle_save(name, n_type, desc, val, t_o, t_m, t_p,
                                   interest, diff, status_done, context, subctx,
                                   obs_path, drive_path, website_path,
                                   e_needs_h, e_needs_s,
                                   e_supp_h, e_supp_s, e_helps,
                                   progress_val)
            except (ValueError, TypeError):
                msg = "Error: Please check your mathematical inputs."
                return current_elements, msg, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, False, 0, dash.no_update, dash.no_update, next_ed_style, next_fil_style, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
            except Exception as e:
                msg = f"Error: {e}"
        elif trigger_id == 'btn-delete' and name:
            try:
                msg = _handle_delete(name)
            except Exception as e:
                msg = f"Error: {e}"
        elif trigger_id == 'btn-toggle-done-node' and tapped_node:
            try:
                node_id = tapped_node.get('id')
                _pre_node = manager.get_node(node_id)
                if _pre_node and _pre_node.status != "Done":
                    completion_check_node = node_id
                msg = _handle_toggle_done(tapped_node)
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
                msg = _handle_group_delete(group_delete_data)
            except Exception as e:
                msg = f"Error: {e}"
        # --- Visual Generation ---
        ui_only_triggers = ('btn-edit-node', 'btn-add', 'edit-trigger-input', 'cytoscape-graph', 'btn-close-editor')
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
            node_completion_events = dash.no_update
            node_count_text = dash.no_update
            
            # Still format sidebar traversal UI
            count = sugg_count if sugg_count else 10
            sugg_ui = _format_suggestions_table(get_suggestions(filters, count=count), active_suggestion_id)
            effective_tapped_node = None if trigger_id in ('background-click-input', 'btn-add') else tapped_node
            hard_chains_ui, soft_chains_ui, synergies_ui, description_ui = _format_traversal_ui(effective_tapped_node, active_node_id)
            
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

            elements = generate_elements(filters, active_node_id, community_names=community_names)

            count = sugg_count if sugg_count else 10
            sugg_ui = _format_suggestions_table(get_suggestions(filters, count=count), active_suggestion_id)
            effective_tapped_node = None if trigger_id in ('background-click-input', 'btn-add') else tapped_node
            hard_chains_ui, soft_chains_ui, synergies_ui, description_ui = _format_traversal_ui(effective_tapped_node, active_node_id)

            all_nodes = manager.get_all_nodes()
            search_options = _node_options(manager.get_all_nodes(include_dormant=True))
            
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

            # Check for events triggered by node completion
            node_completion_events = dash.no_update
            if completion_check_node:
                try:
                    triggered_events = _event_mgr.get_events_triggered_by_node(completion_check_node)
                    if triggered_events:
                        node_completion_events = [e.name for e in triggered_events]
                except Exception:
                    pass

            node_count = sum(1 for el in elements if 'source' not in el.get('data', {}))
            node_count_text = f"{node_count} node{'s' if node_count != 1 else ''} displayed"

        return elements, msg, sugg_ui, hard_chains_ui, soft_chains_ui, synergies_ui, description_ui, False if msg else True, 0, community_options, search_options, next_ed_style, next_fil_style, f_ctx_list, ctx_list, type_list, f_type_list, goal_opts, active_stylesheet, clear_focus_style, node_completion_events, node_count_text

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
        trigger_id = _get_trigger_id()
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
        seen = set()
        opts = []
        for c in contexts:
            for s in all_subs.get(c, []):
                if s not in seen:
                    seen.add(s)
                    opts.append({"label": s, "value": s})
        return opts, []

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
        count = current_count or 10
        if trigger_id == 'btn-sugg-plus': count = count + 1
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
        Output('setting-gdrive-path', 'value'),
        Output('setting-node-shapes-container', 'children'),
        Output('setting-node-status-colors-container', 'children'),
        Output('setting-node-type-colors-container', 'children'),
        Output('setting-hpw', 'value'),
        Output('setting-hpm', 'value'),
        Output('setting-default-time-unit', 'value'),
        Output('setting-default-time-o', 'value'),
        Output('setting-default-time-m', 'value'),
        Output('setting-default-time-p', 'value'),
        Input('main-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    def load_settings(active_tab: str) -> Tuple[Any, ...]:
        if active_tab != 'tab-settings':
            return (dash.no_update,) * 24

        hp = ConfigManager.get_hyperparams()
        obs = ConfigManager.get_obsidian_vault()
        gdrive = ConfigManager.get_gdrive_path()
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
        display_types = node_types.copy()
        for ft in ["Goal"]:
            if ft not in display_types:
                display_types.append(ft)

        shapes = ConfigManager.get_node_shapes()
        shape_options = [
            {"label": s.title(), "value": s}
            for s in ["ellipse", "triangle", "rectangle", "star", "pentagon", "hexagon",
                       "diamond", "octagon", "round-rectangle", "vee"]
        ]
        shape_rows = []
        for t in display_types:
            shape_rows.append(dbc.Row([
                dbc.Col(dbc.Label(t, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Select(
                    id={"type": "setting-shape", "index": t},
                    options=shape_options,  # type: ignore[reportArgumentType]
                    value=shapes.get(t, "ellipse"),
                ), width=8),
            ], className="mb-2"))

        # Build colors editor — split into Status and Type sections
        colors = ConfigManager.get_node_colors()

        def _color_row(label, key):
            return dbc.Row([
                dbc.Col(dbc.Label(label, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Input(
                    id={"type": "setting-color", "index": key},
                    type="color",  # type: ignore[reportArgumentType]
                    value=colors.get(key, "#6c757d"),
                    style={"height": "38px", "padding": "2px"},
                ), width=4),
                dbc.Col(html.Small(
                    colors.get(key, "#6c757d"),
                    className="text-muted d-flex align-items-center",
                    style={"fontSize": "0.8rem"},
                ), width=4),
            ], className="mb-2")

        status_color_rows = [
            _color_row("Open", "Open"),
            _color_row("Blocked", "Blocked"),
            _color_row("Done", "Done"),
        ]

        type_color_rows = [
            _color_row("Goal", "Goal"),
            _color_row("Resource", "Resource"),
        ]

        ts = ConfigManager.get_time_settings()
        ted = ConfigManager.get_time_estimate_defaults()

        return (hp.get('w_v'), hp.get('w_i'), hp.get('d_H'), hp.get('d_S'), hp.get('d_Syn'),
                hp.get('w_e'), hp.get('w_t'), hp.get('beta'), hp.get('goal_boost', 1.5),
                ntypes, ctxts, subctxts, "Custom", obs, gdrive, shape_rows,
                status_color_rows, type_color_rows,
                ts.get('hours_per_week', 40), ts.get('hours_per_month', 160),
                ted.get('unit', 'weeks'),
                ted.get('optimistic', 2), ted.get('expected', 4), ted.get('pessimistic', 6))

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

    # --- Settings: Sync Time Estimates ---
    @app.callback(
        Output('setting-hpw', 'value', allow_duplicate=True),
        Output('setting-hpm', 'value', allow_duplicate=True),
        Input('setting-hpw', 'value'),
        Input('setting-hpm', 'value'),
        prevent_initial_call=True,
    )
    def sync_time_settings(hpw, hpm):
        from dash import ctx, no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update
            
        try:
            if triggered == 'setting-hpw' and hpw is not None:
                return no_update, round(float(hpw) * 4.0, 2)
            elif triggered == 'setting-hpm' and hpm is not None:
                return round(float(hpm) / 4.0, 2), no_update
        except Exception:
            pass
        return no_update, no_update

    # --- Settings: Save ---
    @app.callback(
        Output('settings-save-status', 'children'),
        Output('pending-settings-store', 'data'),
        Output('settings-clear-interval', 'disabled'),
        Output('settings-clear-interval', 'n_intervals'),
        Input('btn-settings-save', 'n_clicks'),
        State('hp-wv', 'value'), State('hp-wi', 'value'),
        State('hp-dh', 'value'), State('hp-ds', 'value'), State('hp-dsyn', 'value'),
        State('hp-we', 'value'), State('hp-wt', 'value'), State('hp-beta', 'value'),
        State('hp-goal-boost', 'value'),
        State('setting-node-types', 'value'),
        State('setting-contexts', 'value'),
        State('setting-subcontexts', 'value'),
        State('setting-obsidian-path', 'value'),
        State('setting-gdrive-path', 'value'),
        State({"type": "setting-shape", "index": ALL}, "value"),
        State({"type": "setting-shape", "index": ALL}, "id"),
        State({"type": "setting-color", "index": ALL}, "value"),
        State({"type": "setting-color", "index": ALL}, "id"),
        State('setting-hpw', 'value'), State('setting-hpm', 'value'),
        State('setting-default-time-unit', 'value'),
        State('setting-default-time-o', 'value'),
        State('setting-default-time-m', 'value'),
        State('setting-default-time-p', 'value'),
        prevent_initial_call=True,
    )
    def save_settings(n_clicks, wv, wi, dh, ds, dsyn, we, wt, beta, goal_boost,
                      n_types_val, contexts_val, subcontexts_val, obs_path, gdrive_path,
                      shape_values, shape_ids, color_values, color_ids,
                      hpw, hpm,
                      def_time_unit, def_time_o, def_time_m, def_time_p):
        if not n_clicks:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        try:
            new_hp = {
                'w_v': float(wv), 'w_i': float(wi),
                'd_H': float(dh), 'd_S': float(ds), 'd_Syn': float(dsyn),
                'w_e': float(we), 'w_t': float(wt), 'beta': float(beta),
                'goal_boost': float(goal_boost) if goal_boost is not None else 1.5,
            }

            new_ts = {
                'hours_per_week': float(hpw) if hpw is not None else 40,
                'hours_per_month': float(hpm) if hpm is not None else 160,
            }

            from config import DEFAULT_TIME_ESTIMATE_DEFAULTS
            new_ted = {
                'optimistic': float(def_time_o) if def_time_o is not None else DEFAULT_TIME_ESTIMATE_DEFAULTS['optimistic'],
                'expected': float(def_time_m) if def_time_m is not None else DEFAULT_TIME_ESTIMATE_DEFAULTS['expected'],
                'pessimistic': float(def_time_p) if def_time_p is not None else DEFAULT_TIME_ESTIMATE_DEFAULTS['pessimistic'],
                'unit': def_time_unit or DEFAULT_TIME_ESTIMATE_DEFAULTS['unit'],
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
                # Serialize shapes/colors from form so they survive the deferred save
                pending_shapes = {}
                if shape_ids and shape_values:
                    for sid, sval in zip(shape_ids, shape_values):
                        if sval:
                            pending_shapes[sid["index"]] = sval
                pending_colors = {}
                if color_ids and color_values:
                    for cid, cval in zip(color_ids, color_values):
                        if cval:
                            pending_colors[cid["index"]] = cval

                # Defer save — store pending data and open migration modal
                pending = {
                    'hp': new_hp,
                    'ts': new_ts,
                    'ted': new_ted,
                    'obs_path': obs_path,
                    'gdrive_path': gdrive_path or "",
                    'types': new_types,
                    'contexts': new_contexts,
                    'subcontexts': new_subcontexts,
                    'shapes': pending_shapes,
                    'colors': pending_colors,
                    'orphans': orphans,
                    'new_values': {
                        'type': new_types,
                        'context': new_contexts,
                        'subcontext': new_sub_flat,
                    }
                }
                return "Migration required — check the migration dialog.", pending, False, 0

            # No orphans — save immediately
            ConfigManager.set_hyperparams(new_hp)
            ConfigManager.set_time_settings(new_ts)
            ConfigManager.set_time_estimate_defaults(new_ted)
            ConfigManager.set_obsidian_vault(obs_path)
            ConfigManager.set_gdrive_path(gdrive_path or "")
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

            return "Settings saved.", dash.no_update, False, 0

        except Exception:
            logger.exception("Failed to save settings")
            return "Error saving settings.", dash.no_update, False, 0

    # --- Migration Modal ---
    @app.callback(
        Output('modal-migration', 'is_open'),
        Output('migration-modal-body', 'children'),
        Output('migration-mapping-store', 'data'),
        Input('pending-settings-store', 'data'),
        Input('btn-migration-apply', 'n_clicks'),
        Input('btn-migration-skip', 'n_clicks'),
        State({"type": "migration-dropdown", "index": dash.ALL}, "value"),
        State({"type": "migration-ctx-dropdown", "index": dash.ALL}, "value"),
        State({"type": "migration-sub-dropdown", "index": dash.ALL}, "value"),
        State('migration-mapping-store', 'data'),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True
    )
    def handle_migration(pending_data, apply_clicks, skip_clicks,
                         type_dropdown_values, ctx_dropdown_values, sub_dropdown_values,
                         mapping_data, pending_state):
        from layout import build_migration_content

        trigger_id = _get_trigger_id()

        if trigger_id == 'pending-settings-store' and pending_data:
            orphans = pending_data.get('orphans', {})
            new_values = pending_data.get('new_values', {})
            subcontexts_by_context = pending_data.get('subcontexts', {})

            # Create lightweight objects with .name for the UI builder
            orphans_for_ui = {}
            for field, val_map in orphans.items():
                orphans_for_ui[field] = {}
                for old_val, node_names in val_map.items():
                    orphans_for_ui[field][old_val] = [type('N', (), {'name': n})() for n in node_names]

            children, mapping = build_migration_content(orphans_for_ui, new_values, subcontexts_by_context)
            return True, children, mapping

        if trigger_id in ('btn-migration-apply', 'btn-migration-skip') and pending_state:
            # Save the pending settings
            try:
                ConfigManager.set_hyperparams(pending_state['hp'])
                if 'ts' in pending_state:
                    ConfigManager.set_time_settings(pending_state['ts'])
                if 'ted' in pending_state:
                    ConfigManager.set_time_estimate_defaults(pending_state['ted'])
                ConfigManager.set_obsidian_vault(pending_state['obs_path'])
                ConfigManager.set_gdrive_path(pending_state.get('gdrive_path', ''))
                new_types = pending_state.get('types', [])
                if new_types:
                    ConfigManager.set_node_types(new_types)
                    ConfigManager.sync_shapes_to_types(new_types)
                new_contexts = pending_state.get('contexts', [])
                if new_contexts:
                    ConfigManager.set_contexts(new_contexts)
                ConfigManager.set_subcontexts(pending_state.get('subcontexts', {}))

                # Save shapes and colors from the form (captured before deferral)
                pending_shapes = pending_state.get('shapes', {})
                if pending_shapes:
                    ConfigManager.set_node_shapes(pending_shapes)
                pending_colors = pending_state.get('colors', {})
                if pending_colors:
                    ConfigManager.set_node_colors(pending_colors)
            except Exception:
                logger.exception("Failed to save pending settings")

            # Apply migrations if user clicked Apply
            if trigger_id == 'btn-migration-apply' and mapping_data:
                new_subcontexts = pending_state.get('subcontexts', {})

                # Apply type-field migrations (migration-dropdown)
                type_entries = mapping_data.get('type', []) if isinstance(mapping_data, dict) else mapping_data
                for i, entry in enumerate(type_entries):
                    if i >= len(type_dropdown_values) or not type_dropdown_values[i]:
                        continue
                    manager.apply_node_migration(entry['node_name'], entry['field'],
                                                 type_dropdown_values[i], new_subcontexts)

                # Apply context/subcontext migrations (migration-ctx/sub-dropdown)
                ctx_sub_entries = mapping_data.get('ctx_sub', []) if isinstance(mapping_data, dict) else []
                for i, entry in enumerate(ctx_sub_entries):
                    node_name = entry['node_name']
                    if entry.get('has_ctx_orphan') and i < len(ctx_dropdown_values):
                        ctx_val = ctx_dropdown_values[i]
                        if ctx_val:
                            manager.apply_node_migration(node_name, 'context', ctx_val, new_subcontexts)
                    if entry.get('has_sub_orphan') and i < len(sub_dropdown_values):
                        sub_val = sub_dropdown_values[i]
                        if sub_val:
                            manager.apply_node_migration(node_name, 'subcontext', sub_val, new_subcontexts)

            return False, [], None

        return dash.no_update, dash.no_update, dash.no_update

    # --- Migration: dynamic subcontext filtering based on selected context ---
    @app.callback(
        Output({"type": "migration-sub-dropdown", "index": dash.ALL}, "options"),
        Output({"type": "migration-sub-dropdown", "index": dash.ALL}, "value"),
        Input({"type": "migration-ctx-dropdown", "index": dash.ALL}, "value"),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True
    )
    def update_migration_subcontext_options(ctx_values, pending_data):
        if not ctx_values:
            return dash.no_update, dash.no_update
        subcontexts_map = (pending_data or {}).get('subcontexts', {})
        new_options_list = []
        new_values_list = []
        for ctx_val in ctx_values:
            if ctx_val and ctx_val != '__clear__':
                subs = subcontexts_map.get(ctx_val, [])
            else:
                subs = [s for ss in subcontexts_map.values() for s in ss]
            options = [{"label": s, "value": s} for s in subs]
            options.append({"label": "Clear (set to none)", "value": "__clear__"})
            new_options_list.append(options)
            new_values_list.append(subs[0] if subs else "__clear__")
        return new_options_list, new_values_list

    # --- Settings: Auto-dismiss status message ---
    @app.callback(
        Output('settings-save-status', 'children', allow_duplicate=True),
        Output('settings-clear-interval', 'disabled', allow_duplicate=True),
        Input('settings-clear-interval', 'n_intervals'),
        prevent_initial_call=True,
    )
    def clear_settings_message(n):
        if n > 0:
            return "", True
        return dash.no_update, dash.no_update

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
        display_types = node_types.copy()
        for ft in ["Goal"]:
            if ft not in display_types:
                display_types.append(ft)

        shape_options = [
            {"label": s.title(), "value": s}
            for s in ["ellipse", "triangle", "rectangle", "star", "pentagon", "hexagon",
                       "diamond", "octagon", "round-rectangle", "vee"]
        ]
        shape_rows = []
        for t in display_types:
            shape_rows.append(dbc.Row([
                dbc.Col(dbc.Label(t, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Select(
                    id={"type": "setting-shape", "index": t},
                    options=shape_options,  # type: ignore[reportArgumentType]
                    value=DEFAULT_NODE_SHAPES.get(t, "ellipse"),
                ), width=8),
            ], className="mb-2"))
        return shape_rows

    # --- Settings: Restore Default Status Colors ---
    @app.callback(
        Output('setting-node-status-colors-container', 'children', allow_duplicate=True),
        Input('btn-restore-status-colors', 'n_clicks'),
        prevent_initial_call=True,
    )
    def restore_default_status_colors(n_clicks):
        if not n_clicks:
            return dash.no_update
        from config import DEFAULT_NODE_COLORS

        def _color_row(label, key):
            return dbc.Row([
                dbc.Col(dbc.Label(label, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Input(
                    id={"type": "setting-color", "index": key},
                    type="color",  # type: ignore[reportArgumentType]
                    value=DEFAULT_NODE_COLORS.get(key, "#6c757d"),
                    style={"height": "38px", "padding": "2px"},
                ), width=4),
                dbc.Col(html.Small(
                    DEFAULT_NODE_COLORS.get(key, "#6c757d"),
                    className="text-muted d-flex align-items-center",
                    style={"fontSize": "0.8rem"},
                ), width=4),
            ], className="mb-2")

        return [
            _color_row("Open", "Open"),
            _color_row("Blocked", "Blocked"),
            _color_row("Done", "Done"),
        ]

    # --- Settings: Restore Default Type Colors ---
    @app.callback(
        Output('setting-node-type-colors-container', 'children', allow_duplicate=True),
        Input('btn-restore-type-colors', 'n_clicks'),
        prevent_initial_call=True,
    )
    def restore_default_type_colors(n_clicks):
        if not n_clicks:
            return dash.no_update
        from config import DEFAULT_NODE_COLORS

        def _color_row(label, key):
            return dbc.Row([
                dbc.Col(dbc.Label(label, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Input(
                    id={"type": "setting-color", "index": key},
                    type="color",  # type: ignore[reportArgumentType]
                    value=DEFAULT_NODE_COLORS.get(key, "#6c757d"),
                    style={"height": "38px", "padding": "2px"},
                ), width=4),
                dbc.Col(html.Small(
                    DEFAULT_NODE_COLORS.get(key, "#6c757d"),
                    className="text-muted d-flex align-items-center",
                    style={"fontSize": "0.8rem"},
                ), width=4),
            ], className="mb-2")

        return [
            _color_row("Goal", "Goal"),
            _color_row("Resource", "Resource"),
        ]