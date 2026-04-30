"""
Callback definitions for the Skill Tree Dash application.
"""

import json
import logging
import os
import subprocess
import urllib.parse

from typing import List, Set

import dash
from dash import html, Input, Output, State, ALL, ctx, no_update, ClientsideFunction
import dash_bootstrap_components as dbc

from graph_manager import GraphManager
from event_manager import EventManager
from config import (ConfigManager, badge_style, sort_subcontexts)
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from next_callbacks import get_suggestions, get_override_set
from callback_helpers import (
    parse_links, serialize_links, get_trigger_id, get_all_triggered_ids,
    node_options, build_filters, is_filters_active,
    handle_save, handle_delete, handle_toggle_done, handle_group_delete,
    format_suggestions_table, format_traversal_ui,
    render_link_rows, spawn_local_file_picker,
    strip_gdrive_prefix, expand_gdrive_prefix,
    should_open_editor, resolve_active_node_id,
    normalize_name_for_comparison,
    build_editor_snapshot, is_form_dirty_vs_snapshot, NEW_NODE_SNAPSHOT,
    snapshot_from_form_state,
    habit_to_hours, compute_habit_time_omp, resolve_time_mode,
)

logger = logging.getLogger(__name__)

manager = GraphManager()
event_manager = EventManager()


# core_engine has 24 outputs; this constant + helper let the tab-gating guard
# return a no_update tuple of the correct arity. test_core_engine_arity verifies
# that it stays in sync with the actual callback registration.
_CORE_ENGINE_NUM_OUTPUTS = 24

# Tabs whose own callbacks already refresh their content; switching to them
# should NOT trigger a graph regen via core_engine.
_NON_GRAPH_TABS = frozenset({"tab-settings", "tab-events", "tab-analyze"})

# Triggers that only open/close the editor sidebar without touching graph data,
# filters, or focus. When core_engine fires on one of these (and nothing else
# in the same cycle), we can skip the expensive scoring + element regen and
# just compute the three sidebar styles. Saves ~100-300 ms per Edit click.
_EDITOR_UI_ONLY_TRIGGERS = frozenset({
    'edit-trigger-input', 'details-edit-trigger-input',
    'btn-close-editor', 'btn-goals-toggle',
})

# Output slot indices within the core_engine output tuple. Kept here so the
# editor-only short-circuit can build its partial tuple without repeating
# magic numbers. Must stay in sync with the Output list at the callback
# decoration site.
_SIDEBAR_EDITOR_STYLE_IDX = 11
_DETAILS_GOAL_SIDEBAR_STYLE_IDX = 19
_EVENTS_SIDEBAR_STYLE_IDX = 20


def _core_engine_noop_tuple():
    """Return a tuple of dash.no_update matching core_engine's output arity."""
    return (dash.no_update,) * _CORE_ENGINE_NUM_OUTPUTS


def _core_engine_editor_only_tuple(next_ed_style, next_goal_style, next_events_style):
    """Return a tuple populated only at the three sidebar-style slots.

    Used by the editor-UI-only short-circuit in core_engine.
    """
    out = [dash.no_update] * _CORE_ENGINE_NUM_OUTPUTS
    out[_SIDEBAR_EDITOR_STYLE_IDX] = next_ed_style
    out[_DETAILS_GOAL_SIDEBAR_STYLE_IDX] = next_goal_style
    out[_EVENTS_SIDEBAR_STYLE_IDX] = next_events_style
    return tuple(out)


# Output slot indices for the new undo-Done modal outputs (added in Group 3).
_UNDO_DONE_MODAL_IDX = 21
_UNDO_DONE_BODY_IDX = 22
_PENDING_UNDO_DONE_IDX = 23


def _build_undo_done_body(target_names, downstream_done):
    """Construct the modal body warning the user about Done dependents that
    will flip Blocked when the listed targets are un-marked."""
    target_label = (
        f"'{target_names[0]}'" if len(target_names) == 1
        else f"{len(target_names)} selected nodes"
    )
    items = [html.Li(name) for name in downstream_done[:25]]
    overflow = (
        html.Div(f"...and {len(downstream_done) - 25} more.",
                 className="text-muted small mt-1")
        if len(downstream_done) > 25 else None
    )
    children = [
        html.P([
            "Un-marking ", html.Strong(target_label), " will flip "
            f"{len(downstream_done)} downstream Done node(s) to Blocked, "
            "because their hard prerequisite is no longer complete:"
        ]),
        html.Ul(items, className="mb-0"),
    ]
    if overflow is not None:
        children.append(overflow)
    return children


def _core_engine_save_error_tuple(msg, next_ed_style, next_goal_style, next_events_style):
    """Return a tuple matching core_engine's output arity, populated only with
    the save-error message + sidebar styles.

    Used when the save flow detects a validation error (missing name / type)
    and wants to surface the error without touching graph state, filters,
    or the modal-confirmation flow.
    """
    out = [dash.no_update] * _CORE_ENGINE_NUM_OUTPUTS
    out[1] = msg                  # save-output.children
    out[7] = False                # clear-interval.disabled
    out[8] = 0                    # clear-interval.n_intervals
    out[_SIDEBAR_EDITOR_STYLE_IDX] = next_ed_style
    out[_DETAILS_GOAL_SIDEBAR_STYLE_IDX] = next_goal_style
    out[_EVENTS_SIDEBAR_STYLE_IDX] = next_events_style
    return tuple(out)


_DEFAULT_EDITOR_SIDEBAR_STYLE = {
    "position": "absolute", "top": "0", "left": "0", "width": "380px",
    "minWidth": "380px", "height": "100%", "zIndex": 1000,
    "overflowX": "hidden", "overflowY": "auto",
    "borderRight": "1px solid #495057", "transition": "transform 0.3s ease",
    "transform": "translateX(-380px)", "willChange": "transform",
    "backgroundColor": "#212529",
}


