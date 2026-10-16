"""
Shared helper functions for Dash callback modules.

Contains stateless utility functions extracted from callbacks.py to keep
the callback registration files focused on Dash I/O wiring.
"""

import logging
from skilltree.ui.components.duration import NEW_NODE_TIME_UNIT
from skilltree.store import database

import dash
from dash import html, State, ALL
import dash_bootstrap_components as dbc
from skilltree.domain.time import (
    ALL_WEEKDAYS, habit_day_count as _habit_day_count, habit_to_hours,
    parse_habit_days,
)

logger = logging.getLogger(__name__)

from skilltree.store.settings import ConfigManager
from skilltree.domain.models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_DONE
from skilltree.ui.kit import add_button
from skilltree.store.resources import get_sections


# --- Habit-mode time conversion ---


def habit_editor_view(intensity_unit, int_o, int_m, int_p, habit_days):
    """Map stored habit fields to the minutes-per-session editor widgets.

    The editor expresses cadence as minutes per session over a set of weekdays,
    so every stored breakdown is normalized to that form. Hour-based legacy
    amounts are converted to minutes (×60). Legacy ``*_per_day`` units map to
    all seven days; legacy ``*_per_week`` units spread the weekly amount across
    seven days. The computed total hours are preserved in every case.
    Returns ``(unit, o, m, p, days_list)`` with unit always ``min_per_session``.
    """
    unit = intensity_unit or 'min_per_day'
    o, m, p = (int_o or 0), (int_m or 0), (int_p or 0)
    if unit.startswith('hr'):
        o, m, p = o * 60, m * 60, p * 60
    if unit.endswith('_per_session'):
        return 'min_per_session', o, m, p, parse_habit_days(habit_days)
    if unit.endswith('_per_week'):
        return ('min_per_session', round(o / 7.0, 4), round(m / 7.0, 4),
                round(p / 7.0, 4), list(ALL_WEEKDAYS))
    # per_day (or anything unrecognized): every day, amount unchanged.
    return 'min_per_session', o, m, p, list(ALL_WEEKDAYS)


def habit_preview_text(duration, dur_unit, intensity_m, int_unit, days=None):
    """Human-readable live preview of the habit estimate's total hours."""
    int_unit = int_unit or 'min_per_session'
    total = habit_to_hours(duration or 0, dur_unit or 'weeks',
                           intensity_m or 0, int_unit, days)
    if total <= 0:
        return ""
    if int_unit.endswith('_per_session'):
        n = _habit_day_count(days)
        mag = 'min' if int_unit.startswith('min') else 'hr'
        day_str = f"{n} day{'' if n == 1 else 's'}/wk"
        dur_str = f"{(duration or 0):g} {dur_unit or 'weeks'}"
        return (f"≈ {round(total, 1)} h total — "
                f"{(intensity_m or 0):g} {mag} × {day_str} × {dur_str}")
    return f"Computes to ~{round(total, 1)} h total"


# --- Editor Dirty-State Check (snapshot-based) ---


def _norm_str(s):
    return (s or '').strip()


def _norm_list(lst):
    """Canonicalize a list: drop empty strings, sort."""
    return sorted([v for v in (lst or []) if v])


# --- Dormancy in the node editor ---
# Dormant is a form field like any other: flipping it writes nothing until
# Save. A dormant node belongs to one event. The section's controls are
# collected into one dict by a clientside callback (node-dormancy-form); this
# is its shape:
#
#   dormant      the Dormant switch
#   event        the node's event, NEW_EVENT_OPTION, or None
#   event_name   name for the new event when event is NEW_EVENT_OPTION
#   delay_value / delay_unit   how long after the event fires the node wakes;
#                0 while the Delay switch is off
#   wake_date    the date a fired event gave the node, while it is still in
#                that event; None otherwise. '' means the date was cleared.
#   now          Add to Now

NEW_EVENT_OPTION = '__new__'

