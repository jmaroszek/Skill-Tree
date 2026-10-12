"""Shared editor and calibration values, independent of callback registration."""
from config import ConfigManager
from models import STATUS_DONE

def _calibration_modal_text(node):
    """Returns (title, prompt) for the time-calibration modal: the node name
    goes in the modal title, the prompt recalls its original estimate so the
    user can calibrate actual against estimated time."""
    est = getattr(node, 'time', 0) or 0
    if est > 0:
        prompt = (f"You estimated this project would take "
                  f"{ConfigManager.format_time_friendly(est)}. "
                  f"How long did it actually take?")
    else:
        prompt = "How long did it actually take?"
    return node.name, prompt


def _calibration_review_queue(manager):
    """Names of completed nodes eligible for the calibration review cycle:
    status Done, an own time estimate (> 0, so inherited-time Goals are
    excluded), no actual time captured yet, and not permanently dismissed.
    Returned in stable name order."""
    queue = []
    for n in manager.get_all_nodes():
        if n.status != STATUS_DONE:
            continue
        if (n.actual_time_lower is not None or n.actual_time_point is not None
                or n.actual_time_upper is not None):
            continue
        if n.calibration_dismissed:
            continue
        if n.time <= 0:
            continue
        queue.append(n.name)
    return sorted(queue)


def _calibration_unit_for(hours):
    """The Unit-dropdown value matching the friendly formatter's choice for
    `hours` (e.g. a ~3.5w estimate → 'weeks'). Years cap to 'months' — the
    modal dropdown offers hours / days / weeks / months."""
    _, unit = ConfigManager.hours_to_friendly_unit(hours or 0)
    return 'months' if unit == 'years' else unit


def _calibration_prepop(node):
    """Pre-population values for the focused-review modal when it opens for
    `node`. Returns (time_lower, time_point, time_upper, time_unit, val,
    interest, diff, notes) — all in the modal's display semantics (time values are
    in `time_unit`, NOT canonical hours; Submit converts on the way to the
    DB).

    The modal starts from what the user already answered. A reflection with
    ratings and no time keeps its node in the review queue, and a node
    reopened and finished again keeps the actual times of its first finish.
    Starting from the estimates, or from blank times, Submit wrote over them.

    With no saved times, the actual-time fields start blank. Lifecycle dates
    measure how long a node remained selected, not how many hours the user
    worked on it; turning that span into an hours estimate creates a
    misleading anchor. The unit still follows the original estimate's scale
    as an entry convenience. Saved times show in the unit that suits them.

    A V/I/E slider with no saved rating defaults to the node's own estimate,
    so the user's starting point is "same as I thought" and they only have
    to move sliders that actually diverged.
    """
    if node is None:
        return (None, None, None, _calibration_unit_for(0), 5, 5, 5, '')

    saved = (node.actual_time_lower, node.actual_time_point, node.actual_time_upper)
    anchor = next((hours for hours in (saved[1], saved[0], saved[2])
                   if hours is not None), None)
    time_unit = _calibration_unit_for(node.time if anchor is None else anchor)
    multiplier = ConfigManager.get_time_multiplier(time_unit)
    time_lower, time_point, time_upper = (
        None if hours is None or not multiplier else round(hours / multiplier, 2)
        for hours in saved)

    def rating(answer, estimate):
        # Sliders need a number even when the node carries no rating (e.g.
        # inherited-mode containers, whose local rating is 0 or None).
        return answer if answer is not None else (estimate or 5)

    return (time_lower, time_point, time_upper, time_unit,
            rating(node.reflect_value, node.value),
            rating(node.reflect_interest, node.interest),
            rating(node.reflect_difficulty, node.difficulty),
            node.reflect_notes or '')


def _friendly_time_estimates(time_o, time_m, time_p):
    """Convert stored hour values for display in the node editor.

    Uses weeks as the maximum unit — never months or years — so the editor
    always shows values in hours, days or weeks regardless of magnitude. Returns
    (o, m, p, unit_string).
    """
    max_hours = max(time_o or 0, time_m or 0, time_p or 0)
    _, unit = ConfigManager.hours_to_friendly_unit(max_hours)
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
