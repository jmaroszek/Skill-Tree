"""
Callback definitions for the Skill Tree Dash application.
"""

import json
import logging
import os
import subprocess
import urllib.parse
from datetime import date

from typing import List, Set

import dash
from dash import html, Input, Output, State, ALL, ctx, no_update, ClientsideFunction
import dash_bootstrap_components as dbc

from graph_manager import GraphManager
from event_manager import EventManager
from config import (ConfigManager, badge_style, sort_subcontexts, sort_contexts,
                    SIDEBAR_WIDTH_PX, SIDEBAR_WIDTH_NEG_PX, SIDEBAR_TRANSLATE_CLOSED,
                    DEFAULT_GRAPH_LAYOUT, DEFAULT_DETAILS_GRAPH_LAYOUT,
                    DEFAULT_EVENTS_GRAPH_LAYOUT)
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
    habit_to_hours, compute_habit_time_omp, resolve_time_mode, resolve_value_mode,
    habit_editor_view, parse_habit_days, ALL_WEEKDAYS, habit_preview_text,
)

logger = logging.getLogger(__name__)

manager = GraphManager()
event_manager = EventManager()


# core_engine has 28 outputs; this constant + helper let the tab-gating guard
# return a no_update tuple of the correct arity. test_core_engine_arity verifies
# that it stays in sync with the actual callback registration.
_CORE_ENGINE_NUM_OUTPUTS = 28

# Tabs whose own callbacks already refresh their content; switching to them
# should NOT trigger a graph regen via core_engine.
_NON_GRAPH_TABS = frozenset({"tab-events", "tab-analyze"})

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
_DETAILS_GOAL_SIDEBAR_STYLE_IDX = 18
_EVENTS_SIDEBAR_STYLE_IDX = 19


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


# Output slot indices for the undo-Done modal outputs.
_UNDO_DONE_MODAL_IDX = 20
_UNDO_DONE_BODY_IDX = 21
_PENDING_UNDO_DONE_IDX = 22

# Output slot indices for the time-calibration modal outputs.
_TIME_CALIB_MODAL_IDX = 23
_TIME_CALIB_REFERENCE_IDX = 24
_TIME_CALIB_PENDING_IDX = 25


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


def _calibration_modal_text(node):
    """Returns (title, prompt) for the time-calibration modal: the node name
    goes in the modal title, the prompt recalls its original estimate so the
    user can calibrate actual against estimated time."""
    est = getattr(node, 'time', 0) or 0
    if est > 0:
        prompt = (f"You estimated this project would take "
                  f"{ConfigManager.format_time_friendly(est)}. "
                  f"How long did it actually take?")
    else:
        prompt = "How long did it actually take?"
    return node.name, prompt


def _calibration_review_queue(manager):
    """Names of completed nodes eligible for the calibration review cycle:
    status Done, an own time estimate (> 0, so inherited-time Goals are
    excluded), no actual time captured yet, and not permanently dismissed.
    Returned in stable name order."""
    queue = []
    for n in manager.get_all_nodes():
        if n.status != STATUS_DONE:
            continue
        if (n.actual_time_lower is not None or n.actual_time_point is not None
                or n.actual_time_upper is not None):
            continue
        if n.calibration_dismissed:
            continue
        if n.time <= 0:
            continue
        queue.append(n.name)
    return sorted(queue)


def _calibration_unit_for(hours):
    """The Unit-dropdown value matching the friendly formatter's choice for
    `hours` (e.g. a ~3.5w estimate → 'weeks'). Years cap to 'months' — the
    modal dropdown offers only hours / weeks / months."""
    _, unit = ConfigManager.hours_to_friendly_unit(hours or 0)
    return 'months' if unit == 'years' else unit


def _calibration_prepop(node):
    """Pre-population values for the focused-review modal when it opens for
    `node`. Returns (time_lower, time_point, time_upper, time_unit, val,
    interest, diff) — all in the modal's display semantics (time values are
    in `time_unit`, NOT canonical hours; Submit converts on the way to the
    DB).

    Time point comes from `done_date - start_date` × productive
    hours_per_week (Settings → Time). Using `done_date` rather than `today`
    keeps the estimate accurate for nodes completed weeks ago. The display
    unit is chosen to match the magnitude (e.g. 140 elapsed hours → "1
    weeks"; 6 elapsed hours → "6 hours"). Lower/upper bounds stay blank —
    the user widens them only if they want to express uncertainty.

    V/I/E sliders default to the node's own estimates so the user's
    starting point is "same as I thought" and they only have to move
    sliders that actually diverged.
    """
    time_lower = None
    time_upper = None

    point_hours = None
    if node and node.start_date and node.done_date:
        try:
            start = date.fromisoformat(node.start_date)
            end = date.fromisoformat(node.done_date)
            delta_days = (end - start).days
        except (ValueError, TypeError):
            delta_days = None
        if delta_days is not None and delta_days >= 0:
            hpw = ConfigManager.get_time_settings().get('hours_per_week', 20)
            point_hours = max(0.0, delta_days / 7.0 * hpw)

    if point_hours is None:
        time_point = None
        time_unit = 'hours'
    else:
        time_unit = _calibration_unit_for(point_hours)
        mult = ConfigManager.get_time_multiplier(time_unit)
        time_point = round(point_hours / mult, 2) if mult > 0 else point_hours

    val = getattr(node, 'value', None) if node else None
    interest = getattr(node, 'interest', None) if node else None
    diff = getattr(node, 'difficulty', None) if node else None
    # Sliders need a numeric default if the node didn't carry one (e.g.
    # inherited-mode containers where the local rating is 0/None).
    if not val:
        val = 5
    if not interest:
        interest = 5
    if not diff:
        diff = 5

    return (time_lower, time_point, time_upper, time_unit, val, interest, diff)


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
    "position": "absolute", "top": "0", "left": "0", "width": SIDEBAR_WIDTH_PX,
    "minWidth": SIDEBAR_WIDTH_PX, "height": "100%", "zIndex": 1000,
    "overflowX": "hidden", "overflowY": "auto",
    "borderRight": "1px solid #495057", "transition": "transform 0.3s ease",
    "transform": SIDEBAR_TRANSLATE_CLOSED, "willChange": "transform",
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
        next_ed_style['transform'] = SIDEBAR_TRANSLATE_CLOSED
    elif trigger_id == 'btn-save':
        # Save only — keep editor open, don't change transform
        next_ed_style['transform'] = "translateX(0px)"
    elif trigger_id in ('btn-save-close', 'btn-node-delete-confirm', 'btn-close-editor', 'btn-unsaved-discard', 'btn-unsaved-save'):
        # btn-save-close and unsaved-save close it after saving.
        # btn-unsaved-discard closes without saving.
        # btn-close-editor only silently closes if the form is blank (otherwise modal handles it).
        if trigger_id in ('btn-unsaved-save', 'btn-unsaved-discard') and pending_nav_store == '__background__':
            # User dismissed via canvas click — close the editor after save/discard.
            next_ed_style['transform'] = SIDEBAR_TRANSLATE_CLOSED
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
                'aliases': form_state.get('alias_values'),
            })
            if not form_has_content:
                next_ed_style['transform'] = SIDEBAR_TRANSLATE_CLOSED
        else:
            next_ed_style['transform'] = SIDEBAR_TRANSLATE_CLOSED
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
        if goal_sidebar_style and goal_sidebar_style.get('left', SIDEBAR_WIDTH_NEG_PX) == '0px':
            next_goal_style = dict(goal_sidebar_style)
            next_goal_style['left'] = SIDEBAR_WIDTH_NEG_PX
        if events_sidebar_style and events_sidebar_style.get('left', SIDEBAR_WIDTH_NEG_PX) == '0px':
            next_events_sidebar_style = dict(events_sidebar_style)
            next_events_sidebar_style['left'] = SIDEBAR_WIDTH_NEG_PX
    return next_ed_style, next_goal_style, next_events_sidebar_style