NEW_NODE_DORMANCY = {'dormant': False, 'event': None, 'event_name': '',
                     'delay_value': 0, 'delay_unit': 'days',
                     'wake_date': None, 'now': False}


def build_dormancy_snapshot(node, event_manager=None):
    """What the editor's Dormant switch and Event section show for `node`."""
    if node is None or not node.dormant:
        return dict(NEW_NODE_DORMANCY)
    if event_manager is None:
        from skilltree.store.events import EventManager
        event_manager = EventManager()
    membership = event_manager.get_node_membership(node.name)
    if membership is None:
        return dict(NEW_NODE_DORMANCY, dormant=True)
    wake_date = membership.get('activation_date') or None
    if wake_date:
        value, unit = 0, 'days'
    else:
        from skilltree.ui.components.duration import days_to_duration
        value, unit = days_to_duration(membership.get('delay_days'))
    return {
        'dormant': True,
        'event': membership['event'],
        'event_name': '',
        'delay_value': value,
        'delay_unit': unit,
        'wake_date': wake_date,
        'now': bool(membership.get('now_on_trigger')),
    }


def _norm_dormancy(dormancy):
    """Comparable form of a dormancy dict. Delays compare in days, so
    "1 week" and "7 days" are the same setting. The rest of the section
    means nothing while Dormant is off."""
    from skilltree.ui.components.duration import duration_to_days
    d = dormancy or {}
    if not d.get('dormant'):
        return (False,)
    event = d.get('event') or None
    event_name = _norm_str(d.get('event_name')) if event == NEW_EVENT_OPTION else ''
    wake_date = d.get('wake_date')
    when = (('date', wake_date) if wake_date is not None
            else ('days', duration_to_days(d.get('delay_value'), d.get('delay_unit'))))
    return True, event, event_name, when, bool(d.get('now'))


def woke_during_edit(events, name, dormancy, pristine_snapshot):
    """The event `name` woke from while its editor was open, or None.

    Every save runs the date sweeps first, so a node can wake between loading
    the editor and saving it. The form still says Dormant, and saving that
    asked to put an awake node back to sleep: refused, and the whole save
    with it. When the user left the Dormant section as it loaded and the node
    has since woken from that event, the wake stands and the rest saves.
    """
    loaded = pristine_snapshot.get('dormancy') if isinstance(pristine_snapshot, dict) else None
    if (not (dormancy or {}).get('dormant') or not (loaded or {}).get('dormant')
            or _norm_dormancy(dormancy) != _norm_dormancy(loaded)
            or pristine_snapshot.get('name') != name):
        return None
    event = loaded.get('event')
    return event if event and events.woke_from(name) == event else None


def dormancy_for_save(dormancy):
    """The node-dormancy-form dict in the shape node_commands.apply_dormancy
    takes: the delay in days, and the new-event choice resolved to its name."""
    from skilltree.ui.components.duration import duration_to_days
    d = dormancy or {}
    event = d.get('event') or None
    new_event = event == NEW_EVENT_OPTION
    if new_event:
        event = _norm_str(d.get('event_name')) or None
    wake_date = d.get('wake_date')
    return {
        'dormant': bool(d.get('dormant')),
        'event': event,
        'new_event': new_event,
        'delay_days': (None if wake_date is not None
                       else duration_to_days(d.get('delay_value'), d.get('delay_unit'))),
        'wake_date': wake_date,
        'now': bool(d.get('now')),
    }


