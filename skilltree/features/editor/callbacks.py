"""The node editor's callbacks: loading a node into the form, and taking in a
save's result. The rest of the editor's callbacks are in the modules beside this
one, and this registers them.

The save itself is the core engine's (engine/callbacks.py), since a save
redraws the canvas in the same response.
"""

import time

import dash
from dash import Input, Output, State, no_update

from skilltree.domain.models import STATUS_OPEN
from skilltree.features.editor.aliases import register_alias_callbacks
from skilltree.features.editor.checks import register_check_callbacks
from skilltree.features.editor.dialogs import register_dialog_callbacks
from skilltree.features.editor.dormancy import register_dormancy_callbacks
from skilltree.features.editor.fields import register_field_callbacks
from skilltree.features.editor.form import (
    DORMANT_WIDGETS,
    EDITOR_FORM,
    NEW_NODE_DORMANCY,
    NEW_NODE_SNAPSHOT,
    RELATIONSHIP_FIELDS,
    build_editor_snapshot,
    dormancy_fill,
    dormant_event_options,
    editor_form_values_from,
    is_form_dirty_vs_snapshot,
    snapshot_from_form_state,
)
from skilltree.features.editor.layout import alias_rows_label, render_alias_rows
from skilltree.features.editor.merge import register_merge_callbacks
from skilltree.features.editor.navigation import ASK, CLOSE, KEEP, next_step
from skilltree.features.editor.ratings import register_ratings_callbacks
from skilltree.features.editor.resources import register_resource_link_callbacks
from skilltree.features.editor.view import VIEW_FILL, editor_view
from skilltree.store.commands import bridge_form, plan_bridge
from skilltree.ui import payloads as bridge_payloads
from skilltree.ui.canvas.view import node_options
from skilltree.ui.dash_tools import get_all_triggered_ids, get_trigger_id
from skilltree.ui.left_panel import close_editor


# populate_editor's outputs. An output that shows a form field takes the key of
# the snapshot value it shows (form.build_editor_snapshot, NEW_NODE_SNAPSHOT):
# the form is filled from the snapshot that becomes its pristine copy, so the
# two always agree. The view keys are everything the form shows around those
# values (view.py), sent with them so a load draws at once.
EDITOR_FILL = dict(
    name=Output('node-name', 'value', allow_duplicate=True),
    n_type=Output('node-type', 'value'),
    desc=Output('node-desc', 'value'),
    context=Output('node-context', 'value'),
    subctx=Output('node-subcontext', 'value'),
    val=Output('node-value', 'value'),
    interest=Output('node-interest', 'value'),
    diff=Output('node-difficulty', 'value'),
    time_o=Output('node-time-o', 'value'),
    time_m=Output('node-time-m', 'value'),
    time_p=Output('node-time-p', 'value'),
    status_text=Output('auto-status-display', 'children'),
    status_done=Output('node-status-done', 'value'),
    now=Output('node-now', 'value'),
    e_needs_h=Output('edge-needs-hard', 'value'),
    e_needs_s=Output('edge-needs-soft', 'value'),
    e_supp_h=Output('edge-supports-hard', 'value'),
    e_supp_s=Output('edge-supports-soft', 'value'),
    e_helps=Output('edge-helps', 'value'),
    e_needs_h_options=Output('edge-needs-hard', 'options'),
    e_needs_s_options=Output('edge-needs-soft', 'options'),
    e_supp_h_options=Output('edge-supports-hard', 'options'),
    e_supp_s_options=Output('edge-supports-soft', 'options'),
    e_helps_options=Output('edge-helps', 'options'),
    # The links show as rows (view.editor_view draws them).
    resource_links=Output('editor-resources', 'children', allow_duplicate=True),
    time_unit=Output('node-time-unit', 'value'),
    time_unit_prev=Output('node-time-unit-prev', 'data', allow_duplicate=True),
    original_name=Output('node-original-name', 'data', allow_duplicate=True),
    search=Output('search-node', 'value', allow_duplicate=True),
    priority_rank=Output('node-priority-rank', 'value'),
    time_mode=Output('node-time-mode', 'value'),
    aliases=Output('aliases-store', 'data'),
    aliases_open=Output('collapse-aliases', 'is_open'),
    pending_nav=Output('pending-navigation-store', 'data'),
    unsaved_open=Output('modal-unsaved-changes', 'is_open'),
    close_request=Output('left-panel-request', 'data', allow_duplicate=True),
    snapshot=Output('editor-pristine-snapshot', 'data', allow_duplicate=True),
    value_mode=Output('node-value-mode', 'value'),
    time_habit_mode=Output('node-time-habit-mode', 'value'),
    habit_duration=Output('node-habit-duration', 'value'),
    habit_duration_unit=Output('node-habit-duration-unit', 'value'),
    habit_intensity_o=Output('node-habit-intensity-o', 'value'),
    habit_intensity_m=Output('node-habit-intensity-m', 'value'),
    habit_intensity_p=Output('node-habit-intensity-p', 'value'),
    habit_intensity_unit=Output('node-habit-intensity-unit', 'value'),
    habit_days=Output('node-habit-days', 'value'),
    # The bridge this editor was opened for, if any. Every load of the
    # editor replaces it, so a bridge never outlives its form.
    bridge=Output('bridge-pending-store', 'data'),
    # The Dormant section, filled from the snapshot's one dict.
    **{key: Output(component, 'value') for key, component in DORMANT_WIDGETS.items()},
    dormant_event_options=Output('node-dormant-event', 'options'),
    dormant_preset=Output('editor-dormant-preset', 'data', allow_duplicate=True),
    **VIEW_FILL,
)


