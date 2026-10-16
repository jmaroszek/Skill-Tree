"""
Callback definitions for the Skill Tree Dash application.
"""

from skilltree.features.review.values import (
    calibration_modal_text,
    calibration_unit_for,
)

import functools
import logging
import time
from skilltree.store import database
from skilltree.engine.sidebars import _compute_sidebar_styles
from skilltree.engine.response import CoreResponse
from skilltree.ui.canvas.view import build_canvas_view, canvas_wanted, CANVAS_DEFERRED

from typing import List, Set

import dash
from dash import html, Input, Output, State, no_update

from skilltree.store.graph.manager import GraphManager
from skilltree.store.events import EventManager
from skilltree.store.settings import ConfigManager
from skilltree.ui.styles import SIDEBAR_TRANSLATE_CLOSED
from skilltree.domain.models import STATUS_OPEN, STATUS_DONE
from skilltree.ui import payloads as bridge_payloads
from skilltree.store.commands import (
    handle_save, handle_delete, handle_toggle_done, handle_group_delete,
    prior_node_for_completion, apply_dormancy, conflicting_node_name,
    finish_bridge, done_names, ReopensDoneNodes,
)
from skilltree.features.editor.form import (
    resource_link_values, EDITOR_FORM, dormancy_for_save, NEW_NODE_DORMANCY, woke_during_edit, follow_done_status,
    resolve_done_intent, RELATIONSHIP_FIELDS, stored_relationships,
    resolve_relationship_intent,
)
from skilltree.ui.components.confirm import reopen_body
from skilltree.ui.canvas.elements import (
    build_node_element, build_edge_element, canvas_node_styles,
)
from skilltree.ui.filters import (
    build_filters,
)
from skilltree.ui.dash_tools import get_trigger_id, get_all_triggered_ids
from skilltree.domain.time import (
    compute_habit_time_omp, resolve_time_mode, resolve_value_mode,
    time_estimate_problem,
)
from skilltree.domain.names import format_name
from skilltree.features.editor.callbacks import register_editor_callbacks
from skilltree.features.filters.callbacks import register_filter_callbacks
from skilltree.ui.canvas.callbacks import register_canvas_callbacks
from skilltree.features.nodes.callbacks import register_nodes_callbacks
from skilltree.features.home.now import register_now_callbacks
from skilltree.features.review.ratings import register_reflection_ratings_callbacks

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
_EDITOR_SAVE_TRIGGERS = ('btn-save', 'btn-unsaved-save')

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

    The unsaved-changes dialog's Save computes a closed style before the save
    runs. A save that is
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


# What generate_elements takes as ``active_node_id`` to leave every node's
# selection as the canvas has it. dash-cytoscape changes a node's selection
# only when its ``selected`` differs from the previous render's, so a node
# without one is left alone.
KEEP_SELECTION = object()