# Pristine snapshot for the new-node form — mirrors the def_out defaults
# emitted by populate_editor when the user clicks "+ New Node". The type
# starts unselected there, so it is blank here too.
NEW_NODE_SNAPSHOT = {
    'name': '', 'n_type': '', 'desc': '',
    'context': '', 'subctx': '',
    'status_done': [],
    'val': 5, 'interest': 5, 'diff': 5,
    # Blank: an estimate is the user's own call, and Save requires one.
    'time_o': None, 'time_m': None, 'time_p': None, 'time_unit': NEW_NODE_TIME_UNIT,
    'e_needs_h': [], 'e_needs_s': [],
    'e_supp_h': [], 'e_supp_s': [], 'e_helps': [],
    'resource_links': {},
    'time_mode': [],
    'time_habit_mode': [],
    'habit_duration': 0,
    'habit_duration_unit': 'weeks',
    'habit_intensity_o': 0, 'habit_intensity_m': 0, 'habit_intensity_p': 0,
    'habit_intensity_unit': 'min_per_session',
    'habit_days': list(ALL_WEEKDAYS),
    'value_mode': [],
    'priority_rank': 'none',
    'aliases': [''],
    'dormancy': NEW_NODE_DORMANCY,
}


@database.snapshot_read
def build_editor_snapshot(manager, node_name):
    """Build a snapshot of the editor form state for an existing node.

    The snapshot dict mirrors exactly what populate_editor writes into the form
    fields, *including* any post-display transformations. The dirty check
    compares form State against this snapshot so display transformations don't
    produce false-positives.

    Returns None if the node doesn't exist.
    """
    # Local import — _friendly_time_estimates lives in callbacks.py which
    # imports from this module, so we defer to avoid a circular import.
    from skilltree.features.editor.values import _friendly_time_estimates

    node = manager.get_node(node_name) if node_name else None
    if node is None:
        return None

    relationships = stored_relationships(manager.get_edges(), node_name)

    priority_goals = ConfigManager.get_priority_goals()
    if node.type == 'Goal' and node.name in priority_goals:
        priority_rank = str(priority_goals.index(node.name) + 1)
    else:
        priority_rank = 'none'

    friendly_o, friendly_m, friendly_p, friendly_unit = _friendly_time_estimates(
        node.time_o, node.time_m, node.time_p
    )

    aliases = manager.get_aliases(node_name) or ['']

    return {
        'name': node.name,
        'n_type': node.type,
        'desc': node.description or '',
        'context': node.context or '',
        'subctx': node.subcontext or '',
        'status_done': [STATUS_DONE] if node.status == STATUS_DONE else [],
        'val': node.value or 5,
        'interest': node.interest or 5,
        'diff': node.difficulty or 5,
        'time_o': friendly_o,
        'time_m': friendly_m,
        'time_p': friendly_p,
        'time_unit': friendly_unit,
        **relationships,
        'resource_links': node.resource_links,
        'time_mode': ['inherited'] if node.time_mode == 'inherited' else [],
        'time_habit_mode': ['habit'] if node.time_mode == 'habit' else [],
        'habit_duration': node.habit_duration or 0,
        'habit_duration_unit': node.habit_duration_unit or 'weeks',
        **(lambda hu, ho, hm, hp, hd: {
            'habit_intensity_o': ho, 'habit_intensity_m': hm,
            'habit_intensity_p': hp, 'habit_intensity_unit': hu,
            'habit_days': hd,
        })(*habit_editor_view(
            node.habit_intensity_unit, node.habit_intensity_o,
            node.habit_intensity_m, node.habit_intensity_p, node.habit_days)),
        'value_mode': ['inherited'] if node.value_mode == 'inherited' else [],
        'priority_rank': priority_rank,
        'aliases': aliases,
        'dormancy': build_dormancy_snapshot(node),
    }


def resolve_done_intent(node, switch, snapshot):
    """An untouched editor switch follows the latest stored completion.

    Save must do this too: a graph refresh may still be in flight when the
    user saves unrelated fields. A deliberate unsaved flip keeps its intent.
    """
    if (node is not None and isinstance(snapshot, dict)
            and snapshot.get('name') == node.name and 'status_done' in snapshot
            and (switch or []) == (snapshot['status_done'] or [])):
        return [STATUS_DONE] if node.status == STATUS_DONE else []
    return switch


