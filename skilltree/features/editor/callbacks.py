"""The node editor's callbacks: loading a node into the form, and keeping each
field in step as the user edits.

The save itself is the core engine's (engine/callbacks.py), since a save
redraws the canvas in the same response. The Dormant section's callbacks are
in dormancy.py, the Resources section's in resources.py.
"""

import dash
from dash import ALL, ClientsideFunction, Input, Output, State, ctx, html, no_update

from skilltree.domain.contexts import sort_subcontexts
from skilltree.domain.models import STATUS_DONE, STATUS_OPEN
from skilltree.domain.names import normalize_name_for_comparison
from skilltree.domain.time import ALL_WEEKDAYS, time_estimate_problem
from skilltree.features.editor.form import (
    EDITOR_FORM,
    NEW_NODE_SNAPSHOT,
    RELATIONSHIP_FIELDS,
    build_editor_snapshot,
    editor_form_values_from,
    follow_done_status,
    follow_relationships,
    habit_editor_view,
    habit_preview_text,
    is_form_dirty_vs_snapshot,
    snapshot_from_form_state,
    stored_relationships,
)
from skilltree.features.editor.layout import (
    alias_rows_label,
    render_alias_rows,
    update_alias_rows,
)
from skilltree.features.editor.values import friendly_time_estimates
from skilltree.store import database
from skilltree.store.commands import bridge_form, plan_bridge
from skilltree.store.settings import ConfigManager
from skilltree.ui import payloads as bridge_payloads
from skilltree.ui import tokens
from skilltree.ui.canvas.view import node_options
from skilltree.ui.components.duration import work_time_tooltip
from skilltree.ui.components.ratings_table import (
    build_editor_table,
    build_popup_table_rows,
)
from skilltree.ui.dash_tools import get_trigger_id
from skilltree.ui.prerender import prerendered
from skilltree.features.editor.resources import register_resource_link_callbacks
from skilltree.features.editor.dormancy import register_dormancy_callbacks