def _relationship_options(options):
    return {f'{key}_options': options for key in RELATIONSHIP_FIELDS}


def _untouched(**changes):
    """populate_editor's outputs left as they are, except ``changes``."""
    return {**dict.fromkeys(EDITOR_FILL, no_update), **changes}


def _filled(snapshot, options, *, status, original_name, node=None, search=no_update,
            bridge=None, event_options=no_update, preset=no_update):
    """populate_editor's outputs for a form that shows ``snapshot``.

    A load closes the unsaved-changes dialog and forgets where it was going.
    ``search`` is what the node picker shows. Leaving it alone avoids
    triggering core_engine again. The relationship options only go out with a
    form: at about 230 KB, nothing else that happens here should pay for them.
    ``preset`` is what the Events tab's "+" left waiting, once a form has used it.
    ``node`` is the stored node the form shows, or None for a new one.
    """
    out = {key: snapshot[key] for key in EDITOR_FILL if key in snapshot}
    out.update(_relationship_options(options))
    out.update(dormancy_fill(snapshot.get('dormancy') or NEW_NODE_DORMANCY))
    out.update(dormant_event_options=event_options, dormant_preset=preset)
    out.update(status_text=status, time_unit_prev=snapshot['time_unit'],
               original_name=original_name, search=search, pending_nav=None,
               unsaved_open=False, close_request=no_update, snapshot=snapshot, bridge=bridge,
               aliases_open=any((a or '').strip() for a in snapshot.get('aliases') or []))
    out.update(editor_view(snapshot, node))
    return out