def follow_done_status(node, switch, snapshot):
    """(switch, snapshot) for an editor showing ``node`` after its status may
    have changed outside the editor: the node menu's Toggle Done, the undo-Done
    confirmation, or a cascade re-blocking it.

    Returns (no_update, no_update) when the snapshot already agrees with the
    database, or when there is nothing to judge by. The switch follows only
    while it still shows what was loaded, so a flip the user hasn't saved
    stays; the snapshot always takes the stored status, so the unsaved-changes
    check compares the form with what is really there.
    """
    if node is None or not isinstance(snapshot, dict) or 'status_done' not in snapshot:
        return dash.no_update, dash.no_update
    stored = [STATUS_DONE] if node.status == STATUS_DONE else []
    loaded = snapshot.get('status_done') or []
    if loaded == stored:
        return dash.no_update, dash.no_update
    new_switch = stored if (switch or []) == loaded else dash.no_update
    return new_switch, {**snapshot, 'status_done': stored}


# The editor's relationship pickers, by their EDITOR_FORM and snapshot keys.
RELATIONSHIP_FIELDS = ('e_needs_h', 'e_needs_s', 'e_supp_h', 'e_supp_s', 'e_helps')


def stored_relationships(edges, node_name):
    """{field: sorted names} for the editor's relationship pickers, from ``edges``."""
    def linked(end, other, edge_type):
        return {e[other] for e in edges
                if e[end] == node_name and e['type'] == edge_type}

    return {
        'e_needs_h': sorted(linked('target', 'source', EDGE_NEEDS_HARD)),
        'e_needs_s': sorted(linked('target', 'source', EDGE_NEEDS_SOFT)),
        'e_supp_h': sorted(linked('source', 'target', EDGE_NEEDS_HARD)),
        'e_supp_s': sorted(linked('source', 'target', EDGE_NEEDS_SOFT)),
        'e_helps': sorted(linked('source', 'target', EDGE_HELPS)
                          | linked('target', 'source', EDGE_HELPS)),
    }


def merge_relationships(loaded, edited, stored):
    """One relationship list after a three-way merge.

    ``loaded`` is what the editor was filled with, ``edited`` what the form
    holds now, and ``stored`` what the database holds now. A name stays if
    neither side removed it, and joins if either side added it. So the user's
    edits and a change made elsewhere while the editor was open (the link
    menu, the Details tab, a bridge) both survive. The form's order is kept,
    and names only the database added follow it.
    """
    base = set(_norm_list(loaded))
    mine = set(_norm_list(edited))
    theirs = set(_norm_list(stored))
    keep = (mine & theirs) | ((mine | theirs) - base)
    ordered = [name for name in dict.fromkeys(edited or []) if name in keep]
    return ordered + sorted(keep - set(ordered))


def resolve_relationship_intent(stored, form, snapshot):
    """The relationship lists a save writes: the form's edits on top of what
    is stored now, not the lists as they were when the editor loaded.

    Save must do this as well as follow_relationships: a save can land before
    the editor has caught up with a change made elsewhere. A list the
    snapshot doesn't hold gives nothing to judge by, so the form's stands.
    """
    return {key: (merge_relationships(snapshot[key], form.get(key), stored.get(key))
                  if key in snapshot else list(form.get(key) or []))
            for key in RELATIONSHIP_FIELDS}


def follow_relationships(stored, form, snapshot):
    """(values, snapshot) for relationship pickers whose edges changed
    outside the editor.

    ``values`` holds the pickers that should change: an untouched one now
    shows what is stored, and an edited one keeps the user's edits on top of
    it. ``snapshot`` holds the stored lists for every changed key, so the
    unsaved-changes check compares the form with what is really there. Both
    are empty when the snapshot already matches the database, or holds no
    relationship lists to compare.
    """
    values, followed = {}, {}
    for key in RELATIONSHIP_FIELDS:
        now = _norm_list(stored.get(key))
        if key not in snapshot or _norm_list(snapshot[key]) == now:
            continue
        merged = merge_relationships(snapshot.get(key), form.get(key), now)
        if _norm_list(merged) != _norm_list(form.get(key)):
            values[key] = merged
        followed[key] = now
    return values, followed


