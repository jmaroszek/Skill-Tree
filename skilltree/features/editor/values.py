"""How the node editor shows a node's time estimates."""
from math import floor, log10

from skilltree.store import settings
from skilltree.ui.components.duration import hours_to_friendly_unit


def estimate_in_unit(time_o, time_m, time_p, unit):
    """Stored hour values as the editor shows them in ``unit``, at today's
    rates: rounded to two decimals, and whole numbers without them."""
    multiplier = settings.time_multiplier(unit)
    def _convert(h):
        v = round((h or 0) / multiplier, 2)
        if v == int(v):
            v = int(v)
        return v
    return _convert(time_o), _convert(time_m), _convert(time_p)


def estimate_rates():
    """The Settings an estimate's days and weeks are read at. A baseline keeps
    what it was shown at, which says when they have changed since."""
    time_settings = settings.TIME_SETTINGS.get()
    return {key: time_settings[key] for key in ('hours_per_week', 'hours_per_month')}


def reexpressed_estimate(value):
    """An estimate field's number after a change of unit: two decimals, or
    four significant digits when it is smaller than that can hold, and whole
    numbers without them.

    Two decimals alone turned 100 hours into 0.1 years, which is 104 hours on
    the way back, and a few hours into 0 years.
    """
    if not value:
        return 0
    result = round(value, max(2, 3 - floor(log10(abs(value)))))
    return int(result) if result == int(result) else result


def friendly_time_estimates(time_o, time_m, time_p):
    """Convert stored hour values for display in the node editor.

    Uses weeks as the maximum unit — never months or years — so the editor
    always shows values in hours, days or weeks regardless of magnitude. Returns
    (o, m, p, unit_string).
    """
    max_hours = max(time_o or 0, time_m or 0, time_p or 0)
    _, unit = hours_to_friendly_unit(max_hours)
    # Cap at weeks: months/years are too coarse for direct editing
    if unit in ('months', 'years'):
        unit = 'weeks'
    return (*estimate_in_unit(time_o, time_m, time_p, unit), unit)
