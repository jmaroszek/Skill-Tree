"""
Callback definitions for the Skill Tree Dash application.
"""

from editor_values import (
    _calibration_modal_text,
    _calibration_unit_for,
    _friendly_time_estimates,
)

import functools
import json
import logging
import time
import database
from sidebar_state import _compute_sidebar_styles
from core_response import CoreResponse
from canvas_view import build_canvas_view, canvas_wanted, CANVAS_DEFERRED

from typing import List, Set

import dash
from dash import html, Input, Output, State, ALL, ctx, no_update, ClientsideFunction

from graph_manager import GraphManager
from event_manager import EventManager
from canvases import CANVASES
from prerender import prerendered
from config import (ConfigManager, sort_subcontexts, SIDEBAR_TRANSLATE_CLOSED,
                    DEFAULT_GRAPH_LAYOUT)
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_DONE
import bridge_payloads
from node_commands import (
    handle_save, handle_delete, handle_toggle_done, handle_group_delete,
    prior_node_for_completion, apply_dormancy, conflicting_node_name,
)
from callback_helpers import (
    get_trigger_id, get_all_triggered_ids,
    node_options, build_filters, is_filters_active,
    render_alias_rows, alias_rows_label, update_alias_rows,
    resource_link_values,
    resolve_active_node_id, normalize_name_for_comparison,
    build_editor_snapshot, is_form_dirty_vs_snapshot, NEW_NODE_SNAPSHOT,
    snapshot_from_form_state, EDITOR_FORM, editor_form_values_from, dormancy_for_save,
    follow_done_status,
    compute_habit_time_omp, resolve_time_mode, resolve_value_mode,
    habit_editor_view, ALL_WEEKDAYS, habit_preview_text,
    build_node_element, build_edge_element, canvas_node_styles,
)
import style_tokens as tokens
from ui_kit import (progress_bar_color)
from duration_ui import work_time_tooltip

logger = logging.getLogger(__name__)


def _unexpected_error_message(action):
    """Log the exception being handled, and describe it for the user.

    Call this from an ``except`` block. The traceback goes to the log file,
    where a bug report can pick it up, and the user sees what failed rather
    than the exception's text.
    """
    logger.exception("%s failed", action)
    return (f"Error: {action} failed unexpectedly. The details are in the log, "
            "which a bug report should include.")

manager = GraphManager()
event_manager = EventManager()


# core_engine's outputs are CoreResponse's fields. This constant and the helper
# below let the tab-gating guard return a no_update tuple of the correct arity;
# test_core_engine_tab_gate checks it against the callback's registration.
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