def snapshot_from_form_state(form_values, linted_name, linted_aliases):
    """Build a pristine snapshot directly from the form State just saved.

    Unlike build_editor_snapshot (DB round-trip + display transforms),
    this snapshots what the form actually holds — so the post-save dirty
    check can't trip on heuristic drift (e.g. _friendly_time_estimates
    picking a different time_unit from DB hours than the user selected).

    linted_name / linted_aliases are the only values the app legitimately
    rewrites in the form after save (via the title-case linter). Pass them
    in so the snapshot agrees with the form's post-save rewritten state.
    """
    return {
        'name': linted_name,
        'n_type': form_values.get('n_type'),
        'desc': form_values.get('desc') or '',
        'context': form_values.get('context') or '',
        'subctx': form_values.get('subctx') or '',
        'status_done': form_values.get('status_done') or [],
        'val': form_values.get('val', 5),
        'interest': form_values.get('interest', 5),
        'diff': form_values.get('diff', 5),
        'time_o': form_values.get('time_o'),
        'time_m': form_values.get('time_m'),
        'time_p': form_values.get('time_p'),
        'time_unit': form_values.get('time_unit'),
        'e_needs_h': form_values.get('e_needs_h') or [],
        'e_needs_s': form_values.get('e_needs_s') or [],
        'e_supp_h': form_values.get('e_supp_h') or [],
        'e_supp_s': form_values.get('e_supp_s') or [],
        'e_helps': form_values.get('e_helps') or [],
        'resource_links': form_values.get('resource_links') or {},
        'time_mode': form_values.get('time_mode') or [],
        'time_habit_mode': form_values.get('time_habit_mode') or [],
        'habit_duration': form_values.get('habit_duration') or 0,
        'habit_duration_unit': form_values.get('habit_duration_unit') or 'weeks',
        'habit_intensity_o': form_values.get('habit_intensity_o') or 0,
        'habit_intensity_m': form_values.get('habit_intensity_m') or 0,
        'habit_intensity_p': form_values.get('habit_intensity_p') or 0,
        'habit_intensity_unit': form_values.get('habit_intensity_unit') or 'min_per_session',
        'habit_days': form_values.get('habit_days') or list(ALL_WEEKDAYS),
        'value_mode': form_values.get('value_mode') or [],
        'priority_rank': form_values.get('priority_rank') or 'none',
        'aliases': linted_aliases or [''],
        # The Event section is refreshed from the database after any save
        # that touches dormancy, and that refresh re-baselines this key.
        'dormancy': form_values.get('dormancy') or NEW_NODE_DORMANCY,
    }