def _friendly_time_estimates(time_o, time_m, time_p):
    """Convert stored hour values for display in the node editor.

    Uses weeks as the maximum unit — never months or years — so the editor
    always shows values in hours or weeks regardless of magnitude. Returns
    (o, m, p, unit_string).
    """
    max_hours = max(time_o or 0, time_m or 0, time_p or 0)
    _, unit = ConfigManager.hours_to_friendly_unit(max_hours)
    # Cap at weeks: months/years are too coarse for direct editing
    if unit in ('months', 'years'):
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
    # Always fetch dormant nodes too — filter_nodes decides whether to keep
    # them based on the `show_dormant` filter. Fetching unconditionally keeps
    # the include/exclude decision in one place (the filter pipeline).
    nodes = manager.get_all_nodes(include_dormant=True)
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
        node_classes = []
        if node.name in trigger_names:
            node_classes.append('trigger')
        if node.dormant:
            node_classes.append('dormant')
        if node.now:
            node_classes.append('now')
            node_data['data']['now_color'] = colors.get('Now', '#ffd000')
        # Always emit `classes` (possibly empty) so Cytoscape's element diff
        # actually clears the class when a node loses it — omitting the key
        # leaves the prior value in place and a node that was just cleared
        # of Now would keep its pulse.
        node_data['classes'] = ' '.join(node_classes)
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
    # Note: filter-subcontext.value is reset clientside (see below) because we
    # deliberately keep that prop free of server-side callback Outputs so Dash
    # preserves the layout-set value (used to restore Memory state).
    @app.callback(
        Output('filter-node-type', 'value'),
        Output('filter-context', 'value'),
        Output('community-method', 'value'),
        Output('filter-community', 'value'),
        Output('filter-value', 'value'),
        Output('filter-interest', 'value'),
        Output('filter-difficulty', 'value'),
        Output('filter-time', 'value'),
        Output('filter-time-unit', 'value'),
        Output('filter-done', 'value', allow_duplicate=True),
        Output('filter-dormant', 'value', allow_duplicate=True),
        Input('btn-clear-filters', 'n_clicks'),
        Input('btn-details-focus', 'n_clicks'),
        prevent_initial_call=True,
    )
    def clear_filters(_clear_clicks, _focus_clicks):
        return [], [], 'components', 'All', 1, 1, 10, None, 'hours', [], []

    # Clientside reset of filter-subcontext.value on Clear Filters / Focus.
    # Server-side reset would put a callback Output on this prop, which Dash
    # uses as license to discard the layout-set value on initial render.
    app.clientside_callback(
        """
        function(clear_clicks, focus_clicks) {
            if (!clear_clicks && !focus_clicks) {
                return window.dash_clientside.no_update;
            }
            return [];
        }
        """,
        Output('filter-subcontext', 'value', allow_duplicate=True),
        Input('btn-clear-filters', 'n_clicks'),
        Input('btn-details-focus', 'n_clicks'),
        prevent_initial_call=True,
    )

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

        # Identity marker — tooltip.js reads this to verify the rendered
        # content matches the currently hovered node before showing. Necessary
        # because Dash callback responses can lag cursor movement, so the
        # tooltip's children may briefly hold a previous node's data.
        marker = html.Span(
            node_id,
            className='_tt-marker',
            style={"display": "none"}
        )

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

            lines = [marker, header]

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

            lines = [marker, header]

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
         Output('node-habit-intensity-unit', 'value'),
         Output('node-habit-days', 'value')],
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
         State('node-priority-rank', 'value'),
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
         State('node-habit-intensity-unit', 'value'),
         State('node-habit-days', 'value')],
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
                        cur_time_mode, cur_priority_rank,
                        cur_aliases,
                        pending_nav, pristine_snapshot,
                        cur_value_mode,
                        cur_time_habit_mode,
                        cur_habit_duration, cur_habit_duration_unit,
                        cur_habit_int_o, cur_habit_int_m, cur_habit_int_p,
                        cur_habit_int_unit, cur_habit_days):
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
            'min_per_session',  # node-habit-intensity-unit
            list(ALL_WEEKDAYS),  # node-habit-days
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
                'habit_days': cur_habit_days,
                'value_mode': cur_value_mode,
                'priority_rank': cur_priority_rank,
                'aliases': cur_aliases,
            })

        if trigger_id == 'btn-new-node':
            editor_open = ed_style and ed_style.get('transform', '') == 'translateX(0px)'
            if editor_open and _has_unsaved_changes():
                # Show unsaved modal; store 'new-node' as pending action
                no_change = [dash.no_update] * 18 + [options]*5 + [dash.no_update]*22
                no_change[33] = '__new_node__'  # pending-navigation-store (special sentinel)
                no_change[34] = True            # modal-unsaved-changes
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
                    no_change[33] = '__background__'  # pending-navigation-store sentinel
                    no_change[34] = True              # modal-unsaved-changes
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
                no_change = [dash.no_update] * 18 + [options]*5 + [dash.no_update]*22
                no_change[33] = tapped_id  # pending-navigation-store
                no_change[34] = True       # modal-unsaved-changes
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

        # Map stored habit fields onto the per-session editor widgets (legacy
        # per-day/per-week units fold into the weekday picker; total preserved).
        habit_unit_val, habit_o_val, habit_m_val, habit_p_val, habit_days_val = (
            habit_editor_view(
                data.get('habit_intensity_unit'),
                data.get('habit_intensity_o', 0) or 0,
                data.get('habit_intensity_m', 0) or 0,
                data.get('habit_intensity_p', 0) or 0,
                data.get('habit_days'),
            )
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
            parse_links(data.get('obsidian_path', '')),
            parse_links(data.get('google_drive_path', '')),
            parse_links(data.get('website', '')),
            # Type-specific fields
            friendly_unit, friendly_unit,
            name,  # node-original-name — track what was loaded
            name if (trigger_id in ('edit-trigger-input', 'details-edit-trigger-input') or (ed_style and ed_style.get('transform', '') == 'translateX(0px)')) else dash.no_update,  # search-node — update when editor is open or edit-trigger
            rank_value,  # node-priority-rank
            time_mode_val,  # node-time-mode
            manager.get_aliases(name) or [''],  # aliases-store
            None,  # pending-navigation-store — clear on successful populate
            False,  # modal-unsaved-changes — close on successful populate
            build_editor_snapshot(manager, name),  # editor-pristine-snapshot
            value_mode_val,  # node-value-mode (appended)
            # Habit-mode fields
            time_habit_mode_val,
            data.get('habit_duration', 0) or 0,
            data.get('habit_duration_unit') or 'weeks',
            habit_o_val,
            habit_m_val,
            habit_p_val,
            habit_unit_val,
            habit_days_val,
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
         State('node-value-mode', 'value'),
         State('node-time-habit-mode', 'value'),
         State('node-habit-duration', 'value'),
         State('node-habit-duration-unit', 'value'),
         State('node-habit-intensity-o', 'value'),
         State('node-habit-intensity-m', 'value'),
         State('node-habit-intensity-p', 'value'),
         State('node-habit-intensity-unit', 'value'),
         State('node-habit-days', 'value')],
        prevent_initial_call=True,
    )
    def sync_original_name_after_save(_save_clicks, _save_close_clicks,
                                      cur_name, cur_type, cur_desc,
                                      cur_context, cur_subctx, cur_status_done,
                                      cur_val, cur_interest, cur_diff,
                                      cur_time_o, cur_time_m, cur_time_p, cur_time_unit,
                                      cur_needs_h, cur_needs_s, cur_supp_h, cur_supp_s, cur_helps,
                                      cur_obs, cur_drive, cur_website,
                                      cur_time_mode, cur_priority_rank,
                                      cur_value_mode,
                                      cur_time_habit_mode,
                                      cur_habit_duration, cur_habit_duration_unit,
                                      cur_habit_int_o, cur_habit_int_m, cur_habit_int_p,
                                      cur_habit_int_unit, cur_habit_days):
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
            'habit_days': cur_habit_days,
            'value_mode': cur_value_mode,
            'priority_rank': cur_priority_rank,
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
    app.clientside_callback(
        """
        function(time_mode_val, habit_mode_val) {
            var hidden_w = {display: 'none', width: '100px'};
            var visible_w = {width: '100px'};
            var inherit_on = !!(time_mode_val && time_mode_val.indexOf('inherited') >= 0);
            var habit_on = !!(habit_mode_val && habit_mode_val.indexOf('habit') >= 0);
            if (inherit_on) return [{display: 'none'}, {display: 'none'}, hidden_w];
            if (habit_on) return [{display: 'none'}, {}, hidden_w];
            return [{}, {display: 'none'}, visible_w];
        }
        """,
        Output('section-time-omp', 'style'),
        Output('section-time-habit', 'style'),
        Output('node-time-unit', 'style'),
        Input('node-time-mode', 'value'),
        Input('node-time-habit-mode', 'value'),
    )

    # --- Mutual exclusivity: Habit and Inherit cannot both be ON ---
    # Clientside to eliminate the visible flash of the "other" toggle
    # flipping on before the server bounces it off. Same fix pattern as
    # enforce_locked_time_mode above.
    app.clientside_callback(
        """
        function(inherit_val, habit_val) {
            var ctx = window.dash_clientside.callback_context;
            var triggered = (ctx && ctx.triggered) || [];
            var trig = triggered.length ? triggered[0].prop_id.split('.')[0] : null;
            if (trig === 'node-time-mode' && inherit_val && inherit_val.indexOf('inherited') >= 0) {
                return [inherit_val, []];
            }
            if (trig === 'node-time-habit-mode' && habit_val && habit_val.indexOf('habit') >= 0) {
                return [[], habit_val];
            }
            return [inherit_val, habit_val];
        }
        """,
        Output('node-time-mode', 'value', allow_duplicate=True),
        Output('node-time-habit-mode', 'value', allow_duplicate=True),
        Input('node-time-mode', 'value'),
        Input('node-time-habit-mode', 'value'),
        prevent_initial_call=True,
    )

    # --- Locked Inherit toggle for Goal / Milestone ---
    # Container types must always inherit time from their children. Forces
    # 'inherited' ON whenever the type is Goal or Milestone, and reveals an
    # inline warning if the user attempts to toggle it off. Runs clientside
    # so the bounce-back happens in the same paint cycle as the click — a
    # server round-trip causes the toggle to visibly flip OFF before
    # snapping back ON. The triggered-IDs check distinguishes user toggles
    # from form-populate cycles (where node-type also fires).
    app.clientside_callback(
        """
        function(time_mode_val, node_type) {
            var no_update = window.dash_clientside.no_update;
            var hidden = {display: "none"};
            var visible = {display: "block", color: "#dc3545", fontSize: "0.85rem"};
            var ctx = window.dash_clientside.callback_context;
            var triggered = (ctx && ctx.triggered) || [];
            var ids = triggered.map(function(t) { return t.prop_id.split('.')[0]; });
            var only_time_mode = ids.length === 1 && ids[0] === 'node-time-mode';

            if (node_type !== 'Goal' && node_type !== 'Milestone') {
                return [time_mode_val, hidden, ""];
            }
            var inherited_on = !!(time_mode_val && time_mode_val.indexOf('inherited') >= 0);
            if (inherited_on) {
                if (only_time_mode) return [no_update, no_update, no_update];
                return [no_update, hidden, ""];
            }
            var msg = "Inherit mode is required for " + node_type + " nodes — " +
                      "their time is the sum of their children's.";
            if (only_time_mode) return [['inherited'], visible, msg];
            return [['inherited'], hidden, ""];
        }
        """,
        Output('node-time-mode', 'value', allow_duplicate=True),
        Output('time-mode-warning', 'style'),
        Output('time-mode-warning', 'children'),
        Input('node-time-mode', 'value'),
        Input('node-type', 'value'),
        prevent_initial_call=True,
    )

    # --- Live total-hours preview for habit mode ---
    @app.callback(
        Output('node-habit-total-preview', 'children'),
        Input('node-habit-duration', 'value'),
        Input('node-habit-duration-unit', 'value'),
        Input('node-habit-intensity-m', 'value'),
        Input('node-habit-intensity-unit', 'value'),
        Input('node-habit-days', 'value'),
    )
    def update_habit_total_preview(duration, dur_unit, intensity_m, int_unit, days):
        return habit_preview_text(duration, dur_unit, intensity_m, int_unit, days)

    # --- Toggle Value/Interest/Effort sliders based on value_mode ---
    app.clientside_callback(
        """
        function(value_mode_val) {
            if (value_mode_val && value_mode_val.indexOf('inherited') >= 0) {
                return {display: 'none'};
            }
            return {};
        }
        """,
        Output('section-ratings', 'style'),
        Input('node-value-mode', 'value'),
    )

    # --- Locked Inherit-value toggle for Milestones ---
    # Milestones are transparent checkpoints: their own value/interest/effort
    # must never enter scoring. Force value_mode='inherited' ON whenever the
    # type is Milestone, and show an inline warning if the user tries to clear
    # it. Mirrors the Goal/Milestone time-mode lock above. Goals are NOT locked
    # here — a Goal legitimately carries its own value (see docs/modeling.md).
    # Clientside so the bounce-back happens in the same paint cycle as the
    # click. The triggered-IDs check distinguishes user toggles from form-
    # populate cycles (where node-type also fires).
    app.clientside_callback(
        """
        function(value_mode_val, node_type) {
            var no_update = window.dash_clientside.no_update;
            var hidden = {display: "none"};
            var visible = {display: "block", color: "#dc3545", fontSize: "0.85rem"};
            var ctx = window.dash_clientside.callback_context;
            var triggered = (ctx && ctx.triggered) || [];
            var ids = triggered.map(function(t) { return t.prop_id.split('.')[0]; });
            var only_value_mode = ids.length === 1 && ids[0] === 'node-value-mode';

            if (node_type !== 'Milestone') {
                return [no_update, hidden, ""];
            }
            var inherited_on = !!(value_mode_val && value_mode_val.indexOf('inherited') >= 0);
            if (inherited_on) {
                if (only_value_mode) return [no_update, no_update, no_update];
                return [no_update, hidden, ""];
            }
            var msg = "Inherit is required for Milestone nodes — they are " +
                      "checkpoints, so their own ratings don't affect scoring.";
            if (only_value_mode) return [['inherited'], visible, msg];
            return [['inherited'], hidden, ""];
        }
        """,
        Output('node-value-mode', 'value', allow_duplicate=True),
        Output('value-mode-warning', 'style'),
        Output('value-mode-warning', 'children'),
        Input('node-value-mode', 'value'),
        Input('node-type', 'value'),
        prevent_initial_call=True,
    )

    # --- Hide Effort slider on Goals; show caption instead ---
    # Effort on a Goal is decorative — _rank_goals omits it, total_value
    # doesn't cascade it, and w_t * time^beta dwarfs w_e * difficulty on
    # the Goal's own priority score. The caption tells the user why the
    # input is absent so the UI stops asking for a value the system ignores.
    app.clientside_callback(
        """
        function(node_type) {
            if (node_type === 'Goal') return [{display: 'none'}, {}];
            return [{}, {display: 'none'}];
        }
        """,
        Output('node-effort-row', 'style'),
        Output('node-effort-caption', 'style'),
        Input('node-type', 'value'),
    )

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
        Input('node-time-mode', 'value'),
        Input('node-time-habit-mode', 'value'),
        prevent_initial_call=True,
    )
    def validate_time_estimates(time_o, time_m, time_p, time_mode_val, habit_mode_val):
        """Enforce one of the supported (l, m, u) input patterns and the
        Lower <= Expected <= Upper ordering; disable Save on violation.

        Valid patterns (mirroring `blend_time_estimate` in models.py):
          - Expected only          {m}
          - Lower + Upper          {o, p}
          - All three              {o, m, p}

        Validation is skipped when the node uses inherited time (container
        draws from children) or habit mode (separate input section).
        """
        hidden = {"display": "none", "color": "#dc3545", "fontSize": "0.85rem"}
        visible = {"display": "block", "color": "#dc3545", "fontSize": "0.85rem"}

        if (time_mode_val and 'inherited' in time_mode_val) or \
           (habit_mode_val and 'habit' in habit_mode_val):
            return "", hidden, False, False

        o = float(time_o or 0)
        m = float(time_m or 0)
        p = float(time_p or 0)
        has_o, has_m, has_p = o > 0, m > 0, p > 0
        pattern = (has_o, has_m, has_p)

        valid_patterns = {
            (False, True, False),   # m only
            (True, False, True),    # o + p
            (True, True, True),     # all three
        }

        if pattern == (False, False, False):
            return ("Enter at least an Expected estimate, or both Lower and Upper.",
                    visible, True, True)

        if pattern not in valid_patterns:
            if pattern == (True, False, False):
                msg = "Lower alone is not enough — also enter Upper, or use Expected instead."
            elif pattern == (False, False, True):
                msg = "Upper alone is not enough — also enter Lower, or use Expected instead."
            elif pattern == (True, True, False):
                msg = "Lower + Expected is not a valid pair — also enter Upper, or drop Lower."
            elif pattern == (False, True, True):
                msg = "Expected + Upper is not a valid pair — also enter Lower, or drop Upper."
            else:
                msg = "Invalid time-estimate combination."
            return msg, visible, True, True

        errors = []
        if has_o and has_m and o > m:
            errors.append("Lower must be ≤ Expected")
        if has_m and has_p and m > p:
            errors.append("Expected must be ≤ Upper")
        if has_o and has_p and o > p:
            errors.append("Lower must be ≤ Upper")

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
         Output('cytoscape-graph', 'stylesheet'),
         Output('btn-clear-focus', 'style'),
         Output('details-goal-sidebar', 'style', allow_duplicate=True),
         Output('events-sidebar-container', 'style', allow_duplicate=True),
         Output('modal-undo-done-confirm', 'is_open'),
         Output('undo-done-confirm-body', 'children'),
         Output('pending-undo-done-store', 'data'),
         Output('modal-time-calibration', 'is_open'),
         Output('time-calibration-reference', 'children'),
         Output('time-calibration-pending-store', 'data'),
         Output('time-calibration-unit', 'value', allow_duplicate=True),
         Output('time-calibration-title', 'children', allow_duplicate=True)],

        [Input('btn-save', 'n_clicks'), Input('btn-save-close', 'n_clicks'), Input('btn-node-delete-confirm', 'n_clicks'),
         Input('filter-context', 'value'), Input('filter-subcontext', 'value'), Input('filter-done', 'value'),
         Input('filter-dormant', 'value'),
         Input('search-node', 'value'),
         Input('cytoscape-graph', 'tapNodeData'),
         Input('filter-community', 'value'), Input('community-method', 'value'),
         Input('filter-value', 'value'), Input('filter-interest', 'value'),
         Input('filter-time', 'value'), Input('filter-time-unit', 'value'),
         Input('filter-difficulty', 'value'),
         Input('suggestion-count-store', 'data'),
         Input('btn-edit-node', 'n_clicks'), Input('btn-add', 'n_clicks'), Input('btn-new-node', 'n_clicks'),
         Input('btn-close-editor', 'n_clicks'), Input('btn-goals-toggle', 'n_clicks'),
         Input('btn-unsaved-save', 'n_clicks'), Input('btn-unsaved-discard', 'n_clicks'),
         Input('settings-save-status', 'children'),
         Input('modal-migration', 'is_open'),
         Input('btn-toggle-done-node', 'n_clicks'),
         Input('group-delete-input', 'value'),
         Input('filter-node-type', 'value'),
         Input('selected-suggestion-store', 'data'),
         Input('focus-goal-store', 'data'),
         Input('edit-trigger-input', 'value'),
         Input('details-edit-trigger-input', 'value'),
         Input('toggle-done-trigger-input', 'value'),
         Input('node-now-trigger-input', 'value'),
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
         State('node-habit-intensity-unit', 'value'),
         State('node-habit-days', 'value')],
        prevent_initial_call='initial_duplicate'
    )
    def core_engine(save_clicks, save_close_clicks, delete_confirm_clicks, f_context, f_subcontext, f_done, f_show_dormant, search_val,
                     tapped_node,  # Cytoscape tapNodeData dict (not a Node object)
                     f_community, community_method, f_value, f_interest, f_time, f_time_unit, f_difficulty, sugg_count,
                     btn_edit, btn_add, btn_new_node, btn_close_ed, btn_goals_toggle, btn_unsaved_save, btn_unsaved_discard, settings_save_status, migration_open, btn_toggle_done,
                     group_delete_data, f_node_types,
                     active_suggestion_id,
                     focus_goal,
                     edit_trigger_data, details_edit_trigger_data, toggle_done_trigger_data, _node_now_trigger, _events_refresh, _details_refresh, _bg_click,
                     gs_max_depth, gs_neighbor_links, active_tab, _relayout, _sidebar_relayout,
                     btn_undo_done_confirm,
                     name, n_type, desc, context, subctx, status_done, val, interest, diff,
                     time_o, time_m, time_p, time_unit,
                     e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                     obs_link_values, drive_link_values, website_link_values,
                     current_elements, ed_style, original_name,
                     time_mode_val, priority_rank_val,
                     goal_sidebar_style, events_sidebar_style, pending_nav_store, alias_values,
                     pristine_snapshot, pending_undo_done,
                     value_mode_val,
                     time_habit_mode_val,
                     habit_duration, habit_duration_unit,
                     habit_int_o, habit_int_m, habit_int_p, habit_int_unit,
                     habit_days):
        """Central state callback handling node CRUD, filtering, and UI updates.

        This is intentionally a single large callback because Dash requires each Output
        to belong to exactly one callback. Since save/delete/filter operations all need
        to refresh the graph elements and sidebar state, they must share one callback.
        """
                     
        trigger_id = get_trigger_id()

        # Tab-switch gate: switching to Events/Analyze doesn't need a graph
        # regen — those tabs have their own refresh callbacks. Short-circuit
        # to no_update so we skip the scoring + generate_elements cycle.
        if trigger_id == 'main-tabs' and active_tab in _NON_GRAPH_TABS:
            return _core_engine_noop_tuple()

        # Settings-save gate: we trigger off `settings-save-status` (not the
        # raw save-button click) so this runs AFTER save_settings has written
        # the new contexts/types to the DB — otherwise we'd race the write and
        # re-read stale config, leaving the context/type dropdowns showing
        # values the user just deleted. Only the "Settings saved" message means
        # config was actually persisted with no migration pending; the auto-clear
        # to "", the "Migration required" message (the modal-close path handles
        # that), and "Error..." carry no config change to render.
        if trigger_id == 'settings-save-status' and settings_save_status != 'Settings saved':
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
                'habit_days': habit_days,
                'value_mode_val': value_mode_val,
                'priority_rank_val': priority_rank_val,
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

        filters = build_filters(f_context, f_subcontext, f_done, f_value, f_interest, f_time, f_difficulty, f_node_types, f_time_unit=f_time_unit, f_show_dormant=f_show_dormant)

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
                    next_ed_style['transform'] = SIDEBAR_TRANSLATE_CLOSED
                    return _core_engine_save_error_tuple("", next_ed_style, next_goal_style, next_events_sidebar_style)
            if not n_type:
                msg = "Error: Node type is required."
                return _core_engine_save_error_tuple(msg, next_ed_style, next_goal_style, next_events_sidebar_style)
            try:
                # Track if this save marks the node Done. Only count a true
                # Open/Blocked → Done transition (or a brand-new node created
                # Done) — re-saving an already-Done node must not re-trigger
                # the time-calibration modal.
                if status_done and STATUS_DONE in (status_done or []):
                    _prior_for_completion = manager.get_node(name)
                    if not (_prior_for_completion
                            and _prior_for_completion.status == STATUS_DONE):
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
                        habit_int_unit or 'min_per_session', habit_days,
                    )
                # Mirror time_mode: the shared resolver centralizes the
                # Milestone-must-inherit-value invariant (Goals are exempt —
                # they carry their own value).
                value_mode = resolve_value_mode(n_type, value_mode_val)
                msg = handle_save(manager, name, n_type, desc, val, t_o, t_m, t_p,
                                  interest, diff, status_done, context, subctx,
                                  obs_path, drive_path, website_path,
                                  e_needs_h, e_needs_s,
                                  e_supp_h, e_supp_s, e_helps,
                                  time_mode=time_mode,
                                  value_mode=value_mode,
                                  habit_duration=habit_duration or 0,
                                  habit_duration_unit=habit_duration_unit or 'weeks',
                                  habit_intensity_o=habit_int_o or 0,
                                  habit_intensity_m=habit_int_m or 0,
                                  habit_intensity_p=habit_int_p or 0,
                                  habit_intensity_unit=habit_int_unit or 'min_per_session',
                                  habit_days=habit_days)

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
            except (ValueError, TypeError) as e:
                msg = f"Error: {e}"
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

            # Populate dynamic contexts datalists from DB + Config, sorted per user setting.
            base_ctx = sort_contexts(ConfigManager.get_contexts())

            ctx_list = [{"label": c, "value": c} for c in base_ctx]
            f_ctx_list = [{"label": c, "value": c} for c in base_ctx]

            base_types = ConfigManager.get_node_types()
            type_list = [{"label": t, "value": t} for t in base_types]

            f_type_list = [{"label": t, "value": t} for t in base_types]

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

        # Time-calibration: when an explicit single-node completion just
        # happened and the feature is enabled, open the modal to capture how
        # long the work actually took. completion_check_node is set only on
        # the explicit single-node completion paths (graph tap, context-menu,
        # editor save) — auto-cascade and bulk completion never set it.
        tc_modal_open = False
        tc_reference = ""
        tc_pending = None
        tc_unit = no_update  # only set the dropdown when the modal opens
        tc_title = no_update
        if completion_check_node and ConfigManager.get_time_calibration_enabled():
            _tc_node = manager.get_node(completion_check_node)
            if _tc_node is not None:
                tc_modal_open = True
                tc_title, tc_reference = _calibration_modal_text(_tc_node)
                tc_pending = {'mode': 'single', 'node': completion_check_node}
                tc_unit = _calibration_unit_for(_tc_node.time)

        # Last 6 outputs: the undo-Done modal trio followed by the
        # time-calibration modal trio. The undo-Done path either opens its
        # modal earlier (return short-circuit in the toggle branch) or, as
        # here, leaves it closed with the pending store cleared.
        return (elements, msg, sugg_ui, hard_chains_ui, soft_chains_ui, synergies_ui, description_ui, False if msg else True, 0, community_options, search_options, next_ed_style, f_ctx_list, ctx_list, type_list, f_type_list, active_stylesheet, clear_focus_style, next_goal_style, next_events_sidebar_style, False, "", None, tc_modal_open, tc_reference, tc_pending, tc_unit, tc_title)

    # The filters-sidebar toggle and editor-sidebar fast-path clientside
    # callbacks live in sidebars_callbacks.register_sidebars_callbacks.

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

    # --- Time-Calibration Modal: Submit / Skip / Don't ask again ---
    # The modal serves three flows, distinguished by the 'mode' in
    # time-calibration-pending-store:
    #   'single' — opened by core_engine after one explicit completion.
    #   'review' — opened by the review-launch callback; cycles a queue of
    #              completed nodes, advancing on each Submit/Skip/Dismiss.
    #   'edit'   — opened by review_hub_callbacks.open_calibration_from_history
    #              for editing an already-rated node. Same write semantics as
    #              'single'; on close, re-opens the hub on the History tab.
    # Submit writes actual_time_* (canonical hours) AND reflect_value/
    # interest/difficulty; Skip leaves all four dimensions NULL; "Don't ask
    # again" sets calibration_dismissed without touching the rating columns.
    # Inputs reset between nodes; pre_populate_calibration_inputs (driven by
    # the store) replaces the reset with node-specific defaults.
    @app.callback(
        Output('modal-time-calibration', 'is_open', allow_duplicate=True),
        Output('time-calibration-pending-store', 'data', allow_duplicate=True),
        Output('save-output', 'children', allow_duplicate=True),
        Output('time-calibration-lower', 'value'),
        Output('time-calibration-point', 'value'),
        Output('time-calibration-upper', 'value'),
        Output('time-calibration-unit', 'value'),
        Output('calibration-value', 'value'),
        Output('calibration-interest', 'value'),
        Output('calibration-difficulty', 'value'),
        Output('time-calibration-reference', 'children', allow_duplicate=True),
        Output('calibration-review-progress', 'value', allow_duplicate=True),
        Output('calibration-review-progress', 'label', allow_duplicate=True),
        Output('time-calibration-complete', 'children', allow_duplicate=True),
        Output('time-calibration-title', 'children', allow_duplicate=True),
        Output('modal-review-hub', 'is_open', allow_duplicate=True),
        Output('review-hub-tabs', 'active_tab', allow_duplicate=True),
        Input('btn-time-calibration-submit', 'n_clicks'),
        Input('btn-time-calibration-skip', 'n_clicks'),
        Input('btn-time-calibration-dismiss', 'n_clicks'),
        State('time-calibration-lower', 'value'),
        State('time-calibration-point', 'value'),
        State('time-calibration-upper', 'value'),
        State('time-calibration-unit', 'value'),
        State('calibration-value', 'value'),
        State('calibration-interest', 'value'),
        State('calibration-difficulty', 'value'),
        State('time-calibration-pending-store', 'data'),
        prevent_initial_call=True,
    )
    def handle_time_calibration(_submit, _skip, _dismiss, lower, point, upper,
                                unit, val, interest, diff, pending):
        # cleared inputs for the next node: 4 time slots + 3 V/I/E sliders
        reset = (None, None, None, 'hours', 5, 5, 5)
        trig = get_trigger_id()
        pending = pending if isinstance(pending, dict) else {}
        mode = pending.get('mode')

        if mode == 'review':
            queue = pending.get('queue', [])
            idx = pending.get('index', 0)
            node_name = queue[idx] if 0 <= idx < len(queue) else None
        elif mode in ('single', 'edit'):
            queue, idx = [], 0
            node_name = pending.get('node')
        else:
            # Stale / no pending node — just close.
            return (False, None, no_update, *reset,
                    no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update)

        node = manager.get_node(node_name) if node_name else None

        # Apply the chosen action to the current node.
        if node is not None:
            if trig == 'btn-time-calibration-submit':
                mult = ConfigManager.get_time_multiplier(unit or 'hours')

                def _to_hours(v):
                    return float(v) * mult if v not in (None, '') else None

                node.actual_time_lower = _to_hours(lower)
                node.actual_time_point = _to_hours(point)
                node.actual_time_upper = _to_hours(upper)
                node.actual_time_unit = unit or 'hours'
                node.reflect_value = int(val) if val is not None else None
                node.reflect_interest = int(interest) if interest is not None else None
                node.reflect_difficulty = int(diff) if diff is not None else None
                manager.update_node(node)
            elif trig == 'btn-time-calibration-dismiss':
                node.calibration_dismissed = 1
                manager.update_node(node)
            # Skip / Cancel: no write.

        if mode == 'single':
            msg = (f"Logged actuals for '{node.name}'."
                   if (trig == 'btn-time-calibration-submit' and node) else no_update)
            return (False, None, msg, *reset,
                    no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update)

        if mode == 'edit':
            # Submit or Cancel both close the modal and bounce the user back
            # to the History tab. Submit emits a save-output toast so the
            # change is visible even after the hub re-opens.
            msg = (f"Updated actuals for '{node.name}'."
                   if (trig == 'btn-time-calibration-submit' and node) else no_update)
            return (False, None, msg, *reset,
                    no_update, no_update, no_update, no_update, no_update,
                    True, 'tab-review-history')

        # Review mode — advance to the next node, or finish.
        n = len(queue)
        next_idx = idx + 1
        if next_idx < n:
            nxt = manager.get_node(queue[next_idx])
            if nxt is not None:
                next_title, ref = _calibration_modal_text(nxt)
            else:
                next_title, ref = "", ""
            new_store = {'mode': 'review', 'queue': queue, 'index': next_idx}
            human = next_idx + 1  # 1-based node number now showing
            pct = round(human / n * 100)
            next_unit = _calibration_unit_for(nxt.time) if nxt else 'hours'
            return (True, new_store, no_update,
                    None, None, None, next_unit, 5, 5, 5,
                    ref, pct, f"{human} / {n}", no_update, next_title,
                    no_update, no_update)
        # Last node done — switch to the completion screen (stays open).
        complete_msg = html.Div([
            html.Div("✓", className="text-success",
                     style={"fontSize": "2.4rem", "lineHeight": "1"}),
            html.H5("All caught up", className="mt-2 mb-1"),
            html.P(f"You reflected on {n} completed node(s).",
                   className="text-muted small mb-0"),
        ])
        return (True, {'mode': 'complete'},
                f"Reflection complete — {n} node(s).",
                *reset, no_update, 100, f"{n} / {n}", complete_msg,
                "Reflection complete", no_update, no_update)

    # --- Calibration Review: launch the cycle ---
    # Fired by the "Start review" button inside the Review Hub modal.
    # The toolbar's clock-history icon opens the hub (see
    # review_hub_callbacks.toggle_review_hub); from the hub, this button kicks
    # off the focused-review queue. Output('modal-review-hub', 'is_open') is
    # additionally driven to False so the hub closes as the queue opens — the
    # two modals shouldn't be visible at once.
    @app.callback(
        Output('modal-time-calibration', 'is_open', allow_duplicate=True),
        Output('time-calibration-pending-store', 'data', allow_duplicate=True),
        Output('time-calibration-reference', 'children', allow_duplicate=True),
        Output('calibration-review-progress', 'value', allow_duplicate=True),
        Output('calibration-review-progress', 'label', allow_duplicate=True),
        Output('calibration-review-toast', 'is_open'),
        Output('calibration-review-toast', 'children'),
        Output('time-calibration-unit', 'value', allow_duplicate=True),
        Output('time-calibration-title', 'children', allow_duplicate=True),
        Output('modal-review-hub', 'is_open', allow_duplicate=True),
        Input('btn-hub-pending-launch', 'n_clicks'),
        prevent_initial_call=True,
    )
    def launch_calibration_review(_n):
        queue = _calibration_review_queue(manager)
        if not queue:
            # Leave the hub open so the user sees the toast without losing
            # their place in the hub.
            return (no_update, no_update, no_update, no_update, no_update,
                    True, "All completed nodes are already reflected on or excluded.",
                    no_update, no_update, no_update)
        first = manager.get_node(queue[0])
        title, ref = _calibration_modal_text(first) if first else ("", "")
        store = {'mode': 'review', 'queue': queue, 'index': 0}
        n = len(queue)
        unit = _calibration_unit_for(first.time) if first else 'hours'
        return (True, store, ref, round(1 / n * 100), f"1 / {n}", False,
                no_update, unit, title, False)

    # --- Calibration Review: close the completion screen ---
    @app.callback(
        Output('modal-time-calibration', 'is_open', allow_duplicate=True),
        Input('btn-time-calibration-done', 'n_clicks'),
        prevent_initial_call=True,
    )
    def close_calibration_review(_n):
        return False

    # --- Calibration modal chrome: mode-dependent buttons / progress / panels ---
    @app.callback(
        Output('btn-time-calibration-dismiss', 'style'),
        Output('btn-time-calibration-skip', 'style'),
        Output('btn-time-calibration-submit', 'style'),
        Output('btn-time-calibration-done', 'style'),
        Output('calibration-review-progress-wrap', 'style'),
        Output('time-calibration-active', 'style'),
        Output('time-calibration-complete', 'style'),
        Output('btn-time-calibration-skip', 'children'),
        Input('time-calibration-pending-store', 'data'),
        prevent_initial_call=True,
    )
    def _calibration_modal_chrome(pending):
        mode = pending.get('mode') if isinstance(pending, dict) else None
        hide = {"display": "none"}
        if mode == 'complete':
            # Completion screen: only "Done", progress + completion panel.
            return (hide, hide, hide, {}, {}, hide, {}, "Skip")
        if mode == 'review':
            return ({}, {}, {}, hide, {}, {}, hide, "Skip for now")
        if mode == 'edit':
            # Dismiss makes no sense for an already-rated node; Skip is
            # relabeled "Cancel" so the no-write semantic reads as intended.
            return (hide, {}, {}, hide, hide, {}, hide, "Cancel")
        # single (or cleared) — completion-modal layout.
        return (hide, {}, {}, hide, hide, {}, hide, "Skip")

    # --- Calibration modal cleanup: clear state when the modal closes ---
    # Covers the corner-X abort (which closes the modal without firing any
    # footer button) so a half-finished review queue isn't left in the store.
    @app.callback(
        Output('time-calibration-pending-store', 'data', allow_duplicate=True),
        Output('time-calibration-lower', 'value', allow_duplicate=True),
        Output('time-calibration-point', 'value', allow_duplicate=True),
        Output('time-calibration-upper', 'value', allow_duplicate=True),
        Output('time-calibration-unit', 'value', allow_duplicate=True),
        Output('calibration-value', 'value', allow_duplicate=True),
        Output('calibration-interest', 'value', allow_duplicate=True),
        Output('calibration-difficulty', 'value', allow_duplicate=True),
        Input('modal-time-calibration', 'is_open'),
        State('time-calibration-pending-store', 'data'),
        prevent_initial_call=True,
    )
    def _calibration_modal_closed(is_open, pending):
        if is_open or pending is None:
            return (no_update,) * 8
        return None, None, None, None, 'hours', 5, 5, 5

    # --- Calibration modal pre-population: fill inputs when the store changes
    # to point at a new node ---
    # Single source of truth for "what values does the user see when the
    # modal opens / advances / re-opens for editing". Triggered by every
    # store-mode transition that names a node (single, review, edit). Fires
    # after the store-setting callback (core_engine / launch /
    # handle_time_calibration / Phase-6 edit hand-off) so its outputs win on
    # the same flush cycle.
    @app.callback(
        Output('time-calibration-lower', 'value', allow_duplicate=True),
        Output('time-calibration-point', 'value', allow_duplicate=True),
        Output('time-calibration-upper', 'value', allow_duplicate=True),
        Output('time-calibration-unit', 'value', allow_duplicate=True),
        Output('calibration-value', 'value', allow_duplicate=True),
        Output('calibration-interest', 'value', allow_duplicate=True),
        Output('calibration-difficulty', 'value', allow_duplicate=True),
        Input('time-calibration-pending-store', 'data'),
        prevent_initial_call=True,
    )
    def pre_populate_calibration_inputs(pending):
        if not isinstance(pending, dict):
            return (no_update,) * 7
        mode = pending.get('mode')
        if mode == 'single':
            node_name = pending.get('node')
        elif mode == 'review':
            queue = pending.get('queue', [])
            idx = pending.get('index', 0)
            node_name = queue[idx] if 0 <= idx < len(queue) else None
        else:
            # 'complete' or unrecognized — don't touch the inputs.
            return (no_update,) * 7
        node = manager.get_node(node_name) if node_name else None
        if not node:
            return (no_update,) * 7
        return _calibration_prepop(node)

    # --- Calibration review button: hidden when the feature is off ---
    # Re-evaluated on load and on every tab switch — a tab switch is the
    # natural action after toggling the setting in Settings, and it happens
    # after the save has committed, so there's no read-before-write race.
    @app.callback(
        Output('btn-calibration-review', 'style'),
        Input('app-load-interval', 'n_intervals'),
        Input('main-tabs', 'active_tab'),
    )
    def _calibration_review_button_visibility(_n, _active_tab):
        if ConfigManager.get_time_calibration_enabled():
            return {"display": "inline-block"}
        return {"display": "none"}

    # --- Calibration: editor read-only "excluded" badge ---
    # Keyed off node-original-name (set when a node loads into the editor) so
    # it stays decoupled from the large populate_editor callback.
    @app.callback(
        Output('node-calibration-dismissed-badge', 'children'),
        Output('node-calibration-dismissed-badge', 'style'),
        Input('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def _calibration_editor_badge(original_name):
        node = manager.get_node(original_name) if original_name else None
        if node is not None and node.calibration_dismissed:
            return ("Excluded from calibration review — restore in Settings.",
                    {"display": "block"})
        return "", {"display": "none"}

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
         State('node-priority-rank', 'value'),
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
                              time_mode_val, priority_rank_val,
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
            'priority_rank': priority_rank_val,
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
        return (f"{t['n_nodes']} nodes \u00b7 {t['n_edges']} edges \u00b7 "
                f"{t['total_ms']:.0f}ms")

    @app.callback(
        Output('canvas-node-count', 'children'),
        Input('cytoscape-graph', 'elements'),
        Input('filter-node-type', 'value'),
        Input('filter-context', 'value'),
        Input('filter-subcontext', 'value'),
        Input('filter-community', 'value'),
        Input('community-method', 'value'),
        Input('filter-value', 'value'),
        Input('filter-interest', 'value'),
        Input('filter-difficulty', 'value'),
        Input('filter-time', 'value'),
        Input('filter-time-unit', 'value'),
        Input('filter-done', 'value'),
        Input('graph-settings-max-depth', 'value'),
    )
    def update_canvas_node_count(elements, f_type, f_ctx, f_sub,
                                 f_comm, f_comm_method, f_val, f_int,
                                 f_diff, f_time, f_time_unit, f_done, max_depth):
        n = sum(1 for el in (elements or []) if 'source' not in el.get('data', {}))
        text = f"{n} node{'s' if n != 1 else ''}"
        # Non-default max-depth (anything other than 0 = "All") narrows the
        # rendered subtree just like a filter does — surface it the same way.
        depth_active = bool(max_depth)
        if depth_active or is_filters_active(
                node_type=f_type, context=f_ctx, subcontext=f_sub,
                community=f_comm,
                community_method=f_comm_method, value=f_val,
                interest=f_int, difficulty=f_diff, time=f_time,
                done=f_done):
            return f"{text} · filtered"
        return text

    @app.callback(
        Output('next-filter-indicator', 'children'),
        Input('filter-node-type', 'value'),
        Input('filter-context', 'value'),
        Input('filter-subcontext', 'value'),
        Input('filter-community', 'value'),
        Input('community-method', 'value'),
        Input('filter-value', 'value'),
        Input('filter-interest', 'value'),
        Input('filter-difficulty', 'value'),
        Input('filter-time', 'value'),
        Input('filter-time-unit', 'value'),
        Input('filter-done', 'value'),
    )
    def update_next_filter_indicator(f_type, f_ctx, f_sub, f_comm,
                                     f_comm_method, f_val, f_int, f_diff,
                                     f_time, f_time_unit, f_done):
        if is_filters_active(
                node_type=f_type, context=f_ctx, subcontext=f_sub,
                community=f_comm,
                community_method=f_comm_method, value=f_val,
                interest=f_int, difficulty=f_diff, time=f_time,
                done=f_done):
            return "filtered"
        return ""

    @app.callback(
        Output('filter-remember', 'value'),
        Input('filter-remember', 'value'),
        State('filter-node-type', 'value'),
        State('filter-context', 'value'),
        State('filter-subcontext', 'value'),
        State('community-method', 'value'),
        State('filter-community', 'value'),
        State('filter-value', 'value'),
        State('filter-interest', 'value'),
        State('filter-difficulty', 'value'),
        State('filter-time', 'value'),
        State('filter-time-unit', 'value'),
        State('filter-done', 'value'),
        State('filter-dormant', 'value'),
        prevent_initial_call=True,
    )
    def persist_remember_filters(val, f_type, f_ctx, f_sub, f_comm_method,
                                 f_comm, f_val, f_int, f_diff, f_time, f_time_unit, f_done, f_show_dormant):
        enabled = bool(val and "enabled" in val)
        ConfigManager.set_remember_filters(enabled)
        # When the user flips Memory ON, snapshot the *current* sidebar state
        # so a refresh restores what they see now, not whatever stale state
        # was left in the DB from a previous Memory-on session.
        if enabled:
            ConfigManager.set_filters({
                "node_type": f_type or [],
                "context": f_ctx or [],
                "subcontext": f_sub or [],
                "community_method": f_comm_method or "components",
                "community": f_comm or "All",
                "value": f_val if f_val is not None else 1,
                "interest": f_int if f_int is not None else 1,
                "difficulty": f_diff if f_diff is not None else 10,
                "time": f_time if f_time is not None else "",
                "time_unit": f_time_unit or "hours",
                "done": f_done or [],
                "show_dormant": f_show_dormant or [],
            })
        return no_update

    @app.callback(
        Output('filter-persist-sink', 'data'),
        Input('filter-node-type', 'value'),
        Input('filter-context', 'value'),
        Input('filter-subcontext', 'value'),
        Input('community-method', 'value'),
        Input('filter-community', 'value'),
        Input('filter-value', 'value'),
        Input('filter-interest', 'value'),
        Input('filter-difficulty', 'value'),
        Input('filter-time', 'value'),
        Input('filter-time-unit', 'value'),
        Input('filter-done', 'value'),
        Input('filter-dormant', 'value'),
    )
    def persist_filters(f_type, f_ctx, f_sub, f_comm_method, f_comm,
                        f_val, f_int, f_diff, f_time, f_time_unit, f_done, f_show_dormant):
        if not ConfigManager.get_remember_filters():
            return no_update
        ConfigManager.set_filters({
            "node_type": f_type or [],
            "context": f_ctx or [],
            "subcontext": f_sub or [],
            "community_method": f_comm_method or "components",
            "community": f_comm or "All",
            "value": f_val if f_val is not None else 1,
            "interest": f_int if f_int is not None else 1,
            "difficulty": f_diff if f_diff is not None else 10,
            "time": f_time if f_time is not None else "",
            "time_unit": f_time_unit or "hours",
            "done": f_done or [],
            "show_dormant": f_show_dormant or [],
        })
        return no_update

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

    # Clear node-subcontext value when the new context doesn't include it.
    # populate_editor sets a valid pair on edit-load, so this no-ops then;
    # only a user-driven context change to an incompatible context clears.
    app.clientside_callback(
        """
        function(ctx, currentSub, options) {
            if (!currentSub) return window.dash_clientside.no_update;
            const opts = options || [];
            for (let i = 0; i < opts.length; i++) {
                if (opts[i] && opts[i].value === currentSub) {
                    return window.dash_clientside.no_update;
                }
            }
            return '';
        }
        """,
        Output('node-subcontext', 'value', allow_duplicate=True),
        Input('node-subcontext', 'options'),
        State('node-subcontext', 'value'),
        State('node-subcontext', 'options'),
        prevent_initial_call=True,
    )

    # Server-side: only update OPTIONS. Dash strips the layout's `value=` for
    # any prop that has a server-side callback Output, which would nuke the
    # memory-restored picks. By leaving `value` untouched here, the dropdown's
    # value comes only from layout init + user interaction + clientside resets
    # (below), so the persisted value sticks.
    @app.callback(
        Output('filter-subcontext', 'options'),
        Input('filter-context', 'value'),
    )
    def update_filter_subcontexts(ctx):
        if not ctx or ctx == "All" or (isinstance(ctx, list) and not ctx):
            return []
        contexts = ctx if isinstance(ctx, list) else [ctx]
        all_subs = ConfigManager.get_subcontexts()
        multi_context = len(contexts) > 1
        opts = []
        for c in contexts:
            none_label = f"{c} > None" if multi_context else "None"
            opts.append({"label": none_label, "value": f"{c}\x1f"})
            for s in sort_subcontexts(all_subs.get(c, [])):
                label = f"{c} > {s}" if multi_context else s
                opts.append({"label": label, "value": f"{c}\x1f{s}"})
        return opts

    # When the user changes context, prune any subcontext picks whose context
    # is no longer in the selection. Clientside only — see note above on why
    # filter-subcontext.value has no server-side callback Output.
    app.clientside_callback(
        """
        function(ctx, current_subs) {
            if (!current_subs || current_subs.length === 0) {
                return window.dash_clientside.no_update;
            }
            const contexts = Array.isArray(ctx) ? ctx : (ctx ? [ctx] : []);
            const ctxSet = new Set(contexts);
            const SEP = '\\u001f';
            const kept = current_subs.filter(v => {
                const sep = v.indexOf(SEP);
                if (sep < 0) return false;
                return ctxSet.has(v.slice(0, sep));
            });
            if (kept.length === current_subs.length) {
                return window.dash_clientside.no_update;
            }
            return kept;
        }
        """,
        Output('filter-subcontext', 'value'),
        Input('filter-context', 'value'),
        State('filter-subcontext', 'value'),
        prevent_initial_call=True,
    )



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
                    initial_dir=ConfigManager.get_gdrive_path() or '',
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
    # the closed translateX. Only writing when the tab actually needs to change
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
        Input('btn-close-graph-settings', 'n_clicks'),
        State('graph-settings-panel', 'style'),
        prevent_initial_call=True,
    )
    def toggle_graph_settings(_n_open, _n_close, current_style):
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
            gl.get('edge_length', DEFAULT_GRAPH_LAYOUT['edge_length']),
            gl.get('gravity', DEFAULT_GRAPH_LAYOUT['gravity']),
            gl.get('repulsion', DEFAULT_GRAPH_LAYOUT['repulsion']),
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
                nodeRepulsion: repulsion || 50000,
                gravity: (gravity !== null && gravity !== undefined) ? gravity : 0,
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

    # --- Editor Now Toggle: populate switch from DB on node change ---
    # Mirrors the dormant-toggle population pattern (event_callbacks.py).
    # The DB is the source of truth; the switch never holds a value the DB
    # doesn't agree with.
    @app.callback(
        Output("node-now", "value"),
        Input("node-original-name", "data"),
        Input("node-now-trigger-input", "value"),
    )
    def populate_node_now_state(node_name, _trigger):
        if not node_name:
            return []
        node = manager.get_node(node_name)
        if not node:
            return []
        return ["now"] if node.now else []

    # --- Editor Now Toggle: dispatcher ---
    # User flipped the switch — compare to the loaded node's DB state. On a
    # real transition, write the new value directly to the DB and bump the
    # node-now-trigger-input so core_engine re-renders the canvas with
    # the new amber border. No modal: Now is a low-friction state flip,
    # unlike dormant which involves event-attachment logic.
    @app.callback(
        Output("node-now-trigger-input", "value", allow_duplicate=True),
        Output("now-cap-refused-trigger", "value", allow_duplicate=True),
        Input("node-now", "value"),
        State("node-original-name", "data"),
        prevent_initial_call=True,
    )
    def dispatch_now_toggle(toggle_val, node_name):
        import time as _time
        from config import NOW_NODE_CAP
        if not node_name:
            return no_update, no_update
        node = manager.get_node(node_name)
        if not node:
            return no_update, no_update
        wants_now = bool(toggle_val and "now" in toggle_val)
        is_now = bool(node.now)
        if wants_now == is_now:
            # Toggle already matches DB — this fire was the populate sync,
            # not a user click. Don't bump the trigger.
            return no_update, no_update
        # Cap enforcement on setting Now only — clearing is always allowed.
        # On refusal we bump node-now-trigger-input so populate re-syncs
        # and bounces the switch back to off, AND bump the cap-refused
        # trigger so the toast pops.
        if wants_now and not is_now:
            current_count = len(manager.get_now_nodes())
            if current_count >= NOW_NODE_CAP:
                ts = int(_time.time() * 1000)
                return f"refused|{ts}", f"refused|{ts}"
        node.now = 1 if wants_now else 0
        manager.update_node(node)
        return f"{node_name}|{int(_time.time() * 1000)}", no_update

    # --- Context-Menu Now Toggle ---
    # Right-click → "Now" on the canvas / mini-graphs / goal sidebar
    # writes a JSON list of names + timestamp to toggle-now-trigger-input.
    # Flip each node's Now flag, then bump node-now-trigger-input to
    # cause the canvas to re-render. Bulk operation supported for parity
    # with toggle-done, though Now's soft cap of 3 makes bulk unlikely.
    @app.callback(
        Output("node-now-trigger-input", "value", allow_duplicate=True),
        Output("now-cap-refused-trigger", "value", allow_duplicate=True),
        Input("toggle-now-trigger-input", "value"),
        prevent_initial_call=True,
    )
    def handle_now_trigger(trigger_data):
        import time as _time
        from config import NOW_NODE_CAP
        if not trigger_data:
            return no_update, no_update
        try:
            raw = trigger_data.split('|')[0]
            names = json.loads(raw) if raw else []
        except (ValueError, json.JSONDecodeError):
            return no_update, no_update
        if not names:
            return no_update, no_update
        # Track count locally so a bulk set-Now stops at the cap. Pull
        # the live count once, then update it as we flip — get_now_nodes
        # would re-query the DB each iteration and miss our pending writes.
        current_count = len(manager.get_now_nodes())
        refused_any = False
        for name in names:
            node = manager.get_node(name)
            if not node:
                continue
            if node.now:
                # Clearing Now is always allowed.
                node.now = 0
                current_count -= 1
            else:
                if current_count >= NOW_NODE_CAP:
                    refused_any = True
                    continue  # Cap reached — skip this set-Now.
                node.now = 1
                current_count += 1
            manager.update_node(node)
        ts = int(_time.time() * 1000)
        refused_out = f"refused|{ts}" if refused_any else no_update
        return f"ctx|{ts}", refused_out

    # --- Now cap toast ---
    # Pops a transient warning when setting Now is refused for hitting the
    # cap. Both the editor dispatcher and the context-menu handler bump
    # now-cap-refused-trigger on refusal; this callback flips is_open and
    # dbc.Toast's `duration` auto-dismisses after 5s.
    @app.callback(
        Output("now-cap-toast", "is_open"),
        Input("now-cap-refused-trigger", "value"),
        prevent_initial_call=True,
    )
    def show_now_cap_toast(trigger):
        return bool(trigger)


