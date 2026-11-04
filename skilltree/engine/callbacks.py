"""
Callback definitions for the Skill Tree Dash application.
"""

from skilltree.features.review.values import (
    calibration_modal_text,
    calibration_sections,
    calibration_unit_for,
)

import functools
import logging
import time
from skilltree.store import database
from skilltree.engine.sidebars import register_left_panel_callbacks
from skilltree.ui.left_panel import close_editor
from skilltree.engine.handlers import (
    SAVE_TRIGGERS, Request, SaveMemory, handle, undo_done_body, unexpected_error,
)
from skilltree.engine.response import CORE_OUTPUTS, CoreResponse, keyed
from skilltree.ui.canvas.view import build_canvas_view, canvas_wanted, deferred_canvas


import dash
from skilltree.ui.timing import TOAST_CLEAR_INTERVAL_MS
from skilltree.ui.toast import register_toast_timer
from dash import ClientsideFunction, html, Input, Output, State, no_update

from skilltree.store import settings
from skilltree.domain.models import STATUS_DONE
from skilltree.ui import payloads as bridge_payloads
from skilltree.ui.notices import error, info
from skilltree.features.editor.form import EDITOR_FORM
from skilltree.ui.filters import (
    build_filters,
)
from skilltree.ui.dash_tools import get_trigger_id, get_all_triggered_ids
from skilltree.store.graph.state import revisions
from skilltree.ui.canvas.elements import KEEP_SELECTION, generate_elements

logger = logging.getLogger(__name__)


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

# The filter sidebar's controls. They choose which nodes the canvas shows and
# nothing else.
_FILTER_TRIGGERS = frozenset({
    'filter-context', 'filter-subcontext', 'filter-done', 'filter-dormant',
    'filter-community', 'community-method', 'filter-value', 'filter-interest',
    'filter-time', 'filter-time-unit', 'filter-difficulty', 'filter-node-type',
    'filter-time-min', 'filter-search-query',
})


# The core callback's inputs and state, under the names core_engine takes them
# by. Its outputs are CORE_OUTPUTS (engine/response.py).
#
# What changes the graph comes in by its own door. When a callback fires again
# before its last run has answered, Dash throws that answer away, though the run
# still finishes on the server. Renders can replace each other. A save can't be
# replaced: a tab switch right after Save committed it and lost the answer, so the
# page went on holding the node's old name, and the next Save was refused as a
# duplicate of itself.
CORE_ACTIONS = dict(
    save_clicks=Input('btn-save', 'n_clicks'),
    delete_confirm_clicks=Input('btn-node-delete-confirm', 'n_clicks'),
    btn_unsaved_save=Input('btn-unsaved-save', 'n_clicks'),
    btn_toggle_done=Input('btn-toggle-done-node', 'n_clicks'),
    group_delete_data=Input('group-delete-input', 'value'),
    toggle_done_trigger_data=Input('toggle-done-trigger-input', 'value'),
    btn_undo_done_confirm=Input('btn-undo-done-confirm', 'n_clicks'),
    # The confirmation of a save that reopens Done nodes.
    btn_editor_reopen_confirm=Input('btn-editor-reopen-confirm', 'n_clicks'),
)
_ACTION_TRIGGERS = frozenset(dep.component_id for dep in CORE_ACTIONS.values())
CORE_RENDERS = dict(
    f_context=Input('filter-context', 'value'),
    f_subcontext=Input('filter-subcontext', 'value'),
    f_done=Input('filter-done', 'value'),
    f_show_dormant=Input('filter-dormant', 'value'),
    search_val=Input('search-node', 'value'),
    tapped_node=Input('cytoscape-graph', 'tapNodeData'),
    f_community=Input('filter-community', 'value'),
    community_method=Input('community-method', 'value'),
    f_value=Input('filter-value', 'value'),
    f_interest=Input('filter-interest', 'value'),
    f_time=Input('filter-time', 'value'),
    f_time_unit=Input('filter-time-unit', 'value'),
    f_difficulty=Input('filter-difficulty', 'value'),
    sugg_count=Input('suggestion-count-store', 'data'),
    settings_version=Input('settings-version-store', 'data'),
    f_node_types=Input('filter-node-type', 'value'),
    focus_goal=Input('focus-goal-store', 'data'),
    _node_now_trigger=Input('node-now-trigger-input', 'value'),
    _events_refresh=Input('events-refresh-trigger', 'data'),
    _details_refresh=Input('details-refresh-trigger', 'data'),
    _bg_click=Input('background-click-input', 'value'),
    active_tab=Input('main-tabs', 'active_tab'),
    f_time_min=Input('filter-time-min', 'value'),
    f_search=Input('filter-search-query', 'data'),
)
CORE_STATE = dict(
    # A State: selecting a suggestion asks the server for nothing.
    active_suggestion_id=State('selected-suggestion-store', 'data'),
    # A State too. Settle only lays out what the canvas shows. As an Input it
    # rebuilt the whole canvas payload, and that response, its restyle and
    # the callbacks chained to its message landed inside the Settle's
    # animation as stalls of up to 120 ms.
    _relayout=State('graph-settings-relayout', 'n_clicks'),
    original_name=State('node-original-name', 'data'),
    pristine_snapshot=State('editor-pristine-snapshot', 'data'),
    pending_undo_done=State('pending-undo-done-store', 'data'),
    canvas_stamp=State('canvas-payload-stamp', 'data'),
    bridge_pending=State('bridge-pending-store', 'data'),
    editor_reopen_pending=State('editor-reopen-pending-store', 'data'),
    community_memory=State('community-memory-store', 'data'),
    form=EDITOR_FORM,
)