def editor_form_values(
    *,
    name, n_type, desc, context, subctx, status_done,
    val, interest, diff,
    time_o, time_m, time_p, time_unit,
    e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
    resource_links,
    time_mode, value_mode, priority_rank, aliases,
    dormancy,
    time_habit_mode=None,
    habit_duration=0, habit_duration_unit='weeks',
    habit_intensity_o=0, habit_intensity_m=0, habit_intensity_p=0,
    habit_intensity_unit='min_per_session',
    habit_days=None,
):
    """Assemble the canonical editor form-values dict for the dirty check.

    This is the single source of truth for the key set that
    is_form_dirty_vs_snapshot compares against a snapshot. Every call site that
    needs a dirty check must build its form dict through here, so the schema
    can't drift per-call-site. Per-call-site drift — a call site omitting a
    field that the snapshot carries — was the historical cause of spurious
    "unsaved changes" prompts: an omitted field read back as a coercion default
    that disagreed with the snapshot, flagging an unchanged form as dirty.

    All args are keyword-only so a forgotten field is a loud TypeError at the
    call site rather than a silent omission. The habit_* defaults mirror the
    editor's component defaults (see sidebars_layout.py) so they stay aligned
    with NEW_NODE_SNAPSHOT for any caller that legitimately has no habit state.
    """
    return {
        'name': name, 'n_type': n_type, 'desc': desc,
        'context': context, 'subctx': subctx,
        'status_done': status_done,
        'val': val, 'interest': interest, 'diff': diff,
        'time_o': time_o, 'time_m': time_m, 'time_p': time_p,
        'time_unit': time_unit,
        'e_needs_h': e_needs_h, 'e_needs_s': e_needs_s,
        'e_supp_h': e_supp_h, 'e_supp_s': e_supp_s, 'e_helps': e_helps,
        'resource_links': resource_links or {},
        'time_mode': time_mode,
        'time_habit_mode': time_habit_mode,
        'habit_duration': habit_duration,
        'habit_duration_unit': habit_duration_unit,
        'habit_intensity_o': habit_intensity_o,
        'habit_intensity_m': habit_intensity_m,
        'habit_intensity_p': habit_intensity_p,
        'habit_intensity_unit': habit_intensity_unit,
        'habit_days': habit_days if habit_days is not None else list(ALL_WEEKDAYS),
        'value_mode': value_mode,
        'priority_rank': priority_rank,
        'aliases': aliases,
        'dormancy': dormancy,
    }


# The node editor's form: every field a save writes and the unsaved-changes
# check compares. The callbacks that read the form (core_engine,
# populate_editor, toggle_unsaved_modal, sync_original_name_after_save) take
# it as one grouped State, and Dash hands each of them this dict with the
# fields' values. A new field is added here once. The keys are
# editor_form_values' names, except that the resource links arrive as the two
# lists their pattern-matched inputs give (resource_link_values joins them).
EDITOR_FORM = {
    'name': State('node-name', 'value'),
    'n_type': State('node-type', 'value'),
    'desc': State('node-desc', 'value'),
    'context': State('node-context', 'value'),
    'subctx': State('node-subcontext', 'value'),
    'status_done': State('node-status-done', 'value'),
    'val': State('node-value', 'value'),
    'interest': State('node-interest', 'value'),
    'diff': State('node-difficulty', 'value'),
    'time_o': State('node-time-o', 'value'),
    'time_m': State('node-time-m', 'value'),
    'time_p': State('node-time-p', 'value'),
    'time_unit': State('node-time-unit', 'value'),
    'e_needs_h': State('edge-needs-hard', 'value'),
    'e_needs_s': State('edge-needs-soft', 'value'),
    'e_supp_h': State('edge-supports-hard', 'value'),
    'e_supp_s': State('edge-supports-soft', 'value'),
    'e_helps': State('edge-helps', 'value'),
    'link_values': State({'type': 'resource-link', 'index': ALL}, 'value'),
    'link_ids': State({'type': 'resource-link', 'index': ALL}, 'id'),
    'time_mode': State('node-time-mode', 'value'),
    'time_habit_mode': State('node-time-habit-mode', 'value'),
    'habit_duration': State('node-habit-duration', 'value'),
    'habit_duration_unit': State('node-habit-duration-unit', 'value'),
    'habit_intensity_o': State('node-habit-intensity-o', 'value'),
    'habit_intensity_m': State('node-habit-intensity-m', 'value'),
    'habit_intensity_p': State('node-habit-intensity-p', 'value'),
    'habit_intensity_unit': State('node-habit-intensity-unit', 'value'),
    'habit_days': State('node-habit-days', 'value'),
    'value_mode': State('node-value-mode', 'value'),
    'priority_rank': State('node-priority-rank', 'value'),
    'aliases': State({'type': 'alias-input', 'index': ALL}, 'value'),
    'dormancy': State('node-dormancy-form', 'data'),
}


