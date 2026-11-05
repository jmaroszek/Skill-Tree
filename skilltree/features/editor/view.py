"""What the node editor shows around a node's values, sent with them.

A load used to send only the values. Everything that depends on them came after,
from callbacks of their own: which sections the type shows, the alias and link
rows, whether Save is on, the hour hints, the calibration badge. Each was another
pass through the browser, so a load drew in up to eight frames over most of a
second. populate_editor now sends all of it with the values, so the form changes
at once. The callbacks still answer the user's own changes afterwards. After a
load they work out what the form already shows.

Some of these rules run in the browser, where the user's clicks need them at once.
Their twins here are checked against that JavaScript in
tests/features/editor/test_editor_view.py, so the two can't drift apart.
"""
import math

from dash import Output

from skilltree.features.editor.checks import time_estimate_checks
from skilltree.features.editor.form import dormancy_fill, habit_preview_text
from skilltree.features.editor.layout import alias_rows_label, render_alias_rows
from skilltree.features.editor.resources import render_resource_sections
from skilltree.store import settings
from skilltree.ui.components.context_picker import picker_state

CALIBRATION_BADGE = "Excluded from calibration review — restore in Reflection."

_TIME_FIELDS = ('o', 'm', 'p')

# The outputs editor_view fills, by key: what can look different from one node
# to the next. Save's tooltip and the time warnings are left out, since a load
# can't show them: the warnings wait until the user leaves the time section
# (data-validation-ready). So are the Inherit locks' warnings, which answer a
# click. Most of these have a callback that keeps them in step with the user's
# edits, so they all allow duplicates.
VIEW_OUTPUTS = {
    'view_habit_toggle': ('section-time-habit-toggle', 'style'),
    'view_time_omp': ('section-time-omp', 'style'),
    'view_time_habit': ('section-time-habit', 'style'),
    'view_time_unit': ('node-time-unit', 'style'),
    'view_ratings': ('section-ratings', 'style'),
    'view_effort_row': ('node-effort-row', 'style'),
    'view_effort_caption': ('node-effort-caption', 'style'),
    'view_now_wrapper': ('node-now-wrapper', 'style'),
    'view_done_wrapper': ('node-status-done-wrapper', 'style'),
    'view_dormant_wrapper': ('node-dormant-wrapper', 'style'),
    'view_dormant_section': ('node-dormant-section', 'style'),
    'view_dormant_event_name': ('node-dormant-event-name', 'style'),
    'view_dormant_settings': ('node-dormant-settings', 'style'),
    'view_dormant_wake_date': ('node-dormant-wake-date-wrapper', 'style'),
    'view_dormant_delay_switch': ('node-dormant-delay-switch', 'style'),
    'view_dormant_delay_fields': ('node-dormant-delay-fields', 'style'),
    'view_dormant_wake_warning_style': ('node-dormant-wake-warning', 'style'),
    'view_dormant_wake_warning_text': ('node-dormant-wake-warning', 'children'),
    **{f'view_hours_{f}_text': (f'node-time-{f}-hours', 'children') for f in _TIME_FIELDS},
    **{f'view_hours_{f}_style': (f'node-time-{f}-hours', 'style') for f in _TIME_FIELDS},
    'view_bracket_row': ('node-time-bracket-row', 'className'),
    'view_save_disabled': ('btn-save', 'disabled'),
    'view_validation_ready': ('section-time-estimates', 'data-validation-ready'),
    'view_habit_preview': ('node-habit-total-preview', 'children'),
    'view_alias_rows': ('aliases-container', 'children'),
    'view_alias_label': ('aliases-label', 'children'),
    'view_badge_text': ('node-calibration-dismissed-badge', 'children'),
    'view_badge_style': ('node-calibration-dismissed-badge', 'style'),
    'view_revert_disabled': ('btn-revert', 'disabled'),
    'view_locate_disabled': ('btn-locate-node', 'disabled'),
    'view_context_picker': ('node-context-picker-state', 'children'),
}

VIEW_FILL = {key: Output(component, prop, allow_duplicate=True)
             for key, (component, prop) in VIEW_OUTPUTS.items()}


def _hide():
    return {'display': 'none'}


def _show():
    return {}


def _on(value, option):
    return bool(value) and option in value


def type_section_styles(node_type):
    """Done time, time estimates, priority rank and the Habit switch, for a type.

    The priority rank stays hidden: ranking is the Goals sidebar's job. Its
    section is kept so the hidden select other callbacks read still has a
    container. Goals and Milestones hide the Habit switch, since their time is
    always inherited."""
    container = node_type in ('Goal', 'Milestone')
    return _show(), _show(), _hide(), _hide() if container else _show()


def time_mode_styles(time_mode, habit_mode):
    """The bracket, the habit fields and the unit select, for the time switches.
    The twin of fields.py's clientside rule."""
    if _on(time_mode, 'inherited'):
        return _hide(), _hide(), _hide()
    if _on(habit_mode, 'habit'):
        return _hide(), _show(), _hide()
    return _show(), _hide(), _show()


def ratings_style(value_mode):
    """Value and Interest hide while they're inherited. The twin of fields.py's rule."""
    return _hide() if _on(value_mode, 'inherited') else _show()


def effort_styles(node_type, time_mode):
    """Effort's slider, or the note that it comes from subtasks. The twin of
    fields.py's rule."""
    if node_type == 'Goal' or _on(time_mode, 'inherited'):
        return _hide(), _show()
    return _show(), _hide()