# The filter sidebar's controls. They choose which nodes the canvas shows and
# nothing else.
_FILTER_TRIGGERS = frozenset({
    'filter-context', 'filter-subcontext', 'filter-done', 'filter-dormant',
    'filter-community', 'community-method', 'filter-value', 'filter-interest',
    'filter-time', 'filter-time-unit', 'filter-difficulty', 'filter-node-type',
    'filter-time-min', 'filter-search-query',
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


# The editor's own saves: each commits the whole form, so the form is what
# the database holds afterwards.
_EDITOR_SAVE_TRIGGERS = ('btn-save', 'btn-save-close', 'btn-unsaved-save')

# What changes a node's Done status outside the editor: the node menu's
# toggles, and the undo-Done confirmation, which also re-blocks the Done
# nodes after the one it reopens. None of them loads another node into the
# editor, which populate_editor would be doing at the same moment.
_STATUS_CHANGING_TRIGGERS = ('btn-toggle-done-node', 'toggle-done-trigger-input',
                             'btn-undo-done-confirm')

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


def _editor_kept_open(ed_style):
    """The editor style for a refused save: open, so the form stays on screen.

    Save & Close computes a closed style before the save runs. A save that is
    then refused must not slide the form away with the user's input in it.
    """
    if not isinstance(ed_style, dict):
        return ed_style
    return {**ed_style, 'transform': "translateX(0px)"}


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
        Output('filter-time-min', 'value'),
        Output('filter-time', 'value'),
        Output('filter-time-unit', 'value'),
        Output('filter-done', 'value', allow_duplicate=True),
        Output('filter-dormant', 'value', allow_duplicate=True),
        Output('filter-text', 'value', allow_duplicate=True),
        Output('filter-text-scope', 'value'),
        Input('btn-clear-filters', 'n_clicks'),
        Input('btn-details-focus', 'n_clicks'),
        prevent_initial_call=True,
    )
    def clear_filters(_clear_clicks, _focus_clicks):
        return ([], [], 'louvain', 'All', [1, 10], [1, 10], [1, 10], None, None,
                'hours', [], [], '', [])

    # The Search query every canvas filters by: the field's text and the
    # descriptions switch, as one value. None without text, so a switch change
    # with nothing to search is not a filter change, and an unchanged query is
    # not rewritten. A rewrite would start a layout for the same nodes.
    app.clientside_callback(
        """
        function(text, scope, current) {
            var q = (text || '').trim();
            var next = q ? {text: q, descriptions: (scope || []).indexOf('descriptions') !== -1} : null;
            return JSON.stringify(next) === JSON.stringify(current || null)
                ? window.dash_clientside.no_update : next;
        }
        """,
        Output('filter-search-query', 'data'),
        Input('filter-text', 'value'),
        Input('filter-text-scope', 'value'),
        State('filter-search-query', 'data'),
        prevent_initial_call=True,
    )

    # The Search field's own clear button. It empties the field, which the
    # canvas then answers like any other change to it.
    app.clientside_callback(
        """
        function(clicks) {
            return clicks ? '' : window.dash_clientside.no_update;
        }
        """,
        Output('filter-text', 'value', allow_duplicate=True),
        Input('btn-clear-filter-text', 'n_clicks'),
        prevent_initial_call=True,
    )

    # The suggestions under the Search field come from the node editor's own
    # Search list, which holds every node's name. The script keeps the names; it
    # draws the panel (assets/filter_suggest.js).
    app.clientside_callback(
        """
        function(options) {
            var suggest = window.SkillTree && window.SkillTree.filterSuggest;
            if (suggest) suggest.setNames(
                (options || []).map(function (o) { return o.value; }));
        }
        """,
        Input('search-node', 'options'),
    )

    # An applied query outlines the field, so a narrowing is never invisible.
    app.clientside_callback(
        """
        function(text) {
            return 'editor-field-group filter-search'
                + (text && text.trim() ? ' filter-search-active' : '');
        }
        """,
        Output('filter-search', 'className'),
        Input('filter-text', 'value'),
        prevent_initial_call=True,
    )

    # The placeholder says what the field searches, and follows the switch.
    # The opening text is in build_filters_content.
    app.clientside_callback(
        """
        function(scope) {
            return (scope || []).indexOf('descriptions') !== -1
                ? 'Filter by names, aliases and descriptions...'
                : 'Filter by names and aliases...';
        }
        """,
        Output('filter-text', 'placeholder'),
        Input('filter-text-scope', 'value'),
        prevent_initial_call=True,
    )

    # A minimum above the maximum matches nothing, so build_filters ignores
    # the time range then; outline both fields so that is not silent.
    app.clientside_callback(
        """
        function(low, high) {
            var crossed = low !== null && low !== undefined && low !== ''
                && high !== null && high !== undefined && high !== ''
                && Number(low) > Number(high);
            return [crossed, crossed];
        }
        """,
        Output('filter-time-min', 'invalid'),
        Output('filter-time', 'invalid'),
        Input('filter-time-min', 'value'),
        Input('filter-time', 'value'),
    )

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
            pct = completion.get('pct', 0)
            remaining = completion.get('remaining_time', 0)

            lines = [marker, header]

            if total > 0:
                bar_color = progress_bar_color(pct)
                lines += [
                    html.Hr(style={"margin": "6px 0", "borderColor": tokens.BORDER_PANEL}),
                    html.Div([html.Strong("Progress: "), f"{pct}% of the estimated work"]),
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
         Input('editor-save-result-store', 'data'),
         Input('search-node', 'value'),
         Input('background-click-input', 'value'),
         Input('btn-new-node', 'n_clicks'),
         Input('btn-editor-new', 'n_clicks'),
         Input('edit-trigger-input', 'value'),
         Input('details-edit-trigger-input', 'value'),
         Input('details-add-choice-input', 'value')],
        [State('sidebar-editor-container', 'style'),
         State('node-original-name', 'data'),
         State('pending-navigation-store', 'data'),
         State('editor-pristine-snapshot', 'data'),
         State('details-selected-node-store', 'data'),
         EDITOR_FORM],
        # Nothing to populate on page load. The form's defaults and its empty
        # alias and link rows are in the layout, and every path that opens
        # the editor runs this callback, which sends the relationship options.
        # The load-time run used to send ~230 KB of those options and set off
        # a dozen follow-on callbacks, all before the editor could be seen.
        prevent_initial_call=True,
    )
    def populate_editor(data, add_clicks, discard_clicks, save_result, search_val, _bg_click, new_node_clicks, editor_new_clicks, edit_trigger_val,
                        details_edit_trigger_val, details_add_choice,
                        ed_style, original_name, pending_nav, pristine_snapshot,
                        details_selected_node, form):
        """Populate the editor sidebar form fields when a node is selected, searched, or cleared.

        `form` is what the editor holds now (callback_helpers.EDITOR_FORM),
        checked against `pristine_snapshot` before a switch discards it.
        """
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
            return is_form_dirty_vs_snapshot(pristine_snapshot, editor_form_values_from(form))

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

        # The unsaved-changes dialog's Save moves on only once the save has
        # committed, which core_engine reports here. It used to move on at
        # the click, so a refused save (a name clash, a cycle) still swapped
        # the form out and lost the edits the error was about.
        if trigger_id == 'editor-save-result-store':
            if (save_result or {}).get('via') != 'btn-unsaved-save':
                return [dash.no_update] * len(def_out)
            trigger_id = 'btn-unsaved-save'

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
                edit_node_name = bridge_payloads.strip_stamp(edit_val)
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
        Input('editor-save-result-store', 'data'),
        [State('node-original-name', 'data'),
         EDITOR_FORM],
        prevent_initial_call=True,
    )
    def sync_original_name_after_save(save_result, cur_original_name, form):
        # core_engine writes the result only once a save has committed, with
        # the name it saved under. This used to fire on the Save click and
        # poll the database for the form's name, which a refused save could
        # also find: saving a new node under an existing node's name found
        # that node, so the editor adopted it and the next Save overwrote it.
        # The unsaved-changes dialog's Save moves on to another node instead,
        # and populate_editor handles that.
        if (not isinstance(save_result, dict)
                or save_result.get('via') not in ('btn-save', 'btn-save-close')):
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        linted = save_result.get('name')
        if not linted or manager.get_node(linted) is None:
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
        snapshot = snapshot_from_form_state(editor_form_values_from(form), linted,
                                            linted_aliases)
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

    # --- Work-time tooltips: habit wording, and live hour rates ---
    # The layout builds these once per page load. The editor heading's text
    # depends on the Habit switch, and both tooltips quote the hour rates, which
    # Settings can change. Settings saves close the modal, so its is_open covers
    # both the open and the close.
    @app.callback(
        Output('node-time-heading-tooltip', 'children'),
        Output('time-calibration-heading-tooltip', 'children'),
        Input('node-time-habit-mode', 'value'),
        Input('settings-modal', 'is_open'),
        prevent_initial_call=True,
    )
    def refresh_work_time_tooltips(habit_mode_val, _settings_open):
        habit = bool(habit_mode_val and 'habit' in habit_mode_val)
        return (work_time_tooltip("habit" if habit else "estimate"),
                work_time_tooltip("actual"))

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
        # The time fields sit below the fold; hovering Save says why it's off.
        Output('btn-save', 'title'),
        Output('btn-save-close', 'title'),
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
            return "", hidden, False, False, "", ""

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
            msg = "Enter at least an Expected estimate, or both Lower and Upper."
            return msg, visible, True, True, msg, msg

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
            return msg, visible, True, True, msg, msg

        errors = []
        if has_o and has_m and o > m:
            errors.append("Lower must be ≤ Expected")
        if has_m and has_p and m > p:
            errors.append("Expected must be ≤ Upper")
        if has_o and has_p and o > p:
            errors.append("Lower must be ≤ Upper")

        if errors:
            msg = "; ".join(errors)
            return msg, visible, True, True, msg, msg
        return "", hidden, False, False, "", ""

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
         Output('time-calibration-title', 'children', allow_duplicate=True),
         Output('editor-save-result-store', 'data'),
         Output('node-status-done', 'value', allow_duplicate=True),
         Output('editor-pristine-snapshot', 'data', allow_duplicate=True)],

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
         Input('btn-editor-new', 'n_clicks'),
         # Also appended at the end of the Inputs: the Time range's minimum,
         # then the Search query.
         Input('filter-time-min', 'value'),
         Input('filter-search-query', 'data')],

        [State('sidebar-editor-container', 'style'),
         State('node-original-name', 'data'),
         State('details-goal-sidebar', 'style'),
         State('events-sidebar-container', 'style'),
         State('pending-navigation-store', 'data'),
         State('editor-pristine-snapshot', 'data'),
         State('pending-undo-done-store', 'data'),
         State('canvas-payload-stamp', 'data'),
         EDITOR_FORM],
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
                     btn_undo_done_confirm, btn_editor_new, f_time_min,
                     f_search,
                     ed_style, original_name, goal_sidebar_style, events_sidebar_style,
                     pending_nav_store, pristine_snapshot, pending_undo_done, canvas_stamp,
                     form):
        """Central state callback handling node CRUD, filtering, and UI updates.

        The existing Dash wiring preserves mutation and refresh ordering. Sidebar
        decisions and canvas rendering are delegated; CoreResponse names the stable
        output contract so partial responses do not depend on numeric slots.
        `form` is the node editor's form (callback_helpers.EDITOR_FORM).
        """
        form = form or {}
        # The form's fields, under the names the save below reads them by.
        # The *_val names are the raw switches the save resolves into modes.
        name, n_type, desc = form.get('name'), form.get('n_type'), form.get('desc')
        context, subctx, status_done = form.get('context'), form.get('subctx'), form.get('status_done')
        val, interest, diff = form.get('val'), form.get('interest'), form.get('diff')
        time_o, time_m, time_p = form.get('time_o'), form.get('time_m'), form.get('time_p')
        time_unit = form.get('time_unit')
        e_needs_h, e_needs_s = form.get('e_needs_h'), form.get('e_needs_s')
        e_supp_h, e_supp_s, e_helps = form.get('e_supp_h'), form.get('e_supp_s'), form.get('e_helps')
        link_values, link_ids = form.get('link_values'), form.get('link_ids')
        time_mode_val, time_habit_mode_val = form.get('time_mode'), form.get('time_habit_mode')
        value_mode_val, alias_values = form.get('value_mode'), form.get('aliases')
        habit_duration, habit_duration_unit = form.get('habit_duration'), form.get('habit_duration_unit')
        habit_int_o, habit_int_m, habit_int_p = (form.get('habit_intensity_o'),
                                                 form.get('habit_intensity_m'),
                                                 form.get('habit_intensity_p'))
        habit_int_unit, habit_days = form.get('habit_intensity_unit'), form.get('habit_days')
        dormancy = form.get('dormancy')
        # What the sidebar decisions read: the form, and the baseline its
        # unsaved-changes check compares against.
        form_state = {**form, 'pristine_snapshot': pristine_snapshot}

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
            ed, goal, events = _compute_sidebar_styles(
                trigger_id, all_triggered_ids, search_val,
                ed_style, goal_sidebar_style, events_sidebar_style,
                pending_nav_store, form_state,
            )
            return _core_engine_editor_only_tuple(ed, goal, events)

        msg = ""
        completion_check_node = None  # Set when a node transitions to Done
        save_result = no_update  # set once an editor save commits
        # Names an editor save un-marked but kept Done, and the Done nodes
        # after them that reopening would re-block. The undo-Done modal asks.
        undo_pending = None
        undo_downstream = []

        # Check for any delayed event nodes or scheduled events that are due
        from event_manager import EventManager
        _event_mgr = EventManager()
        _event_mgr.check_pending_activations()
        _event_mgr.check_scheduled_triggers()

        filters = build_filters(f_context, f_subcontext, f_done, f_value, f_interest, f_time, f_difficulty, f_node_types, f_time_unit=f_time_unit, f_show_dormant=f_show_dormant,
                                f_time_min=f_time_min, f_search=f_search)

        # Editor Sidebar State — delegate to the shared helper so both the
        # short-circuit path above and the full path below compute sidebars
        # identically.
        next_ed_style, next_goal_style, next_events_sidebar_style = _compute_sidebar_styles(
            trigger_id, all_triggered_ids, search_val,
            ed_style, goal_sidebar_style, events_sidebar_style,
            pending_nav_store, form_state,
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
        if trigger_id in _EDITOR_SAVE_TRIGGERS:
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
            # A new node, or a rename, may not take another node's name: the
            # save would update that node in place and wipe its relationships.
            clash = conflicting_node_name(manager, name, original_name)
            if clash:
                msg = (f"Error: A node named '{clash}' already exists. Choose a "
                       f"different name, or search for '{clash}' to edit it.")
                return _core_engine_save_error_tuple(
                    msg, _editor_kept_open(next_ed_style), next_goal_style,
                    next_events_sidebar_style)
            # Done is hidden while Dormant is on; a sleeping node isn't finished.
            if (dormancy or {}).get('dormant'):
                status_done = []
            try:
                with database.transaction():
                    _prior_for_completion = prior_node_for_completion(
                        manager, name, original_name)
                    _was_done = bool(_prior_for_completion
                                     and _prior_for_completion.status == STATUS_DONE)
                    # Track if this save marks the node Done. Only count a true
                    # Open/Blocked → Done transition (or a brand-new node created
                    # Done) — re-saving an already-Done node must not re-trigger
                    # the time-calibration modal.
                    if status_done and STATUS_DONE in (status_done or []):
                        if not _was_done:
                            completion_check_node = name
                    # Un-marking a Done node re-blocks the Done nodes after
                    # it, and the node menu asks before doing that. The save
                    # keeps it Done; below, once its relationships are saved,
                    # it is either reopened or the user is asked.
                    reopening = _was_done and STATUS_DONE not in (status_done or [])
                    if reopening:
                        status_done = [STATUS_DONE]

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

                    # Still Done unless a new unfinished prerequisite has
                    # already re-blocked it.
                    _saved = manager.get_node(name) if reopening else None
                    if _saved is not None and _saved.status == STATUS_DONE:
                        undo_downstream = manager.get_downstream_done_dependents(name)
                        if undo_downstream:
                            undo_pending = [name]
                        else:
                            _saved.status = STATUS_OPEN
                            manager.update_node(_saved)

                    # Priority rank is deliberately NOT written here. The
                    # Goals sidebar owns it, because ranking is a judgement
                    # about the whole list rather than about one node, and it
                    # is the only surface that shows the list. This block used
                    # to rewrite the ranking from the editor's hidden select on
                    # every Goal save.
                # Reached only when the transaction committed.
                save_result = {"name": name, "via": trigger_id,
                               "ts": int(time.time() * 1000)}
            except (ValueError, TypeError) as e:
                msg = f"Error: {e}"
                return _core_engine_save_error_tuple(
                    msg, _editor_kept_open(next_ed_style), next_goal_style,
                    next_events_sidebar_style)
            except Exception:
                msg = _unexpected_error_message("Saving the node")
                return _core_engine_save_error_tuple(
                    msg, _editor_kept_open(next_ed_style), next_goal_style,
                    next_events_sidebar_style)
        elif trigger_id == 'btn-node-delete-confirm' and name:
            try:
                msg = handle_delete(manager, name)
            except ValueError as e:
                msg = f"Error: {e}"
            except Exception:
                msg = _unexpected_error_message("Deleting the node")
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
            except ValueError as e:
                msg = f"Error: {e}"
            except Exception:
                msg = _unexpected_error_message("Changing the node's status")
        elif trigger_id == 'toggle-done-trigger-input' and toggle_done_trigger_data:
            try:
                node_names = bridge_payloads.names(toggle_done_trigger_data)

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
                    # One transaction, so a failure part-way through leaves
                    # every selected node as it was. Prerequisites go first,
                    # so a chain selected in any order can be completed.
                    if new_status == STATUS_DONE:
                        order = manager.completion_order([n.name for n in nodes])
                        nodes = sorted(nodes, key=lambda n: order.index(n.name))
                    with database.transaction():
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
            except ValueError as e:
                msg = f"Error: {e}"
            except Exception:
                msg = _unexpected_error_message("Changing the nodes' status")
        elif trigger_id == 'btn-undo-done-confirm' and pending_undo_done:
            # Modal confirmed: perform the previously-gated Done → Open toggle
            # on every node in pending_undo_done. Cascade re-blocks downstream
            # Done dependents via _update_node_state.
            try:
                target_names = list(pending_undo_done) if isinstance(pending_undo_done, list) else [pending_undo_done]
                flipped = 0
                with database.transaction():
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
            except ValueError as e:
                msg = f"Error: {e}"
            except Exception:
                msg = _unexpected_error_message("Reopening the nodes")
        elif trigger_id == 'group-delete-input' and group_delete_data:
            try:
                msg = handle_group_delete(manager, group_delete_data)
            except ValueError as e:
                msg = f"Error: {e}"
            except Exception:
                msg = _unexpected_error_message("Deleting the nodes")
        # Every mutation above has committed, so the view is all reads. One
        # snapshot serves them: naming the community filter's options alone
        # used to open a connection per node, about 0.3 s per render.
        with database.read_snapshot():
            view = build_canvas_view(
                manager, render_elements, trigger_id, active_node_id, community_method, filters, f_community, focus_goal, focus_subtree_override, focus_path_info)

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

        if all_triggered_ids <= _FILTER_TRIGGERS:
            # A filter only narrows the view. The search list, the option
            # lists and the stylesheet are what they were, no message or
            # modal can result, and the reset outputs below would each wake
            # their listeners: the save message alone woke six callbacks,
            # all landing inside the layout this filter change starts.
            return CoreResponse(elements=view.elements,
                                community_options=view.community_options)

        # The editor may be showing a node whose status just changed from
        # the node menu or a cascade; its Done switch follows.
        editor_done = editor_snapshot = no_update
        if trigger_id in _STATUS_CHANGING_TRIGGERS and original_name:
            editor_done, editor_snapshot = follow_done_status(
                manager.get_node(original_name), status_done, pristine_snapshot)

        # The undo-Done modal: the node menu's toggles open it earlier (a
        # return short-circuit in their branch), an editor save that
        # un-marked a node opens it here, and otherwise it stays closed
        # with the pending store cleared.
        return view._replace(
            message=msg,
            clear_disabled=False if msg else True,
            clear_intervals=0,
            editor_style=next_ed_style,
            goal_style=next_goal_style,
            events_style=next_events_sidebar_style,
            undo_open=bool(undo_pending),
            undo_body=(_build_undo_done_body(undo_pending, undo_downstream)
                       if undo_pending else ''),
            undo_pending=undo_pending,
            calibration_open=tc_modal_open,
            calibration_reference=tc_reference,
            calibration_pending=tc_pending,
            calibration_unit=tc_unit,
            calibration_title=tc_title,
            save_result=save_result,
            editor_done=editor_done,
            editor_snapshot=editor_snapshot,
        )

    # The filters-sidebar toggle and editor-sidebar fast-path clientside
    # callbacks live in sidebars_callbacks.register_sidebars_callbacks.

    @app.callback(
        Output('modal-undo-done-confirm', 'is_open', allow_duplicate=True),
        Output('pending-undo-done-store', 'data', allow_duplicate=True),
        Output('node-status-done', 'value', allow_duplicate=True),
        Output('editor-pristine-snapshot', 'data', allow_duplicate=True),
        Input('btn-undo-done-cancel', 'n_clicks'),
        Input('btn-undo-done-confirm', 'n_clicks'),
        State('pending-undo-done-store', 'data'),
        State('node-original-name', 'data'),
        State('editor-pristine-snapshot', 'data'),
        prevent_initial_call=True,
    )
    def close_undo_done_modal(_cancel, _confirm, pending, editing, snapshot):
        """Close the undo-Done modal and clear the pending store on either
        button. The actual toggle (on confirm) is performed by core_engine
        listening to btn-undo-done-confirm; this callback only manages the
        modal/store cleanup so the next toggle starts fresh.

        An editor save that un-marked a node kept it Done and asked. Cancel
        leaves it Done, so the editor's switch, and the saved-form snapshot
        the unsaved-changes check compares against, go back on.
        """
        if (get_trigger_id() == 'btn-undo-done-cancel'
                and editing and editing in (pending or [])):
            kept = ({**snapshot, 'status_done': [STATUS_DONE]}
                    if isinstance(snapshot, dict) else no_update)
            return False, None, [STATUS_DONE], kept
        return False, None, no_update, no_update

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
                    save_msg_out = (
                        f"Error marking '{target}' Done: {exc}"
                        if isinstance(exc, ValueError)
                        else _unexpected_error_message(f"Marking '{target}' Done"))
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
         State('editor-pristine-snapshot', 'data'),
         EDITOR_FORM],
        prevent_initial_call=True
    )
    def toggle_unsaved_modal(_close, _add, _cancel, _save, _discard,
                             ed_style, pristine_snapshot, form):
        trig = get_trigger_id()
        if trig == 'btn-add':
            # btn-add is the toolbar toggle: only its close half (editor already
            # open) should guard against unsaved changes. Opening never does.
            editor_open = bool(ed_style) and ed_style.get('transform', '') == 'translateX(0px)'
            if not editor_open:
                return False
        elif trig != 'btn-close-editor':
            return False
        return is_form_dirty_vs_snapshot(pristine_snapshot, editor_form_values_from(form))

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
        trigger_id = get_trigger_id()
        if trigger_id == 'group-delete-request-input':
            if not request_value:
                return dash.no_update, dash.no_update, dash.no_update
            names = bridge_payloads.names(request_value)
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

    # Whether any filter narrows the Nodes canvas, for its count and for
    # Next's indicator. It writes only when the answer changes: a filter
    # change starts the Nodes layout, and each write would land inside it.
    @app.callback(
        Output('canvas-filters-active-store', 'data'),
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
        Input('filter-time-min', 'value'),
        Input('filter-search-query', 'data'),
        State('canvas-filters-active-store', 'data'),
        prevent_initial_call=True,
    )
    @prerendered
    def update_canvas_filters_active(f_type, f_ctx, f_sub, f_comm,
                                     f_comm_method, f_val, f_int, f_diff,
                                     f_time, f_time_unit, f_time_min, f_search,
                                     current):
        active = is_filters_active(
            node_type=f_type, context=f_ctx, subcontext=f_sub,
            community=f_comm,
            community_method=f_comm_method, value=f_val,
            interest=f_int, difficulty=f_diff, time=f_time,
            time_min=f_time_min, search=f_search)
        if active == bool(current):
            return no_update, no_update
        return active, "filtered" if active else ""

    # The count is read in the browser from the payload's stamp, as Details
    # counts its own.
    app.clientside_callback(
        """
        function(stamp, filtered) {
            var n = (stamp && stamp.nodes) || 0;
            var text = n + (n === 1 ? ' node' : ' nodes');
            return filtered ? text + ' · filtered' : text;
        }
        """,
        Output('canvas-node-count', 'children'),
        Input('canvas-payload-stamp', 'data'),
        Input('canvas-filters-active-store', 'data'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('focus-goal-store', 'data', allow_duplicate=True),
        Input('btn-clear-focus', 'n_clicks'),
        prevent_initial_call=True,
    )
    def clear_focus(n_clicks):
        if n_clicks:
            return None
        return dash.no_update


    # The unexpected-error modal opens from app.report_callback_error, through
    # set_props, so only its Close needs a callback.
    app.clientside_callback(
        "function(n) { return false; }",
        Output("modal-app-error", "is_open", allow_duplicate=True),
        Input("btn-close-app-error", "n_clicks"),
        prevent_initial_call=True,
    )

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
        node_name = bridge_payloads.strip_stamp(value)
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

        # Bypass: pending-store -> cytoscape.elements. A hidden canvas's
        # payload waits for its tab (assets/hidden_canvas_payloads.js).
        app.clientside_callback(
            """
            function(pending, activeTab) {
                var st = window.SkillTree || {};
                var noUpdate = window.dash_clientside.no_update;
                function frozen(elements) {
                    if (st.isFrozen && st.isFrozen(__CANVAS__) && st.applyDelta) {
                        st.applyDelta(__CANVAS__, elements);
                        return true;
                    }
                    return false;
                }
                var fired = (window.dash_clientside.callback_context.triggered || [])
                    .map(function (t) { return t.prop_id; });
                if (fired.indexOf(__PENDING__ + '.data') === -1) {
                    // The tab changed. What this canvas was holding lands
                    // once the tab has painted.
                    if (st.showHeldPayload) {
                        st.showHeldPayload(__CANVAS__, activeTab, function (elements) {
                            if (!frozen(elements)) {
                                window.dash_clientside.set_props(__CYTOSCAPE__, {elements: elements});
                            }
                        });
                    }
                    return noUpdate;
                }
                // Anything but a list is a render with no elements to apply,
                // such as the Nodes canvas's deferred marker.
                if (!Array.isArray(pending)) return noUpdate;
                if (st.holdHiddenPayload && st.holdHiddenPayload(__CANVAS__, pending, activeTab)) {
                    return noUpdate;
                }
                return frozen(pending) ? noUpdate : pending;
            }
            """.replace('__CANVAS__', js_canvas).replace('__PENDING__', repr(pending_id))
               .replace('__CYTOSCAPE__', repr(cytoscape_id)),
            Output(cytoscape_id, 'elements'),
            Input(pending_id, 'data'),
            Input('main-tabs', 'active_tab'),
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
        names = bridge_payloads.names(trigger_data)
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