@database.snapshot_read
def generate_elements(filters=None, active_node_id=None, community_names=None,
                      graph=None, events=None):
    """Convert nodes and edges from the database into Cytoscape elements.

    ``active_node_id`` names the one node to select, None selects none, and
    KEEP_SELECTION leaves the selection to the canvas.

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

    def _selected(node):
        if active_node_id is KEEP_SELECTION:
            return None
        return node.name == active_node_id if active_node_id else False

    elements = [
        build_node_element(node, styles, selected=_selected(node))
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
         Output('editor-pristine-snapshot', 'data', allow_duplicate=True),
         Output('modal-editor-reopen-confirm', 'is_open', allow_duplicate=True),
         Output('editor-reopen-confirm-body', 'children'),
         Output('editor-reopen-pending-store', 'data'),
         Output('filter-community', 'value', allow_duplicate=True),
         Output('community-memory-store', 'data')],

        [Input('btn-save', 'n_clicks'), Input('btn-node-delete-confirm', 'n_clicks'),
         Input('filter-context', 'value'), Input('filter-subcontext', 'value'), Input('filter-done', 'value'),
         Input('filter-dormant', 'value'),
         Input('search-node', 'value'),
         Input('cytoscape-graph', 'tapNodeData'),
         Input('filter-community', 'value'), Input('community-method', 'value'),
         Input('filter-value', 'value'), Input('filter-interest', 'value'),
         Input('filter-time', 'value'), Input('filter-time-unit', 'value'),
         Input('filter-difficulty', 'value'),
         Input('suggestion-count-store', 'data'),
         Input('btn-edit-node', 'n_clicks'), Input('btn-add', 'n_clicks'),
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
         # A State, like the selection above, so the argument order holds.
         # Settle only lays out what the canvas shows. As an Input it rebuilt
         # the whole canvas payload, and that response, its restyle and the
         # callbacks chained to save-output landed inside the Settle's
         # animation as stalls of up to 120 ms.
         State('graph-settings-relayout', 'n_clicks'),
         Input('btn-undo-done-confirm', 'n_clicks'),
         # Appended at the end of the Inputs so existing positional indices
         # (used by core_engine tests) stay stable. The toolbar "+" new-node
         # button; only its trigger_id matters, the value is unused.
         Input('btn-editor-new', 'n_clicks'),
         # Also appended at the end of the Inputs: the Time range's minimum,
         # then the Search query.
         Input('filter-time-min', 'value'),
         Input('filter-search-query', 'data'),
         # Then the confirmation of a save that reopens Done nodes.
         Input('btn-editor-reopen-confirm', 'n_clicks')],

        [State('sidebar-editor-container', 'style'),
         State('node-original-name', 'data'),
         State('details-goal-sidebar', 'style'),
         State('events-sidebar-container', 'style'),
         State('pending-navigation-store', 'data'),
         State('editor-pristine-snapshot', 'data'),
         State('pending-undo-done-store', 'data'),
         State('canvas-payload-stamp', 'data'),
         State('bridge-pending-store', 'data'),
         State('editor-reopen-pending-store', 'data'),
         State('community-memory-store', 'data'),
         EDITOR_FORM],
        prevent_initial_call='initial_duplicate'
    )
    def core_engine(save_clicks, delete_confirm_clicks, f_context, f_subcontext, f_done, f_show_dormant, search_val,
                     tapped_node,  # Cytoscape tapNodeData dict (not a Node object)
                     f_community, community_method, f_value, f_interest, f_time, f_time_unit, f_difficulty, sugg_count,
                     btn_edit, btn_add, btn_close_ed, btn_goals_toggle, btn_unsaved_save, btn_unsaved_discard, settings_save_status, migration_open, btn_toggle_done,
                     group_delete_data, f_node_types,
                     active_suggestion_id,
                     focus_goal,
                     edit_trigger_data, details_edit_trigger_data, toggle_done_trigger_data, _node_now_trigger, _events_refresh, _details_refresh, _bg_click,
                     active_tab, _relayout,
                     btn_undo_done_confirm, btn_editor_new, f_time_min,
                     f_search, btn_editor_reopen_confirm,
                     ed_style, original_name, goal_sidebar_style, events_sidebar_style,
                     pending_nav_store, pristine_snapshot, pending_undo_done, canvas_stamp,
                     bridge_pending, editor_reopen_pending, community_memory, form):
        """Central state callback handling node CRUD, filtering, and UI updates.

        The existing Dash wiring preserves mutation and refresh ordering. Sidebar
        decisions and canvas rendering are delegated; CoreResponse names the stable
        output contract so partial responses do not depend on numeric slots.
        `form` is the node editor's form (editor form.EDITOR_FORM).
        """
        form = form or {}
        # The form's fields, under the names the save below reads them by.
        # The *_val names are the raw switches the save resolves into modes.
        name, n_type, desc = form.get('name'), form.get('n_type'), form.get('desc')
        context, subctx, status_done = form.get('context'), form.get('subctx'), form.get('status_done')
        val, interest, diff = form.get('val'), form.get('interest'), form.get('diff')
        time_o, time_m, time_p = form.get('time_o'), form.get('time_m'), form.get('time_p')
        time_unit = form.get('time_unit')
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

        # A save that would reopen Done nodes was held for the user to
        # confirm. Their yes finishes it as the Save button they pressed.
        reopen_confirmed = False
        if trigger_id == 'btn-editor-reopen-confirm':
            via = (editor_reopen_pending or {}).get('via')
            if not btn_editor_reopen_confirm or via not in _EDITOR_SAVE_TRIGGERS:
                return _core_engine_noop_tuple()
            trigger_id, all_triggered_ids, reopen_confirmed = via, {via}, True

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
        from skilltree.store.events import EventManager
        EventManager().run_sweeps()

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
                name = format_name(name.strip(), ConfigManager.get_name_formatting())
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
            try:
                with database.transaction():
                    _done_before = done_names(manager)
                    _prior_for_completion = prior_node_for_completion(
                        manager, name, original_name)
                    status_done = resolve_done_intent(
                        _prior_for_completion, status_done, pristine_snapshot)
                    from skilltree.store.events import EventManager
                    woke_from = woke_during_edit(
                        EventManager(), (original_name or name).strip(), dormancy,
                        pristine_snapshot)
                    if woke_from:
                        dormancy = None  # the wake stands; see woke_during_edit
                    sleeping = bool((dormancy or {}).get('dormant'))
                    if sleeping:
                        status_done = []
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
                    if reopening and not sleeping:
                        status_done = [STATUS_DONE]

                    multiplier = ConfigManager.get_time_multiplier(time_unit)
                    t_o = float(time_o or 0) * multiplier
                    t_m = float(time_m or 0) * multiplier
                    t_p = float(time_p or 0) * multiplier

                    # Intercept rename: if original name differs from current name, rename node atomically
                    if (trigger_id in _EDITOR_SAVE_TRIGGERS and
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
                    # Save is disabled while the estimate is invalid, but the
                    # unsaved-changes dialog's Save, and habit mode, went
                    # around the button. A refusal rolls the save back.
                    if time_mode == 'habit' and not (t_o or t_m or t_p):
                        raise ValueError("Enter a habit duration and the minutes "
                                         "per session, so it comes to some hours.")
                    if time_mode in ('manual', 'habit'):
                        problem = time_estimate_problem(t_o, t_m, t_p)
                        if problem:
                            raise ValueError(problem)
                    # Mirror time_mode: the shared resolver centralizes the
                    # Milestone-must-inherit-value invariant (Goals are exempt —
                    # they carry their own value).
                    value_mode = resolve_value_mode(n_type, value_mode_val)
                    _prior = manager.get_node(name)
                    was_dormant = bool(_prior and _prior.dormant)
                    # Wake before applying completion intent. Both still
                    # belong to this save and roll back together on refusal.
                    from skilltree.store.events import EventManager
                    if was_dormant and not sleeping:
                        EventManager().detach_node_from_all_events(name)
                        was_dormant = False
                    # The pickers were filled when the editor loaded. The link
                    # menu, the Details tab or a bridge may have changed this
                    # node's links since, so write the user's edits on top of
                    # what is stored rather than the lists as loaded, which
                    # would quietly undo those changes.
                    relationships = {key: form.get(key) for key in RELATIONSHIP_FIELDS}
                    if (_prior is not None and original_name
                            and isinstance(pristine_snapshot, dict)
                            and pristine_snapshot.get('name') == original_name.strip()):
                        relationships = resolve_relationship_intent(
                            stored_relationships(manager.get_edges(), name),
                            form, pristine_snapshot)
                    msg = handle_save(manager, name, n_type, desc, val, t_o, t_m, t_p,
                                      interest, diff, status_done, context, subctx,
                                      resource_link_values(link_values, link_ids),
                                      *(relationships[key] for key in RELATIONSHIP_FIELDS),
                                      time_mode=time_mode,
                                      value_mode=value_mode,
                                      habit_duration=habit_duration or 0,
                                      habit_duration_unit=habit_duration_unit or 'weeks',
                                      habit_intensity_o=habit_int_o or 0,
                                      habit_intensity_m=habit_int_m or 0,
                                      habit_intensity_p=habit_int_p or 0,
                                      habit_intensity_unit=habit_int_unit or 'min_per_session',
                                      habit_days=habit_days)

                    # A bridge replaces the link it was made across. Only
                    # the save that creates the node does it: once the node
                    # exists, its relationships are the user's to edit.
                    if bridge_pending and not original_name:
                        replaced = finish_bridge(manager, name, bridge_pending)
                        if replaced:
                            msg += (f", replacing the link from '{replaced[0]}' "
                                    f"to '{replaced[1]}'")

                    # Save aliases
                    clean_aliases = [a for a in (alias_values or []) if a and a.strip()]
                    manager.set_aliases(name, clean_aliases)

                    # Dormant switch and Event section. A refusal raises
                    # ValueError and rolls the whole save back.
                    apply_dormancy(manager, EventManager(), name,
                                   dormancy_for_save(dormancy), was_dormant)
                    if woke_from:
                        msg += (f". It woke from '{woke_from}' while you were "
                                "editing, so it stays awake")

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

                    # A new Hard prerequisite that isn't Done reopens the
                    # Done node it leads to, and the Done nodes after it. The
                    # user is asked first; raising rolls the save back. The
                    # node the user un-marked is reopening by their own hand.
                    if original_name and original_name in _done_before:
                        _done_before = (_done_before - {original_name}) | {name}
                    _reopened = _done_before - done_names(manager)
                    if reopening:
                        _reopened.discard(name)
                    if _reopened and not reopen_confirmed:
                        raise ReopensDoneNodes(sorted(_reopened))

                    # Priority rank is deliberately NOT written here. The
                    # Goals sidebar owns it, because ranking is a judgement
                    # about the whole list rather than about one node, and it
                    # is the only surface that shows the list. This block used
                    # to rewrite the ranking from the editor's hidden select on
                    # every Goal save.
                # Reached only when the transaction committed.
                # The status the save committed, which can differ from the
                # switch: an untouched switch follows a completion made
                # elsewhere, and sleeping or a pending undo changes it.
                _committed = manager.get_node(name)
                # `form` is the form as it was saved: the new baseline for the
                # unsaved-changes check (sync_original_name_after_save).
                save_result = {"name": name, "via": trigger_id,
                               "status_done": ([STATUS_DONE] if _committed.status == STATUS_DONE
                                               else []),
                               "form": form,
                               "ts": int(time.time() * 1000)}
                if woke_from:
                    # The node is awake, whatever the form said: that is the
                    # baseline, and populate_node_dormancy redraws the section.
                    save_result["form"] = {**form, "dormancy": dict(NEW_NODE_DORMANCY)}
                    save_result["woke"] = woke_from
            except ReopensDoneNodes as e:
                return tuple(CoreResponse(
                    editor_style=_editor_kept_open(next_ed_style),
                    goal_style=next_goal_style, events_style=next_events_sidebar_style,
                    reopen_open=True, reopen_body=reopen_body(e.names),
                    reopen_pending={'via': trigger_id}))
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
        elif trigger_id == 'btn-node-delete-confirm' and (original_name or '').strip():
            # Delete the node the editor loaded, never whatever the Name field
            # says now: a half-typed rename, or another node's name typed over
            # it, must not choose what gets deleted. A form that never loaded
            # a node has nothing stored to delete; the editor just closes.
            try:
                msg = handle_delete(manager, original_name.strip())
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
                # A sleeping node can't be Done, and one in the selection
                # used to refuse the whole action. It sits out instead.
                asleep = [n for n in nodes if n.dormant]
                nodes = [n for n in nodes if not n.dormant]
                if asleep and not nodes:
                    msg = "Error: a sleeping node can't be marked Done. Wake it first."
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
                    if asleep:
                        msg += f", leaving out {len(asleep)} sleeping"
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
        # The canvas keeps the nodes the user picked. A render picks for them
        # only when it was asked to show one node: a search, a save, or
        # entering focus, which clears it.
        if trigger_id in _EDITOR_SAVE_TRIGGERS:
            canvas_selection = name
        elif trigger_id == 'search-node' or (trigger_id == 'focus-goal-store' and focus_goal):
            canvas_selection = active_node_id
        else:
            canvas_selection = KEEP_SELECTION
        with database.read_snapshot():
            view = build_canvas_view(
                manager, render_elements, trigger_id, canvas_selection, community_method, filters, f_community, focus_goal, focus_subtree_override, focus_path_info,
                community_memory=community_memory)

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
            if _tc_node is not None and _tc_node.status == STATUS_DONE and not _tc_node.dormant:
                tc_modal_open = True
                tc_title, tc_reference = calibration_modal_text(_tc_node)
                tc_pending = {'mode': 'single', 'node': completion_check_node}
                tc_unit = calibration_unit_for(_tc_node.time)

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
                                community_options=view.community_options,
                                community_value=view.community_value,
                                community_memory=view.community_memory)

        # The editor may be showing a node whose status just changed from
        # the node menu or a cascade; its Done switch follows.
        editor_done = editor_snapshot = no_update
        if trigger_id in _STATUS_CHANGING_TRIGGERS and original_name:
            editor_done, editor_snapshot = follow_done_status(
                manager.get_node(original_name), status_done, pristine_snapshot)
        if (isinstance(save_result, dict)
                and save_result['status_done'] != (form.get('status_done') or [])):
            editor_done = save_result['status_done']

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
    # single callback to avoid races with the drain trigger. A Mark Done
    # redraws through the core engine, as a link change does, so the canvas
    # keeps the filters, the community, focus and the user's selection. This
    # callback used to draw it bare: every node, nothing selected.
    @app.callback(
        Output('modal-auto-done-suggestion', 'is_open'),
        Output('auto-done-suggestion-body', 'children'),
        Output('auto-done-candidates-store', 'data'),
        Output('details-refresh-trigger', 'data', allow_duplicate=True),
        Output('save-output', 'children', allow_duplicate=True),
        Input('graph-version-store', 'data'),
        Input('btn-auto-done-confirm', 'n_clicks'),
        Input('btn-auto-done-dismiss', 'n_clicks'),
        State('auto-done-candidates-store', 'data'),
        prevent_initial_call=True,
    )
    def manage_auto_done_modal(_version, _confirm, _dismiss, current_candidates):
        from skilltree.domain.models import STATUS_DONE
        trig = get_trigger_id()
        candidates = list(current_candidates or [])
        refresh_out = no_update
        save_msg_out = no_update

        if trig == 'btn-auto-done-confirm' and candidates:
            target = candidates.pop(0)
            node = manager.get_node(target)
            if node is None:
                save_msg_out = f"'{target}' no longer exists"
            elif node.status == STATUS_DONE:
                # Already Done via another path — silently skip.
                pass
            elif not manager.is_auto_done_ready(target):
                # Prereqs no longer all Done (e.g. a sibling un-done) —
                # don't force; let the user re-decide later.
                save_msg_out = (
                    f"'{target}' is no longer eligible — "
                    "its state or prerequisites changed."
                )
            else:
                try:
                    accepted = manager.complete_suggested_node(target)
                    save_msg_out = (f"Marked '{target}' as Done" if accepted
                                    else f"'{target}' is no longer eligible")
                    if accepted:
                        refresh_out = f"auto-done-{time.time()}"
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

        candidates = [c for c in candidates if manager.is_auto_done_ready(c)]

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
            return True, body, candidates, refresh_out, save_msg_out
        return False, "", [], refresh_out, save_msg_out


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
        import json
        import time
        if not n_clicks or not names:
            return dash.no_update
        return json.dumps(names) + '|' + str(time.time())

    @app.callback(
        Output('save-output', 'children', allow_duplicate=True),
        Output('clear-interval', 'disabled', allow_duplicate=True),
        Input('clear-interval', 'n_intervals'),
        prevent_initial_call=True
    )
    def clear_message(n):
        if n > 0: return "", True
        return dash.no_update, dash.no_update


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

    # The features split out of this function. create_app will register each
    # feature itself; until then the engine registers them here.
    register_editor_callbacks(app, services)
    register_filter_callbacks(app, services)
    register_canvas_callbacks(app, services)
    register_nodes_callbacks(app, services)
    register_now_callbacks(app, services)
    register_reflection_ratings_callbacks(app, services)


def resolve_active_node_id(all_triggered_ids, trigger_id, edit_trigger_data,
                           search_val, tapped_node, current_name):
    """Determine which node the editor should display.

    Prefers ``edit-trigger-input`` (carries the node ID explicitly) even when
    it is batched with another trigger like tapNodeData.
    """
    if ('edit-trigger-input' in all_triggered_ids or 'details-edit-trigger-input' in all_triggered_ids) and edit_trigger_data:
        return bridge_payloads.strip_stamp(edit_trigger_data)
    if trigger_id in ('background-click-input', 'btn-editor-new'):
        return None
    if trigger_id == 'search-node' and search_val:
        if search_val.startswith('alias:'):
            _mgr = GraphManager()
            alias_key = search_val[6:]
            # Case-insensitive resolve so 'alias:mathnotes' finds 'MathNotes'.
            resolved = _mgr.resolve_alias(alias_key)
            return resolved if resolved is not None else search_val
        return search_val
    if trigger_id == 'cytoscape-graph' and tapped_node:
        return tapped_node.get('id')
    return current_name