def register_editor_callbacks(app, services):
    manager = services.graph

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
        Input('btn-goals-sidebar-new', 'n_clicks'),
        prevent_initial_call=True,
    )

    # --- A Nodes canvas tap, for the editor ---
    # A click with Ctrl, Cmd or Shift held picks nodes (context_menu.js).
    # Loading the node named it in the node picker, and the core engine
    # took that as a search and selected it alone, dropping the others.
    # The stamp makes a second tap on the same node a fresh value.
    app.clientside_callback(
        """function(tapData) {
            if (!tapData || tapData.id == null
                    || (window.SkillTree && window.SkillTree.additiveTap)) {
                return window.dash_clientside.no_update;
            }
            return Object.assign({}, tapData, {stamp: Date.now()});
        }""",
        Output('editor-tap-store', 'data'),
        Input('cytoscape-graph', 'tapNodeData'),
        prevent_initial_call=True,
    )

    # --- Editor Form Population ---
    @app.callback(
        output=EDITOR_FILL,
        inputs=dict(
            tapped_node=Input('editor-tap-store', 'data'),
            add_clicks=Input('btn-add', 'n_clicks'),
            close_clicks=Input('btn-close-editor', 'n_clicks'),
            close_asked=Input('editor-close-ask', 'data'),
            cancel_clicks=Input('btn-unsaved-cancel', 'n_clicks'),
            answer_save_clicks=Input('btn-unsaved-save', 'n_clicks'),
            discard_clicks=Input('btn-unsaved-discard', 'n_clicks'),
            save_result=Input('editor-save-result-store', 'data'),
            search_val=Input('search-node', 'value'),
            _bg_click=Input('background-click-input', 'value'),
            editor_new_clicks=Input('btn-editor-new', 'n_clicks'),
            goal_new_clicks=Input('btn-goals-sidebar-new', 'n_clicks'),
            edit_trigger_val=Input('edit-trigger-input', 'value'),
            details_edit_trigger_val=Input('details-edit-trigger-input', 'value'),
            details_add_choice=Input('details-add-choice-input', 'value'),
            bridge_clicks=Input('btn-bridge-create', 'n_clicks'),
            revert_clicks=Input('btn-revert', 'n_clicks'),
        ),
        state=dict(
            left_panel=State('left-panel-store', 'data'),
            original_name=State('node-original-name', 'data'),
            pending_nav=State('pending-navigation-store', 'data'),
            pristine_snapshot=State('editor-pristine-snapshot', 'data'),
            dormant_preset=State('editor-dormant-preset', 'data'),
            details_selected_node=State('details-selected-node-store', 'data'),
            bridge_ends=State('bridge-modal-store', 'data'),
            bridge_kind=State('bridge-type', 'value'),
            form=EDITOR_FORM,
        ),
        # Nothing to populate on page load. The form's defaults and its empty
        # alias and link rows are in the layout, and every path that opens
        # the editor runs this callback, which sends the relationship options.
        # The load-time run used to send ~230 KB of those options and set off
        # a dozen follow-on callbacks, all before the editor could be seen.
        prevent_initial_call=True,
    )
    def populate_editor(tapped_node, add_clicks, close_clicks, close_asked, cancel_clicks,
                        answer_save_clicks, discard_clicks, save_result, search_val,
                        _bg_click, editor_new_clicks, goal_new_clicks, edit_trigger_val,
                        details_edit_trigger_val, details_add_choice, bridge_clicks,
                        revert_clicks, left_panel, original_name, pending_nav,
                        pristine_snapshot, dormant_preset, details_selected_node,
                        bridge_ends, bridge_kind, form):
        """What the editor shows and does next, whatever asked (editor navigation).

        `form` is what the editor holds now (editor form.EDITOR_FORM),
        checked against `pristine_snapshot` before a switch discards it.
        Returns EDITOR_FILL's outputs by name.
        """
        trigger_id = get_trigger_id()
        editor_open = left_panel == 'editor'

        def _options(exclude=None):
            # Relationship pickers must include dormant nodes so active nodes
            # can be wired to work that has not triggered yet.
            return node_options(manager.get_all_nodes(include_dormant=True),
                                exclude=exclude, aliases=manager.get_all_aliases())

        def _load(node, search):
            snapshot = build_editor_snapshot(manager, services.events, node.name)
            return _filled(snapshot, _options(exclude=node.name), status=node.status,
                           original_name=node.name, node=node, search=search,
                           event_options=dormant_event_options(
                               services.events, snapshot['dormancy']['event']))

        def _new_node(search=None, bridge=None, **fields):
            """A blank form, with `fields` filled in. Clearing the search bar
            stops it showing the node loaded before.

            node-type starts empty, so the "Choose node type..." placeholder
            survives until the user picks one. Defaulting it to Learn meant a
            new node silently claimed a type nobody chose; saving without one
            is refused ("Node type is required").

            The Events tab's "+" opens one with Dormant already on and the event
            chosen. Its preset is used once, by the next blank form, and only
            while it is fresh."""
            dormancy, preset = NEW_NODE_DORMANCY, no_update
            if dormant_preset and dormant_preset.get('event'):
                preset = None
                if time.time() * 1000 - (dormant_preset.get('ts') or 0) < 30_000:
                    dormancy = {**dormancy, 'dormant': True, 'event': dormant_preset['event']}
            return _filled({**NEW_NODE_SNAPSHOT, 'dormancy': dormancy, **fields}, _options(),
                           status=STATUS_OPEN, original_name=None, search=search, bridge=bridge,
                           event_options=dormant_event_options(services.events, dormancy['event']),
                           preset=preset)

        def _bridge_form():
            """A new node between the bridge dialog's two nodes, with the
            relationships filled in. None when the bridge no longer holds,
            such as a node deleted since the dialog opened."""
            ends = bridge_ends or {}
            start, end = ends.get('start'), ends.get('end')
            plan = plan_bridge(manager, start, end, bridge_kind)
            if plan['problem']:
                return None
            return _new_node(bridge={'start': start, 'end': end, 'kind': bridge_kind,
                                     'replaces': plan['replaces']},
                             **bridge_form(start, end, bridge_kind))

        def _go_to(intent, blank_search=None, gone=None):
            """Show what ``intent`` asked for. ``gone`` is the answer when what it
            named no longer exists, which can happen while a dialog waits."""
            kind = intent['kind']
            if kind == 'bridge':
                return _bridge_form() or gone
            if kind == 'background':
                return _new_node()
            if kind == 'new':
                parent = intent.get('parent')
                if parent:
                    # A subtask starts with its parent under Supports > Hard.
                    return (_new_node(e_supp_h=[parent]) if manager.get_node(parent)
                            else _new_node())
                if intent.get('goal'):
                    # The Goals sidebar's "+": a blank form that is already a
                    # Goal, whose time is always inherited.
                    return _new_node(n_type='Goal', time_mode=['inherited'])
                return _new_node(search=blank_search)
            # The picker names the loaded node while the editor is open, and
            # when an Edit opens it.
            node = manager.get_node(intent['name'])
            if node is None:
                return gone
            return _load(node, node.name if editor_open or kind == 'edit' else no_update)

        def _decide(intent, picker=no_update, blank_search=None):
            """Go to ``intent``, ask first, or leave the form alone (next_step).
            `picker` is what the node picker goes back to meanwhile, so it never
            names a node the form isn't showing."""
            dirty = is_form_dirty_vs_snapshot(pristine_snapshot, editor_form_values_from(form))
            holds = 'name' in intent and intent['name'] == original_name
            step = next_step(intent, editor_open, dirty, holds)
            if step == ASK:
                return _untouched(search=picker, pending_nav=intent, unsaved_open=True)
            if step == KEEP:
                return _untouched(search=picker)
            if step == CLOSE:
                return _untouched(close_request=close_editor())
            return _go_to(intent, blank_search, gone=_untouched())

        def _answered():
            """The dialog was answered and nothing stands in the way. A close
            or an empty canvas click leaves a blank form behind."""
            intent = pending_nav or {'kind': 'close'}
            if intent['kind'] in ('close', 'background'):
                return {**_new_node(), 'close_request': close_editor()}
            return _go_to(intent, gone=_new_node(search=no_update))

        # Dash holds this callback back while a save runs, since that writes one
        # of its Inputs, and whatever fired meanwhile arrives as one run. So what
        # must not be missed is looked for among everything fired, not only
        # what's named first.
        fired = get_all_triggered_ids()

        # --- The dialog's answers ---
        if 'editor-save-result-store' in fired:
            if (save_result or {}).get('via') == 'btn-unsaved-save':
                return _answered()
            # A rename takes the old name out of the picker, which empties it.
            # That isn't a request for a blank form.
            if trigger_id in ('editor-save-result-store', 'search-node'):
                return _untouched()
        if trigger_id == 'btn-unsaved-cancel':
            # Keep editing forgets where it was going, or a later Discard would
            # load the node a cancelled tap was heading for. A "+" that never got
            # its blank form doesn't leave its preset waiting for the next one.
            return _untouched(pending_nav=None, unsaved_open=False, dormant_preset=None)
        if trigger_id == 'btn-unsaved-save':
            # Its save may be refused, which keeps the form and the edits. It
            # moves on once core_engine reports the commit, above.
            return _untouched(unsaved_open=False)
        if trigger_id == 'btn-unsaved-discard':
            return _answered()

        # --- Closing ---
        # Only left_panel.js knows whether the toolbar icon's click found the
        # editor open: by the time this runs, left-panel-store can already say
        # what the click did. So the script asks.
        if close_asked and 'editor-close-ask' in fired:
            return _decide({'kind': 'close'})
        if trigger_id == 'btn-add':
            # left_panel.js opens the editor, keeping the last-loaded node.
            return _untouched(**_relationship_options(_options()))
        if trigger_id == 'btn-close-editor':
            return _decide({'kind': 'close'})

        # --- Starting a new form ---
        if trigger_id == 'btn-editor-new':
            return _decide({'kind': 'new'})
        if trigger_id == 'details-add-choice-input':
            if (not (details_add_choice or '').startswith('new|') or not details_selected_node
                    or manager.get_node(details_selected_node) is None):
                return _untouched()
            return _decide({'kind': 'new', 'parent': details_selected_node})
        if trigger_id == 'btn-goals-sidebar-new':
            return _decide({'kind': 'new', 'goal': True}) if goal_new_clicks else _untouched()
        if trigger_id == 'btn-bridge-create':
            return _decide({'kind': 'bridge'}) if bridge_clicks else _untouched()
        if trigger_id == 'background-click-input':
            return _decide({'kind': 'background'})

        # --- Reverting ---
        if trigger_id == 'btn-revert':
            # Reload the node the editor holds, dropping what wasn't saved.
            node = manager.get_node(original_name) if revert_clicks and original_name else None
            if node is None:
                return _untouched()
            return _load(node, node.name if editor_open else no_update)

        # --- Loading a node ---
        if trigger_id in ('edit-trigger-input', 'details-edit-trigger-input'):
            # The node's name is carried in the trigger value.
            edit_val = (edit_trigger_val if trigger_id == 'edit-trigger-input'
                        else details_edit_trigger_val)
            node = manager.get_node(bridge_payloads.strip_stamp(edit_val)) if edit_val else None
            return _decide({'kind': 'edit', 'name': node.name}) if node else _untouched()
        if trigger_id == 'search-node':
            if not search_val:
                # Clearing the picker starts a blank form, as New Node does.
                return _decide({'kind': 'new'}, picker=original_name, blank_search=no_update)
            # Resolve alias: prefix to actual node name
            resolved_name = search_val
            if search_val.startswith('alias:'):
                # Case-insensitive resolve so the user's typed casing
                # doesn't have to match the stored titlecase form.
                resolved = manager.resolve_alias(search_val[6:])
                resolved_name = resolved if resolved is not None else search_val
            node = manager.get_node(resolved_name)
            if node is None:
                return _untouched()
            return _decide({'kind': 'picker', 'name': node.name}, picker=original_name)
        if trigger_id == 'editor-tap-store' and tapped_node and tapped_node.get('id'):
            # Read the node from the database: the canvas's copy may be stale.
            node = manager.get_node(tapped_node['id'])
            return _decide({'kind': 'tap', 'name': node.name}) if node else _untouched()
        return _untouched()


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
         Output('aliases-container', 'children', allow_duplicate=True),
         Output('aliases-label', 'children', allow_duplicate=True),
         Output('editor-pristine-snapshot', 'data', allow_duplicate=True),
         Output('node-now', 'value', allow_duplicate=True)],
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
            return (dash.no_update,) * 7
        linted = save_result.get('name')
        if not linted or manager.get_node(linted) is None:
            return (dash.no_update,) * 7
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
        if 'rates' in save_result:
            snapshot['rates'] = save_result['rates']
        # A full list, or a Done that took the node off Now, can leave the
        # switch saying what the save didn't do.
        now = dash.no_update
        if 'now' in save_result:
            snapshot['now'] = save_result['now']
            # A save that asked before reopening the node holds the switch:
            # the answer decides (confirm_undo_done, close_undo_done_modal).
            if (not save_result.get('reopen_asked')
                    and save_result['now'] != (save_result.get('form', form).get('now') or [])):
                now = save_result['now']
        # Rewrite node-original-name only when the save changed it (a rename
        # or a new node). Everything keyed off it reloads from the database,
        # and on a save that failed that reload would throw away what the
        # user had just entered, such as a Dormant switch the save refused.
        original_out = linted if linted != cur_original_name else dash.no_update
        return (original_out, linted, linted_aliases, render_alias_rows(linted_aliases),
                alias_rows_label(linted_aliases), snapshot, now)

    register_merge_callbacks(app, services)
    register_field_callbacks(app, services)
    register_check_callbacks(app, services)
    register_dialog_callbacks(app, services)
    register_alias_callbacks(app, services)
    register_ratings_callbacks(app, services)
    register_resource_link_callbacks(app, services)
    register_dormancy_callbacks(app, services)
