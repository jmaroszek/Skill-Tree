"""
Callback definitions for the Skill Tree Dash application.
"""

from editor_values import (
    _calibration_modal_text,
    _calibration_review_queue,
    _calibration_unit_for,
    _calibration_prepop,
    _friendly_time_estimates,
)

import functools
import json
import logging
import database
from sidebar_state import _compute_sidebar_styles, _DEFAULT_EDITOR_SIDEBAR_STYLE
from core_response import CoreResponse
from canvas_view import build_canvas_view, canvas_wanted, CANVAS_DEFERRED
from next_view import perf_stats_text
from resource_links import get_sections, open_resource, store_path

from typing import List, Set

import dash
from dash import html, Input, Output, State, ALL, ctx, no_update, ClientsideFunction
import dash_bootstrap_components as dbc

from graph_manager import GraphManager
from event_manager import EventManager
from canvases import CANVASES
from prerender import prerendered
from config import (ConfigManager, sort_subcontexts, sort_contexts,
                    SIDEBAR_WIDTH_PX, SIDEBAR_TRANSLATE_CLOSED,
                    DEFAULT_GRAPH_LAYOUT, DEFAULT_DETAILS_GRAPH_LAYOUT,
                    DEFAULT_EVENTS_GRAPH_LAYOUT, SUPPORTED_NODE_TYPES)
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from node_commands import (
    handle_save, handle_delete, handle_toggle_done, handle_group_delete,
    prior_node_for_completion, apply_dormancy,
)
from callback_helpers import (
    get_trigger_id, get_all_triggered_ids,
    node_options, build_filters, is_filters_active,
    format_traversal_ui,
    render_alias_rows, alias_rows_label, update_alias_rows,
    render_resource_sections, resource_link_values,
    spawn_local_file_picker,
    should_open_editor, resolve_active_node_id, left_sidebar_is_open,
    normalize_name_for_comparison,
    build_editor_snapshot, is_form_dirty_vs_snapshot, NEW_NODE_SNAPSHOT,
    snapshot_from_form_state, editor_form_values, dormancy_for_save,
    habit_to_hours, compute_habit_time_omp, resolve_time_mode, resolve_value_mode,
    habit_editor_view, parse_habit_days, ALL_WEEKDAYS, habit_preview_text,
    build_node_element, build_edge_element, canvas_node_styles,
)
import style_tokens as tokens
from ui_kit import (progress_bar_color)

logger = logging.getLogger(__name__)

manager = GraphManager()
event_manager = EventManager()


# core_engine has 28 outputs; this constant + helper let the tab-gating guard
# return a no_update tuple of the correct arity. test_core_engine_arity verifies
# that it stays in sync with the actual callback registration.
_CORE_ENGINE_NUM_OUTPUTS = len(CoreResponse._fields)

# Tabs whose own callbacks already refresh their content; switching to them
# should NOT trigger a graph regen via core_engine. That is every tab except
# tab-canvas, which is the only one that shows `cytoscape-graph`:
#   Events / Analyze — their own refresh callbacks.
#   Details          — update_details_graph + select_detail_node.
#   Next             — next_callbacks.populate_suggestions, which listens to
#                      graph-version-store and the filters directly.
# The regen core_engine ran here cost ~750 KB and ~700 ms of serialize +
# diff per tab switch, landing right on top of whatever the user did next.
_NON_GRAPH_TABS = frozenset({"tab-events", "tab-analyze", "tab-details", "tab-next"})

# Triggers that only open/close the editor sidebar without touching graph data,
# filters, or focus. When core_engine fires on one of these (and nothing else
# in the same cycle), we can skip the expensive scoring + element regen and
# just compute the three sidebar styles. Saves ~100-300 ms per Edit click.
_EDITOR_UI_ONLY_TRIGGERS = frozenset({
    'edit-trigger-input', 'details-edit-trigger-input',
    'btn-close-editor', 'btn-goals-toggle',
    # btn-add is the toolbar toggle. Its close half must run the same
    # unsaved-changes guard as btn-close-editor, which needs the short-circuit
    # path's pristine_snapshot — so route it here too.
    'btn-add',
})

# Output slot indices within the core_engine output tuple. Kept here so the
# editor-only short-circuit can build its partial tuple without repeating
# magic numbers. Must stay in sync with the Output list at the callback
# decoration site.
_SIDEBAR_EDITOR_STYLE_IDX = CoreResponse._fields.index('editor_style')
_DETAILS_GOAL_SIDEBAR_STYLE_IDX = CoreResponse._fields.index('goal_style')
_EVENTS_SIDEBAR_STYLE_IDX = CoreResponse._fields.index('events_style')


def _core_engine_noop_tuple():
    """Return a tuple of dash.no_update matching core_engine's output arity."""
    return CoreResponse()


def _core_engine_editor_only_tuple(next_ed_style, next_goal_style, next_events_style):
    """Return a tuple populated only at the three sidebar-style slots.

    Used by the editor-UI-only short-circuit in core_engine.
    """
    out = CoreResponse()
    out = out._replace(editor_style=next_ed_style)
    out = out._replace(goal_style=next_goal_style)
    out = out._replace(events_style=next_events_style)
    return tuple(out)


# Output slot indices for the undo-Done modal outputs.
_UNDO_DONE_MODAL_IDX = CoreResponse._fields.index('undo_open')
_UNDO_DONE_BODY_IDX = CoreResponse._fields.index('undo_body')
_PENDING_UNDO_DONE_IDX = CoreResponse._fields.index('undo_pending')

# Output slot indices for the time-calibration modal outputs.
_TIME_CALIB_MODAL_IDX = CoreResponse._fields.index('calibration_open')
_TIME_CALIB_REFERENCE_IDX = CoreResponse._fields.index('calibration_reference')
_TIME_CALIB_PENDING_IDX = CoreResponse._fields.index('calibration_pending')


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
    out = CoreResponse()
    out = out._replace(message=msg)
    out = out._replace(clear_disabled=False)
    out = out._replace(clear_intervals=0)
    out = out._replace(editor_style=next_ed_style)
    out = out._replace(goal_style=next_goal_style)
    out = out._replace(events_style=next_events_style)
    return tuple(out)






@database.snapshot_read
def generate_elements(filters=None, active_node_id=None, community_names=None,
                      graph=None, events=None):
    """Convert nodes and edges from the database into Cytoscape elements.

    `graph`/`events` default to the module-level managers so standalone callers
    (and tests) can call this with no wiring. `register_callbacks` binds the
    AppServices instances instead, so the canvas renders through the same
    managers the callbacks mutate.
    """
    graph = manager if graph is None else graph
    events = event_manager if events is None else events
    if filters is None: filters = {}
    # Always fetch dormant nodes too — filter_nodes decides whether to keep
    # them based on the `show_dormant` filter. Fetching unconditionally keeps
    # the include/exclude decision in one place (the filter pipeline).
    nodes = graph.get_all_nodes(include_dormant=True)
    filtered_nodes = graph.filter_nodes(nodes, filters)

    if community_names is not None:
        filtered_nodes = [n for n in filtered_nodes if n.name in community_names]

    valid_names = {n.name for n in filtered_nodes}
    styles = canvas_node_styles(events)

    elements = [
        build_node_element(
            node, styles,
            selected=node.name == active_node_id if active_node_id else False)
        for node in filtered_nodes
    ]
    elements.extend(
        build_edge_element(e) for e in graph.get_edges()
        if e['source'] in valid_names and e['target'] in valid_names)
    return elements


