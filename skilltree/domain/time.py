"""Time estimates: brackets, capacity, habits, and which node types inherit
their time."""
import math


def habit_day_count(days) -> int:
    """Count selected weekdays from a list/tuple or comma-separated string."""
    if days is None:
        return 0
    if isinstance(days, (list, tuple, set)):
        return len([d for d in days if d is not None and str(d).strip() != ''])
    return len([p for p in str(days).split(',') if p.strip() != ''])


def habit_to_hours(duration: float, duration_unit: str,
                   intensity: float, intensity_unit: str, days=None) -> float:
    """Convert a (duration, intensity) habit estimate to total hours.

    intensity_unit is '{min|hr}_per_{day|week|session}'. duration_unit is one
    of 'days' / 'weeks' / 'months' / 'years'. Months use a 30-day approximation
    and years use 365 — the blend is for ROI cost, not calendar precision.

    For the '_per_session' cadence, ``days`` selects which weekdays the session
    happens on (a list of indices or a comma-separated string); the per-session
    amount is applied on each selected day. Selecting all seven days reproduces
    the legacy '_per_day' total. Returns 0.0 if either side is zero.
    """
    if not duration or not intensity:
        return 0.0
    if duration_unit == 'weeks':
        days_total = float(duration) * 7
    elif duration_unit == 'months':
        days_total = float(duration) * 30
    elif duration_unit == 'years':
        days_total = float(duration) * 365
    else:
        days_total = float(duration)
    # Per-session cadence: the amount applies on each selected weekday, so the
    # number of weekly sessions scales the total. All seven days ⇒ identical to
    # the legacy per-day total.
    if intensity_unit and intensity_unit.endswith('_per_session'):
        num_days = habit_day_count(days)
        if num_days == 0:
            return 0.0
        hours_per_session = (
            float(intensity) / 60.0
            if intensity_unit.startswith('min') else float(intensity)
        )
        sessions = (days_total / 7.0) * num_days
        return round(sessions * hours_per_session, 2)
    parts = (intensity_unit or 'min_per_day').split('_per_')
    mag_unit, period = parts[0], (parts[1] if len(parts) == 2 else 'day')
    hours_per_mag = (1 / 60.0) if mag_unit == 'min' else 1.0
    if period == 'week':
        hours_per_day = float(intensity) * hours_per_mag / 7.0
    else:
        hours_per_day = float(intensity) * hours_per_mag
    return round(days_total * hours_per_day, 2)


def sync_time_fields(triggered, hpd, hpw, hpm, hpy):
    """Fill the other productive-hours fields from the one just edited.

    Returns (hpd, hpw, hpm, hpy) with None for a field to leave alone. A week is
    seven days, a month four weeks, a year 52 weeks.

    The day field is a rounded display of the week (20h/week reads 2.86). When
    that rounded value lands back here as the trigger, it must not overwrite the
    week: 2.86 x 7 is 20.02, which then drifts the month and year with it. So a
    day value that is just the rounding of the current week is ignored.
    """
    none = (None, None, None, None)
    try:
        if triggered == 'setting-hpd' and hpd is not None:
            if hpw is not None and abs(round(float(hpw) / 7.0, 2) - float(hpd)) < 1e-9:
                return none
            w = float(hpd) * 7.0
            return None, round(w, 2), round(w * 4.0, 2), round(w * 52.0, 2)
        if triggered == 'setting-hpw' and hpw is not None:
            w = float(hpw)
            return round(w / 7.0, 2), None, round(w * 4.0, 2), round(w * 52.0, 2)
        if triggered == 'setting-hpm' and hpm is not None:
            m = float(hpm)
            return round(m / 28.0, 2), round(m / 4.0, 2), None, round(m * 13.0, 2)
        if triggered == 'setting-hpy' and hpy is not None:
            y = float(hpy)
            return round(y / 364.0, 2), round(y / 52.0, 2), round(y / 13.0, 2), None
    except (TypeError, ValueError):
        pass
    return none


