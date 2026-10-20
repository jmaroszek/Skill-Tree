"""The node editor's Save: the form, written to the graph in one transaction.

Dash-free. The engine checks the name and type first, calls save_editor_form,
and turns what it returns, or raises, into its response.
"""
import time
from typing import NamedTuple, Optional

from skilltree.domain.models import STATUS_DONE, STATUS_OPEN
from skilltree.domain.time import (
    compute_habit_time_omp, resolve_time_mode, resolve_value_mode,
    time_estimate_problem,
)
from skilltree.features.editor.form import (
    NEW_NODE_DORMANCY, RELATIONSHIP_FIELDS, dormancy_for_save, resolve_context_intent,
    resolve_done_intent, resolve_relationship_intent, resolve_time_intent,
    resource_link_values, stored_relationships, woke_during_edit,
)
from skilltree.store import database
from skilltree.store.commands import (
    ReopensDoneNodes, apply_dormancy, done_names, finish_bridge, handle_save,
    prior_node_for_completion,
)
from skilltree.store import settings


class SavedForm(NamedTuple):
    """What a committed save did."""
    message: str
    # The node this save marked Done, for the time-calibration modal. Only a
    # true transition counts: re-saving a Done node must not ask again.
    completed: Optional[str]
    # The node the save un-marked but kept Done, and the Done nodes after it
    # that reopening it would re-block. The undo-Done modal asks first.
    undo_pending: Optional[list]
    undo_downstream: list
    # What editor-save-result-store holds: the name, the Save button it came
    # from, the status committed, the form as saved and when.
    result: dict


def save_editor_form(graph, events, form, name, *, original_name, pristine_snapshot,
                     bridge_pending, reopen_confirmed, via):
    """Save the editor's form as the node `name`, in one transaction.

    `name` is formatted and checked already. `via` is the Save button the
    save came from. Raises ReopensDoneNodes when the save would reopen Done
    nodes the user hasn't agreed to reopen, and ValueError or TypeError when
    the form can't be saved. Either rolls the whole save back.
    """
    # The form's fields, under the names the save reads them by. The *_val
    # names are the raw switches the save resolves into modes.
    n_type, desc = form.get('n_type'), form.get('desc')
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
    completed = None
    undo_pending = None
    undo_downstream = []
    with database.transaction():
        _done_before = done_names(graph)
        _prior_for_completion = prior_node_for_completion(
            graph, name, original_name)
        status_done = resolve_done_intent(
            _prior_for_completion, status_done, pristine_snapshot)
        context, subctx = resolve_context_intent(
            _prior_for_completion, context, subctx, pristine_snapshot)
        woke_from = woke_during_edit(
            events, (original_name or name).strip(), dormancy,
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
                completed = name
        # Un-marking a Done node re-blocks the Done nodes after
        # it, and the node menu asks before doing that. The save
        # keeps it Done; below, once its relationships are saved,
        # it is either reopened or the user is asked.
        reopening = _was_done and STATUS_DONE not in (status_done or [])
        if reopening and not sleeping:
            status_done = [STATUS_DONE]

        multiplier = settings.time_multiplier(time_unit)
        t_o = float(time_o or 0) * multiplier
        t_m = float(time_m or 0) * multiplier
        t_p = float(time_p or 0) * multiplier
        # An estimate the user left as it loaded keeps its stored hours.
        kept_hours = resolve_time_intent(_prior_for_completion, form, pristine_snapshot)
        if kept_hours is not None:
            t_o, t_m, t_p = kept_hours

        # Intercept rename: if original name differs from current name, rename node atomically
        if (original_name and original_name.strip() and
                name.strip() != original_name.strip() and
                graph.get_node(original_name.strip())):
            graph.rename_node(original_name.strip(), name.strip())

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
        _prior = graph.get_node(name)
        was_dormant = bool(_prior and _prior.dormant)
        # Wake before applying completion intent. Both still
        # belong to this save and roll back together on refusal.
        if was_dormant and not sleeping:
            events.detach_node_from_all_events(name)
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
                stored_relationships(graph.get_edges(), name),
                form, pristine_snapshot)
        msg = handle_save(graph, name, n_type, desc, val, t_o, t_m, t_p,
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
            replaced = finish_bridge(graph, name, bridge_pending)
            if replaced:
                msg += (f", replacing the link from '{replaced[0]}' "
                        f"to '{replaced[1]}'")

        # Save aliases
        clean_aliases = [a for a in (alias_values or []) if a and a.strip()]
        graph.set_aliases(name, clean_aliases)

        # Dormant switch and Event section. A refusal raises
        # ValueError and rolls the whole save back.
        apply_dormancy(graph, events, name,
                       dormancy_for_save(dormancy), was_dormant)
        if woke_from:
            msg += (f". It woke from '{woke_from}' while you were "
                    "editing, so it stays awake")

        # Still Done unless a new unfinished prerequisite has
        # already re-blocked it.
        _saved = graph.get_node(name) if reopening else None
        if _saved is not None and _saved.status == STATUS_DONE:
            undo_downstream = graph.get_downstream_done_dependents(name)
            if undo_downstream:
                undo_pending = [name]
            else:
                _saved.status = STATUS_OPEN
                graph.update_node(_saved)

        # A new Hard prerequisite that isn't Done reopens the
        # Done node it leads to, and the Done nodes after it. The
        # user is asked first; raising rolls the save back. The
        # node the user un-marked is reopening by their own hand.
        if original_name and original_name in _done_before:
            _done_before = (_done_before - {original_name}) | {name}
        _reopened = _done_before - done_names(graph)
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
    _committed = graph.get_node(name)
    # `form` is the form as it was saved: the new baseline for the
    # unsaved-changes check (sync_original_name_after_save).
    result = {"name": name, "via": via,
              "status_done": [STATUS_DONE] if _committed.status == STATUS_DONE else [],
              "form": form,
              "ts": int(time.time() * 1000)}
    if woke_from:
        # The node is awake, whatever the form said: that is the
        # baseline, and populate_node_dormancy redraws the section.
        result["form"] = {**form, "dormancy": dict(NEW_NODE_DORMANCY)}
        result["woke"] = woke_from
    return SavedForm(msg, completed, undo_pending, undo_downstream, result)