def editor_form_values_from(form):
    """The grouped EDITOR_FORM values as editor_form_values builds them.

    ``form`` is the dict Dash passes for EDITOR_FORM. None, or a missing
    field, reads as an empty field, which is how an unset component reads.
    """
    form = form or {}
    fields = {key: form.get(key) for key in EDITOR_FORM
              if key not in ('link_values', 'link_ids')}
    return editor_form_values(
        **fields,
        resource_links=resource_link_values(form.get('link_values'), form.get('link_ids')))


def is_form_dirty_vs_snapshot(snapshot, form_values):
    """Compare current editor form State to the pristine snapshot.

    snapshot:    dict from build_editor_snapshot / NEW_NODE_SNAPSHOT, or None.
    form_values: dict of current State values keyed the same as the snapshot.
                 Build it via editor_form_values() so the key set can't drift.

    Returns False if snapshot is None — no baseline means we can't tell, and
    treating as not-dirty lets the X button always close in that edge case.
    """
    if snapshot is None:
        return False

    # Scalar string fields — strip whitespace before comparing.
    for k in ('name', 'desc', 'context', 'subctx'):
        if _norm_str(form_values.get(k)) != _norm_str(snapshot.get(k)):
            return True

    # Type / time_unit / priority_rank / habit unit selectors — direct
    # equality with empty-coercion.
    if (form_values.get('n_type') or '') != (snapshot.get('n_type') or ''):
        return True
    if (form_values.get('time_unit') or '') != (snapshot.get('time_unit') or ''):
        return True
    if (form_values.get('priority_rank') or 'none') != (snapshot.get('priority_rank') or 'none'):
        return True
    if (form_values.get('habit_duration_unit') or 'weeks') != (snapshot.get('habit_duration_unit') or 'weeks'):
        return True
    if (form_values.get('habit_intensity_unit') or 'min_per_session') != (snapshot.get('habit_intensity_unit') or 'min_per_session'):
        return True

    # Integer fields with a default-of-5 convention.
    for k in ('val', 'interest', 'diff'):
        if int(form_values.get(k) or 5) != int(snapshot.get(k) or 5):
            return True

    # Time fields — compare with 2-decimal rounding to match form display.
    for k in ('time_o', 'time_m', 'time_p',
              'habit_duration',
              'habit_intensity_o', 'habit_intensity_m', 'habit_intensity_p'):
        if round(float(form_values.get(k) or 0), 2) != round(float(snapshot.get(k) or 0), 2):
            return True

    # Checkbox-list fields — set comparison (weekday picker order-insensitive).
    for k in ('status_done', 'time_mode', 'time_habit_mode', 'value_mode',
              'habit_days'):
        if set(form_values.get(k) or []) != set(snapshot.get(k) or []):
            return True

    # Multi-value list fields — drop empties, sort, compare.
    for k in ('e_needs_h', 'e_needs_s', 'e_supp_h', 'e_supp_s', 'e_helps',
              'aliases'):
        if _norm_list(form_values.get(k)) != _norm_list(snapshot.get(k)):
            return True
    left = form_values.get('resource_links') or {}
    right = snapshot.get('resource_links') or {}
    for section_id in set(left) | set(right):
        if _norm_list(left.get(section_id)) != _norm_list(right.get(section_id)):
            return True

    if _norm_dormancy(form_values.get('dormancy')) != _norm_dormancy(snapshot.get('dormancy')):
        return True

    return False


# --- Node CRUD Helpers ---


# --- UI Formatting Helpers ---


# --- Link Row UI Helper ---

def resource_link_values(values, ids):
    """The editor's mounted resource inputs as {section_id: [links]}."""
    mounted = {}
    for value, component_id in zip(values or [], ids or []):
        section_id, _, index = component_id['index'].rpartition(':')
        mounted.setdefault(section_id, {})[int(index)] = value or ''
    return {section_id: [by_index.get(i, '') for i in range(max(by_index) + 1)]
            for section_id, by_index in mounted.items()}