def register_editor_callbacks(app, services):
    manager = services.graph

    # --- Editor follows status changed elsewhere ---
    # Any mutation can change the open node's Done or Now from outside the
    # editor: the "Mark Done?" suggestion, an event putting it to sleep, a
    # cascade. Its switches follow, unless the user has flipped Done and not
    # saved. Only the snapshot's status key is patched, so a newer snapshot
    # written by a save in flight is never replaced by this older copy.
    @app.callback(
        Output('node-status-done', 'value', allow_duplicate=True),
        Output('editor-pristine-snapshot', 'data', allow_duplicate=True),
        Output('node-now', 'value', allow_duplicate=True),
        Input('graph-version-store', 'data'),
        State('node-original-name', 'data'),
        State('node-status-done', 'value'),
        State('editor-pristine-snapshot', 'data'),
        State('node-now', 'value'),
        prevent_initial_call=True,
    )
    def sync_editor_status(_version, name, switch, snapshot, now_switch):
        if not name or not isinstance(snapshot, dict) or snapshot.get('name') != name:
            return (no_update,) * 3
        node = manager.get_node(name)
        if node is None:
            return (no_update,) * 3
        done, followed = follow_done_status(node, switch, snapshot)
        snapshot_out = no_update
        if followed is not no_update:
            snapshot_out = dash.Patch()
            snapshot_out['status_done'] = followed['status_done']
        now = ["now"] if node.now else []
        return done, snapshot_out, (now if now != (now_switch or []) else no_update)

    # --- Editor follows relationships changed elsewhere ---
    # The link menu, the Details tab and a bridge change the open node's links
    # without the editor, whose pickers were filled when it loaded. A picker
    # the user hasn't touched takes the stored links; an edited one keeps the
    # edits on top of them (editor form.follow_relationships). Save
    # merges the same way, so it never depends on this having run. A changed
    # snapshot also checks again: after a save that merged in an outside
    # change, the snapshot holds the form's lists rather than what was stored.
    @app.callback(
        Output('editor-relationships-follow', 'data'),
        Input('graph-version-store', 'data'),
        Input('editor-pristine-snapshot', 'data'),
        [State('node-original-name', 'data'),
         {key: EDITOR_FORM[key] for key in RELATIONSHIP_FIELDS}],
        prevent_initial_call=True,
    )
    def follow_editor_relationships(_version, snapshot, original_name, form):
        if (not original_name or not isinstance(snapshot, dict)
                or snapshot.get('name') != original_name
                or manager.get_node(original_name) is None):
            return no_update
        stored = stored_relationships(manager.get_edges(), original_name)
        values, followed = follow_relationships(stored, form, snapshot)
        if not followed:
            return no_update
        return {'name': original_name, 'values': values, 'snapshot': followed,
                'seen': {key: {'snapshot': snapshot.get(key), 'form': form.get(key)}
                         for key in followed}}

    # Applied in the browser, against the editor as it is when the answer
    # lands: if another node has loaded, or the user has changed a picker
    # since, the answer is stale and is dropped rather than written into it.
    app.clientside_callback(
        """
        function(follow, name, snapshot, needsHard, needsSoft, suppHard, suppSoft, helps) {
            var NO = window.dash_clientside.no_update;
            var keys = ['e_needs_h', 'e_needs_s', 'e_supp_h', 'e_supp_s', 'e_helps'];
            var form = {e_needs_h: needsHard, e_needs_s: needsSoft, e_supp_h: suppHard,
                        e_supp_s: suppSoft, e_helps: helps};
            var unchanged = [NO, NO, NO, NO, NO, NO];
            if (!follow || !snapshot || follow.name !== name || snapshot.name !== name) {
                return unchanged;
            }
            var same = function (a, b) {
                return JSON.stringify(a || []) === JSON.stringify(b || []);
            };
            for (var key in follow.seen) {
                if (!same(follow.seen[key].snapshot, snapshot[key])
                        || !same(follow.seen[key].form, form[key])) {
                    return unchanged;
                }
            }
            var out = keys.map(function (key) {
                return key in follow.values ? follow.values[key] : NO;
            });
            out.push(Object.assign({}, snapshot, follow.snapshot));
            return out;
        }
        """,
        Output('edge-needs-hard', 'value', allow_duplicate=True),
        Output('edge-needs-soft', 'value', allow_duplicate=True),
        Output('edge-supports-hard', 'value', allow_duplicate=True),
        Output('edge-supports-soft', 'value', allow_duplicate=True),
        Output('edge-helps', 'value', allow_duplicate=True),
        Output('editor-pristine-snapshot', 'data', allow_duplicate=True),
        Input('editor-relationships-follow', 'data'),
        State('node-original-name', 'data'),
        State('editor-pristine-snapshot', 'data'),
        State('edge-needs-hard', 'value'),
        State('edge-needs-soft', 'value'),
        State('edge-supports-hard', 'value'),
        State('edge-supports-soft', 'value'),
        State('edge-helps', 'value'),
        prevent_initial_call=True,
    )

    # --- Scroll editor to top on New Node / Add ---
    app.clientside_callback(
        """function(n1, n2) {
            var el = document.getElementById('sidebar-editor-container');
            if (el) el.scrollTop = 0;
            return window.dash_clientside.no_update;
        }""",
        Output('btn-editor-new', 'title'),
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
         Output('node-habit-days', 'value'),
         # The bridge this editor was opened for, if any. Every load of the
         # editor replaces it, so a bridge never outlives its form.
         Output('bridge-pending-store', 'data')],
        [Input('cytoscape-graph', 'tapNodeData'),
         Input('btn-add', 'n_clicks'),
         Input('btn-unsaved-discard', 'n_clicks'),
         Input('editor-save-result-store', 'data'),
         Input('search-node', 'value'),
         Input('background-click-input', 'value'),
         Input('btn-editor-new', 'n_clicks'),
         Input('edit-trigger-input', 'value'),
         Input('details-edit-trigger-input', 'value'),
         Input('details-add-choice-input', 'value'),
         Input('btn-bridge-create', 'n_clicks'),
         Input('btn-revert', 'n_clicks')],
        [State('sidebar-editor-container', 'style'),
         State('node-original-name', 'data'),
         State('pending-navigation-store', 'data'),
         State('editor-pristine-snapshot', 'data'),
         State('details-selected-node-store', 'data'),
         State('bridge-modal-store', 'data'),
         State('bridge-type', 'value'),
         EDITOR_FORM],
        # Nothing to populate on page load. The form's defaults and its empty
        # alias and link rows are in the layout, and every path that opens
        # the editor runs this callback, which sends the relationship options.
        # The load-time run used to send ~230 KB of those options and set off
        # a dozen follow-on callbacks, all before the editor could be seen.
        prevent_initial_call=True,
    )
    def populate_editor(data, add_clicks, discard_clicks, save_result, search_val, _bg_click, editor_new_clicks, edit_trigger_val,
                        details_edit_trigger_val, details_add_choice, bridge_clicks,
                        revert_clicks,
                        ed_style, original_name, pending_nav, pristine_snapshot,
                        details_selected_node, bridge_ends, bridge_kind, form):
        """Populate the editor sidebar form fields when a node is selected, searched, or cleared.

        `form` is what the editor holds now (editor form.EDITOR_FORM),
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
            "", "", "", "", "", 5, 5, 5, None, None, None, STATUS_OPEN, [],
            [], [], [], [], [],
            options, options, options, options, options,
            {},  # resource-links-store
            # Type-specific defaults
            NEW_NODE_SNAPSHOT['time_unit'], NEW_NODE_SNAPSHOT['time_unit'],
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
            None,  # bridge-pending-store
        ]

        def _untouched():
            """Every output left as it is, but for the relationship options,
            which are always refreshed. The one place the output count is
            written for early returns."""
            return [dash.no_update] * 18 + [options]*5 + [dash.no_update]*21

        def _has_unsaved_changes():
            return is_form_dirty_vs_snapshot(pristine_snapshot, editor_form_values_from(form))

        def _ask_before_leaving(target, picker=dash.no_update):
            """The unsaved-changes dialog in place of loading `target`, or
            None when the open form has nothing to lose. `target` is a node
            name or a pending-navigation sentinel. Loading the node the form
            already holds keeps its edits and asks nothing. `picker` is what
            the node picker goes back to while the dialog asks."""
            editor_open = ed_style and ed_style.get('transform', '') == 'translateX(0px)'
            if not (editor_open and _has_unsaved_changes()):
                return None
            no_change = _untouched()
            no_change[27] = picker  # search-node
            if target != original_name:
                no_change[31] = target  # pending-navigation-store
                no_change[32] = True    # modal-unsaved-changes
            return no_change

        def _bridge_form_out():
            """def_out for a new node between the bridge dialog's two nodes,
            with the relationships filled in. None when the bridge no longer
            holds, such as a node deleted since the dialog opened."""
            ends = bridge_ends or {}
            start, end = ends.get('start'), ends.get('end')
            plan = plan_bridge(manager, start, end, bridge_kind)
            if plan['problem']:
                return None
            fields = bridge_form(start, end, bridge_kind)
            out = list(def_out)
            for key, slot in (('e_needs_h', 13), ('e_needs_s', 14), ('e_supp_h', 15),
                              ('e_supp_s', 16), ('e_helps', 17)):
                out[slot] = fields[key]
            out[27] = None  # clear the search bar
            out[33] = {**NEW_NODE_SNAPSHOT, **fields}  # editor-pristine-snapshot
            out[43] = {'start': start, 'end': end, 'kind': bridge_kind,
                       'replaces': plan['replaces']}
            return out

        if trigger_id == 'btn-add':
            # Toolbar toggle: open/close is handled by core_engine + the
            # clientside fast-path. Leave the form untouched so reopening shows
            # the last-loaded node (matches the Goals/Events toggles).
            return _untouched()

        if trigger_id in ('btn-editor-new', 'details-add-choice-input'):
            if trigger_id == 'details-add-choice-input':
                if not (details_add_choice or '').startswith('new|') or not details_selected_node:
                    return _untouched()
                if manager.get_node(details_selected_node) is None:
                    return _untouched()
            editor_open = ed_style and ed_style.get('transform', '') == 'translateX(0px)'
            if editor_open and _has_unsaved_changes():
                # Show unsaved modal; store 'new-node' as pending action
                no_change = _untouched()
                no_change[31] = (f'__new_subtask__|{details_selected_node}'
                                 if trigger_id == 'details-add-choice-input'
                                 else '__new_node__')
                no_change[32] = True            # modal-unsaved-changes
                return no_change
            # No unsaved changes — clear and reset, including the search bar so it
            # doesn't keep showing the previously-loaded node. Clearing search-node
            # re-fires core_engine with an empty value, but the editor is already
            # open here and compute_sidebar_styles guards that case (search-node +
            # no value → leave the editor untouched), so it stays open.
            def_out[27] = None  # search-node value position
            if trigger_id == 'details-add-choice-input':
                def_out[15] = [details_selected_node]  # Supports > Hard
                def_out[33] = {**NEW_NODE_SNAPSHOT,
                               'e_supp_h': [details_selected_node]}
            return def_out

        if trigger_id == 'btn-bridge-create':
            if not bridge_clicks:
                return _untouched()
            editor_open = ed_style and ed_style.get('transform', '') == 'translateX(0px)'
            if editor_open and _has_unsaved_changes():
                no_change = _untouched()
                no_change[31] = '__bridge__'  # pending-navigation-store
                no_change[32] = True          # modal-unsaved-changes
                return no_change
            return _bridge_form_out() or _untouched()

        if trigger_id == 'background-click-input':
            # Intercept background click when the editor is open with unsaved
            # changes — show the save/discard modal instead of silently clobbering.
            editor_open = ed_style and ed_style.get('transform', '') == 'translateX(0px)'
            if editor_open and _has_unsaved_changes():
                no_change = _untouched()
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
                if pending_nav == '__bridge__':
                    return _bridge_form_out() or def_out
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

        # A tap, an Edit (the node menu, the Events table, Details) and the
        # node picker all ask before they replace unsaved edits.
        if trigger_id == 'cytoscape-graph' and data and data.get('id'):
            asked = _ask_before_leaving(data.get('id'))
            if asked is not None:
                return asked

        name = None
        if trigger_id == 'btn-revert':
            # Reload the node the editor holds, dropping what wasn't saved.
            node = manager.get_node(original_name) if revert_clicks and original_name else None
            if node is None:
                return _untouched()
            name = node.name
            data = node.to_dict()
            data['id'] = name
        elif trigger_id in ('edit-trigger-input', 'details-edit-trigger-input'):
            # Context menu / Events-table Edit: node ID carried in the trigger value
            edit_val = edit_trigger_val if trigger_id == 'edit-trigger-input' else details_edit_trigger_val
            if edit_val:
                edit_node_name = bridge_payloads.strip_stamp(edit_val)
                node = manager.get_node(edit_node_name)
                if node:
                    asked = _ask_before_leaving(node.name)
                    if asked is not None:
                        return asked
                    name = node.name
                    data = node.to_dict()
                    data['id'] = name
                else:
                    return _untouched()
        elif trigger_id == 'search-node':
            # While the dialog asks, the picker goes back to the node the
            # form holds, so it never names a node the form isn't showing.
            if not search_val:
                # Clearing the picker starts a blank form, as New Node does.
                return _ask_before_leaving('__new_node__', picker=original_name) or def_out
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
                asked = _ask_before_leaving(node.name, picker=original_name)
                if asked is not None:
                    return asked
                name = node.name
                data = node.to_dict()
                data['id'] = name
            else:
                return _untouched()
        elif data:
            name = data.get('id')
            # Always read fresh data from DB on tap (Cytoscape data may be stale)
            if name:
                db_node = manager.get_node(name)
                if db_node:
                    data = db_node.to_dict()
                    data['id'] = name

        if not name or not data:
            return _untouched()

        # In/Out Edges mapping
        relationships = stored_relationships(manager.get_edges(), name)
        needs_hard_vals, needs_soft_vals, supp_hard_vals, supp_soft_vals, helps_vals = (
            relationships[key] for key in RELATIONSHIP_FIELDS)
        filtered_options = node_options(all_nodes, exclude=name)

        actual_status = data.get('status', STATUS_OPEN)
        done_val = [STATUS_DONE] if actual_status == STATUS_DONE else []

        friendly_o, friendly_m, friendly_p, friendly_unit = friendly_time_estimates(
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
            build_editor_snapshot(manager, services.events, name),  # editor-pristine-snapshot
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
            None,  # bridge-pending-store
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
                or save_result.get('via') != 'btn-save'):
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        linted = save_result.get('name')
        if not linted or manager.get_node(linted) is None:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        # Build the post-save snapshot from the form as it was saved, which
        # core_engine hands over, not from a DB round-trip. Not from the form
        # as it is now either: this runs after the save's whole response, and
        # anything typed meanwhile would join the baseline and never count as
        # unsaved. A DB-derived snapshot (via build_editor_snapshot)
        # re-applies display transforms — most notably friendly_time_estimates,
        # which picks its unit from max DB-hours and can diverge from the unit
        # the user had selected. Snapshotting the form State guarantees the
        # immediate post-save dirty check sees the form as clean, since the
        # snapshot mirrors the form byte-for-byte (with only name and aliases
        # overridden by their linted versions — the two values the save
        # pipeline legitimately rewrites in the form).
        linted_aliases = manager.get_aliases(linted) or ['']
        snapshot = snapshot_from_form_state(
            editor_form_values_from(save_result.get('form', form)), linted, linted_aliases)
        if 'status_done' in save_result:
            snapshot['status_done'] = save_result['status_done']
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
    #
    # Changing the type away from Goal or Milestone used to leave the forced
    # Inherit on: an Action or Resource then had no time of its own and scored
    # at no cost. They get their own estimate back. A Learn may be a header
    # over its children, so it keeps Inherit, with a note saying so.
    app.clientside_callback(
        """
        function(time_mode_val, node_type) {
            var no_update = window.dash_clientside.no_update;
            var hidden = {display: "none"};
            var visible = {display: "block", color: "var(--st-danger-text)", fontSize: "var(--st-fs-base)"};
            var note = {display: "block", color: "var(--st-text-dim)", fontSize: "var(--st-fs-base)"};
            var ctx = window.dash_clientside.callback_context;
            var triggered = (ctx && ctx.triggered) || [];
            var ids = triggered.map(function(t) { return t.prop_id.split('.')[0]; });
            var only_time_mode = ids.length === 1 && ids[0] === 'node-time-mode';
            var only_type = ids.length === 1 && ids[0] === 'node-type';
            var store = window.SkillTree = window.SkillTree || {};
            var prev = store.editorTypeForTime;
            store.editorTypeForTime = node_type;
            var inherited_on = !!(time_mode_val && time_mode_val.indexOf('inherited') >= 0);

            if (node_type !== 'Goal' && node_type !== 'Milestone') {
                if (only_type && inherited_on && (prev === 'Goal' || prev === 'Milestone')) {
                    if (node_type === 'Learn') {
                        return [no_update, note, "Inherit came with the " + prev +
                                ". Keep it if this Learn is a header over its children; " +
                                "turn it off to give it its own estimate."];
                    }
                    return [[], hidden, ""];
                }
                return [time_mode_val, hidden, ""];
            }
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
        Output('editor-time-settings', 'data'),
        Input('node-time-habit-mode', 'value'),
        Input('settings-modal', 'is_open'),
        prevent_initial_call=True,
    )
    def refresh_work_time_tooltips(habit_mode_val, _settings_open):
        habit = bool(habit_mode_val and 'habit' in habit_mode_val)
        return (work_time_tooltip("habit" if habit else "estimate"),
                work_time_tooltip("actual"), ConfigManager.get_time_settings())

    # Display conversions locally while typing; the store uses saved Settings.
    app.clientside_callback(
        ClientsideFunction(namespace='time_hour_hints', function_name='render'),
        [Output(f'node-time-{field}-hours', 'children') for field in ('o', 'm', 'p')],
        [Output(f'node-time-{field}-hours', 'style') for field in ('o', 'm', 'p')],
        Output('node-time-bracket-row', 'className'),
        Input('node-time-o', 'value'),
        Input('node-time-m', 'value'),
        Input('node-time-p', 'value'),
        Input('node-time-unit', 'value'),
        Input('editor-time-settings', 'data'),
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

    # --- Toggle Value/Interest sliders based on value_mode ---
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
            var note = {display: "block", color: "var(--st-text-dim)", fontSize: "var(--st-fs-base)"};
            var ctx = window.dash_clientside.callback_context;
            var triggered = (ctx && ctx.triggered) || [];
            var ids = triggered.map(function(t) { return t.prop_id.split('.')[0]; });
            var only_value_mode = ids.length === 1 && ids[0] === 'node-value-mode';
            var only_type = ids.length === 1 && ids[0] === 'node-type';
            var store = window.SkillTree = window.SkillTree || {};
            var prev = store.editorTypeForValue;
            store.editorTypeForValue = node_type;
            var inherited_on = !!(value_mode_val && value_mode_val.indexOf('inherited') >= 0);

            if (node_type !== 'Milestone') {
                // A former Milestone gets its own ratings back, as the time
                // lock above gives back an estimate. A Learn may stay a
                // header that passes value through.
                if (only_type && inherited_on && prev === 'Milestone') {
                    if (node_type === 'Learn') {
                        return [no_update, note, "Inherit came with the Milestone. " +
                                "Keep it if this Learn only passes value through; " +
                                "turn it off to rate it."];
                    }
                    return [[], hidden, ""];
                }
                return [no_update, hidden, ""];
            }
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

    # --- Hide Effort slider when the node has no work of its own ---
    # Effort describes a node's own hours, so scoring ignores it when time is
    # inherited (Node.has_no_own_work). A Goal's Effort is decorative too:
    # rank_goals counts only the effort of the tasks beneath it. The caption
    # tells the user why the input is absent so the UI stops asking for a
    # value the system ignores. Inheriting ratings alone keeps the slider.
    app.clientside_callback(
        """
        function(node_type, time_mode_val) {
            var no_own_work = !!(time_mode_val && time_mode_val.indexOf('inherited') >= 0);
            if (node_type === 'Goal' || no_own_work) return [{display: 'none'}, {}];
            return [{}, {display: 'none'}];
        }
        """,
        Output('node-effort-row', 'style'),
        Output('node-effort-caption', 'style'),
        Input('node-type', 'value'),
        Input('node-time-mode', 'value'),
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
    # A newly loaded/reverted form starts quiet. Leaving the section reveals
    # the latest validation result (assets/time_validation.js); validity and
    # the save guards below remain independent of the warning's visibility.
    app.clientside_callback(
        "function(_snapshot) { return 'false'; }",
        Output('section-time-estimates', 'data-validation-ready'),
        Input('editor-pristine-snapshot', 'data'),
    )

    @app.callback(
        Output('time-validation-error', 'children'),
        Output('time-validation-error', 'style'),
        Output('btn-save', 'disabled'),
        # The time fields sit below the fold; hovering Save says why it's off.
        Output('btn-save', 'title'),
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
            return "", hidden, False, ""

        msg = time_estimate_problem(time_o, time_m, time_p)
        if msg:
            return msg, visible, True, msg
        return "", hidden, False, ""

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

    # --- Revert: populate_editor reloads the loaded node from the database,
    # discarding any unsaved edits. Disabled when no node is loaded. It used
    # to go through the context menu's Edit trigger, whose payload it got
    # wrong, so it reloaded nothing while saying it had, and from Details or
    # Events it also switched to the Nodes tab.
    app.clientside_callback(
        "function(name) { return !name; }",
        Output('btn-revert', 'disabled'),
        Input('node-original-name', 'data'),
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
        if manager.get_node(name) is None:
            return (f"Couldn't revert: '{name}' no longer exists.", False, 0)
        return "Changes reverted.", False, 0

    # Either answer closes the reopen confirmation. The core engine reads the
    # held Save from the store on a yes, so only a no clears it.
    app.clientside_callback(
        """
        function(confirm, cancel) {
            var NO = window.dash_clientside.no_update;
            var ctx = window.dash_clientside.callback_context;
            var cancelled = (ctx.triggered || []).some(function (t) {
                return t.prop_id.indexOf('btn-editor-reopen-cancel') === 0;
            });
            if (!confirm && !cancel) return [NO, NO];
            return [false, cancelled ? null : NO];
        }
        """,
        Output('modal-editor-reopen-confirm', 'is_open', allow_duplicate=True),
        Output('editor-reopen-pending-store', 'data', allow_duplicate=True),
        Input('btn-editor-reopen-confirm', 'n_clicks'),
        Input('btn-editor-reopen-cancel', 'n_clicks'),
        prevent_initial_call=True,
    )

    # The dialog's pending navigation is where Discard and Save go next.
    # "Edit" (keep editing) and a close request both forget it, or a later
    # Discard would load the node a cancelled tap was heading for.
    @app.callback(
        Output('modal-unsaved-changes', 'is_open'),
        Output('pending-navigation-store', 'data', allow_duplicate=True),
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
        if trig == 'btn-unsaved-cancel':
            return False, None
        if trig == 'btn-add':
            # btn-add is the toolbar toggle: only its close half (editor already
            # open) should guard against unsaved changes. Opening never does.
            editor_open = bool(ed_style) and ed_style.get('transform', '') == 'translateX(0px)'
            if not editor_open:
                return False, dash.no_update
        elif trig != 'btn-close-editor':
            return False, dash.no_update
        if not is_form_dirty_vs_snapshot(pristine_snapshot, editor_form_values_from(form)):
            return False, dash.no_update
        return True, None

    # --- Delete Confirmation Modal ---
    @app.callback(
        Output('modal-node-delete-confirm', 'is_open'),
        Output('node-delete-confirm-body', 'children'),
        [Input('btn-delete', 'n_clicks'),
         Input('btn-node-delete-cancel', 'n_clicks'),
         Input('btn-node-delete-confirm', 'n_clicks')],
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def toggle_delete_modal(_delete, _cancel, _confirm, original_name):
        if get_trigger_id() != 'btn-delete':
            return False, dash.no_update
        # Name the node the confirm will delete: the one the editor loaded,
        # which is not always what the Name field says by now.
        loaded = (original_name or '').strip()
        if not loaded:
            return True, "This node hasn't been saved yet. Deleting it just closes the editor."
        return True, f'Are you sure you want to delete "{loaded}"? This action cannot be undone.'

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
        subs = sort_subcontexts(ConfigManager.get_subcontexts().get(ctx, []),
                                ConfigManager.get_subcontext_sort_mode())
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

    # --- Ratings Editor ---

    @app.callback(
        Output("modal-ratings-editor", "is_open"),
        Output("ratings-editor-body", "children"),
        Input("btn-ratings-edit", "n_clicks"),
        Input("btn-ratings-editor-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_ratings_editor(edit_clicks, cancel_clicks):
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
    @database.serialized  # the cap check and the write, as one step
    def dispatch_now_toggle(toggle_val, node_name):
        import time
        if not node_name:
            return no_update, no_update
        node = manager.get_node(node_name)
        if not node:
            return no_update, no_update
        if toggle_val and (node.dormant or node.status == STATUS_DONE):
            return f"ineligible|{int(time.time() * 1000)}", no_update
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
                ts = int(time.time() * 1000)
                return f"refused|{ts}", f"refused|{ts}"
            max_now = max([n.now for n in now_nodes]) if now_nodes else 0
            node.now = max_now + 1
        elif not wants_now and is_now:
            node.now = 0
        try:
            manager.update_node(node)
        except ValueError as e:
            # A refusal (a node with no context, say) bounces the switch back
            # and says why, instead of failing in silence.
            ts = int(time.time() * 1000)
            return f"refused|{ts}", f"error|{ts}|{e}"
        return f"{node_name}|{int(time.time() * 1000)}", no_update
    register_resource_link_callbacks(app, services)
    register_dormancy_callbacks(app, services)