def actual_bracket_hours(entered, multiplier, stored=(None, None, None)):
    """The lower, best and upper actual times a reflection submits, in hours.

    ``entered`` is the three fields as typed, in the unit ``multiplier``
    converts to hours. A blank, zero or negative field is no data. The rest
    are put in order, so a bracket typed back to front still reads lower,
    best, upper. A field still showing its ``stored`` value, as the form
    rounds it, keeps the stored hours: a Submit with no changes used to
    rewrite every actual time with its rounded copy.
    """
    hours = []
    for value, before in zip(entered, stored):
        try:
            value = float(value)
        except (TypeError, ValueError):
            hours.append(None)
            continue
        if not math.isfinite(value) or value <= 0:
            hours.append(None)
        elif before is not None and round(before / multiplier, 2) == value:
            hours.append(before)
        else:
            hours.append(value * multiplier)
    ordered = iter(sorted(h for h in hours if h is not None))
    return tuple(None if h is None else next(ordered) for h in hours)


def capacity_hours(hpw, hpm, stored):
    """The hours per week and per month to save from the Settings fields.

    A field left blank, or one the browser can't read as a number, arrives as
    None. Both used to save as 40 or 160, so one blank field broke the
    four-week month every unit converts with. Now a month is four weeks: one
    readable field gives the other, and with neither the ``stored`` pair stays.
    """
    def positive(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) and value > 0 else None

    week, month = positive(hpw), positive(hpm)
    if week is None and month is None:
        return {'hours_per_week': stored['hours_per_week'],
                'hours_per_month': stored['hours_per_month']}
    if week is None:
        week = month / 4.0
    if month is None:
        month = week * 4.0
    return {'hours_per_week': week, 'hours_per_month': month}


def time_estimate_problem(time_o, time_m, time_p):
    """Why a lower / expected / upper bracket can't be saved, or None.

    The supported patterns mirror `expected_time_estimate` in models.py:
    Expected only, Lower + Upper, or all three, in order. The editor disables
    Save while this says something, and every save path checks it too: the
    unsaved-changes dialog's Save, and habit mode, went around the button.
    """
    o, m, p = float(time_o or 0), float(time_m or 0), float(time_p or 0)
    pattern = (o > 0, m > 0, p > 0)
    if pattern == (False, False, False):
        return "Enter at least an Expected estimate, or both Lower and Upper."
    problems = {
        (True, False, False): "Lower alone is not enough — also enter Upper, "
                              "or use Expected instead.",
        (False, False, True): "Upper alone is not enough — also enter Lower, "
                              "or use Expected instead.",
        (True, True, False): "Lower + Expected is not a valid pair — also "
                             "enter Upper, or drop Lower.",
        (False, True, True): "Expected + Upper is not a valid pair — also "
                             "enter Lower, or drop Upper.",
    }
    if pattern in problems:
        return problems[pattern]
    errors = []
    if pattern[0] and pattern[1] and o > m:
        errors.append("Lower must be ≤ Expected")
    if pattern[1] and pattern[2] and m > p:
        errors.append("Expected must be ≤ Upper")
    if pattern[0] and pattern[2] and o > p:
        errors.append("Lower must be ≤ Upper")
    return "; ".join(errors) or None


def compute_habit_time_omp(duration, duration_unit,
                           int_o, int_m, int_p, intensity_unit, days=None):
    """Convert a lower/expected/upper intensity bracket into the same bracket
    on total hours."""
    return (
        habit_to_hours(duration, duration_unit, int_o, intensity_unit, days),
        habit_to_hours(duration, duration_unit, int_m, intensity_unit, days),
        habit_to_hours(duration, duration_unit, int_p, intensity_unit, days),
    )


ALL_WEEKDAYS = [0, 1, 2, 3, 4, 5, 6]


def parse_habit_days(days):
    """Normalize stored/widget weekday data to a list of ints (0-6).

    Accepts a list/tuple of ints or a comma-separated string. None falls back
    to all seven days (the safe default for rows predating the column)."""
    if days is None:
        return list(ALL_WEEKDAYS)
    if isinstance(days, (list, tuple, set)):
        seq = days
    else:
        seq = str(days).split(',')
    out = []
    for x in seq:
        s = str(x).strip()
        if s.lstrip('-').isdigit():
            d = int(s)
            if 0 <= d <= 6:
                out.append(d)
    return out


def resolve_time_mode(n_type, time_mode_val, time_habit_mode_val):
    """Map node type + form widget values to the canonical time_mode string.

    Goal and Milestone are container types whose time is the sum of their
    children's; they must always use ``time_mode='inherited'``. The editor
    locks the toggle for these types, but this resolver is the canonical
    server-side enforcement — used by every save path (main editor,
    dormant-node creation, details-panel save) so that any future caller
    (convert-type, programmatic save, etc.) can't accidentally bypass the
    invariant. Otherwise, habit > inherited > manual.
    """
    if n_type in ('Goal', 'Milestone'):
        return 'inherited'
    if time_habit_mode_val and 'habit' in time_habit_mode_val:
        return 'habit'
    if time_mode_val and 'inherited' in time_mode_val:
        return 'inherited'
    return 'manual'