def render_resource_sections(links):
    """The node editor's Resources: one labeled block of link rows per section.

    Each row is an input plus trailing browse / open / remove icons in one
    .editor-field-group. A section always shows at least one (empty) row. The
    row index rides in the id ("<section>:<i>") so one set of pattern-matched
    callbacks serves every section.
    """
    blocks = []
    for section in get_sections():
        section_id = section['id']
        values = (links or {}).get(section_id) or ['']
        rows = []
        for index, value in enumerate(values):
            key = f"{section_id}:{index}"
            children = [dbc.Input(id={'type': 'resource-link', 'index': key},
                                  value=value, type='text', placeholder='Enter path or URL...'),
                        dbc.Button(html.I(className='bi bi-folder2-open'),
                                   id={'type': 'resource-browse', 'index': key},
                                   title='Browse', className='editor-icon-btn'),
                        dbc.Button(html.I(className='bi bi-box-arrow-up-right'),
                                   id={'type': 'resource-open', 'index': key},
                                   title='Open', className='editor-icon-btn')]
            if len(values) > 1:
                children.append(dbc.Button(html.I(className='bi bi-x-lg'),
                           id={'type': 'resource-remove', 'index': key},
                           title='Remove', className='editor-icon-btn editor-icon-btn-danger'))
            rows.append(html.Div(children, className='d-flex editor-field-group mb-1'))
        blocks.append(html.Div([
            html.Div([dbc.Label(section['name'], className='mb-0'),
                      add_button({'type': 'resource-add', 'index': section_id}, "Add link")],
                     className='d-flex align-items-center mt-2 mb-1'),
            html.Div(rows),
        ], **{'data-resource-root': section['root_path'],
              'data-resource-id': section_id}))
    return blocks


def render_alias_rows(aliases, input_type="alias-input", remove_type="btn-alias-remove"):
    """Build the alias input rows (one unified field per alias, trailing ×).

    Shared by the main node editor and the add-node modals (dormant / subtask);
    callers pass the prefixed pattern-matching id types so each surface keeps
    its own component namespace. Mirrors render_resource_sections' visual style.
    """
    alias_list = aliases or ['']
    rows = []
    for i, val in enumerate(alias_list):
        rows.append(html.Div([
            dbc.Input(id={'type': input_type, 'index': i}, type='text',
                      value=val or '', placeholder='Enter alias...'),
            dbc.Button(html.I(className='bi bi-x-lg'),
                       id={'type': remove_type, 'index': i}, title='Remove alias',
                       className='editor-icon-btn editor-icon-btn-danger'),
        ], className='d-flex editor-field-group mb-1'))
    return rows


def alias_rows_label(aliases):
    """Return the singular/plural label for the rendered alias row count."""
    return "Alias" if len(aliases or ['']) == 1 else "Aliases"


def update_alias_rows(trigger, current_values, stored_values, aliases_open,
                      add_button_id, remove_button_type):
    """Apply one add/remove action to an editor's repeatable alias rows.

    The first click on the Name-label ``+`` reveals the existing first row;
    later clicks add rows. Removing the final row closes the optional section,
    ready for the next ``+`` click to reveal a fresh blank row.
    """
    aliases = (list(current_values) if current_values
               else list(stored_values or ['']))
    collapse_update = dash.no_update

    if trigger == add_button_id:
        if aliases_open:
            aliases.append('')
        collapse_update = True
    elif (isinstance(trigger, dict)
          and trigger.get('type') == remove_button_type):
        idx = trigger.get('index')
        if isinstance(idx, int) and 0 <= idx < len(aliases):
            aliases.pop(idx)
            if not aliases:
                collapse_update = False

    return aliases, collapse_update


# ---------------------------------------------------------------------------
# Explain Score modal renderer
# ---------------------------------------------------------------------------


# --- Reopening Done nodes ---
# A Done node stays Done only while all of its Hard prerequisites are. The link
# menu and the node editor ask before a change reopens one.