def _compute_sidebar_styles(trigger_id, all_triggered_ids, search_val,
                             ed_style, goal_sidebar_style, events_sidebar_style,
                             pending_nav_store,
                             form_state):
    """Determine next sidebar styles based on the triggering Input.

    Returns (next_ed_style, next_goal_style, next_events_sidebar_style). The
    editor-sidebar logic and the goal/events sidebar mutex both live here so
    the short-circuit path and the full core_engine path share one
    implementation.

    `form_state` is a dict carrying the editor-form state used only when
    trigger_id == 'btn-close-editor' (the unsaved-changes check). For triggers
    that don't need it, pass an empty dict.
    """
    next_ed_style = ed_style or dict(_DEFAULT_EDITOR_SIDEBAR_STYLE)
    if trigger_id == 'btn-add':
        next_ed_style['transform'] = "translateX(0px)"
    elif trigger_id == 'btn-new-node':
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
    elif trigger_id in ('btn-save-close', 'btn-node-delete-confirm', 'btn-close-editor', 'btn-unsaved-discard', 'btn-unsaved-save'):
        # btn-save-close and unsaved-save close it after saving.
        # btn-unsaved-discard closes without saving.
        # btn-close-editor only silently closes if the form is blank (otherwise modal handles it).
        if trigger_id in ('btn-unsaved-save', 'btn-unsaved-discard') and pending_nav_store == '__background__':
            # User dismissed via canvas click — close the editor after save/discard.
            next_ed_style['transform'] = "translateX(-380px)"
        elif trigger_id in ('btn-unsaved-save', 'btn-unsaved-discard') and pending_nav_store:
            pass  # Keep editor open — pending navigation will load the next node
        elif trigger_id in ('btn-save-close', 'btn-unsaved-save') and (not form_state.get('name') or not form_state.get('n_type')):
            pass  # Keep sidebar open — validation error shown below
        elif trigger_id == 'btn-close-editor':
            form_has_content = is_form_dirty_vs_snapshot(form_state.get('pristine_snapshot'), {
                'name': form_state.get('name'), 'n_type': form_state.get('n_type'),
                'desc': form_state.get('desc'),
                'context': form_state.get('context'), 'subctx': form_state.get('subctx'),
                'status_done': form_state.get('status_done'),
                'val': form_state.get('val'), 'interest': form_state.get('interest'),
                'diff': form_state.get('diff'),
                'time_o': form_state.get('time_o'), 'time_m': form_state.get('time_m'),
                'time_p': form_state.get('time_p'), 'time_unit': form_state.get('time_unit'),
                'e_needs_h': form_state.get('e_needs_h'), 'e_needs_s': form_state.get('e_needs_s'),
                'e_supp_h': form_state.get('e_supp_h'), 'e_supp_s': form_state.get('e_supp_s'),
                'e_helps': form_state.get('e_helps'),
                'obs_links': form_state.get('obs_link_values'),
                'drive_links': form_state.get('drive_link_values'),
                'website_links': form_state.get('website_link_values'),
                'time_mode': form_state.get('time_mode_val'),
                'time_habit_mode': form_state.get('time_habit_mode_val'),
                'habit_duration': form_state.get('habit_duration'),
                'habit_duration_unit': form_state.get('habit_duration_unit'),
                'habit_intensity_o': form_state.get('habit_int_o'),
                'habit_intensity_m': form_state.get('habit_int_m'),
                'habit_intensity_p': form_state.get('habit_int_p'),
                'habit_intensity_unit': form_state.get('habit_int_unit'),
                'value_mode': form_state.get('value_mode_val'),
                'priority_rank': form_state.get('priority_rank_val'),
                'competence': form_state.get('competence_val'),
                'aliases': form_state.get('alias_values'),
            })
            if not form_has_content:
                next_ed_style['transform'] = "translateX(-380px)"
        else:
            next_ed_style['transform'] = "translateX(-380px)"
    else:
        # Race-prevention guard: if the trigger has nothing to do with the
        # editor (tab switches, refresh triggers, filter changes, etc.),
        # don't echo ed_style back to the DOM. Otherwise, a late response
        # from a slow non-editor trigger can clobber an in-flight
        # edit-trigger response that had opened the sidebar — causing the
        # intermittent "Edit menu clicked but editor doesn't open" symptom
        # (especially right after tab switching to Nodes tab).
        next_ed_style = dash.no_update

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
    return next_ed_style, next_goal_style, next_events_sidebar_style


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
    depth_by_name = {}

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
        # BFS — retain per-node depth so the neighbor_links filter can use it
        visited = {active_node_id}
        depth_by_name = {active_node_id: 0}
        frontier = {active_node_id}
        for d in range(max_depth):
            next_frontier = set()
            for n in frontier:
                for nb in adj.get(n, set()):
                    if nb not in visited:
                        visited.add(nb)
                        depth_by_name[nb] = d + 1
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
    trigger_names = event_manager.get_trigger_node_names()

    elements = []
    for node in filtered_nodes:
        if node.name in override_set:
            node_color = override_color
        elif node.status == STATUS_DONE:
            node_color = colors.get(STATUS_DONE, '#198754')
        elif node.status == STATUS_BLOCKED:
            node_color = colors.get(STATUS_BLOCKED, '#dc3545')
        else:
            node_color = colors.get(node.type, colors.get(STATUS_OPEN, '#0d6efd'))

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
        if node.name in trigger_names:
            node_data['classes'] = 'trigger'
        elements.append(node_data)

    for e in edges:
        if e['source'] in valid_names and e['target'] in valid_names:
            # Neighbor links filter: when off, hide peer edges between same-BFS-depth
            # nodes so the local subtree stays legible (Obsidian local-graph style).
            # When no BFS ran (max_depth == 0), fall back to "edges touching active node".
            if not neighbor_links and active_node_id:
                if depth_by_name:
                    if depth_by_name.get(e['source']) == depth_by_name.get(e['target']):
                        continue
                else:
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

    # --- Graph Version Bridge ---
    # Observes cytoscape element changes and updates graph-version-store only
    # when GraphManager's internal version actually advanced (i.e. a real
    # node/edge mutation happened). Cosmetic changes (filter, depth, highlight)
    # regenerate elements without bumping the version, so downstream callbacks
    # subscribed to graph-version-store skip unnecessary recomputation.
    @app.callback(
        Output('graph-version-store', 'data'),
        Input('cytoscape-graph', 'elements'),
        State('graph-version-store', 'data'),
        prevent_initial_call=True,
    )
    def sync_graph_version(_elements, current):
        if manager._graph_version != current:
            return manager._graph_version
        return dash.no_update

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
        Output('filter-done', 'value', allow_duplicate=True),
        Input('btn-clear-filters', 'n_clicks'),
        Input('btn-details-focus', 'n_clicks'),
        prevent_initial_call=True,
    )
    def clear_filters(_clear_clicks, _focus_clicks):
        return [], [], [], [], 'components', 'All', 1, 1, 10, None, ['hide_done']

    # --- Tooltip Formatting ---
    @app.callback(
        Output('hover-tooltip', 'children'),
        Input('cytoscape-graph', 'mouseoverNodeData'),
        Input('details-mini-graph', 'mouseoverNodeData'),
        Input('events-detail-graph', 'mouseoverNodeData'),
    )
    def display_hover_data(data, details_data, events_data):
        trigger = get_trigger_id()
        if trigger == 'details-mini-graph':
            data = details_data
        elif trigger == 'events-detail-graph':
            data = events_data
        if not data: return ""

        node_type = data.get('type', '')
        node_id = data.get('id', data.get('label', ''))

        header = html.Div(
            html.Strong(data.get('label', node_id)),
            style={"fontSize": "0.95rem", "marginBottom": "4px",
                   "borderBottom": "1px solid #495057", "paddingBottom": "4px"}
        )

        if node_type in ('Goal', 'Milestone'):
            completion = manager.get_goal_completion(node_id, include_soft=False)
            total = completion.get('total', 0)
            done = completion.get('done', 0)
            pct = completion.get('pct', 0)
            remaining = completion.get('remaining_time', 0)

            lines = [header]

            if total > 0:
                bar_color = "#198754" if pct == 100 else "#0d6efd"
                lines += [
                    html.Hr(style={"margin": "6px 0", "borderColor": "#495057"}),
                    html.Div([html.Strong("Progress: "), f"{done}/{total} hard subtasks ({pct}%)"]),
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
            ratings_inherited = data.get('value_mode') == 'inherited'
            time_inherited = data.get('time_mode') == 'inherited'

            lines = [header]

            if ratings_inherited and time_inherited:
                lines.append(html.Div("Container", style={"color": "#adb5bd"}))
            else:
                if ratings_inherited:
                    lines.append(html.Div([html.Strong("Ratings: "), "inherited"]))
                else:
                    lines += [
                        html.Div([html.Strong("Value: "), str(data.get('value', ''))]),
                        html.Div([html.Strong("Interest: "), str(data.get('interest', ''))]),
                        html.Div([html.Strong("Effort: "), str(data.get('difficulty', ''))]),
                    ]

                if time_inherited:
                    lines.append(html.Div([html.Strong("Time: "), "inherited"]))
                else:
                    time_str = ConfigManager.format_time_friendly(data.get('time', 0))
                    lines.append(html.Div([html.Strong("Time: "), time_str]))

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
        [Output('node-name', 'value', allow_duplicate=True), Output('node-type', 'value'), Output('node-desc', 'value'),
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
         Output('node-time-unit', 'value'),
         Output('node-time-unit-prev', 'data', allow_duplicate=True),
         Output('node-original-name', 'data', allow_duplicate=True),
         Output('search-node', 'value', allow_duplicate=True),
         Output('node-priority-rank', 'value'),
         Output('node-time-mode', 'value'),
         Output('node-competence', 'value'),
         Output('aliases-store', 'data'),
         Output('pending-navigation-store', 'data'),
         Output('modal-unsaved-changes', 'is_open', allow_duplicate=True),
         Output('editor-pristine-snapshot', 'data', allow_duplicate=True),
         Output('node-value-mode', 'value'),
         Output('node-time-habit-mode', 'value'),
         Output('node-habit-duration', 'value'),
         Output('node-habit-duration-unit', 'value'),
         Output('node-habit-intensity-o', 'value'),
         Output('node-habit-intensity-m', 'value'),
         Output('node-habit-intensity-p', 'value'),
         Output('node-habit-intensity-unit', 'value')],
        [Input('cytoscape-graph', 'tapNodeData'),
         Input('btn-add', 'n_clicks'),
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
         State('node-name', 'value'), State('node-type', 'value'), State('node-desc', 'value'),
         State('node-context', 'value'), State('node-subcontext', 'value'),
         State('node-status-done', 'value'),
         State('node-value', 'value'), State('node-interest', 'value'),
         State('node-difficulty', 'value'),
         State('node-time-o', 'value'), State('node-time-m', 'value'),
         State('node-time-p', 'value'), State('node-time-unit', 'value'),
         State('edge-needs-hard', 'value'), State('edge-needs-soft', 'value'),
         State('edge-supports-hard', 'value'), State('edge-supports-soft', 'value'),
         State('edge-helps', 'value'),
         State({'type': 'obsidian-link', 'index': ALL}, 'value'),
         State({'type': 'drive-link', 'index': ALL}, 'value'),
         State({'type': 'website-link', 'index': ALL}, 'value'),
         State('node-time-mode', 'value'),
         State('node-priority-rank', 'value'), State('node-competence', 'value'),
         State({'type': 'alias-input', 'index': ALL}, 'value'),
         State('pending-navigation-store', 'data'),
         State('editor-pristine-snapshot', 'data'),
         State('node-value-mode', 'value'),
         State('node-time-habit-mode', 'value'),
         State('node-habit-duration', 'value'),
         State('node-habit-duration-unit', 'value'),
         State('node-habit-intensity-o', 'value'),
         State('node-habit-intensity-m', 'value'),
         State('node-habit-intensity-p', 'value'),
         State('node-habit-intensity-unit', 'value')],
        prevent_initial_call='initial_duplicate'
    )
    def populate_editor(data, add_clicks, discard_clicks, unsaved_save_clicks, search_val, _bg_click, new_node_clicks, edit_trigger_val,
                        details_edit_trigger_val,
                        elements, ed_style, original_name,
                        cur_name, cur_type, cur_desc, cur_context, cur_subctx, cur_status_done,
                        cur_val, cur_interest, cur_diff,
                        cur_time_o, cur_time_m, cur_time_p, cur_time_unit,
                        cur_needs_h, cur_needs_s, cur_supp_h, cur_supp_s, cur_helps,
                        cur_obs, cur_drive, cur_website,
                        cur_time_mode, cur_priority_rank, cur_competence,
                        cur_aliases,
                        pending_nav, pristine_snapshot,
                        cur_value_mode,
                        cur_time_habit_mode,
                        cur_habit_duration, cur_habit_duration_unit,
                        cur_habit_int_o, cur_habit_int_m, cur_habit_int_p,
                        cur_habit_int_unit):
        """Populate the editor sidebar form fields when a node is selected, searched, or cleared."""
        trigger_id = get_trigger_id()

        all_nodes = manager.get_all_nodes()
        options = node_options(all_nodes)

        def_out = [
            "", "Learn", "", "", "", 5, 5, 5, 2, 4, 6, STATUS_OPEN, [],
            [], [], [], [], [],
            options, options, options, options, options,
            [''], [''], [''],
            # Type-specific defaults
            "weeks", "weeks",
            None,  # node-original-name
            dash.no_update,  # search-node — don't change; avoids retriggering core_engine
            "none",  # node-priority-rank
            [],  # node-time-mode
            "",  # node-competence
            [''],  # aliases-store
            None,  # pending-navigation-store
            False,  # modal-unsaved-changes
            NEW_NODE_SNAPSHOT,  # editor-pristine-snapshot
            [],  # node-value-mode (appended to keep existing indices stable)
            # Habit-mode defaults (appended after value-mode)
            [],  # node-time-habit-mode
            0,   # node-habit-duration
            'weeks',  # node-habit-duration-unit
            0, 0, 0,  # node-habit-intensity o/m/p
            'min_per_day',  # node-habit-intensity-unit
        ]

        def _has_unsaved_changes():
            return is_form_dirty_vs_snapshot(pristine_snapshot, {
                'name': cur_name, 'n_type': cur_type, 'desc': cur_desc,
                'context': cur_context, 'subctx': cur_subctx,
                'status_done': cur_status_done,
                'val': cur_val, 'interest': cur_interest, 'diff': cur_diff,
                'time_o': cur_time_o, 'time_m': cur_time_m, 'time_p': cur_time_p,
                'time_unit': cur_time_unit,
                'e_needs_h': cur_needs_h, 'e_needs_s': cur_needs_s,
                'e_supp_h': cur_supp_h, 'e_supp_s': cur_supp_s, 'e_helps': cur_helps,
                'obs_links': cur_obs, 'drive_links': cur_drive,
                'website_links': cur_website,
                'time_mode': cur_time_mode,
                'time_habit_mode': cur_time_habit_mode,
                'habit_duration': cur_habit_duration,
                'habit_duration_unit': cur_habit_duration_unit,
                'habit_intensity_o': cur_habit_int_o,
                'habit_intensity_m': cur_habit_int_m,
                'habit_intensity_p': cur_habit_int_p,
                'habit_intensity_unit': cur_habit_int_unit,
                'value_mode': cur_value_mode,
                'priority_rank': cur_priority_rank, 'competence': cur_competence,
                'aliases': cur_aliases,
            })

        if trigger_id == 'btn-new-node':
            editor_open = ed_style and ed_style.get('transform', '') == 'translateX(0px)'
            if editor_open and _has_unsaved_changes():
                # Show unsaved modal; store 'new-node' as pending action
                no_change = [dash.no_update] * 18 + [options]*5 + [dash.no_update]*22
                no_change[34] = '__new_node__'  # pending-navigation-store (special sentinel)
                no_change[35] = True            # modal-unsaved-changes
                return no_change
            # No unsaved changes — clear and reset (don't clear search-node;
            # that would re-trigger core_engine and overwrite the editor-open state)
            return def_out

        if trigger_id in ['btn-add', 'background-click-input']:
            # Intercept background click when the editor is open with unsaved
            # changes — show the save/discard modal instead of silently clobbering.
            if trigger_id == 'background-click-input':
                editor_open = ed_style and ed_style.get('transform', '') == 'translateX(0px)'
                if editor_open and _has_unsaved_changes():
                    no_change = [dash.no_update] * 18 + [options]*5 + [dash.no_update]*22
                    no_change[34] = '__background__'  # pending-navigation-store sentinel
                    no_change[35] = True              # modal-unsaved-changes
                    return no_change
            # Clear search bar on reset triggers — but NOT for btn-add, because
            # setting search-node to None re-triggers core_engine via the callback
            # chain, and the second invocation reads stale editor state and
            # overwrites the first invocation's "open editor" output.
            if trigger_id != 'btn-add':
                def_out[29] = None  # search-node value position
            return def_out

        # Handle unsaved-discard / unsaved-save with pending navigation
        if trigger_id in ('btn-unsaved-discard', 'btn-unsaved-save'):
            if pending_nav:
                if pending_nav in ('__new_node__', '__background__'):
                    # Discard/save done — reset form. __new_node__ leaves the editor
                    # open on a blank form; __background__ closes it (core_engine).
                    def_out[29] = None  # clear search bar
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
                # 18 form fields + 5 edge options + 13 remaining = 36 total outputs
                no_change = [dash.no_update] * 18 + [options]*5 + [dash.no_update]*22
                no_change[34] = tapped_id  # pending-navigation-store (index 34)
                no_change[35] = True       # modal-unsaved-changes (index 35)
                return no_change

        name = None
        if trigger_id in ('edit-trigger-input', 'details-edit-trigger-input'):
            # Context menu / dormant-node Edit: node ID carried in the trigger value
            edit_val = edit_trigger_val if trigger_id == 'edit-trigger-input' else details_edit_trigger_val
            if edit_val:
                edit_node_name = edit_val.split('|')[0]
                node = manager.get_node(edit_node_name)
                if node and node.dormant:
                    # Dormant nodes have their own editor (Events-tab dormant modal).
                    # Defense-in-depth: if any code path forwards a dormant name here,
                    # don't load it into the generic sidebar.
                    return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*22
                if node:
                    name = node.name
                    data = node.to_dict()
                    data['id'] = name
                else:
                    return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*22
        elif trigger_id == 'search-node':
            if not search_val:
                # User cleared the search bar — reset form to defaults
                return def_out
            # Resolve alias: prefix to actual node name
            resolved_name = search_val
            if search_val.startswith('alias:'):
                alias_key = search_val[6:]
                # Case-insensitive resolve so the user's typed casing
                # doesn't have to match the stored titlecase form.
                resolved = manager.resolve_alias(alias_key)
                resolved_name = resolved if resolved is not None else search_val
            node = manager.get_node(resolved_name)
            if node and node.dormant:
                return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*22
            if node:
                name = node.name
                data = node.to_dict()
                data['id'] = name
            else:
                return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*22
        elif data:
            name = data.get('id')
            # Always read fresh data from DB on tap (Cytoscape data may be stale)
            if name:
                db_node = manager.get_node(name)
                if db_node:
                    data = db_node.to_dict()
                    data['id'] = name

        if not name or not data:
            return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*22

        edges = manager.get_edges()

        # The edge dropdowns get their options from `all_nodes`, which excludes
        # dormant nodes. dcc.Dropdown filters its initial value to entries in
        # `options`, but on subsequent value updates (e.g. re-opening the same
        # node without a full remount) it does NOT re-filter — so the State
        # would carry dormant items the user can't actually see. Filter the
        # value-side here too so the form's State is consistent across opens
        # and matches build_editor_snapshot's filtered view.
        non_dormant_names = {n.name for n in all_nodes}

        # In/Out Edges mapping
        needs_hard_vals = [e['source'] for e in edges
                           if e['target'] == name and e['type'] == EDGE_NEEDS_HARD
                           and e['source'] in non_dormant_names]
        needs_soft_vals = [e['source'] for e in edges
                           if e['target'] == name and e['type'] == EDGE_NEEDS_SOFT
                           and e['source'] in non_dormant_names]
        supp_hard_vals = [e['target'] for e in edges
                          if e['source'] == name and e['type'] == EDGE_NEEDS_HARD
                          and e['target'] in non_dormant_names]
        supp_soft_vals = [e['target'] for e in edges
                          if e['source'] == name and e['type'] == EDGE_NEEDS_SOFT
                          and e['target'] in non_dormant_names]

        helps_vals = [e['target'] for e in edges
                      if e['source'] == name and e['type'] == EDGE_HELPS
                      and e['target'] in non_dormant_names]
        helps_vals += [e['source'] for e in edges
                       if e['target'] == name and e['type'] == EDGE_HELPS
                       and e['source'] in non_dormant_names]
        helps_vals = list(set(helps_vals))
        filtered_options = node_options(all_nodes, exclude=name)

        actual_status = data.get('status', STATUS_OPEN)
        done_val = [STATUS_DONE] if actual_status == STATUS_DONE else []

        friendly_o, friendly_m, friendly_p, friendly_unit = _friendly_time_estimates(
            data.get('time_o', 1.0), data.get('time_m', 1.0), data.get('time_p', 1.0)
        )

        # Priority rank for Goal nodes
        priority_goals = ConfigManager.get_priority_goals()
        if data.get('type') == 'Goal' and name in priority_goals:
            rank_value = str(priority_goals.index(name) + 1)
        else:
            rank_value = "none"

        # Time mode — Inherit, Habit, or Manual (mutually exclusive in the UI)
        time_mode_val = ["inherited"] if data.get('time_mode') == 'inherited' else []
        time_habit_mode_val = ["habit"] if data.get('time_mode') == 'habit' else []
        # Value mode (mirrors time_mode)
        value_mode_val = ["inherited"] if data.get('value_mode') == 'inherited' else []

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
            friendly_unit, friendly_unit,
            name,  # node-original-name — track what was loaded
            name if (trigger_id in ('edit-trigger-input', 'details-edit-trigger-input') or (ed_style and ed_style.get('transform', '') == 'translateX(0px)')) else dash.no_update,  # search-node — update when editor is open or edit-trigger
            rank_value,  # node-priority-rank
            time_mode_val,  # node-time-mode
            data.get('competence') or '',  # node-competence
            manager.get_aliases(name) or [''],  # aliases-store
            None,  # pending-navigation-store — clear on successful populate
            False,  # modal-unsaved-changes — close on successful populate
            build_editor_snapshot(manager, name),  # editor-pristine-snapshot
            value_mode_val,  # node-value-mode (appended)
            # Habit-mode fields
            time_habit_mode_val,
            data.get('habit_duration', 0) or 0,
            data.get('habit_duration_unit') or 'weeks',
            data.get('habit_intensity_o', 0) or 0,
            data.get('habit_intensity_m', 0) or 0,
            data.get('habit_intensity_p', 0) or 0,
            data.get('habit_intensity_unit') or 'min_per_day',
        ]

    # --- Post-save sync of original_name / name ---
    # After a Save (no close), the form still holds whatever the user typed but
    # the DB now holds the *linted* / renamed version. Without this sync,
    # has_editor_unsaved_changes would see "original_name" still pointing at
    # the pre-save identity (or None for a brand-new node) and flag the form as
    # dirty — producing spurious unsaved-changes modals on the next background
    # click. Re-reading the DB by the form's current name confirms the save
    # succeeded before touching state.
    @app.callback(
        [Output('node-original-name', 'data', allow_duplicate=True),
         Output('node-name', 'value', allow_duplicate=True),
         Output('aliases-store', 'data', allow_duplicate=True),
         Output('editor-pristine-snapshot', 'data', allow_duplicate=True)],
        [Input('btn-save', 'n_clicks'),
         Input('btn-save-close', 'n_clicks')],
        [State('node-name', 'value'),
         State('node-type', 'value'),
         State('node-desc', 'value'),
         State('node-context', 'value'), State('node-subcontext', 'value'),
         State('node-status-done', 'value'),
         State('node-value', 'value'), State('node-interest', 'value'),
         State('node-difficulty', 'value'),
         State('node-time-o', 'value'), State('node-time-m', 'value'),
         State('node-time-p', 'value'), State('node-time-unit', 'value'),
         State('edge-needs-hard', 'value'), State('edge-needs-soft', 'value'),
         State('edge-supports-hard', 'value'), State('edge-supports-soft', 'value'),
         State('edge-helps', 'value'),
         State({'type': 'obsidian-link', 'index': ALL}, 'value'),
         State({'type': 'drive-link', 'index': ALL}, 'value'),
         State({'type': 'website-link', 'index': ALL}, 'value'),
         State('node-time-mode', 'value'),
         State('node-priority-rank', 'value'),
         State('node-competence', 'value'),
         State('node-value-mode', 'value'),
         State('node-time-habit-mode', 'value'),
         State('node-habit-duration', 'value'),
         State('node-habit-duration-unit', 'value'),
         State('node-habit-intensity-o', 'value'),
         State('node-habit-intensity-m', 'value'),
         State('node-habit-intensity-p', 'value'),
         State('node-habit-intensity-unit', 'value')],
        prevent_initial_call=True,
    )
    def sync_original_name_after_save(_save_clicks, _save_close_clicks,
                                      cur_name, cur_type, cur_desc,
                                      cur_context, cur_subctx, cur_status_done,
                                      cur_val, cur_interest, cur_diff,
                                      cur_time_o, cur_time_m, cur_time_p, cur_time_unit,
                                      cur_needs_h, cur_needs_s, cur_supp_h, cur_supp_s, cur_helps,
                                      cur_obs, cur_drive, cur_website,
                                      cur_time_mode, cur_priority_rank, cur_competence,
                                      cur_value_mode,
                                      cur_time_habit_mode,
                                      cur_habit_duration, cur_habit_duration_unit,
                                      cur_habit_int_o, cur_habit_int_m, cur_habit_int_p,
                                      cur_habit_int_unit):
        if not cur_name or not cur_name.strip():
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        linted = ConfigManager.apply_titlecase_linter(cur_name.strip())
        if not manager.get_node(linted):
            # Save failed to persist — leave state alone rather than stomping
            # a stale snapshot on top of a non-existent node.
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        # Build the post-save snapshot directly from what the form holds, not
        # from a DB round-trip. A DB-derived snapshot (via build_editor_snapshot)
        # re-applies display transforms — most notably _friendly_time_estimates,
        # which picks its unit from max DB-hours and can diverge from the unit
        # the user had selected. Snapshotting the form State guarantees the
        # immediate post-save dirty check sees the form as clean, since the
        # snapshot mirrors the form byte-for-byte (with only name and aliases
        # overridden by their linted versions — the two values the save
        # pipeline legitimately rewrites in the form).
        linted_aliases = manager.get_aliases(linted) or ['']
        form_values = {
            'n_type': cur_type, 'desc': cur_desc,
            'context': cur_context, 'subctx': cur_subctx,
            'status_done': cur_status_done,
            'val': cur_val, 'interest': cur_interest, 'diff': cur_diff,
            'time_o': cur_time_o, 'time_m': cur_time_m, 'time_p': cur_time_p,
            'time_unit': cur_time_unit,
            'e_needs_h': cur_needs_h, 'e_needs_s': cur_needs_s,
            'e_supp_h': cur_supp_h, 'e_supp_s': cur_supp_s, 'e_helps': cur_helps,
            'obs_links': cur_obs, 'drive_links': cur_drive, 'website_links': cur_website,
            'time_mode': cur_time_mode,
            'time_habit_mode': cur_time_habit_mode,
            'habit_duration': cur_habit_duration,
            'habit_duration_unit': cur_habit_duration_unit,
            'habit_intensity_o': cur_habit_int_o,
            'habit_intensity_m': cur_habit_int_m,
            'habit_intensity_p': cur_habit_int_p,
            'habit_intensity_unit': cur_habit_int_unit,
            'value_mode': cur_value_mode,
            'priority_rank': cur_priority_rank, 'competence': cur_competence,
        }
        snapshot = snapshot_from_form_state(form_values, linted, linted_aliases)
        return linted, linted, linted_aliases, snapshot

    # --- Type-adaptive field visibility ---
    @app.callback(
        [Output('section-done-time', 'style'),
         Output('section-time-estimates', 'style'),
         Output('section-priority-rank', 'style'),
         Output('section-time-habit-toggle', 'style')],
        Input('node-type', 'value')
    )
    def toggle_type_fields(node_type):
        show = {}
        hide = {'display': 'none'}
        if node_type == 'Goal':
            # Priority rank visible; habit toggle hidden (containers must inherit).
            return show, show, show, hide
        if node_type == 'Milestone':
            # No priority rank (top-level-Goal mechanic only);
            # habit toggle hidden (containers must inherit).
            return show, show, hide, hide
        # Learn, Action, Resource: full set, habit toggle visible.
        return show, show, hide, show

    # --- Toggle O/M/P / Habit / unit-dropdown visibility based on mode ---
    @app.callback(
        Output('section-time-omp', 'style'),
        Output('section-time-habit', 'style'),
        Output('node-time-unit', 'style'),
        Input('node-time-mode', 'value'),
        Input('node-time-habit-mode', 'value'),
    )
    def toggle_time_section_visibility(time_mode_val, habit_mode_val):
        inherit_on = bool(time_mode_val and 'inherited' in time_mode_val)
        habit_on = bool(habit_mode_val and 'habit' in habit_mode_val)
        if inherit_on:
            return {'display': 'none'}, {'display': 'none'}, {'display': 'none', 'width': '100px'}
        if habit_on:
            return {'display': 'none'}, {}, {'display': 'none', 'width': '100px'}
        return {}, {'display': 'none'}, {'width': '100px'}

    # --- Mutual exclusivity: Habit and Inherit cannot both be ON ---
    @app.callback(
        Output('node-time-mode', 'value', allow_duplicate=True),
        Output('node-time-habit-mode', 'value', allow_duplicate=True),
        Input('node-time-mode', 'value'),
        Input('node-time-habit-mode', 'value'),
        prevent_initial_call=True,
    )
    def enforce_time_mode_exclusivity(inherit_val, habit_val):
        trig = get_trigger_id()
        if trig == 'node-time-mode' and inherit_val and 'inherited' in inherit_val:
            return inherit_val, []
        if trig == 'node-time-habit-mode' and habit_val and 'habit' in habit_val:
            return [], habit_val
        return inherit_val, habit_val

    # --- Locked Inherit toggle for Goal / Milestone ---
    # Container types must always inherit time from their children. This callback
    # forces 'inherited' ON whenever the type is Goal or Milestone, and reveals an
    # inline warning if the user attempts to toggle it off. The trigger-id check
    # distinguishes user-initiated toggles from system-induced bounce-backs:
    # the bounce-back fires the same Input again with value=['inherited'], and
    # we use no_update for the warning in that second cycle so we don't clobber
    # the message we just made visible.
    @app.callback(
        Output('node-time-mode', 'value', allow_duplicate=True),
        Output('time-mode-warning', 'style'),
        Output('time-mode-warning', 'children'),
        Input('node-time-mode', 'value'),
        Input('node-type', 'value'),
        prevent_initial_call=True,
    )
    def enforce_locked_time_mode(time_mode_val, node_type):
        hidden = {"display": "none"}
        visible = {"display": "block", "color": "#dc3545", "fontSize": "0.85rem"}
        trig = get_trigger_id()

        if node_type not in ('Goal', 'Milestone'):
            # Type isn't a container — clear any lingering warning, no force.
            return time_mode_val, hidden, ""

        inherited_on = bool(time_mode_val and 'inherited' in time_mode_val)
        if inherited_on:
            # Already correct. If the trigger is a type change (just switched
            # into Goal/Milestone), clear any stale warning. If the trigger is
            # node-time-mode, we are in the second cycle of a bounce-back —
            # preserve the warning we just set visible (no_update).
            if trig == 'node-type':
                return no_update, hidden, ""
            return no_update, no_update, no_update

        # Inherited is OFF and type requires it ON — force back.
        msg = (f"Inherit mode is required for {node_type} nodes — "
               "their time is the sum of their children's.")
        if trig == 'node-time-mode':
            # User-initiated toggle-off — bounce back AND show warning.
            return ['inherited'], visible, msg
        # System-induced (type change with form value not yet inherited) — silent.
        return ['inherited'], hidden, ""

    # --- Live total-hours preview for habit mode ---
    @app.callback(
        Output('node-habit-total-preview', 'children'),
        Input('node-habit-duration', 'value'),
        Input('node-habit-duration-unit', 'value'),
        Input('node-habit-intensity-m', 'value'),
        Input('node-habit-intensity-unit', 'value'),
    )
    def update_habit_total_preview(duration, dur_unit, intensity_m, int_unit):
        total = habit_to_hours(duration or 0, dur_unit or 'weeks',
                               intensity_m or 0, int_unit or 'min_per_day')
        if total <= 0:
            return ""
        return f"Computes to ~{round(total, 1)} h total"

    # --- Toggle Value/Interest/Effort sliders based on value_mode ---
    @app.callback(
        Output('section-ratings', 'style'),
        Input('node-value-mode', 'value'),
    )
    def toggle_ratings_visibility(value_mode_val):
        if value_mode_val and 'inherited' in value_mode_val:
            return {'display': 'none'}
        return {}

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

    # --- "Locate on graph": enable/disable based on currently-loaded node ---
    # `node-original-name` is populated by the editor whenever ANY node is
    # loaded (via tap, search, details, edit-trigger). `search-node.value` is
    # only set when the user picks from the dropdown, so it's unreliable here.
    app.clientside_callback(
        "function(name) { return !name; }",
        Output('btn-locate-node', 'disabled'),
        Input('node-original-name', 'data'),
    )

    # --- "Locate on graph": dormant-aware gateway ---
    # Dormant nodes aren't on the canvas — clicking locate would pulse nothing.
    # Show an inline message under the search bar instead and skip the tab switch.
    @app.callback(
        Output('locate-message', 'children'),
        Output('locate-clear-interval', 'disabled'),
        Output('locate-clear-interval', 'n_intervals'),
        Output('main-tabs', 'active_tab', allow_duplicate=True),
        Output('locate-animate-trigger', 'data'),
        Input('btn-locate-node', 'n_clicks'),
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def handle_locate_click(n_clicks, name):
        if not n_clicks or not name:
            return (dash.no_update,) * 5
        node = manager.get_node(name)
        if not node:
            return (dash.no_update,) * 5
        if node.dormant:
            msg = f"'{name}' is dormant — its event must be triggered before it appears on the graph."
            return msg, False, 0, dash.no_update, dash.no_update
        return "", True, 0, 'tab-canvas', n_clicks

    # Run the pulse animation once the gateway has cleared the dormant check.
    # The fcose layout may still be running, so locateNodeOnGraph retries
    # until the node is present on the canvas.
    app.clientside_callback(
        """function(trigger, name) {
            if (!trigger || !name) return window.dash_clientside.no_update;
            if (typeof window.locateNodeOnGraph === 'function') {
                window.locateNodeOnGraph(name);
            }
            return window.dash_clientside.no_update;
        }""",
        Output('locate-message', 'title'),  # dummy/no-op output
        Input('locate-animate-trigger', 'data'),
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('locate-message', 'children', allow_duplicate=True),
        Output('locate-clear-interval', 'disabled', allow_duplicate=True),
        Input('locate-clear-interval', 'n_intervals'),
        prevent_initial_call=True,
    )
    def clear_locate_message(n):
        if n > 0:
            return "", True
        return dash.no_update, dash.no_update

    # --- "Cancel": re-trigger edit flow for the loaded node to re-populate
    # the editor from the DB, discarding any unsaved edits. Disabled when
    # no node is loaded. Suffix + timestamp forces edit-trigger-input to
    # change value even when clicking Cancel twice on the same node.
    app.clientside_callback(
        "function(name) { return !name; }",
        Output('btn-revert', 'disabled'),
        Input('node-original-name', 'data'),
    )

    app.clientside_callback(
        """function(n_clicks, name) {
            if (!n_clicks || !name) return window.dash_clientside.no_update;
            return name + '|revert-' + Date.now();
        }""",
        Output('edit-trigger-input', 'value', allow_duplicate=True),
        Input('btn-revert', 'n_clicks'),
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('save-output', 'children', allow_duplicate=True),
        Output('clear-interval', 'disabled', allow_duplicate=True),
        Output('clear-interval', 'n_intervals', allow_duplicate=True),
        Input('btn-revert', 'n_clicks'),
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def revert_message(n_clicks, name):
        if not n_clicks or not name:
            return dash.no_update, dash.no_update, dash.no_update
        return "Changes reverted.", False, 0

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

        # Order: Override → Priority/RelPriority. Status + Type are handled
        # by other inputs in the editor, so they don't appear in this strip.
        badges = []

        # Override (always first if active)
        override = ConfigManager.get_override()
        if override.get("parent"):
            override_set = ConfigManager.get_override_node_set(manager)
            if node_name in override_set:
                is_parent = (node_name == override["parent"])
                override_label = "Override" if is_parent else "Override (Dependent)"
                badges.append(html.Span(override_label, className="badge",
                                        style=badge_style('Override')))

        # Priority — Priority N for priority Goals; Hard/Soft N for non-priority nodes in a priority subtree.
        priority_goals = ConfigManager.get_priority_goals()
        if priority_goals:
            if node_type == "Goal" and node_name in priority_goals:
                rank = priority_goals.index(node_name) + 1
                badges.append(html.Span(f"Priority {rank}", className="badge",
                                        style=badge_style('Priority')))
            else:
                for rank_idx, goal_name in enumerate(priority_goals[:3]):
                    full_subtree = manager.get_goal_subtree(goal_name)
                    if node_name not in full_subtree:
                        continue
                    rank = rank_idx + 1
                    hard_subtree = manager.get_goal_subtree(goal_name, edge_types=(EDGE_NEEDS_HARD,))
                    rel_type = "Hard" if node_name in hard_subtree else "Soft"
                    palette_name = "HardRelPri" if rel_type == "Hard" else "SoftRelPri"
                    badges.append(html.Span(f"{rel_type} {rank}", className="badge",
                                            style=badge_style(palette_name)))

        if not badges:
            return [], hidden
        return badges, visible

    # --- Core State: Save, Delete, Render ---
    # NOTE: elements output goes to `elements-pending-store`, not directly to
    # `cytoscape-graph.elements`. A clientside callback reads the pending
    # store and, when freeze is on, injects pinned positions into each
    # node's data before pushing to Cytoscape. That's what keeps node
    # positions from drifting on save during bulk-edit freeze mode.
    @app.callback(
        [Output('elements-pending-store', 'data', allow_duplicate=True), Output('save-output', 'children'),
         Output('suggestions-table', 'children'),
         Output('traversal-chains-hard', 'children'), Output('traversal-chains-soft', 'children'),
         Output('synergies-list', 'children'), Output('node-info-description', 'children'),
         Output('clear-interval', 'disabled'), Output('clear-interval', 'n_intervals'),
         Output('filter-community', 'options'), Output('search-node', 'options'),
         Output('sidebar-editor-container', 'style'),
         Output('filter-context', 'options'), Output('node-context', 'options'),
         Output('node-type', 'options'),
         Output('filter-node-type', 'options'),
         Output('filter-goal', 'options'),
         Output('cytoscape-graph', 'stylesheet'),
         Output('btn-clear-focus', 'style'),
         Output('details-goal-sidebar', 'style', allow_duplicate=True),
         Output('events-sidebar-container', 'style', allow_duplicate=True),
         Output('modal-undo-done-confirm', 'is_open'),
         Output('undo-done-confirm-body', 'children'),
         Output('pending-undo-done-store', 'data')],

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
         Input('btn-unsaved-save', 'n_clicks'), Input('btn-unsaved-discard', 'n_clicks'),
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
         Input('main-tabs', 'active_tab'),
         Input('graph-settings-relayout', 'n_clicks'),
         Input('btn-sidebar-relayout', 'n_clicks'),
         Input('btn-undo-done-confirm', 'n_clicks')],

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
         State('cytoscape-graph', 'elements'),
         State('sidebar-editor-container', 'style'),
         State('node-original-name', 'data'),
         State('node-time-mode', 'value'),
         State('node-priority-rank', 'value'),
         State('node-competence', 'value'),
         State('details-goal-sidebar', 'style'),
         State('events-sidebar-container', 'style'),
         State('pending-navigation-store', 'data'),
         State({'type': 'alias-input', 'index': ALL}, 'value'),
         State('editor-pristine-snapshot', 'data'),
         State('pending-undo-done-store', 'data'),
         State('node-value-mode', 'value'),
         State('node-time-habit-mode', 'value'),
         State('node-habit-duration', 'value'),
         State('node-habit-duration-unit', 'value'),
         State('node-habit-intensity-o', 'value'),
         State('node-habit-intensity-m', 'value'),
         State('node-habit-intensity-p', 'value'),
         State('node-habit-intensity-unit', 'value')],
        prevent_initial_call='initial_duplicate'
    )
    def core_engine(save_clicks, save_close_clicks, delete_confirm_clicks, f_context, f_subcontext, f_done, search_val,
                     tapped_node,  # Cytoscape tapNodeData dict (not a Node object)
                     f_community, community_method, f_value, f_interest, f_time, f_difficulty, sugg_count,
                     btn_edit, btn_add, btn_new_node, btn_close_ed, btn_goals_toggle, btn_unsaved_save, btn_unsaved_discard, settings_open, migration_open, btn_toggle_done,
                     group_delete_data, f_node_types,
                     active_suggestion_id,
                     f_goal, focus_goal,
                     edit_trigger_data, details_edit_trigger_data, toggle_done_trigger_data, _events_refresh, _details_refresh, _bg_click,
                     gs_max_depth, gs_neighbor_links, active_tab, _relayout, _sidebar_relayout,
                     btn_undo_done_confirm,
                     name, n_type, desc, context, subctx, status_done, val, interest, diff,
                     time_o, time_m, time_p, time_unit,
                     e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                     obs_link_values, drive_link_values, website_link_values,
                     current_elements, ed_style, original_name,
                     time_mode_val, priority_rank_val, competence_val,
                     goal_sidebar_style, events_sidebar_style, pending_nav_store, alias_values,
                     pristine_snapshot, pending_undo_done,
                     value_mode_val,
                     time_habit_mode_val,
                     habit_duration, habit_duration_unit,
                     habit_int_o, habit_int_m, habit_int_p, habit_int_unit):
        """Central state callback handling node CRUD, filtering, and UI updates.

        This is intentionally a single large callback because Dash requires each Output
        to belong to exactly one callback. Since save/delete/filter operations all need
        to refresh the graph elements and sidebar state, they must share one callback.
        """
                     
        trigger_id = get_trigger_id()

        # Tab-switch gate: switching to Settings/Events/Analyze doesn't need a
        # graph regen — those tabs have their own refresh callbacks. Short-circuit
        # to no_update so we skip the scoring + generate_elements cycle.
        if trigger_id == 'main-tabs' and active_tab in _NON_GRAPH_TABS:
            return _core_engine_noop_tuple()

        all_triggered_ids = get_all_triggered_ids()

        # Editor-UI-only short-circuit: when the only thing that fired is a
        # pure editor UI trigger (e.g. context-menu Edit, close button, goals
        # toggle), skip the scoring + element regen pipeline and return a
        # minimal tuple with just the three sidebar styles. Saves ~100-300 ms
        # per Edit click and prevents the old ed_style race by minimizing the
        # window in which other callbacks could race with us.
        if (trigger_id in _EDITOR_UI_ONLY_TRIGGERS
                and all_triggered_ids <= _EDITOR_UI_ONLY_TRIGGERS):
            _form_state_for_close = {
                'original_name': original_name,
                'name': name, 'n_type': n_type, 'desc': desc,
                'context': context, 'subctx': subctx, 'status_done': status_done,
                'val': val, 'interest': interest, 'diff': diff,
                'time_o': time_o, 'time_m': time_m, 'time_p': time_p,
                'time_unit': time_unit,
                'e_needs_h': e_needs_h, 'e_needs_s': e_needs_s,
                'e_supp_h': e_supp_h, 'e_supp_s': e_supp_s, 'e_helps': e_helps,
                'obs_link_values': obs_link_values,
                'drive_link_values': drive_link_values,
                'website_link_values': website_link_values,
                'time_mode_val': time_mode_val,
                'time_habit_mode_val': time_habit_mode_val,
                'habit_duration': habit_duration,
                'habit_duration_unit': habit_duration_unit,
                'habit_int_o': habit_int_o,
                'habit_int_m': habit_int_m,
                'habit_int_p': habit_int_p,
                'habit_int_unit': habit_int_unit,
                'value_mode_val': value_mode_val,
                'priority_rank_val': priority_rank_val,
                'competence_val': competence_val,
                'alias_values': alias_values,
                'pristine_snapshot': pristine_snapshot,
            }
            ed, goal, events = _compute_sidebar_styles(
                trigger_id, all_triggered_ids, search_val,
                ed_style, goal_sidebar_style, events_sidebar_style,
                pending_nav_store, _form_state_for_close,
            )
            return _core_engine_editor_only_tuple(ed, goal, events)

        msg = ""
        completion_check_node = None  # Set when a node transitions to Done

        # Check for any delayed event nodes or scheduled events that are due
        from event_manager import EventManager
        _event_mgr = EventManager()
        _event_mgr.check_pending_activations()
        _event_mgr.check_scheduled_triggers()

        filters = build_filters(f_context, f_subcontext, f_done, f_value, f_interest, f_time, f_difficulty, f_node_types, f_goal=f_goal)

        # Editor Sidebar State — delegate to the shared helper so both the
        # short-circuit path above and the full path below compute sidebars
        # identically.
        _form_state = {
            'original_name': original_name,
            'name': name, 'n_type': n_type, 'desc': desc,
            'context': context, 'subctx': subctx, 'status_done': status_done,
            'val': val, 'interest': interest, 'diff': diff,
            'time_o': time_o, 'time_m': time_m, 'time_p': time_p,
            'time_unit': time_unit,
            'e_needs_h': e_needs_h, 'e_needs_s': e_needs_s,
            'e_supp_h': e_supp_h, 'e_supp_s': e_supp_s, 'e_helps': e_helps,
            'obs_link_values': obs_link_values,
            'drive_link_values': drive_link_values,
            'website_link_values': website_link_values,
            'time_mode_val': time_mode_val,
            'value_mode_val': value_mode_val,
            'priority_rank_val': priority_rank_val,
            'competence_val': competence_val,
            'alias_values': alias_values,
        }
        next_ed_style, next_goal_style, next_events_sidebar_style = _compute_sidebar_styles(
            trigger_id, all_triggered_ids, search_val,
            ed_style, goal_sidebar_style, events_sidebar_style,
            pending_nav_store, _form_state,
        )

        # Use whichever edit trigger fired (details tab or main)
        _edit_trigger = details_edit_trigger_data if trigger_id == 'details-edit-trigger-input' else edit_trigger_data
        active_node_id = resolve_active_node_id(
            all_triggered_ids, trigger_id, _edit_trigger,
            search_val, tapped_node, name)

        # When entering focus mode, clear the selected node so only the
        # goal's subtree is highlighted (not a previously-tapped node).
        # focus_goal may be a dict {"node": str, "subtree": list,
        #   "path_info": {...}} or a plain string.
        focus_subtree_override = None
        focus_path_info = None
        if isinstance(focus_goal, dict):
            focus_subtree_override = set(focus_goal.get("subtree", []))
            focus_path_info = focus_goal.get("path_info")
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
                    return _core_engine_save_error_tuple(msg, next_ed_style, next_goal_style, next_events_sidebar_style)
                else:
                    next_ed_style['transform'] = "translateX(-380px)"
                    return _core_engine_save_error_tuple("", next_ed_style, next_goal_style, next_events_sidebar_style)
            if not n_type:
                msg = "Error: Node type is required."
                return _core_engine_save_error_tuple(msg, next_ed_style, next_goal_style, next_events_sidebar_style)
            try:
                # Track if this save marks the node Done (for event completion check)
                if status_done and STATUS_DONE in (status_done or []):
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

                # Resolve the canonical time_mode via the shared helper —
                # centralizes the Goal/Milestone-must-inherit invariant and
                # eliminates drift across the three save paths (main editor,
                # dormant-node creation, details-panel save).
                time_mode = resolve_time_mode(n_type, time_mode_val, time_habit_mode_val)
                if time_mode == 'habit':
                    t_o, t_m, t_p = compute_habit_time_omp(
                        habit_duration or 0, habit_duration_unit or 'weeks',
                        habit_int_o or 0, habit_int_m or 0, habit_int_p or 0,
                        habit_int_unit or 'min_per_day',
                    )
                value_mode = 'inherited' if (value_mode_val and 'inherited' in value_mode_val) else 'manual'
                msg = handle_save(manager, name, n_type, desc, val, t_o, t_m, t_p,
                                  interest, diff, status_done, context, subctx,
                                  obs_path, drive_path, website_path,
                                  e_needs_h, e_needs_s,
                                  e_supp_h, e_supp_s, e_helps,
                                  time_mode=time_mode,
                                  value_mode=value_mode,
                                  competence=competence_val,
                                  habit_duration=habit_duration or 0,
                                  habit_duration_unit=habit_duration_unit or 'weeks',
                                  habit_intensity_o=habit_int_o or 0,
                                  habit_intensity_m=habit_int_m or 0,
                                  habit_intensity_p=habit_int_p or 0,
                                  habit_intensity_unit=habit_int_unit or 'min_per_day')

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
                return _core_engine_save_error_tuple(msg, next_ed_style, next_goal_style, next_events_sidebar_style)
            except Exception as e:
                msg = f"Error: {e}"
        elif trigger_id == 'btn-node-delete-confirm' and name:
            try:
                msg = handle_delete(manager, name)
            except Exception as e:
                msg = f"Error: {e}"
        elif trigger_id == 'btn-toggle-done-node' and tapped_node:
            try:
                node_id = tapped_node.get('id')
                _pre_node = manager.get_node(node_id)
                # Done → Open with downstream Done dependents needs explicit
                # user confirmation: re-blocking previously-Done work is
                # destructive enough to warrant a modal.
                if _pre_node and _pre_node.status == STATUS_DONE:
                    downstream_done = manager.get_downstream_done_dependents(node_id)
                    if downstream_done:
                        out = [dash.no_update] * _CORE_ENGINE_NUM_OUTPUTS
                        out[_UNDO_DONE_MODAL_IDX] = True
                        out[_UNDO_DONE_BODY_IDX] = _build_undo_done_body([node_id], downstream_done)
                        out[_PENDING_UNDO_DONE_IDX] = [node_id]
                        return tuple(out)
                if _pre_node and _pre_node.status != STATUS_DONE:
                    completion_check_node = node_id
                msg = handle_toggle_done(manager, tapped_node)
            except Exception as e:
                msg = f"Error: {e}"
        elif trigger_id == 'toggle-done-trigger-input' and toggle_done_trigger_data:
            try:
                raw = toggle_done_trigger_data.split('|')[0]
                try:
                    parsed = json.loads(raw)
                    node_names = parsed if isinstance(parsed, list) else [raw]
                except (ValueError, json.JSONDecodeError):
                    node_names = [raw]

                nodes = [n for n in (manager.get_node(nm) for nm in node_names) if n]
                if nodes:
                    any_not_done = any(n.status != STATUS_DONE for n in nodes)
                    new_status = STATUS_DONE if any_not_done else STATUS_OPEN

                    # Pre-check for Done → Open transition: collect every
                    # downstream Done node that would be re-blocked. If any
                    # exist, gate the toggle behind the confirmation modal.
                    if new_status == STATUS_OPEN:
                        affected_downstream: List[str] = []
                        seen_downstream: Set[str] = set()
                        for node in nodes:
                            if node.status != STATUS_DONE:
                                continue
                            for d in manager.get_downstream_done_dependents(node.name):
                                if d not in seen_downstream:
                                    seen_downstream.add(d)
                                    affected_downstream.append(d)
                        if affected_downstream:
                            out = [dash.no_update] * _CORE_ENGINE_NUM_OUTPUTS
                            target_names = [n.name for n in nodes]
                            out[_UNDO_DONE_MODAL_IDX] = True
                            out[_UNDO_DONE_BODY_IDX] = _build_undo_done_body(target_names, affected_downstream)
                            out[_PENDING_UNDO_DONE_IDX] = target_names
                            return tuple(out)

                    flipped = 0
                    for node in nodes:
                        if node.status != new_status:
                            node.status = new_status
                            manager.update_node(node)
                            flipped += 1

                    if len(nodes) == 1 and new_status == STATUS_DONE and flipped == 1:
                        completion_check_node = nodes[0].name

                    if len(nodes) == 1:
                        msg = f"Toggled status of '{nodes[0].name}' to {new_status}"
                    else:
                        msg = f"Set {flipped} node(s) to {new_status}"
            except Exception as e:
                msg = f"Error: {e}"
        elif trigger_id == 'btn-undo-done-confirm' and pending_undo_done:
            # Modal confirmed: perform the previously-gated Done → Open toggle
            # on every node in pending_undo_done. Cascade re-blocks downstream
            # Done dependents via _update_node_state.
            try:
                target_names = list(pending_undo_done) if isinstance(pending_undo_done, list) else [pending_undo_done]
                flipped = 0
                for nm in target_names:
                    node = manager.get_node(nm)
                    if node and node.status == STATUS_DONE:
                        node.status = STATUS_OPEN
                        manager.update_node(node)
                        flipped += 1
                if flipped == 1:
                    msg = f"Un-marked '{target_names[0]}' (Done → Open)"
                else:
                    msg = f"Un-marked {flipped} node(s) (Done → Open)"
            except Exception as e:
                msg = f"Error: {e}"
        elif trigger_id == 'group-delete-input' and group_delete_data:
            try:
                msg = handle_group_delete(manager, group_delete_data)
            except Exception as e:
                msg = f"Error: {e}"
        # --- Visual Generation ---
        ui_only_triggers = ('btn-edit-node', 'btn-add', 'btn-new-node', 'edit-trigger-input', 'details-edit-trigger-input', 'cytoscape-graph', 'btn-close-editor', 'btn-goals-toggle')
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

            # Still format sidebar traversal UI
            count = sugg_count if sugg_count else 10
            sugg_ui = format_suggestions_table(get_suggestions(filters, count=count), manager, active_suggestion_id, override_set=get_override_set())
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
            effective_tapped_node = None if trigger_id in ('background-click-input', 'btn-add') else tapped_node
            hard_chains_ui, soft_chains_ui, synergies_ui, description_ui = format_traversal_ui(effective_tapped_node, active_node_id, manager)

            all_nodes = manager.get_all_nodes()
            search_options = node_options(manager.get_all_nodes(include_dormant=True))

            # Append alias entries to search options (use alias: prefix for unique values)
            for alias, node_name in manager.get_all_aliases().items():
                search_options.append({'label': f"{alias} \u2192 {node_name}", 'value': f"alias:{alias}"})

            # Populate dynamic contexts datalists from DB + Config preserving defined order
            base_ctx = ConfigManager.get_contexts()
            
            ctx_list = [{"label": c, "value": c} for c in base_ctx]
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
                    'style': {'opacity': 0.06, 'z-index': 0}
                })
                active_stylesheet.append({
                    'selector': 'edge',
                    'style': {'opacity': 0.04, 'z-index': 0}
                })
                # Build an attribute-selector with a delimiter that doesn't
                # clash with quote characters in the id. Cytoscape's selector
                # parser does NOT honor CSS backslash-escape inside string
                # values, so a name like Read "Meditations" inside double-quote
                # delimiters silently matches nothing and leaves the node
                # dimmed. Swap to single-quote delimiters when the id has a
                # double-quote (and vice versa). Names containing both kinds
                # are rare; we skip the per-node highlight in that case rather
                # than emit a broken selector.
                def _attr_selector(prop, value):
                    has_dq = '"' in value
                    has_sq = "'" in value
                    if has_dq and has_sq:
                        return None
                    quote = "'" if has_dq else '"'
                    return f'[{prop} = {quote}{value}{quote}]'

                for node_name in focus_subtree:
                    sel_tail = _attr_selector('id', node_name)
                    if sel_tail is None:
                        continue
                    # Pin every opacity sub-channel so nothing downstream
                    # (node/border/label/background) inherits the dim; z-index
                    # raises focus nodes above the dimmed layer so overlapping
                    # neighbors don't peek through concave shapes (stars).
                    active_stylesheet.append({
                        'selector': f'node{sel_tail}',
                        'style': {
                            'opacity': 1,
                            'background-opacity': 1,
                            'border-opacity': 1,
                            'text-opacity': 1,
                            'z-index': 10,
                        },
                    })
                # Highlight edges between focus subtree nodes
                edges = manager.get_edges()
                for e in edges:
                    if e['source'] in focus_subtree and e['target'] in focus_subtree:
                        eid = f"{e['source']}_{e['target']}_{e['type']}"
                        sel_tail = _attr_selector('id', eid)
                        if sel_tail is None:
                            continue
                        active_stylesheet.append({
                            'selector': f'edge{sel_tail}',
                            'style': {
                                'opacity': 1,
                                'line-opacity': 1,
                                'text-opacity': 1,
                                'z-index': 5,
                            },
                        })

                # Per-path coloring (new focus-paths feature).
                # Populated only when focus_goal_store carries path_info;
                # the existing mini-graph Focus button leaves it None.
                if focus_path_info:
                    # Saturated hues (Material Design A-accent shades) so
                    # paths stay punchy against the dimmed background.
                    PATH_COLORS = {
                        1: '#ff1744',  # vivid red
                        2: '#1de9b6',  # bright teal
                        3: '#d500f9',  # electric purple
                        4: '#ff6d00',  # deep orange
                        5: '#f50057',  # hot pink
                    }
                    for name, rank in (focus_path_info.get('node_rank') or {}).items():
                        color = PATH_COLORS.get(int(rank))
                        if color is None:
                            continue
                        sel_tail = _attr_selector('id', name)
                        if sel_tail is None:
                            continue
                        active_stylesheet.append({
                            'selector': f'node{sel_tail}',
                            'style': {'border-color': color,
                                      'border-width': 4},
                        })
                    for edge_key, rank in (focus_path_info.get('edge_rank') or {}).items():
                        parts = edge_key.split('|')
                        if len(parts) != 3:
                            continue
                        src, tgt, etype = parts
                        color = PATH_COLORS.get(int(rank))
                        if color is None:
                            continue
                        eid = f"{src}_{tgt}_{etype}"
                        sel_tail = _attr_selector('id', eid)
                        if sel_tail is None:
                            continue
                        active_stylesheet.append({
                            'selector': f'edge{sel_tail}',
                            'style': {'line-color': color,
                                      'target-arrow-color': color,
                                      'width': 3},
                        })
                    for name, badge in (focus_path_info.get('target_labels') or {}).items():
                        sel_tail = _attr_selector('id', name)
                        if sel_tail is None:
                            continue
                        active_stylesheet.append({
                            'selector': f'node{sel_tail}',
                            'style': {'label': f'{badge} {name}'},
                        })

            clear_focus_style = {"display": "inline-block"} if focus_goal else {"display": "none"}

            # Node-completion events are now fired from GraphManager.update_node
            # whenever a node transitions to Done — no per-callback hook needed.
            # The time-based sweeps (check_pending_activations / check_scheduled_triggers)
            # still run at the top of core_engine because they're polling and
            # don't have a single transition point to hook into.

        # Last 3 outputs are the undo-Done modal trio. The full path either
        # opens the modal earlier (return short-circuit in the toggle branch)
        # or runs to completion when no confirmation is needed; on this final
        # return the modal stays closed and the pending store is cleared so
        # any prior open state from a now-resolved flow is reset.
        return (elements, msg, sugg_ui, hard_chains_ui, soft_chains_ui, synergies_ui, description_ui, False if msg else True, 0, community_options, search_options, next_ed_style, f_ctx_list, ctx_list, type_list, f_type_list, goal_opts, active_stylesheet, clear_focus_style, next_goal_style, next_events_sidebar_style, False, "", None)

    # --- Filters Sidebar Toggle (CLIENTSIDE) ---
    # Handled entirely in the browser via assets/filters_sidebar.js. Previously
    # this toggle went through core_engine, whose expensive graph-regen branch
    # delayed the CSS transition by 500ms-2s on each click.
    app.clientside_callback(
        ClientsideFunction(namespace='filters', function_name='toggle_sidebar'),
        Output('sidebar-filters-container', 'style'),
        Input('btn-filters-toggle', 'n_clicks'),
        Input('btn-close-filters', 'n_clicks'),
        State('sidebar-filters-container', 'style'),
        prevent_initial_call=True,
    )

    # --- Editor Sidebar Fast-Path (CLIENTSIDE) ---
    # Starts the open-editor CSS transition immediately on btn-add, in parallel
    # with core_engine's form-population work. core_engine still sets the same
    # open-transform value server-side as a safety net. Close/save/new-node
    # stay server-side because they depend on form state.
    app.clientside_callback(
        ClientsideFunction(namespace='editor', function_name='open_on_add'),
        Output('sidebar-editor-container', 'style', allow_duplicate=True),
        Output('details-goal-sidebar', 'style', allow_duplicate=True),
        Output('events-sidebar-container', 'style', allow_duplicate=True),
        Input('btn-add', 'n_clicks'),
        State('sidebar-editor-container', 'style'),
        State('details-goal-sidebar', 'style'),
        State('events-sidebar-container', 'style'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('modal-undo-done-confirm', 'is_open', allow_duplicate=True),
        Output('pending-undo-done-store', 'data', allow_duplicate=True),
        Input('btn-undo-done-cancel', 'n_clicks'),
        Input('btn-undo-done-confirm', 'n_clicks'),
        prevent_initial_call=True,
    )
    def close_undo_done_modal(_cancel, _confirm):
        """Close the undo-Done modal and clear the pending store on either
        button. The actual toggle (on confirm) is performed by core_engine
        listening to btn-undo-done-confirm; this callback only manages the
        modal/store cleanup so the next toggle starts fresh.
        """
        return False, None

    # --- Auto-Done Suggestion Modal ---
    # Single orchestrator that drains GraphManager's auto-done candidate queue
    # on every graph-version bump, and surfaces them one at a time in a modal
    # offering "Mark Done" / "Dismiss". Marking Done re-runs update_node which
    # may queue parent containers (chained), so the modal stays open until the
    # queue is empty. Dismiss simply pops without acting. The store is the
    # SSOT for what's queued — both branches read and write it via this
    # single callback to avoid races with the drain trigger.
    @app.callback(
        Output('modal-auto-done-suggestion', 'is_open'),
        Output('auto-done-suggestion-body', 'children'),
        Output('auto-done-candidates-store', 'data'),
        Output('elements-pending-store', 'data', allow_duplicate=True),
        Output('save-output', 'children', allow_duplicate=True),
        Input('graph-version-store', 'data'),
        Input('btn-auto-done-confirm', 'n_clicks'),
        Input('btn-auto-done-dismiss', 'n_clicks'),
        State('auto-done-candidates-store', 'data'),
        prevent_initial_call=True,
    )
    def manage_auto_done_modal(_version, _confirm, _dismiss, current_candidates):
        from models import STATUS_DONE, STATUS_BLOCKED
        trig = get_trigger_id()
        candidates = list(current_candidates or [])
        elements_out = no_update
        save_msg_out = no_update

        if trig == 'btn-auto-done-confirm' and candidates:
            target = candidates.pop(0)
            node = manager.get_node(target)
            if node is None:
                save_msg_out = f"'{target}' no longer exists"
            elif node.status == STATUS_DONE:
                # Already Done via another path — silently skip.
                pass
            elif node.status == STATUS_BLOCKED:
                # Prereqs no longer all Done (e.g. a sibling un-done) —
                # don't force; let the user re-decide later.
                save_msg_out = (
                    f"'{target}' is no longer eligible — "
                    "a prereq was un-done."
                )
            else:
                try:
                    node.status = STATUS_DONE
                    manager.update_node(node)
                    save_msg_out = f"Marked '{target}' as Done"
                    elements_out = generate_elements()
                except Exception as exc:
                    save_msg_out = f"Error marking '{target}' Done: {exc}"
                    # Re-prepend so the user can retry from the modal.
                    candidates.insert(0, target)

        elif trig == 'btn-auto-done-dismiss' and candidates:
            candidates.pop(0)

        # Drain any newly-queued candidates from the manager (a Mark Done
        # above may have flipped a parent container's prereqs to all-Done,
        # OR an unrelated save bumped graph-version-store and pushed new
        # candidates while the modal was idle).
        new_candidates = manager.pop_auto_done_candidates()
        for c in new_candidates:
            if c not in candidates:
                candidates.append(c)

        if candidates:
            first = candidates[0]
            first_node = manager.get_node(first)
            type_label = (first_node.type if first_node else "node").lower()
            body = html.Div([
                html.P([
                    "All hard prerequisites of ",
                    html.Strong(first),
                    f" are complete. Mark this {type_label} Done?",
                ], className="mb-2"),
                html.Div(
                    f"{len(candidates) - 1} more pending"
                    if len(candidates) > 1 else "",
                    className="text-muted small",
                ),
            ])
            return True, body, candidates, elements_out, save_msg_out
        return False, "", [], elements_out, save_msg_out

    @app.callback(
        Output('modal-unsaved-changes', 'is_open'),
        [Input('btn-close-editor', 'n_clicks'),
         Input('btn-unsaved-cancel', 'n_clicks'),
         Input('btn-unsaved-save', 'n_clicks'),
         Input('btn-unsaved-discard', 'n_clicks')],
        [State('node-name', 'value'), State('node-type', 'value'), State('node-desc', 'value'),
         State('node-context', 'value'), State('node-subcontext', 'value'),
         State('node-status-done', 'value'),
         State('node-value', 'value'), State('node-interest', 'value'),
         State('node-difficulty', 'value'),
         State('node-time-o', 'value'), State('node-time-m', 'value'),
         State('node-time-p', 'value'), State('node-time-unit', 'value'),
         State('edge-needs-hard', 'value'), State('edge-needs-soft', 'value'),
         State('edge-supports-hard', 'value'), State('edge-supports-soft', 'value'),
         State('edge-helps', 'value'),
         State({'type': 'obsidian-link', 'index': ALL}, 'value'),
         State({'type': 'drive-link', 'index': ALL}, 'value'),
         State({'type': 'website-link', 'index': ALL}, 'value'),
         State('node-time-mode', 'value'),
         State('node-priority-rank', 'value'), State('node-competence', 'value'),
         State({'type': 'alias-input', 'index': ALL}, 'value'),
         State('node-original-name', 'data'),
         State('editor-pristine-snapshot', 'data'),
         State('node-value-mode', 'value')],
        prevent_initial_call=True
    )
    def toggle_unsaved_modal(_close, _cancel, _save, _discard,
                              name, n_type, desc, context, subctx, status_done,
                              val, interest, diff,
                              time_o, time_m, time_p, time_unit,
                              e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                              obs_link_values, drive_link_values, website_link_values,
                              time_mode_val, priority_rank_val, competence_val,
                              alias_values, original_name, pristine_snapshot,
                              value_mode_val):
        if get_trigger_id() != 'btn-close-editor':
            return False
        return is_form_dirty_vs_snapshot(pristine_snapshot, {
            'name': name, 'n_type': n_type, 'desc': desc,
            'context': context, 'subctx': subctx,
            'status_done': status_done,
            'val': val, 'interest': interest, 'diff': diff,
            'time_o': time_o, 'time_m': time_m, 'time_p': time_p,
            'time_unit': time_unit,
            'e_needs_h': e_needs_h, 'e_needs_s': e_needs_s,
            'e_supp_h': e_supp_h, 'e_supp_s': e_supp_s, 'e_helps': e_helps,
            'obs_links': obs_link_values, 'drive_links': drive_link_values,
            'website_links': website_link_values,
            'time_mode': time_mode_val,
            'value_mode': value_mode_val,
            'priority_rank': priority_rank_val, 'competence': competence_val,
            'aliases': alias_values,
        })

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

    # --- Group Delete Confirmation Modal (context menu + Delete key) ---
    @app.callback(
        Output('modal-group-delete-confirm', 'is_open'),
        Output('group-delete-pending-store', 'data'),
        Output('group-delete-confirm-body', 'children'),
        Input('group-delete-request-input', 'value'),
        Input('btn-group-delete-cancel', 'n_clicks'),
        Input('btn-group-delete-confirm', 'n_clicks'),
        prevent_initial_call=True,
    )
    def toggle_group_delete_modal(request_value, _cancel, _confirm):
        import json as _json
        trigger_id = get_trigger_id()
        if trigger_id == 'group-delete-request-input':
            if not request_value:
                return dash.no_update, dash.no_update, dash.no_update
            raw = request_value.split('|')[0]
            try:
                names = _json.loads(raw) if raw else []
            except Exception:
                return dash.no_update, dash.no_update, dash.no_update
            if not names:
                return dash.no_update, dash.no_update, dash.no_update
            if len(names) == 1:
                body = f'Are you sure you want to delete "{names[0]}"? This action cannot be undone.'
            else:
                body = f'Are you sure you want to delete these {len(names)} nodes? This action cannot be undone.'
            return True, names, body
        # Cancel or Confirm both close the modal. The confirm path writes to
        # group-delete-input in a separate callback below.
        return False, dash.no_update, dash.no_update

    @app.callback(
        Output('group-delete-input', 'value'),
        Input('btn-group-delete-confirm', 'n_clicks'),
        State('group-delete-pending-store', 'data'),
        prevent_initial_call=True,
    )
    def perform_group_delete(n_clicks, names):
        import json as _json
        import time as _time
        if not n_clicks or not names:
            return dash.no_update
        return _json.dumps(names) + '|' + str(_time.time())

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
        Output('next-perf-stats', 'children', allow_duplicate=True),
        Input('suggestions-table', 'children'),
        State('main-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    def update_next_perf_stats(_sugg_children, active_tab):
        if active_tab != 'tab-next':
            return dash.no_update
        t = GraphManager._last_perf_timings
        if not t:
            return dash.no_update
        # Consume the stashed startup timings — toast renders exactly once
        # and stays visible until the next app start.
        GraphManager._last_perf_timings = None
        return (f"{t['n_nodes']} nodes \u00b7 {t['n_edges']} edges \u00b7 "
                f"{t['total_ms']:.0f}ms")

    @app.callback(
        Output('canvas-node-count', 'children'),
        Input('cytoscape-graph', 'elements'),
        Input('filter-node-type', 'value'),
        Input('filter-context', 'value'),
        Input('filter-subcontext', 'value'),
        Input('filter-goal', 'value'),
        Input('filter-community', 'value'),
        Input('community-method', 'value'),
        Input('filter-value', 'value'),
        Input('filter-interest', 'value'),
        Input('filter-difficulty', 'value'),
        Input('filter-time', 'value'),
        Input('filter-done', 'value'),
    )
    def update_canvas_node_count(elements, f_type, f_ctx, f_sub, f_goal,
                                 f_comm, f_comm_method, f_val, f_int,
                                 f_diff, f_time, f_done):
        n = sum(1 for el in (elements or []) if 'source' not in el.get('data', {}))
        text = f"{n} node{'s' if n != 1 else ''}"
        if is_filters_active(node_type=f_type, context=f_ctx, subcontext=f_sub,
                             goal=f_goal, community=f_comm,
                             community_method=f_comm_method, value=f_val,
                             interest=f_int, difficulty=f_diff, time=f_time,
                             done=f_done):
            return f"{text} (filtered)"
        return text

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
        subs = sort_subcontexts(ConfigManager.get_subcontexts().get(ctx, []))
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
        opts = []
        for c in contexts:
            for s in sort_subcontexts(all_subs.get(c, [])):
                label = f"{c} > {s}" if multi_context else s
                opts.append({"label": label, "value": f"{c}::{s}"})
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
        [Output('aliases-store', 'data', allow_duplicate=True),
         Output('collapse-aliases', 'is_open', allow_duplicate=True)],
        [Input('btn-alias-add', 'n_clicks'),
         Input({'type': 'btn-alias-remove', 'index': ALL}, 'n_clicks')],
        [State({'type': 'alias-input', 'index': ALL}, 'value'),
         State('aliases-store', 'data')],
        prevent_initial_call=True,
    )
    def modify_aliases(add_clicks, remove_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        aliases = list(current_values) if current_values else list(store_data or [''])
        collapse_update = dash.no_update
        if trigger == 'btn-alias-add':
            aliases.append('')
        elif isinstance(trigger, dict) and trigger.get('type') == 'btn-alias-remove':
            idx = trigger['index']
            if 0 <= idx < len(aliases):
                aliases.pop(idx)
                if not aliases:
                    collapse_update = False
        return aliases, collapse_update

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
    # NOTE: short-circuit when already on canvas. Writing the same value to
    # main-tabs.active_tab with allow_duplicate=True still re-fires any Input
    # depending on it (notably core_engine). That second core_engine run had
    # trigger_id='main-tabs', which doesn't match any editor-open branch, so
    # it returned the State-cached ed_style — racing with the open-editor
    # output from the Edit-trigger run and sometimes clobbering it back to
    # translateX(-380px). Only writing when the tab actually needs to change
    # avoids the spurious re-fire.
    @app.callback(
        Output('main-tabs', 'active_tab', allow_duplicate=True),
        Input('edit-trigger-input', 'value'),
        State('main-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    def handle_edit_trigger(value, current_tab):
        if not value:
            return dash.no_update
        node_name = value.split('|')[0]
        if not node_name:
            return dash.no_update
        if current_tab == 'tab-canvas':
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
        Output('graph-settings-freeze-rerender', 'value', allow_duplicate=True),
        Input('btn-reset-graph-settings', 'n_clicks'),
        prevent_initial_call=True,
    )
    def reset_graph_settings(n_clicks):
        if not n_clicks:
            return (dash.no_update,) * 7
        gl = ConfigManager.get_graph_layout_defaults()
        return (
            0, True, True,
            gl.get('edge_length', 100),
            gl.get('gravity', 0.25),
            gl.get('repulsion', 4500),
            False,
        )

    # --- Freeze feature: per-canvas clientside wiring ---
    # Each Cytoscape canvas (main / details / events) gets three parameterized
    # clientside callbacks: pending-store → elements bypass, switch → store
    # sync (also flips the JS frozen flag so the freeze-off refresh doesn't
    # race it), and snowflake/class-name indicator. The Settle (re-layout)
    # button's allowOneLayout call lives inside the layout callback itself
    # so it's sequenced synchronously with the layout-prop write.
    def _register_freeze_callbacks(canvas_id, switch_id, store_id, pending_id,
                                   cytoscape_id, indicator_id, container_id):
        """Wire the three freeze clientside callbacks for one canvas."""
        js_canvas = repr(canvas_id)  # JS-safe quoted string literal

        # Bypass: pending-store -> cytoscape.elements.
        app.clientside_callback(
            """
            function(pending) {
                if (pending === null || pending === undefined) {
                    return window.dash_clientside.no_update;
                }
                var st = window.SkillTree;
                if (st && st.isFrozen && st.isFrozen(__CANVAS__) && st.applyDelta) {
                    st.applyDelta(__CANVAS__, pending);
                    return window.dash_clientside.no_update;
                }
                return pending;
            }
            """.replace('__CANVAS__', js_canvas),
            Output(cytoscape_id, 'elements'),
            Input(pending_id, 'data'),
            prevent_initial_call=True,
        )

        # Switch -> store sync (also flips JS frozen flag synchronously).
        app.clientside_callback(
            """
            function(value) {
                var v = Boolean(value);
                if (window.SkillTree && window.SkillTree.setFreezeActive) {
                    window.SkillTree.setFreezeActive(__CANVAS__, v);
                }
                return v;
            }
            """.replace('__CANVAS__', js_canvas),
            Output(store_id, 'data'),
            Input(switch_id, 'value'),
            prevent_initial_call=True,
        )

        # Indicator: snowflake style + container class.
        app.clientside_callback(
            """
            function(frozen, currentClass) {
                var baseStyle = {
                    position: "absolute", top: "12px", right: "19px",
                    fontSize: "1.6rem", color: "#7ec8e3",
                    textShadow: "0 0 6px rgba(126, 200, 227, 0.5)",
                    pointerEvents: "none", zIndex: 10,
                };
                var classes = (currentClass || "").split(/\\s+/).filter(function(c) {
                    return c && c !== "cyto-frozen";
                });
                if (frozen) classes.push("cyto-frozen");
                baseStyle.display = frozen ? "block" : "none";
                return [baseStyle, classes.join(" ")];
            }
            """,
            Output(indicator_id, 'style'),
            Output(container_id, 'className'),
            Input(store_id, 'data'),
            State(container_id, 'className'),
        )

    _register_freeze_callbacks(
        canvas_id='main',
        switch_id='graph-settings-freeze-rerender',
        store_id='freeze-rerender-store',
        pending_id='elements-pending-store',
        cytoscape_id='cytoscape-graph',
        indicator_id='freeze-indicator',
        container_id='canvas-container',
    )
    _register_freeze_callbacks(
        canvas_id='details',
        switch_id='details-graph-settings-freeze-rerender',
        store_id='details-freeze-rerender-store',
        pending_id='details-elements-pending-store',
        cytoscape_id='details-mini-graph',
        indicator_id='details-freeze-indicator',
        container_id='details-dep-graph-container',
    )
    _register_freeze_callbacks(
        canvas_id='events',
        switch_id='events-graph-settings-freeze-rerender',
        store_id='events-freeze-rerender-store',
        pending_id='events-elements-pending-store',
        cytoscape_id='events-detail-graph',
        indicator_id='events-freeze-indicator',
        container_id='events-detail-graph-container',
    )

    # --- Graph Settings: Apply Layout Parameters ---
    # Clientside so allowOneLayout('main') is set in the same synchronous
    # function that returns the new layout dict. A previous server-side
    # implementation paired with a separate clientside allowOneLayout callback
    # was racy: Dash doesn't order parallel callbacks bound to the same input,
    # so the layout prop sometimes reached Cytoscape before the JS guard's
    # allowNextLayout flag was set, causing the freeze guard at layoutstart
    # to stop the layout (Settle button silently no-op).
    app.clientside_callback(
        """
        function(edge_length, gravity, repulsion, animate, relayout_n, sidebar_relayout_n, freeze_on) {
            var ctx = window.dash_clientside.callback_context;
            var trig = ctx.triggered_id
                || (ctx.triggered && ctx.triggered.length
                    ? ctx.triggered[0].prop_id.split('.')[0]
                    : null);
            var relayout_triggers = ['graph-settings-relayout', 'btn-sidebar-relayout'];
            // Freeze toggle fired: run layout only on the off-transition (refresh).
            // On the on-transition we stay put so the user's current positions hold.
            if (trig === 'freeze-rerender-store' && freeze_on) {
                return window.dash_clientside.no_update;
            }
            // While frozen, slider changes are deferred — they'll apply on the
            // next freeze-off transition. But relayout clicks still force a
            // refresh (user's explicit "update now" action).
            if (freeze_on && trig !== 'freeze-rerender-store'
                && relayout_triggers.indexOf(trig) === -1) {
                return window.dash_clientside.no_update;
            }
            var is_relayout = relayout_triggers.indexOf(trig) !== -1;
            // Sequence the freeze-guard bypass synchronously with the layout-
            // prop write so layoutstart sees allowNextLayout=true next tick.
            if (is_relayout && window.SkillTree && window.SkillTree.allowOneLayout) {
                window.SkillTree.allowOneLayout('main');
            }
            return {
                name: 'fcose',
                quality: 'proof',
                fit: true,
                animate: !!animate,
                randomize: is_relayout,
                idealEdgeLength: edge_length || 100,
                nodeRepulsion: repulsion || 4500,
                gravity: (gravity !== null && gravity !== undefined) ? gravity : 0.25,
                numIter: 2500,
            };
        }
        """,
        Output('cytoscape-graph', 'layout'),
        Input('graph-settings-edge-length', 'value'),
        Input('graph-settings-gravity', 'value'),
        Input('graph-settings-repulsion', 'value'),
        Input('graph-settings-animate', 'value'),
        Input('graph-settings-relayout', 'n_clicks'),
        Input('btn-sidebar-relayout', 'n_clicks'),
        Input('freeze-rerender-store', 'data'),
        prevent_initial_call=True,
    )

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
        Output('override-conflict-mode-wrapper', 'style', allow_duplicate=True),
        Input('override-toggle', 'value'),
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def handle_override_toggle(toggle_val, node_name):
        """Handle override toggle interaction: open popover, show conflicts, or clear."""
        no_change = (False, False, dash.no_update, False, dash.no_update, dash.no_update, dash.no_update, dash.no_update)
        if not node_name:
            return no_change

        toggle_on = bool(toggle_val and "on" in toggle_val)
        override = ConfigManager.get_override()
        current_parent = override.get("parent")
        event_pinned = ConfigManager.get_event_override_nodes()

        if toggle_on:
            # Turning ON
            override_set = ConfigManager.get_override_node_set(manager)
            if node_name in override_set:
                # Node is already in the override set (parent or dep) — sync triggered this
                return no_change
            if current_parent:
                # Conflict: different main override already active. Radio is meaningful here.
                body = f'An override is already active for "{current_parent}". Do you want to keep the current override, or apply it to this new set?'
                return False, True, body, False, dash.no_update, dash.no_update, dash.no_update, {}
            if event_pinned:
                # Conflict: System B is populated from a prior event trigger. Radio is meaningful.
                body = (f'An override is currently active on {len(event_pinned)} event-pinned '
                        f'node(s): {", ".join(event_pinned)}. Do you want to keep the current '
                        f'override, or apply it to this new set?')
                return False, True, body, False, dash.no_update, dash.no_update, dash.no_update, {}
            # No existing override: open popover for mode selection
            return True, False, dash.no_update, False, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        else:
            # Turning OFF
            if not current_parent:
                return no_change
            if node_name == current_parent:
                # Direct parent: clear override
                import time as _time
                ConfigManager.clear_override()
                return False, False, dash.no_update, False, dash.no_update, ConfigManager.get_override(), f"override-{_time.time()}", dash.no_update
            else:
                # Inherited dep: show untoggle modal
                override_set = ConfigManager.get_override_node_set(manager)
                if node_name in override_set:
                    body = f'This override was inherited from "{current_parent}".'
                    return False, False, dash.no_update, True, body, dash.no_update, dash.no_update, dash.no_update
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
        Output('pending-event-override-store', 'data', allow_duplicate=True),
        Output('override-conflict-body', 'children', allow_duplicate=True),
        Output('override-conflict-mode-wrapper', 'style', allow_duplicate=True),
        Input('btn-override-keep', 'n_clicks'),
        Input('btn-override-replace', 'n_clicks'),
        State('override-conflict-mode-radio', 'value'),
        State('node-original-name', 'data'),
        State('pending-event-override-store', 'data'),
        prevent_initial_call=True,
    )
    def resolve_override_conflict(keep_clicks, replace_clicks, mode, node_name, pending_event):
        """Resolve conflict when a new override is attempted while one is active.

        Two modes:
        - Event-batch: pending_event = {"event": ..., "candidates": [...]}. Buttons pin
          candidates to System B (replace) or leave everything untouched (keep). After
          resolution, if another override_conflict entry is queued in pending
          notifications, reopen the modal with its data.
        - Details-tab (legacy): pending_event is None. Buttons set main override to
          node_name with chosen mode (replace) or leave untouched (keep).
        """
        import time
        from event_callbacks import _format_override_conflict_body
        trigger = get_trigger_id()
        if pending_event:
            if trigger == 'btn-override-replace':
                ConfigManager.atomic_set_event_override(
                    pending_event.get("candidates", []), replace=True
                )
            elif trigger != 'btn-override-keep':
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
            # Advance to next queued conflict, if any (also an event-batch entry — keep radio hidden)
            nxt = ConfigManager.pop_next_override_conflict()
            if nxt:
                return (
                    True,
                    ConfigManager.get_override(),
                    f"override-{time.time()}",
                    {"event": nxt.get("event"), "candidates": nxt.get("candidate_nodes", [])},
                    _format_override_conflict_body(nxt),
                    {"display": "none"},
                )
            return False, ConfigManager.get_override(), f"override-{time.time()}", None, dash.no_update, dash.no_update

        if trigger == 'btn-override-keep':
            return False, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        elif trigger == 'btn-override-replace' and node_name:
            ConfigManager.clear_event_override_nodes()
            ConfigManager.set_override({"parent": node_name, "mode": mode or "hard"})
            return False, ConfigManager.get_override(), f"override-{time.time()}", dash.no_update, dash.no_update, dash.no_update
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

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

    # --- Competence Editor ---

    @app.callback(
        Output("modal-competence-editor", "is_open"),
        Output("competence-editor-body", "children"),
        Input("btn-competence-edit", "n_clicks"),
        Input("btn-competence-editor-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_competence_editor(edit_clicks, cancel_clicks):
        from layout import build_competence_editor_table
        if ctx.triggered_id == "btn-competence-edit":
            defs = ConfigManager.get_competence_definitions()
            return True, build_competence_editor_table(defs)
        return False, no_update

    @app.callback(
        Output("competence-popup-table-body", "children"),
        Output("modal-competence-editor", "is_open", allow_duplicate=True),
        Input("btn-competence-editor-save", "n_clicks"),
        State({"type": "competence-edit-essence", "index": ALL}, "value"),
        prevent_initial_call=True,
    )
    def save_competence_definitions(n_clicks, essences):
        from layout import build_competence_popup_table_rows
        defs = ConfigManager.get_competence_definitions()
        new_defs = []
        for i, d in enumerate(defs):
            new_defs.append({
                "stage": d["stage"],
                "essence": essences[i] if i < len(essences) else d["essence"],
            })
        ConfigManager.set_competence_definitions(new_defs)
        return build_competence_popup_table_rows(new_defs), False