def dormancy_styles(dormant, now, done, event, delay_on, snapshot):
    """The Dormant section's fields, and Now's and Done's switches beside it.
    The twin of assets/editor/dormancy.js's show_fields."""
    is_dormant = _on(dormant, 'dormant')
    busy = bool(now) or bool(done)
    saved = (snapshot or {}).get('dormancy') or {}
    scheduled = saved.get('wake_date') is not None and bool(event) and event == saved.get('event')
    waking = bool(saved.get('dormant')) and not is_dormant
    warning = ''
    if waking:
        warning = (f"Saving wakes this node and removes it from {saved['event']}."
                   if saved.get('event') else 'Saving wakes this node.')

    def shown(condition):
        return _show() if condition else _hide()

    return (shown(not is_dormant), shown(not is_dormant), shown(not (busy and not is_dormant)),
            shown(is_dormant), shown(event == '__new__'), shown(bool(event)),
            shown(scheduled), shown(not scheduled),
            shown(not scheduled and bool(delay_on)), shown(waking), warning)


def _hour_text(hours):
    # Math.round, which rounds halves up, then toLocaleString('en-US') to one place.
    rounded = math.floor(hours * 10 + 0.5) / 10
    if hours > 0 and rounded == 0:
        return '< 0.1h'
    text = f"{rounded:,.1f}"
    return f"= {text[:-2] if text.endswith('.0') else text}h"


def hour_hints(values, unit, time_settings):
    """Each estimate's hours, their styles, and the bracket row's class. The twin
    of assets/editor/time_hour_hints.js."""
    time_settings = time_settings or {}
    week = time_settings.get('hours_per_week')
    month = time_settings.get('hours_per_month')
    multipliers = {}
    if isinstance(week, (int, float)):
        multipliers.update(days=week / 7, weeks=week)
    if isinstance(month, (int, float)):
        multipliers.update(months=month, years=month * 13)
    multiplier = multipliers.get(unit)
    enabled = (time_settings.get('show_hour_equivalents') is not False
               and multiplier is not None and multiplier > 0)
    texts, styles = [], []
    for value in values:
        number = isinstance(value, (int, float)) and not isinstance(value, bool)
        hours = value * multiplier if number and enabled else None
        visible = enabled and number and math.isfinite(hours) and value >= 0
        texts.append(_hour_text(hours) if visible else '')
        styles.append({'display': 'block' if visible else 'none'})
    return texts, styles, 'has-hour-hints' if any(s['display'] == 'block' for s in styles) else ''


def calibration_badge(node):
    """The note on a node left out of calibration review, and its style."""
    if node is not None and node.calibration_dismissed:
        return CALIBRATION_BADGE, {'display': 'block'}
    return '', {'display': 'none'}


def editor_view(snapshot, node=None):
    """VIEW_OUTPUTS' values for a form that shows ``snapshot``, and its link rows
    under ``resource_links``. ``node`` is the stored node it was loaded from, or
    None for a new one."""
    n_type = snapshot['n_type']
    time_mode = snapshot['time_mode']
    habit_mode = snapshot['time_habit_mode']
    fill = dormancy_fill(snapshot['dormancy'])
    view = {'view_habit_toggle': type_section_styles(n_type)[3]}
    view.update(zip(('view_time_omp', 'view_time_habit', 'view_time_unit'),
                    time_mode_styles(time_mode, habit_mode)))
    view['view_ratings'] = ratings_style(snapshot['value_mode'])
    view.update(zip(('view_effort_row', 'view_effort_caption'), effort_styles(n_type, time_mode)))
    view.update(zip(
        ('view_now_wrapper', 'view_done_wrapper', 'view_dormant_wrapper', 'view_dormant_section',
         'view_dormant_event_name', 'view_dormant_settings', 'view_dormant_wake_date',
         'view_dormant_delay_switch', 'view_dormant_delay_fields',
         'view_dormant_wake_warning_style', 'view_dormant_wake_warning_text'),
        dormancy_styles(fill['dormant_switch'], snapshot['now'], snapshot['status_done'],
                        fill['dormant_event'], fill['dormant_delay_on'], snapshot)))
    estimates = [snapshot[f'time_{f}'] for f in _TIME_FIELDS]
    texts, styles, row_class = hour_hints(estimates, snapshot['time_unit'],
                                          settings.TIME_SETTINGS.get())
    for field, text, style in zip(_TIME_FIELDS, texts, styles):
        view[f'view_hours_{field}_text'] = text
        view[f'view_hours_{field}_style'] = style
    view['view_bracket_row'] = row_class
    checks = time_estimate_checks(*estimates, time_mode, habit_mode, snapshot['habit_duration'],
                                  snapshot['habit_intensity_o'], snapshot['habit_intensity_m'],
                                  snapshot['habit_intensity_p'], snapshot['habit_days'])
    view['view_save_disabled'] = checks[4]
    # A loaded form starts quiet: its time warnings wait until the user leaves
    # the section. The warnings themselves follow from validate_time_estimates.
    view['view_validation_ready'] = 'false'
    view['view_habit_preview'] = habit_preview_text(
        snapshot['habit_duration'], snapshot['habit_duration_unit'],
        snapshot['habit_intensity_o'], snapshot['habit_intensity_m'],
        snapshot['habit_intensity_p'], snapshot['habit_days'])
    view['view_alias_rows'] = render_alias_rows(snapshot['aliases'])
    view['view_alias_label'] = alias_rows_label(snapshot['aliases'])
    # The links show only as rows: the snapshot's key is the rows' output.
    view['resource_links'] = render_resource_sections(snapshot['resource_links'])
    view['view_badge_text'], view['view_badge_style'] = calibration_badge(node)
    view['view_revert_disabled'] = node is None
    view['view_locate_disabled'] = node is None
    view['view_context_picker'] = picker_state('single', snapshot['context'], snapshot['subctx'])
    return view