def register_callbacks(app, services=None):
    """Register all Dash callbacks for the application."""
    manager = services.graph if services is not None else globals()['manager']
    event_manager = services.events if services is not None else globals()['event_manager']
    render_elements = functools.partial(
        generate_elements, graph=manager, events=event_manager)

    # --- Graph Version Bridge ---
    # Observes cytoscape element changes and updates graph-version-store only
    # when GraphManager's internal version actually advanced (i.e. a real
    # node/edge mutation happened). Cosmetic changes (filter, depth, highlight)
    # regenerate elements without bumping the version, so downstream callbacks
    # subscribed to graph-version-store skip unnecessary recomputation.
    @app.callback(
        Output('graph-version-store', 'data'),
        # Each render's stamp, not the elements themselves: an Input of the
        # elements sent the whole canvas to the server on every render, and a
        # render deferred while the canvas hasn't loaded has none.
        Input('canvas-payload-stamp', 'data'),
        Input('events-refresh-trigger', 'data'),
        Input('details-refresh-trigger', 'data'),
        Input('settings-save-status', 'children'),
        State('graph-version-store', 'data'),
        prevent_initial_call=True,
    )
    def sync_graph_version(_stamp, _events, _details, _settings, current):
        if manager._graph_version != current:
            return manager._graph_version
        return dash.no_update

    # --- Clear Filters ---
    # Note: filter-subcontext.value is reset clientside (see below). The prop is
    # written by the context picker's own JS, and a server-side Output here
    # would let Dash clobber those picks on unrelated callback runs.
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
        return [], [], 'louvain', 'All', 1, 1, 10, None, 'hours', [], []

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
        *(Input(canvas.cytoscape_id, 'mouseoverNodeData') for canvas in CANVASES),
        prevent_initial_call=True,
    )
    @prerendered
    def display_hover_data(*hover_data):
        # Only the canvas that fired holds the node under the cursor. Before
        # any hover nothing has fired, and the first canvas's value is empty.
        trigger = get_trigger_id()
        data = next((value for canvas, value in zip(CANVASES, hover_data)
                     if canvas.cytoscape_id == trigger), hover_data[0])
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
            style={"fontSize": tokens.FS_LG, "marginBottom": "4px",
                   "borderBottom": f"1px solid {tokens.BORDER_PANEL}", "paddingBottom": "4px"}
        )

        if node_type in ('Goal', 'Milestone'):
            completion = manager.get_goal_completion(node_id, include_soft=False)
            total = completion.get('total', 0)
            done = completion.get('done', 0)
            pct = completion.get('pct', 0)
            remaining = completion.get('remaining_time', 0)

            lines = [marker, header]

            if total > 0:
                bar_color = progress_bar_color(pct)
                lines += [
                    html.Hr(style={"margin": "6px 0", "borderColor": tokens.BORDER_PANEL}),
                    html.Div([html.Strong("Progress: "), f"{done}/{total} hard subtasks ({pct}%)"]),
                    html.Div(
                        html.Div(style={
                            "width": f"{pct}%", "height": "6px",
                            "backgroundColor": bar_color, "borderRadius": "3px",
                            "transition": "width 0.3s ease"
                        }),
                        style={"backgroundColor": tokens.BORDER_PANEL, "borderRadius": "3px",
                               "margin": "4px 0", "overflow": "hidden"}
                    ),
                    html.Div([html.Strong("Remaining: "),
                              ConfigManager.format_time_friendly(remaining)]),
                ]
            else:
                lines.append(html.Div("No subtasks yet", style={"color": tokens.TEXT_DIM, "fontStyle": "italic"}))

            ctx_val = data.get('context', '')
            sub_val = data.get('subcontext', '')
            if ctx_val or sub_val:
                subctx_str = f"{ctx_val} > {sub_val}" if ctx_val and sub_val else ctx_val or sub_val
                lines.append(html.Div(subctx_str, style={"color": tokens.TEXT_SOFT}))

        else:
            ratings_inherited = data.get('value_mode') == 'inherited'
            time_inherited = data.get('time_mode') == 'inherited'

            lines = [marker, header]

            if ratings_inherited and time_inherited:
                lines.append(html.Div("Container", style={"color": tokens.TEXT_SOFT}))
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
                lines.append(html.Div(subctx_str, style={"color": tokens.TEXT_SOFT}))

        return lines

    # --- Scroll editor to top on New Node / Add ---
    app.clientside_callback(
        """function(n1, n2, n3) {
            var el = document.getElementById('sidebar-editor-container');
            if (el) el.scrollTop = 0;
            return window.dash_clientside.no_update;
        }""",
        Output('btn-new-node', 'title'),
        Input('btn-new-node', 'n_clicks'),
        Input('btn-add', 'n_clicks'),
        Input('btn-editor-new', 'n_clicks'),
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
         Output('resource-links-store', 'data'),
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
         Input('btn-editor-new', 'n_clicks'),
         Input('edit-trigger-input', 'value'),
         Input('details-edit-trigger-input', 'value'),
         Input('details-add-choice-input', 'value')],
        [State('sidebar-editor-container', 'style'),
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
         State({'type': 'resource-link', 'index': ALL}, 'value'),
         State({'type': 'resource-link', 'index': ALL}, 'id'),
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
         State('node-habit-days', 'value'),
         State('node-dormancy-form', 'data'),
         State('details-selected-node-store', 'data')],
        # Nothing to populate on page load. The form's defaults and its empty
        # alias and link rows are in the layout, and every path that opens
        # the editor runs this callback, which sends the relationship options.
        # The load-time run used to send ~230 KB of those options and set off
        # a dozen follow-on callbacks, all before the editor could be seen.
        prevent_initial_call=True,
    )
    def populate_editor(data, add_clicks, discard_clicks, unsaved_save_clicks, search_val, _bg_click, new_node_clicks, editor_new_clicks, edit_trigger_val,
                        details_edit_trigger_val, details_add_choice,
                        ed_style, original_name,
                        cur_name, cur_type, cur_desc, cur_context, cur_subctx, cur_status_done,
                        cur_val, cur_interest, cur_diff,
                        cur_time_o, cur_time_m, cur_time_p, cur_time_unit,
                        cur_needs_h, cur_needs_s, cur_supp_h, cur_supp_s, cur_helps,
                        cur_link_values, cur_link_ids,
                        cur_time_mode, cur_priority_rank,
                        cur_aliases,
                        pending_nav, pristine_snapshot,
                        cur_value_mode,
                        cur_time_habit_mode,
                        cur_habit_duration, cur_habit_duration_unit,
                        cur_habit_int_o, cur_habit_int_m, cur_habit_int_p,
                        cur_habit_int_unit, cur_habit_days, cur_dormancy,
                         details_selected_node):
        """Populate the editor sidebar form fields when a node is selected, searched, or cleared."""
        trigger_id = get_trigger_id()

        # Relationship pickers must include dormant nodes so active nodes can
        # be wired to work that has not triggered yet.
        all_nodes = manager.get_all_nodes(include_dormant=True)
        options = node_options(all_nodes)

        # node-type starts empty so the "Choose node type..." placeholder
        # survives until the user picks one. Defaulting it to Learn meant a
        # new node silently claimed a type nobody chose; saving without one is
        # already refused below ("Node type is required").
        def_out = [
            "", "", "", "", "", 5, 5, 5, 2, 4, 6, STATUS_OPEN, [],
            [], [], [], [], [],
            options, options, options, options, options,
            {},  # resource-links-store
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
            return is_form_dirty_vs_snapshot(pristine_snapshot, editor_form_values(
                name=cur_name, n_type=cur_type, desc=cur_desc,
                context=cur_context, subctx=cur_subctx,
                status_done=cur_status_done,
                val=cur_val, interest=cur_interest, diff=cur_diff,
                time_o=cur_time_o, time_m=cur_time_m, time_p=cur_time_p,
                time_unit=cur_time_unit,
                e_needs_h=cur_needs_h, e_needs_s=cur_needs_s,
                e_supp_h=cur_supp_h, e_supp_s=cur_supp_s, e_helps=cur_helps,
                resource_links=resource_link_values(cur_link_values, cur_link_ids),
                time_mode=cur_time_mode,
                time_habit_mode=cur_time_habit_mode,
                habit_duration=cur_habit_duration,
                habit_duration_unit=cur_habit_duration_unit,
                habit_intensity_o=cur_habit_int_o,
                habit_intensity_m=cur_habit_int_m,
                habit_intensity_p=cur_habit_int_p,
                habit_intensity_unit=cur_habit_int_unit,
                habit_days=cur_habit_days,
                value_mode=cur_value_mode,
                priority_rank=cur_priority_rank,
                aliases=cur_aliases,
                dormancy=cur_dormancy,
            ))

        if trigger_id == 'btn-add':
            # Toolbar toggle: open/close is handled by core_engine + the
            # clientside fast-path. Leave the form untouched so reopening shows
            # the last-loaded node (matches the Goals/Events toggles).
            return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*20

        if trigger_id in ('btn-new-node', 'btn-editor-new',
                          'details-add-choice-input'):
            if trigger_id == 'details-add-choice-input':
                if not (details_add_choice or '').startswith('new|') or not details_selected_node:
                    return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*20
                if manager.get_node(details_selected_node) is None:
                    return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*20
            editor_open = ed_style and ed_style.get('transform', '') == 'translateX(0px)'
            if editor_open and _has_unsaved_changes():
                # Show unsaved modal; store 'new-node' as pending action
                no_change = [dash.no_update] * 18 + [options]*5 + [dash.no_update]*20
                no_change[31] = (f'__new_subtask__|{details_selected_node}'
                                 if trigger_id == 'details-add-choice-input'
                                 else '__new_node__')
                no_change[32] = True            # modal-unsaved-changes
                return no_change
            # No unsaved changes — clear and reset, including the search bar so it
            # doesn't keep showing the previously-loaded node. Clearing search-node
            # re-fires core_engine with an empty value, but the editor is already
            # open here and _compute_sidebar_styles guards that case (search-node +
            # no value → leave the editor untouched), so it stays open.
            def_out[27] = None  # search-node value position
            if trigger_id == 'details-add-choice-input':
                def_out[15] = [details_selected_node]  # Supports > Hard
                def_out[33] = {**NEW_NODE_SNAPSHOT,
                               'e_supp_h': [details_selected_node]}
            return def_out

        if trigger_id == 'background-click-input':
            # Intercept background click when the editor is open with unsaved
            # changes — show the save/discard modal instead of silently clobbering.
            editor_open = ed_style and ed_style.get('transform', '') == 'translateX(0px)'
            if editor_open and _has_unsaved_changes():
                no_change = [dash.no_update] * 18 + [options]*5 + [dash.no_update]*20
                no_change[31] = '__background__'  # pending-navigation-store sentinel
                no_change[32] = True              # modal-unsaved-changes
                return no_change
            def_out[27] = None  # clear search bar (search-node value position)
            return def_out

        # Handle unsaved-discard / unsaved-save with pending navigation
        if trigger_id in ('btn-unsaved-discard', 'btn-unsaved-save'):
            if pending_nav:
                if pending_nav in ('__new_node__', '__background__') or pending_nav.startswith('__new_subtask__|'):
                    # Discard/save done — reset form. __new_node__ leaves the editor
                    # open on a blank form; __background__ closes it (core_engine).
                    def_out[27] = None  # clear search bar
                    if pending_nav.startswith('__new_subtask__|'):
                        parent = pending_nav.split('|', 1)[1]
                        if manager.get_node(parent) is not None:
                            def_out[15] = [parent]
                            def_out[33] = {**NEW_NODE_SNAPSHOT,
                                           'e_supp_h': [parent]}
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
                no_change = [dash.no_update] * 18 + [options]*5 + [dash.no_update]*20
                no_change[31] = tapped_id  # pending-navigation-store
                no_change[32] = True       # modal-unsaved-changes
                return no_change

        name = None
        if trigger_id in ('edit-trigger-input', 'details-edit-trigger-input'):
            # Context menu / Events-table Edit: node ID carried in the trigger value
            edit_val = edit_trigger_val if trigger_id == 'edit-trigger-input' else details_edit_trigger_val
            if edit_val:
                edit_node_name = edit_val.split('|')[0]
                node = manager.get_node(edit_node_name)
                if node:
                    name = node.name
                    data = node.to_dict()
                    data['id'] = name
                else:
                    return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*20
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
            if node:
                name = node.name
                data = node.to_dict()
                data['id'] = name
            else:
                return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*20
        elif data:
            name = data.get('id')
            # Always read fresh data from DB on tap (Cytoscape data may be stale)
            if name:
                db_node = manager.get_node(name)
                if db_node:
                    data = db_node.to_dict()
                    data['id'] = name

        if not name or not data:
            return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*20

        edges = manager.get_edges()

        # In/Out Edges mapping
        needs_hard_vals = [e['source'] for e in edges
                           if e['target'] == name and e['type'] == EDGE_NEEDS_HARD]
        needs_soft_vals = [e['source'] for e in edges
                           if e['target'] == name and e['type'] == EDGE_NEEDS_SOFT]
        supp_hard_vals = [e['target'] for e in edges
                          if e['source'] == name and e['type'] == EDGE_NEEDS_HARD]
        supp_soft_vals = [e['target'] for e in edges
                          if e['source'] == name and e['type'] == EDGE_NEEDS_SOFT]

        helps_vals = [e['target'] for e in edges
                      if e['source'] == name and e['type'] == EDGE_HELPS]
        helps_vals += [e['source'] for e in edges
                       if e['target'] == name and e['type'] == EDGE_HELPS]
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
            data.get('resource_links') or {},  # resource-links-store
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
         State({'type': 'resource-link', 'index': ALL}, 'value'),
         State({'type': 'resource-link', 'index': ALL}, 'id'),
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
         State('node-habit-days', 'value'),
         State('node-dormancy-form', 'data'),
          State('node-original-name', 'data')],
        prevent_initial_call=True,
    )
    def sync_original_name_after_save(_save_clicks, _save_close_clicks,
                                      cur_name, cur_type, cur_desc,
                                      cur_context, cur_subctx, cur_status_done,
                                      cur_val, cur_interest, cur_diff,
                                      cur_time_o, cur_time_m, cur_time_p, cur_time_unit,
                                      cur_needs_h, cur_needs_s, cur_supp_h, cur_supp_s, cur_helps,
                                      cur_link_values, cur_link_ids,
                                      cur_time_mode, cur_priority_rank,
                                      cur_value_mode,
                                      cur_time_habit_mode,
                                      cur_habit_duration, cur_habit_duration_unit,
                                      cur_habit_int_o, cur_habit_int_m, cur_habit_int_p,
                                      cur_habit_int_unit, cur_habit_days,
                                       cur_dormancy, cur_original_name):
        if not cur_name or not cur_name.strip():
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        linted = ConfigManager.apply_name_formatting(cur_name.strip())
        # core_engine is triggered by the same Save click and runs
        # concurrently with this callback. On a rename (or brand-new node)
        # the node doesn't exist under its linted name until core_engine
        # commits the write, so a single get_node here loses the race and
        # leaves node-original-name stale — which silently breaks every
        # feature keyed off it (locate, Now toggle, dirty checks). Poll
        # briefly for the write to land before concluding the save failed.
        import time as _time
        _deadline = _time.monotonic() + 3.0
        while not manager.get_node(linted):
            if _time.monotonic() >= _deadline:
                # Save genuinely failed to persist — leave state alone rather
                # than stomping a stale snapshot on a non-existent node.
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update
            _time.sleep(0.05)
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
            'resource_links': resource_link_values(cur_link_values, cur_link_ids),
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
            'dormancy': cur_dormancy,
        }
        snapshot = snapshot_from_form_state(form_values, linted, linted_aliases)
        # Rewrite node-original-name only when the save changed it (a rename
        # or a new node). Everything keyed off it reloads from the database,
        # and on a save that failed that reload would throw away what the
        # user had just entered, such as a Dormant switch the save refused.
        original_out = linted if linted != cur_original_name else dash.no_update
        return original_out, linted, linted_aliases, snapshot

    # --- Type-adaptive field visibility ---
    @app.callback(
        [Output('section-done-time', 'style'),
         Output('section-time-estimates', 'style'),
         Output('section-priority-rank', 'style'),
         Output('section-time-habit-toggle', 'style')],
        Input('node-type', 'value'),
        prevent_initial_call=True,
    )
    @prerendered
    def toggle_type_fields(node_type):
        show = {}
        hide = {'display': 'none'}
        # section-priority-rank stays hidden for every type now: rank is the
        # Goals sidebar's job. The Output is kept so the hidden select the
        # other callbacks read as State still has a container.
        if node_type == 'Goal':
            # Habit toggle hidden — containers must inherit.
            return show, show, hide, hide
        if node_type == 'Milestone':
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
            var visible = {display: "block", color: "var(--st-danger-text)", fontSize: "var(--st-fs-base)"};
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
        prevent_initial_call=True,
    )
    @prerendered
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
            var visible = {display: "block", color: "var(--st-danger-text)", fontSize: "var(--st-fs-base)"};
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
    # Effort on a Goal is decorative — _rank_goals counts only the effort
    # of the tasks beneath it, and total_value doesn't cascade it. The caption tells the user why the
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

        Valid patterns (mirroring `expected_time_estimate` in models.py):
          - Expected only          {m}
          - Lower + Upper          {o, p}
          - All three              {o, m, p}

        Validation is skipped when the node uses inherited time (container
        draws from children) or habit mode (separate input section).
        """
        hidden = tokens.ERROR_TEXT_HIDDEN
        visible = tokens.ERROR_TEXT_VISIBLE

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
                               style=tokens.ERROR_TEXT_VISIBLE)
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

    # --- "Locate on graph": validate the editor target, then let the browser
    # inspect the live canvas. Freeze mode mutates Cytoscape directly, so Dash's
    # cached `elements` prop is not authoritative for membership.
    @app.callback(
        Output('locate-message', 'children'),
        Output('locate-clear-interval', 'disabled'),
        Output('locate-clear-interval', 'n_intervals'),
        Output('locate-request-store', 'data'),
        Input('btn-locate-node', 'n_clicks'),
        State('node-original-name', 'data'),
        State('main-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    def handle_locate_click(n_clicks, name, current_tab):
        if not n_clicks or not name:
            return (dash.no_update,) * 4
        node = manager.get_node(name)
        if not node:
            return "This node no longer exists.", False, 0, dash.no_update
        return "", True, 0, {
            'name': name,
            'activeTab': current_tab,
            'request': n_clicks,
        }

    # Resolve the active canvas against the live Cytoscape instance. Details
    # and Events remain in place; tabs without a canvas retain the historical
    # Nodes fallback. The result callback below owns navigation and dialogs.
    app.clientside_callback(
        """function(request) {
            if (!request || !request.name || !window.SkillTree ||
                    typeof window.SkillTree.resolveLocateRequest !== 'function') {
                return window.dash_clientside.no_update;
            }
            return window.SkillTree.resolveLocateRequest(request);
        }""",
        Output('locate-result-store', 'data'),
        Input('locate-request-store', 'data'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('main-tabs', 'active_tab', allow_duplicate=True),
        Output('locate-animate-trigger', 'data'),
        Output('modal-locate-missing', 'is_open'),
        Output('locate-missing-title', 'children'),
        Output('locate-missing-node-store', 'data'),
        Output('details-node-select', 'value', allow_duplicate=True),
        Input('locate-result-store', 'data'),
        Input('btn-locate-dismiss', 'n_clicks'),
        Input('btn-locate-view-details', 'n_clicks'),
        State('locate-missing-node-store', 'data'),
        State('main-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    def handle_locate_result(result, _dismiss_clicks, view_details_clicks,
                             missing_node, current_tab):
        triggered = ctx.triggered_id
        unchanged = (dash.no_update,) * 6

        if triggered == 'btn-locate-dismiss':
            return dash.no_update, dash.no_update, False, dash.no_update, None, dash.no_update

        if triggered == 'btn-locate-view-details':
            name = (missing_node or {}).get('name')
            if not name or not manager.get_node(name):
                return dash.no_update, dash.no_update, False, dash.no_update, None, dash.no_update
            next_tab = dash.no_update if current_tab == 'tab-details' else 'tab-details'
            animate = {
                'name': name,
                'canvasId': 'details-mini-graph',
                'request': view_details_clicks,
            }
            return next_tab, animate, False, dash.no_update, None, name

        if triggered != 'locate-result-store' or not result:
            return unchanged

        status = result.get('status')
        if status == 'located':
            return dash.no_update, dash.no_update, False, dash.no_update, None, dash.no_update
        if status == 'navigate':
            animate = {
                'name': result.get('name'),
                'canvasId': result.get('canvasId'),
                'request': result.get('request'),
            }
            return result.get('targetTab'), animate, False, dash.no_update, None, dash.no_update
        if status == 'missing':
            view_labels = {
                'main': 'Nodes',
                'details': 'Details',
                'events': 'Events',
                'canvas': 'current',
            }
            name = result.get('name')
            label = view_labels.get(result.get('view'), 'current')
            title = f'“{name}” is not in the {label} view'
            return (dash.no_update, dash.no_update, True, title,
                    {'name': name}, dash.no_update)
        return unchanged

    # Run the pulse after a tab switch or Details re-root. The fcose layout may
    # still be running, so locateNodeOnGraph retries until the node is present.
    app.clientside_callback(
        """function(trigger) {
            if (!trigger || !trigger.name || !trigger.canvasId) {
                return window.dash_clientside.no_update;
            }
            if (typeof window.locateNodeOnGraph === 'function') {
                window.locateNodeOnGraph(trigger.name, trigger.canvasId);
            }
            return window.dash_clientside.no_update;
        }""",
        Output('locate-message', 'title'),  # dummy/no-op output
        Input('locate-animate-trigger', 'data'),
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

    # The node editor used to carry a read-only strip of "Priority N" /
    # "Hard N" / "Soft N" badges describing where the node sat relative to the
    # top priority Goals. It is gone: the editor is a form, and that was the
    # only derived, read-only display in it. The Details panel shows the same
    # relationship as part of a complete info strip, which is the surface for
    # reading rather than changing. Same reasoning that moved Priority Rank out
    # to the Goals sidebar.

    # --- Core State: Save, Delete, Render ---
    # NOTE: elements output goes to `elements-pending-store`, not directly to
    # `cytoscape-graph.elements`. A clientside callback reads the pending
    # store and, when freeze is on, injects pinned positions into each
    # node's data before pushing to Cytoscape. That's what keeps node
    # positions from drifting on save during bulk-edit freeze mode.
    @app.callback(
        [Output('elements-pending-store', 'data', allow_duplicate=True), Output('save-output', 'children'),
         Output('suggestions-table', 'children', allow_duplicate=True),
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
         # State in this grouped list preserves the established argument order,
         # while selection no longer triggers a server request.
         State('selected-suggestion-store', 'data'),
         Input('focus-goal-store', 'data'),
         Input('edit-trigger-input', 'value'),
         Input('details-edit-trigger-input', 'value'),
         Input('toggle-done-trigger-input', 'value'),
         Input('node-now-trigger-input', 'value'),
         Input('events-refresh-trigger', 'data'),
         Input('details-refresh-trigger', 'data'),
         Input('background-click-input', 'value'),
         Input('main-tabs', 'active_tab'),
         Input('graph-settings-relayout', 'n_clicks'),
         Input('btn-undo-done-confirm', 'n_clicks'),
         # Appended at the end of the Inputs so existing positional indices
         # (used by core_engine tests) stay stable. The toolbar "+" new-node
         # button; only its trigger_id matters, the value is unused.
         Input('btn-editor-new', 'n_clicks')],

        [State('node-name', 'value'), State('node-type', 'value'), State('node-desc', 'value'),
         State('node-context', 'value'), State('node-subcontext', 'value'), State('node-status-done', 'value'),
         State('node-value', 'value'), State('node-interest', 'value'), State('node-difficulty', 'value'),
         State('node-time-o', 'value'), State('node-time-m', 'value'), State('node-time-p', 'value'),
         State('node-time-unit', 'value'),
         State('edge-needs-hard', 'value'), State('edge-needs-soft', 'value'),
         State('edge-supports-hard', 'value'), State('edge-supports-soft', 'value'),
         State('edge-helps', 'value'),
         State({'type': 'resource-link', 'index': ALL}, 'value'),
         State({'type': 'resource-link', 'index': ALL}, 'id'),
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
         State('node-habit-days', 'value'),
         State('canvas-payload-stamp', 'data'),
          State('node-dormancy-form', 'data')],
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
                     active_tab, _relayout,
                     btn_undo_done_confirm, btn_editor_new,
                     name, n_type, desc, context, subctx, status_done, val, interest, diff,
                     time_o, time_m, time_p, time_unit,
                     e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                     link_values, link_ids,
                     ed_style, original_name,
                     time_mode_val, priority_rank_val,
                     goal_sidebar_style, events_sidebar_style, pending_nav_store, alias_values,
                     pristine_snapshot, pending_undo_done,
                     value_mode_val,
                     time_habit_mode_val,
                     habit_duration, habit_duration_unit,
                     habit_int_o, habit_int_m, habit_int_p, habit_int_unit,
                      habit_days, canvas_stamp, dormancy):
        """Central state callback handling node CRUD, filtering, and UI updates.

        The existing Dash wiring preserves mutation and refresh ordering. Sidebar
        decisions and canvas rendering are delegated; CoreResponse names the stable
        output contract so partial responses do not depend on numeric slots.
        """
                     
        trigger_id = get_trigger_id()

        # Tab-switch gate: switching to Events/Analyze doesn't need a graph
        # regen — those tabs have their own refresh callbacks. Short-circuit
        # to no_update so we skip the scoring + generate_elements cycle.
        # Nodes needs one only for its first load: once loaded, every render
        # keeps it current, and re-sending it cost ~0.3 s of browser work
        # just as the tab appeared.
        if trigger_id == 'main-tabs' and (
                active_tab in _NON_GRAPH_TABS
                or (canvas_stamp or {}).get('loaded')):
            return _core_engine_noop_tuple()

        # Settings-save gate: we trigger off `settings-save-status` (not the
        # raw save-button click) so this runs AFTER save_settings has written
        # the new contexts/types to the DB — otherwise we'd race the write and
        # re-read stale config, leaving the context/type dropdowns showing
        # values the user just deleted. Only a "Settings saved" message means
        # config was actually persisted with no migration pending; a context
        # edit appends what it changed ("Settings saved — 1 rename"), so this
        # matches the prefix. The auto-clear to "", the "Migration required"
        # message (the modal-close path handles that), and "Error..." carry no
        # config change to render.
        if (trigger_id == 'settings-save-status'
                and not str(settings_save_status or '').startswith('Settings saved')):
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
                'resource_links': resource_link_values(link_values, link_ids),
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
                'dormancy': dormancy,
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
            'resource_links': resource_link_values(link_values, link_ids),
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
            'dormancy': dormancy,
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

        # --- Action Routing ---
        if trigger_id in ('btn-save', 'btn-save-close', 'btn-unsaved-save'):
            if name and name.strip():
                name = ConfigManager.apply_name_formatting(name.strip())
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
            # Done is hidden while Dormant is on; a sleeping node isn't finished.
            if (dormancy or {}).get('dormant'):
                status_done = []
            try:
                with database.transaction():
                    # Track if this save marks the node Done. Only count a true
                    # Open/Blocked → Done transition (or a brand-new node created
                    # Done) — re-saving an already-Done node must not re-trigger
                    # the time-calibration modal.
                    if status_done and STATUS_DONE in (status_done or []):
                        _prior_for_completion = prior_node_for_completion(
                            manager, name, original_name)
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
                    # eliminates drift across the save paths (main editor,
                    # details-panel save).
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
                    _prior = manager.get_node(name)
                    was_dormant = bool(_prior and _prior.dormant)
                    msg = handle_save(manager, name, n_type, desc, val, t_o, t_m, t_p,
                                      interest, diff, status_done, context, subctx,
                                      resource_link_values(link_values, link_ids),
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

                    # Dormant switch and Event section. A refusal raises
                    # ValueError and rolls the whole save back.
                    from event_manager import EventManager
                    apply_dormancy(manager, EventManager(), name,
                                   dormancy_for_save(dormancy), was_dormant)

                    # Priority rank is deliberately NOT written here. The
                    # Goals sidebar owns it, because ranking is a judgement
                    # about the whole list rather than about one node, and it
                    # is the only surface that shows the list. This block used
                    # to rewrite the ranking from the editor's hidden select on
                    # every Goal save.
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
                        out = CoreResponse()
                        out = out._replace(undo_open=True)
                        out = out._replace(undo_body=_build_undo_done_body([node_id], downstream_done))
                        out = out._replace(undo_pending=[node_id])
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
                            out = CoreResponse()
                            target_names = [n.name for n in nodes]
                            out = out._replace(undo_open=True)
                            out = out._replace(undo_body=_build_undo_done_body(target_names, affected_downstream))
                            out = out._replace(undo_pending=target_names)
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
        # Every mutation above has committed, so the view is all reads. One
        # snapshot serves them: naming the community filter's options alone
        # used to open a connection per node, about 0.3 s per render.
        with database.read_snapshot():
            view = build_canvas_view(
                manager, render_elements, trigger_id, tapped_node, active_node_id, community_method, filters, f_community, focus_goal, focus_subtree_override, focus_path_info)

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

        if (isinstance(view.elements, list)
                and not canvas_wanted(active_tab, canvas_stamp)):
            view = view._replace(elements=CANVAS_DEFERRED)

        if not trigger_id or trigger_id == 'main-tabs':
            # Page load or a tab switch: nothing ran, so
            # there's no message and no modal to open, and the page already
            # holds every reset below. Sending them anyway woke six callbacks
            # each time that only reset again.
            return view._replace(
                editor_style=next_ed_style,
                goal_style=next_goal_style,
                events_style=next_events_sidebar_style,
            )

        # Last 6 outputs: the undo-Done modal trio followed by the
        # time-calibration modal trio. The undo-Done path either opens its
        # modal earlier (return short-circuit in the toggle branch) or, as
        # here, leaves it closed with the pending store cleared.
        return view._replace(
            message=msg,
            clear_disabled=False if msg else True,
            clear_intervals=0,
            editor_style=next_ed_style,
            goal_style=next_goal_style,
            events_style=next_events_sidebar_style,
            undo_open=False,
            undo_body='',
            undo_pending=None,
            calibration_open=tc_modal_open,
            calibration_reference=tc_reference,
            calibration_pending=tc_pending,
            calibration_unit=tc_unit,
            calibration_title=tc_title,
        )

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
            html.I(className="bi bi-check-circle text-success",
                   style={"fontSize": tokens.FS_DISPLAY, "lineHeight": "1"},
                   **{"aria-hidden": "true"}),
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
    # Evaluated as the layout is built and on every tab switch — a tab switch
    # is the natural action after toggling the setting in Settings, and it
    # happens after the save has committed, so there's no read-before-write
    # race.
    @app.callback(
        Output('btn-calibration-review', 'style'),
        Input('main-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    @prerendered
    def _calibration_review_button_visibility(_active_tab):
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
        State('main-tabs', 'active_tab'),
        State('canvas-payload-stamp', 'data'),
        prevent_initial_call=True,
    )
    def manage_auto_done_modal(_version, _confirm, _dismiss, current_candidates,
                               active_tab, canvas_stamp):
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
                    elements_out = (render_elements()
                                    if canvas_wanted(active_tab, canvas_stamp)
                                    else CANVAS_DEFERRED)
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
         Input('btn-add', 'n_clicks'),
         Input('btn-unsaved-cancel', 'n_clicks'),
         Input('btn-unsaved-save', 'n_clicks'),
         Input('btn-unsaved-discard', 'n_clicks')],
        [State('sidebar-editor-container', 'style'),
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
         State({'type': 'resource-link', 'index': ALL}, 'value'),
         State({'type': 'resource-link', 'index': ALL}, 'id'),
         State('node-time-mode', 'value'),
         State('node-priority-rank', 'value'),
         State({'type': 'alias-input', 'index': ALL}, 'value'),
         State('node-original-name', 'data'),
         State('editor-pristine-snapshot', 'data'),
         State('node-value-mode', 'value'),
         State('node-time-habit-mode', 'value'),
         State('node-habit-duration', 'value'),
         State('node-habit-duration-unit', 'value'),
         State('node-habit-intensity-o', 'value'),
         State('node-habit-intensity-m', 'value'),
         State('node-habit-intensity-p', 'value'),
         State('node-habit-intensity-unit', 'value'),
         State('node-habit-days', 'value'),
          State('node-dormancy-form', 'data')],
        prevent_initial_call=True
    )
    def toggle_unsaved_modal(_close, _add, _cancel, _save, _discard,
                              ed_style,
                              name, n_type, desc, context, subctx, status_done,
                              val, interest, diff,
                              time_o, time_m, time_p, time_unit,
                              e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                              link_values, link_ids,
                              time_mode_val, priority_rank_val,
                              alias_values, original_name, pristine_snapshot,
                              value_mode_val,
                              time_habit_mode_val,
                              habit_duration, habit_duration_unit,
                              habit_int_o, habit_int_m, habit_int_p, habit_int_unit,
                               habit_days, dormancy):
        trig = get_trigger_id()
        if trig == 'btn-add':
            # btn-add is the toolbar toggle: only its close half (editor already
            # open) should guard against unsaved changes. Opening never does.
            editor_open = bool(ed_style) and ed_style.get('transform', '') == 'translateX(0px)'
            if not editor_open:
                return False
        elif trig != 'btn-close-editor':
            return False
        return is_form_dirty_vs_snapshot(pristine_snapshot, editor_form_values(
            name=name, n_type=n_type, desc=desc,
            context=context, subctx=subctx,
            status_done=status_done,
            val=val, interest=interest, diff=diff,
            time_o=time_o, time_m=time_m, time_p=time_p,
            time_unit=time_unit,
            e_needs_h=e_needs_h, e_needs_s=e_needs_s,
            e_supp_h=e_supp_h, e_supp_s=e_supp_s, e_helps=e_helps,
            resource_links=resource_link_values(link_values, link_ids),
            time_mode=time_mode_val,
            time_habit_mode=time_habit_mode_val,
            habit_duration=habit_duration,
            habit_duration_unit=habit_duration_unit,
            habit_intensity_o=habit_int_o,
            habit_intensity_m=habit_int_m,
            habit_intensity_p=habit_int_p,
            habit_intensity_unit=habit_int_unit,
            habit_days=habit_days,
            value_mode=value_mode_val,
            priority_rank=priority_rank_val,
            aliases=alias_values,
            dormancy=dormancy,
        ))

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
        text = perf_stats_text()
        return text if text else dash.no_update

    @app.callback(
        Output('canvas-node-count', 'children'),
        Input('canvas-payload-stamp', 'data'),
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
        prevent_initial_call=True,
    )
    @prerendered
    def update_canvas_node_count(stamp, f_type, f_ctx, f_sub,
                                 f_comm, f_comm_method, f_val, f_int,
                                 f_diff, f_time, f_time_unit):
        n = (stamp or {}).get('nodes') or 0
        text = f"{n} node{'s' if n != 1 else ''}"
        if is_filters_active(
                node_type=f_type, context=f_ctx, subcontext=f_sub,
                community=f_comm,
                community_method=f_comm_method, value=f_val,
                interest=f_int, difficulty=f_diff, time=f_time):
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
        prevent_initial_call=True,
    )
    @prerendered
    def update_next_filter_indicator(f_type, f_ctx, f_sub, f_comm,
                                     f_comm_method, f_val, f_int, f_diff,
                                     f_time, f_time_unit):
        if is_filters_active(
                node_type=f_type, context=f_ctx, subcontext=f_sub,
                community=f_comm,
                community_method=f_comm_method, value=f_val,
                interest=f_int, difficulty=f_diff, time=f_time):
            return "filtered"
        return ""

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
        Input('node-context', 'value'),
        prevent_initial_call=True,
    )
    @prerendered
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

    # When the user changes context, prune any subcontext picks whose context
    # is no longer in the selection. Clientside only: Dash strips the layout's
    # `value=` for any prop that has a server-side callback Output, which
    # would nuke the memory-restored picks.
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


    # --- Aliases Render ---
    @app.callback(
        [Output('aliases-container', 'children'),
         Output('aliases-label', 'children')],
        Input('aliases-store', 'data'),
        prevent_initial_call=True,
    )
    @prerendered
    def render_aliases(aliases):
        return render_alias_rows(aliases), alias_rows_label(aliases)

    # --- Aliases Add/Remove ---
    @app.callback(
        [Output('aliases-store', 'data', allow_duplicate=True),
         Output('collapse-aliases', 'is_open', allow_duplicate=True)],
        [Input('btn-alias-add', 'n_clicks'),
         Input({'type': 'btn-alias-remove', 'index': ALL}, 'n_clicks')],
        [State({'type': 'alias-input', 'index': ALL}, 'value'),
         State('aliases-store', 'data'),
         State('collapse-aliases', 'is_open')],
        prevent_initial_call=True,
    )
    def modify_aliases(add_clicks, remove_clicks, current_values, store_data,
                       aliases_open):
        return update_alias_rows(
            ctx.triggered_id, current_values, store_data, aliases_open,
            'btn-alias-add', 'btn-alias-remove',
        )

    # --- Resources ---
    # One set of pattern-matched callbacks serves every section. A row's id
    # index is "<section id>:<row>", so a trigger names both.
    @app.callback(
        Output('editor-resources', 'children'),
        Input('resource-links-store', 'data'),
        prevent_initial_call=True,
    )
    @prerendered
    def render_resources(links):
        return render_resource_sections(links)

    # A Settings save can add, rename or remove sections. Redraw them around
    # what the user has typed, not the links last loaded.
    @app.callback(
        Output('resource-links-store', 'data', allow_duplicate=True),
        Input('settings-save-status', 'children'),
        State({'type': 'resource-link', 'index': ALL}, 'value'),
        State({'type': 'resource-link', 'index': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def keep_typed_links_across_settings_save(_status, values, ids):
        return resource_link_values(values, ids)

    @app.callback(
        Output('resource-links-store', 'data', allow_duplicate=True),
        Input({'type': 'resource-add', 'index': ALL}, 'n_clicks'),
        Input({'type': 'resource-remove', 'index': ALL}, 'n_clicks'),
        Input({'type': 'resource-browse', 'index': ALL}, 'n_clicks'),
        State({'type': 'resource-link', 'index': ALL}, 'value'),
        State({'type': 'resource-link', 'index': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def modify_resource_links(_adds, _removes, _browses, values, ids):
        trigger = ctx.triggered_id
        # A re-render mounts fresh buttons that match these ALL inputs; only a
        # real click carries n_clicks.
        if not isinstance(trigger, dict) or not ctx.triggered[0].get('value'):
            return dash.no_update
        links = resource_link_values(values, ids)
        if trigger['type'] == 'resource-add':
            links[trigger['index']] = (links.get(trigger['index']) or []) + ['']
            return links
        section_id, _, index_text = trigger['index'].rpartition(':')
        index = int(index_text)
        items = links.get(section_id) or ['']
        if index >= len(items):
            return dash.no_update
        if trigger['type'] == 'resource-remove':
            if len(items) < 2:
                return dash.no_update
            items.pop(index)
        else:
            section = next((s for s in get_sections() if s['id'] == section_id), None)
            if section is None:
                return dash.no_update
            filetypes = ([("Markdown files", "*.md"), ("All files", "*.*")]
                         if section['kind'] == 'obsidian' else [("All files", "*.*")])
            picked = spawn_local_file_picker(section['root_path'],
                                             f"Select {section['name']} file", filetypes)
            if not picked:
                return dash.no_update
            items[index] = store_path(picked, section['root_path'])
        links[section_id] = items
        return links

    @app.callback(
        Output('save-output', 'children', allow_duplicate=True),
        Input({'type': 'resource-open', 'index': ALL}, 'n_clicks'),
        State({'type': 'resource-link', 'index': ALL}, 'value'),
        State({'type': 'resource-link', 'index': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def open_resource_link(_clicks, values, ids):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not ctx.triggered[0].get('value'):
            return dash.no_update
        key = trigger['index']
        section_id = key.rpartition(':')[0]
        section = next((s for s in get_sections() if s['id'] == section_id), None)
        if section is None:
            return 'That resource no longer exists.'
        value = next((value for value, item_id in zip(values, ids)
                      if item_id['index'] == key), '')
        try:
            open_resource(value, section)
            return dash.no_update
        except Exception as exc:
            return f"Error opening {section['name']}: {exc}"

    # The desktop window's native picker (assets/resource_picker.js) reports
    # its choice here; the browser fallback runs in modify_resource_links.
    @app.callback(
        Output('resource-links-store', 'data', allow_duplicate=True),
        Input('electron-file-picked-input', 'value'),
        State({'type': 'resource-link', 'index': ALL}, 'value'),
        State({'type': 'resource-link', 'index': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def receive_electron_file_pick(payload, values, ids):
        try:
            selected = json.loads(payload)
            section_id, _, index_text = selected['index'].rpartition(':')
            section = next(s for s in get_sections() if s['id'] == section_id)
            links = resource_link_values(values, ids)
            links[section_id][int(index_text)] = store_path(selected['path'],
                                                            section['root_path'])
            return links
        except (KeyError, ValueError, TypeError, IndexError, AttributeError, StopIteration):
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

    # --- Graph Layout: Toggle Panel ---
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

    # --- Graph Layout: Reset to Stored Defaults ---
    @app.callback(
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
            return (dash.no_update,) * 5
        gl = ConfigManager.get_graph_layout_defaults()
        return (
            True,
            gl.get('edge_length', DEFAULT_GRAPH_LAYOUT['edge_length']),
            gl.get('gravity', DEFAULT_GRAPH_LAYOUT['gravity']),
            gl.get('repulsion', DEFAULT_GRAPH_LAYOUT['repulsion']),
            False,
        )

    # --- Freeze feature: per-canvas clientside wiring ---
    # Each canvas in canvases.CANVASES gets three parameterized
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
                // Anything but a list is a render with no elements to apply,
                // such as the Nodes canvas's deferred marker.
                if (!Array.isArray(pending)) {
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
                    fontSize: "1.6rem", color: "var(--st-accent-soft)",
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

    for canvas in CANVASES:
        _register_freeze_callbacks(
            canvas_id=canvas.key,
            switch_id=canvas.control_id('freeze-rerender'),
            store_id=canvas.freeze_store_id,
            pending_id=canvas.pending_store_id,
            cytoscape_id=canvas.cytoscape_id,
            indicator_id=canvas.freeze_indicator_id,
            container_id=canvas.container_id,
        )

    # --- Each Nodes render: stamp it, and report it to both covers ---
    # The stamp is what server callbacks listen to instead of the elements,
    # which would send the whole canvas back to the server on every render.
    # `loaded` stays true once the canvas has had elements; until then the
    # core engine sends CANVAS_DEFERRED (see canvas_view.canvas_wanted).
    # The canvas cover waits for the main canvas's layout to settle, and a
    # graph with no nodes never runs one — no `layoutstop` is ever coming, so
    # nothing else would release it. Only the empty case matters to it; the JS
    # ignores the rest. The startup cover (assets/startup_cover.js) waits for
    # the first render of any kind: it arrives with the core engine's first
    # response, which also fills the editor's search and the other dropdowns.
    app.clientside_callback(
        """
        function(pending, previous) {
            if (window.SkillTree && window.SkillTree.notifyCanvasElements) {
                window.SkillTree.notifyCanvasElements(pending);
            }
            if (window.SkillTree && window.SkillTree.notifyStartupPayload) {
                window.SkillTree.notifyStartupPayload(pending);
            }
            var loaded = Boolean(previous && previous.loaded);
            var nodes = previous ? previous.nodes : null;
            if (Array.isArray(pending)) {
                loaded = true;
                nodes = pending.filter(function (element) {
                    return element && element.data && element.data.source == null;
                }).length;
            }
            return {loaded: loaded, nodes: nodes, at: Date.now()};
        }
        """,
        Output('canvas-payload-stamp', 'data'),
        Input('elements-pending-store', 'data'),
        State('canvas-payload-stamp', 'data'),
        prevent_initial_call=True,
    )

    # --- Graph Layout: one layout request per canvas ---
    # assets/layout_requests.js builds each canvas's layout prop. It stays
    # clientside so allowOneLayout() is set in the same synchronous function
    # that returns the new layout dict. A previous server-side implementation
    # paired with a separate clientside allowOneLayout callback was racy: Dash
    # doesn't order parallel callbacks bound to the same input, so the layout
    # prop sometimes reached Cytoscape before the JS guard's allowNextLayout
    # flag was set, causing the freeze guard at layoutstart to stop the layout
    # (Settle button silently no-op).
    def _register_layout_callback(canvas):
        inputs = [
            Input(canvas.control_id('edge-length'), 'value'),
            Input(canvas.control_id('gravity'), 'value'),
            Input(canvas.control_id('repulsion'), 'value'),
            Input(canvas.control_id('animate'), 'value'),
            Input(canvas.control_id('relayout'), 'n_clicks'),
        ]
        if canvas.lays_out_elements:
            inputs.append(Input(canvas.cytoscape_id, 'elements'))
        # Control changes wait while the canvas is frozen. The freeze-off
        # transition lays the graph out with them.
        inputs.append(Input(canvas.freeze_store_id, 'data'))
        states = [State(canvas.view_store_id, 'data')] if canvas.view_store_id else []
        app.clientside_callback(
            ClientsideFunction(namespace='skillTreeLayout', function_name=canvas.key),
            Output(canvas.cytoscape_id, 'layout'),
            *inputs,
            *states,
            # Nodes keeps the transition prop layout.py gives it until a
            # control is touched.
            prevent_initial_call=not canvas.lays_out_elements,
        )

    for canvas in CANVASES:
        _register_layout_callback(canvas)

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

    # --- Reflection Ratings Editor ---
    # Mirrors the estimation editor above but reads/writes the decoupled
    # REFLECTION_RATINGS_DEFINITIONS so the Reflection modal's rubric can be
    # tuned independently of the node-editor/Add-Subtask rubric.

    @app.callback(
        Output("modal-reflection-ratings-editor", "is_open"),
        Output("reflection-ratings-editor-body", "children"),
        Input("btn-reflection-ratings-edit", "n_clicks"),
        Input("btn-reflection-ratings-editor-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_reflection_ratings_editor(edit_clicks, cancel_clicks):
        from layout import build_editor_table
        if ctx.triggered_id == "btn-reflection-ratings-edit":
            defs = ConfigManager.get_reflection_ratings_definitions()
            return True, build_editor_table(defs, id_prefix="reflection-ratings-edit")
        return False, no_update

    @app.callback(
        Output("reflection-ratings-popup-table-body", "children"),
        Output("modal-reflection-ratings-editor", "is_open", allow_duplicate=True),
        Input("btn-reflection-ratings-editor-save", "n_clicks"),
        State({"type": "reflection-ratings-edit-value", "index": ALL}, "value"),
        State({"type": "reflection-ratings-edit-interest", "index": ALL}, "value"),
        State({"type": "reflection-ratings-edit-effort", "index": ALL}, "value"),
        prevent_initial_call=True,
    )
    def save_reflection_ratings_definitions(n_clicks, values, interests, efforts):
        from layout import build_popup_table_rows
        defs = ConfigManager.get_reflection_ratings_definitions()
        new_defs = []
        for i, d in enumerate(defs):
            new_defs.append({
                "rating": d["rating"],
                "value": values[i] if i < len(values) else d["value"],
                "interest": interests[i] if i < len(interests) else d["interest"],
                "effort": efforts[i] if i < len(efforts) else d["effort"],
            })
        ConfigManager.set_reflection_ratings_definitions(new_defs)
        return build_popup_table_rows(new_defs), False

    # --- Editor Now Toggle: populate switch from DB on node change ---
    # Mirrors the dormant-toggle population pattern (event_callbacks.py).
    # The DB is the source of truth; the switch never holds a value the DB
    # doesn't agree with.
    @app.callback(
        Output("node-now", "value"),
        Input("node-original-name", "data"),
        Input("node-now-trigger-input", "value"),
        prevent_initial_call=True,
    )
    @prerendered
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
            now_nodes = manager.get_now_nodes()
            current_count = len(now_nodes)
            if current_count >= ConfigManager.get_now_node_cap():
                ts = int(_time.time() * 1000)
                return f"refused|{ts}", f"refused|{ts}"
            max_now = max([n.now for n in now_nodes]) if now_nodes else 0
            node.now = max_now + 1
        elif not wants_now and is_now:
            node.now = 0
        manager.update_node(node)
        return f"{node_name}|{int(_time.time() * 1000)}", no_update

    # --- Context-Menu Now Toggle ---
    # Right-click → "Now" on the canvas / mini-graphs / goal sidebar
    # writes a JSON list of names + timestamp to toggle-now-trigger-input.
    # Set the selection to one deterministic state, then bump node-now-trigger-
    # input to cause the canvas to re-render. If any target is not Now, every
    # target is set Now; only an all-Now selection is cleared. This mirrors the
    # Done bulk action and avoids a mixed selection silently swapping states.
    @app.callback(
        Output("node-now-trigger-input", "value", allow_duplicate=True),
        Output("now-cap-refused-trigger", "value", allow_duplicate=True),
        Input("toggle-now-trigger-input", "value"),
        prevent_initial_call=True,
    )
    def handle_now_trigger(trigger_data):
        import time as _time
        if not trigger_data:
            return no_update, no_update
        try:
            raw = trigger_data.split('|')[0]
            names = json.loads(raw) if raw else []
        except (ValueError, json.JSONDecodeError):
            return no_update, no_update
        if not names:
            return no_update, no_update
        nodes = [n for n in (manager.get_node(name) for name in names) if n]
        if not nodes:
            return no_update, no_update
        wants_now = any(node.now <= 0 for node in nodes)

        # Track count locally so a bulk set-Now stops at the cap. Pull
        # the live count once, then update it as we flip — get_now_nodes
        # would re-query the DB each iteration and miss our pending writes.
        now_nodes = manager.get_now_nodes()
        current_count = len(now_nodes)
        max_now = max([n.now for n in now_nodes]) if now_nodes else 0
        refused_any = False
        for node in nodes:
            if not wants_now and node.now > 0:
                # Clearing an all-Now selection is always allowed.
                node.now = 0
                current_count -= 1
            elif wants_now and node.now <= 0:
                if current_count >= ConfigManager.get_now_node_cap():
                    refused_any = True
                    continue  # Cap reached — skip this set-Now.
                max_now += 1
                node.now = max_now
                current_count += 1
            else:
                continue
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
        Output("now-cap-toast", "children"),
        Input("now-cap-refused-trigger", "value"),
        prevent_initial_call=True,
    )
    def show_now_cap_toast(trigger):
        if not trigger:
            return False, no_update
        cap = ConfigManager.get_now_node_cap()
        return True, f"{cap} Now nodes is the cap. Clear one to make room."

    # --- Drag and drop reordering of Now cards ---
    @app.callback(
        Output("node-now-trigger-input", "value", allow_duplicate=True),
        Input("now-drag-order-input", "value"),
        prevent_initial_call=True,
    )

    def handle_now_reorder(order_json):
        if not order_json:
            return no_update
        try:
            names = json.loads(order_json)
        except (json.JSONDecodeError, TypeError):
            return no_update
        if isinstance(names, list) and names:
            manager.reorder_now_nodes(names)
            import time as _time
            return f"reorder|{int(_time.time() * 1000)}"
        return no_update
