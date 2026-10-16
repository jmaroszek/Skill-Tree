"""How the node editor shows a node's time estimates."""
from skilltree.store.settings import ConfigManager
from skilltree.ui.components.duration import hours_to_friendly_unit


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
    multiplier = ConfigManager.get_time_multiplier(unit)
    def _convert(h):
        v = round((h or 0) / multiplier, 2)
        if v == int(v):
            v = int(v)
        return v
    return _convert(time_o), _convert(time_m), _convert(time_p), unit