def resolve_value_mode(n_type, value_mode_val):
    """Map node type + the value-inherit toggle to the canonical value_mode.

    Milestones are transparent checkpoints whose own value/interest/effort
    must not enter scoring, so they always use ``value_mode='inherited'``.
    The editor locks the toggle for Milestones, but this resolver is the
    canonical server-side enforcement — used by every save path (main editor,
    details-panel add, dormant-node creation) so no caller can bypass the
    invariant. ``Node.__post_init__`` enforces the same rule as a final
    safety net.

    Unlike ``resolve_time_mode``, Goals are NOT forced here: a Goal carries
    its own value and interest (see docs/modeling.md), which feed the Goal
    ranking. Only Milestones are transparent. Otherwise the toggle wins.
    """
    if n_type == 'Milestone':
        return 'inherited'
    if value_mode_val and 'inherited' in value_mode_val:
        return 'inherited'
    return 'manual'


# One year of productivity is 13 months (about 52 weeks) by definition. It is
# built from hours_per_month, so a user-tuned monthly rate flows through to
# years consistently. A day is a seventh of a week, for the same reason.
HOURS_PER_YEAR_MULT = 13  # × hours_per_month
DAYS_PER_WEEK = 7


def hours_per_unit(unit, time_settings):
    """Hours in one `unit` ('hours', 'days', 'weeks', 'months' or 'years')."""
    if unit == 'days':
        return time_settings['hours_per_week'] / DAYS_PER_WEEK
    if unit == 'weeks':
        return time_settings['hours_per_week']
    if unit == 'months':
        return time_settings['hours_per_month']
    if unit == 'years':
        return HOURS_PER_YEAR_MULT * time_settings['hours_per_month']
    return 1.0


def unit_for(hours, time_settings):
    """The display unit for a duration: (hours in one unit, suffix).

    The largest of year, month, week and day that the duration reaches, else
    hours. format_hours picks its unit this way. A chart can call it once and
    draw every value in that one unit.
    """
    hw = time_settings['hours_per_week']
    hm = time_settings['hours_per_month']
    hy = HOURS_PER_YEAR_MULT * hm
    hd = hw / DAYS_PER_WEEK
    hours = hours or 0.0

    if hy > 0 and hours >= hy:
        return float(hy), "y"
    if hm > 0 and hours >= hm:
        return float(hm), "m"
    if hw > 0 and hours >= hw:
        return float(hw), "w"
    if hd > 0 and hours >= hd:
        return float(hd), "d"
    return 1.0, "h"


def format_hours(hours, time_settings, force_one_decimal=False):
    """Format worked hours in the largest unit they reach ("1w", "8h").

    By default, integer values display without a decimal. Pass
    `force_one_decimal=True` for tabular displays where decimal alignment
    matters: every value gets exactly one decimal place ("1.0w", "8.0h").
    """
    if hours is None or hours <= 0:
        return "0.0h" if force_one_decimal else "0h"
    # Callers such as the Analyze axis ticks pass ints, and round(int, 1)
    # returns an int; as a float it can say whether it is whole.
    hours = float(hours)
    size, suffix = unit_for(hours, time_settings)
    amount = round(hours / size, 1)
    if amount.is_integer() and not force_one_decimal:
        amount = int(amount)
    return f"{amount}{suffix}"


def friendly_unit(hours, time_settings):
    """Hours in the largest unit they reach, as (amount, unit name), such as
    (2.0, 'weeks')."""
    if hours is None or hours <= 0:
        return (0, 'hours')
    hw = time_settings['hours_per_week']
    hm = time_settings['hours_per_month']
    hy = HOURS_PER_YEAR_MULT * hm
    hd = hw / DAYS_PER_WEEK

    if hy > 0 and hours >= hy:
        return (round(hours / hy, 2), 'years')
    if hm > 0 and hours >= hm:
        return (round(hours / hm, 2), 'months')
    if hw > 0 and hours >= hw:
        return (round(hours / hw, 2), 'weeks')
    if hd > 0 and hours >= hd:
        return (round(hours / hd, 2), 'days')
    return (round(hours, 2), 'hours')