def _as_state(inputs):
    return {name: State(dep.component_id, dep.component_property)
            for name, dep in inputs.items()}


def register_engine_callbacks(app, services):
    """Register all Dash callbacks for the application."""
    manager = services.graph
    event_manager = services.events
    render_elements = functools.partial(generate_elements, manager, event_manager)
    saves = SaveMemory()

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
        Input('settings-version-store', 'data'),
        State('graph-version-store', 'data'),
        prevent_initial_call=True,
    )
    def sync_graph_version(_stamp, _events, _details, _settings, current):
        if revisions.graph != current:
            return revisions.graph
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
    @keyed
    def core_engine(save_clicks, delete_confirm_clicks, f_context, f_subcontext, f_done, f_show_dormant, search_val,
                     tapped_node,  # Cytoscape tapNodeData dict (not a Node object)
                     f_community, community_method, f_value, f_interest, f_time, f_time_unit, f_difficulty, sugg_count,
                     btn_unsaved_save, settings_version, btn_toggle_done,
                     group_delete_data, f_node_types,
                     active_suggestion_id,
                     focus_goal,
                     toggle_done_trigger_data, _node_now_trigger, _events_refresh, _details_refresh, _bg_click,
                     active_tab, _relayout,
                     btn_undo_done_confirm, f_time_min,
                     f_search, btn_editor_reopen_confirm,
                     original_name,
                     pristine_snapshot, pending_undo_done, canvas_stamp,
                     bridge_pending, editor_reopen_pending, community_memory, form):
        """Route one action, then render the canvas and the views around it.

        Gates come first: a tab switch or an editor open needs no render.
        Then the handler for what fired changes the graph (engine.handlers),
        the canvas renders, and its view merges with what the handler did.
        The outputs are CoreResponse's fields, by name.
        `form` is the node editor's form (editor form.EDITOR_FORM).
        """
        form = form or {}
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
            return CoreResponse()

        all_triggered_ids = get_all_triggered_ids()

        # A save that would reopen Done nodes was held for the user to
        # confirm. Their yes finishes it as the Save button they pressed.
        reopen_confirmed = False
        if trigger_id == 'btn-editor-reopen-confirm':
            via = (editor_reopen_pending or {}).get('via')
            if not btn_editor_reopen_confirm or via not in SAVE_TRIGGERS:
                return CoreResponse()
            trigger_id, all_triggered_ids, reopen_confirmed = via, {via}, True

        # Check for any delayed event nodes or scheduled events that are due
        event_manager.run_sweeps()

        filters = build_filters(f_context, f_subcontext, f_done, f_value, f_interest, f_time, f_difficulty, f_node_types, f_time_unit=f_time_unit, f_show_dormant=f_show_dormant,
                                f_time_min=f_time_min, f_search=f_search)

        # focus_goal may be a dict {"node": str, "subtree": list,
        #   "path_info": {...}} or a plain string.
        focus_subtree_override = None
        focus_path_info = None
        if isinstance(focus_goal, dict):
            focus_subtree_override = set(focus_goal.get("subtree", []))
            focus_path_info = focus_goal.get("path_info")
            focus_goal = focus_goal.get("node")
        # --- The action: a save, a delete, a Done toggle (engine.handlers) ---
        outcome = handle(Request(
            graph=manager, events=event_manager, trigger=trigger_id, form=form,
            original_name=original_name, pristine_snapshot=pristine_snapshot,
            bridge_pending=bridge_pending, reopen_confirmed=reopen_confirmed,
            now_switch='now' in (form.get('now') or []),
            tapped_node=tapped_node, toggle_done_trigger_data=toggle_done_trigger_data,
            pending_undo_done=pending_undo_done, group_delete_data=group_delete_data,
            saves=saves))
        if outcome.response is not None:
            return outcome.response

        # Every mutation above has committed, so the view is all reads. One
        # snapshot serves them: naming the community filter's options alone
        # used to open a connection per node, about 0.3 s per render.
        # The canvas keeps the nodes the user picked. A render picks for them
        # only when it was asked to show one node: a search, a save, or
        # entering focus, which clears it.
        if outcome.saved_name:
            canvas_selection = outcome.saved_name
        elif trigger_id == 'search-node':
            canvas_selection = searched_node(manager, search_val, form.get('name'))
        elif trigger_id == 'focus-goal-store' and focus_goal:
            # Only the goal's subtree is highlighted, not a tapped node.
            canvas_selection = None
        else:
            canvas_selection = KEEP_SELECTION
        with database.read_snapshot():
            view = CoreResponse(**build_canvas_view(
                manager, render_elements, trigger_id, canvas_selection, community_method, filters, f_community, focus_goal, focus_subtree_override, focus_path_info,
                community_memory=community_memory)._asdict())

        # Time-calibration: when an explicit single-node completion just
        # happened and the feature is enabled, open the modal to capture how
        # long the work actually took. Only the explicit single-node
        # completions report one (graph tap, context menu, editor save):
        # auto-cascade and bulk completion never do.
        tc_modal_open = False
        tc_reference = ""
        tc_pending = None
        tc_unit = no_update  # only set the dropdown when the modal opens
        tc_title = no_update
        tc_sections = (no_update,) * 3
        if outcome.completed and settings.TIME_CALIBRATION_ENABLED.get():
            _tc_node = manager.get_node(outcome.completed)
            if _tc_node is not None and _tc_node.status == STATUS_DONE and not _tc_node.dormant:
                tc_modal_open = True
                tc_title, tc_reference = calibration_modal_text(_tc_node)
                tc_pending = {'mode': 'single', 'node': outcome.completed}
                tc_unit = calibration_unit_for(_tc_node.time)
                tc_sections = calibration_sections(_tc_node)

        if (isinstance(view.elements, list)
                and not canvas_wanted(active_tab, canvas_stamp)):
            view = view._replace(elements=deferred_canvas())

        if not trigger_id or trigger_id == 'main-tabs':
            # Page load or a tab switch: nothing ran, so
            # there's no message and no modal to open, and the page already
            # holds every reset below. Sending them anyway woke six callbacks
            # each time that only reset again.
            return view

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

        if trigger_id not in _ACTION_TRIGGERS:
            # A render only draws. It has no message to give, and resetting the
            # modals here could close one that an action has just opened.
            return view

        # A save can commit another status than the switch said.
        editor_done = no_update
        save_result = outcome.save_result
        if (isinstance(save_result, dict)
                and save_result['status_done'] != (form.get('status_done') or [])):
            editor_done = save_result['status_done']

        # The undo-Done modal: the node menu's toggles open it earlier (an
        # early response from their handler), an editor save that un-marked
        # a node opens it here, and otherwise it stays closed with the
        # pending store cleared.
        undo_pending = outcome.undo_pending
        return view._replace(
            # A run with nothing to say leaves the line to its timer. Saving a
            # rename clears the node picker, which runs this again, and that
            # run wiped the save's confirmation at once.
            notice=outcome.notice or no_update,
            left_panel=close_editor() if trigger_id == 'btn-node-delete-confirm' else no_update,
            undo_open=bool(undo_pending),
            undo_body=(undo_done_body(undo_pending, outcome.undo_downstream)
                       if undo_pending else ''),
            undo_pending=undo_pending,
            calibration_open=tc_modal_open,
            calibration_reference=tc_reference,
            calibration_pending=tc_pending,
            calibration_unit=tc_unit,
            calibration_title=tc_title,
            calibration_ratings_style=tc_sections[0],
            calibration_time_style=tc_sections[1],
            calibration_notes_placeholder=tc_sections[2],
            save_result=save_result,
            editor_done=editor_done,
        )

    # One function with two doors (CORE_ACTIONS says why). Each door reads the
    # other's inputs as State, so the function is called the same way from both.
    # Dash merges the inputs into the state dict it is given, so each is its own.
    app.callback(output=CORE_OUTPUTS, inputs=CORE_ACTIONS,
                 state={**CORE_STATE, **_as_state(CORE_RENDERS)},
                 prevent_initial_call=True)(core_engine)
    app.callback(output={name: Output(dep.component_id, dep.component_property,
                                      allow_duplicate=True)
                         for name, dep in CORE_OUTPUTS.items()},
                 inputs=CORE_RENDERS,
                 state={**CORE_STATE, **_as_state(CORE_ACTIONS)},
                 prevent_initial_call='initial_duplicate')(core_engine)

    # The filters-sidebar toggle and editor-sidebar fast-path clientside
    # callbacks live in sidebars_callbacks.register_goals_callbacks.

    @app.callback(
        Output('modal-undo-done-confirm', 'is_open', allow_duplicate=True),
        Output('pending-undo-done-store', 'data', allow_duplicate=True),
        Output('node-status-done', 'value', allow_duplicate=True),
        Output('node-now', 'value', allow_duplicate=True),
        Input('btn-undo-done-cancel', 'n_clicks'),
        Input('btn-undo-done-confirm', 'n_clicks'),
        State('pending-undo-done-store', 'data'),
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def close_undo_done_modal(_cancel, _confirm, pending, editing):
        """Close the undo-Done modal and clear the pending store on either
        button. The actual toggle (on confirm) is performed by core_engine
        listening to btn-undo-done-confirm; this callback only manages the
        modal/store cleanup so the next toggle starts fresh.

        An editor save that un-marked a node kept it Done and asked, and the
        baseline already says so. Cancel leaves it Done, so the editor's switch
        goes back on. A Done node can't be in Now, so the Now switch that save
        held goes off.
        """
        if (get_trigger_id() == 'btn-undo-done-cancel'
                and editing and editing in (pending or [])):
            return False, None, [STATUS_DONE], []
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
        Output('notice-store', 'data', allow_duplicate=True),
        Input('graph-version-store', 'data'),
        Input('btn-auto-done-confirm', 'n_clicks'),
        Input('btn-auto-done-dismiss', 'n_clicks'),
        State('auto-done-candidates-store', 'data'),
        prevent_initial_call=True,
    )
    def manage_auto_done_modal(_version, _confirm, _dismiss, current_candidates):
        trig = get_trigger_id()
        candidates = list(current_candidates or [])
        refresh_out = no_update
        notice_out = no_update

        if trig == 'btn-auto-done-confirm' and candidates:
            target = candidates.pop(0)
            node = manager.get_node(target)
            if node is None:
                notice_out = f"'{target}' no longer exists"
            elif node.status == STATUS_DONE:
                # Already Done via another path — silently skip.
                pass
            elif not manager.is_auto_done_ready(target):
                # Prereqs no longer all Done (e.g. a sibling un-done) —
                # don't force; let the user re-decide later.
                notice_out = info(
                    f"'{target}' is no longer eligible — "
                    "its state or prerequisites changed."
                )
            else:
                try:
                    accepted = manager.complete_suggested_node(target)
                    notice_out = info(f"Marked '{target}' as Done" if accepted
                                      else f"'{target}' is no longer eligible")
                    if accepted:
                        refresh_out = f"auto-done-{time.time()}"
                except Exception as exc:
                    notice_out = (
                        error(f"Couldn't mark '{target}' Done. {exc}")
                        if isinstance(exc, ValueError)
                        else unexpected_error(f"Marking '{target}' Done"))
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
            return True, body, candidates, refresh_out, notice_out
        return False, "", [], refresh_out, notice_out


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

    register_toast_timer(app, 'save-output', TOAST_CLEAR_INTERVAL_MS)
    register_left_panel_callbacks(app)


    # The unexpected-error modal opens from app.report_callback_error, through
    # set_props, so only its Close needs a callback.
    app.clientside_callback(
        "function(n) { return false; }",
        Output("modal-app-error", "is_open", allow_duplicate=True),
        Input("btn-close-app-error", "n_clicks"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        ClientsideFunction(namespace='notices', function_name='show'),
        Output("save-output", "children"),
        Output("modal-error", "is_open"),
        Output("error-modal-body", "children"),
        Input("notice-store", "data"),
        Input("btn-close-error", "n_clicks"),
        prevent_initial_call=True,
    )


    # --- Each Nodes render: stamp it, and report it to both covers ---
    # The stamp is what server callbacks listen to instead of the elements,
    # which would send the whole canvas back to the server on every render.
    # `loaded` stays true once the canvas has had elements; until then the
    # core engine sends deferred_canvas() (see canvas_view.canvas_wanted).
    # The canvas cover waits for the main canvas's layout to settle, and a
    # graph with no nodes never runs one — no `layoutstop` is ever coming, so
    # nothing else would release it. Only the empty case matters to it; the JS
    # ignores the rest. The startup cover (assets/startup_cover.js) waits for
    # the first render of any kind: it arrives with the core engine's first
    # response, which also fills the editor's search and the other dropdowns.
    app.clientside_callback(
        ClientsideFunction(namespace='canvas_payload', function_name='stamp'),
        Output('canvas-payload-stamp', 'data'),
        Input('elements-pending-store', 'data'),
        State('canvas-payload-stamp', 'data'),
        prevent_initial_call=True,
    )



def searched_node(graph, search_val, current_name):
    """The node the node picker names, or the one the form holds once it's cleared."""
    if not search_val:
        return current_name
    if search_val.startswith('alias:'):
        # Case-insensitive resolve so 'alias:mathnotes' finds 'MathNotes'.
        resolved = graph.resolve_alias(search_val[6:])
        return resolved if resolved is not None else search_val
    return search_val
