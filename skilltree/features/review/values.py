"""What the time calibration and reflection modal shows: its title and reference
line, the first unit, the prefilled actuals, and the queue a review walks."""
from skilltree.domain.models import STATUS_DONE
from skilltree.store import settings
from skilltree.ui.components.duration import format_time_friendly
from skilltree.ui.components.duration import hours_to_friendly_unit


# The Reflection notes box's prompt for any node that holds work.
PROJECT_NOTES_PLACEHOLDER = "Anything worth remembering about this project?"


def reflects_in_notes_only(node):
    """Whether the Reflection modal asks `node` for notes alone.

    A Milestone holds no work of its own, so it has no actual time or
    actual ratings to compare with an estimate. What's worth keeping is what
    got you there, or how a test went.
    """
    return node is not None and node.type == 'Milestone'


def calibration_sections(node):
    """Returns (ratings style, time style, notes placeholder) for `node`.

    The ratings style carries the node's estimates as --est-value/-interest/
    -difficulty, and theme.css draws each slider's "estimated" tick from them;
    a rating the node doesn't carry (an inherited container) gets no tick. A
    Milestone reflects in notes alone, so both sections hide for it and the
    notes ask about the result rather than a project. Every callback that
    opens the modal on a node sends these with it, so the form never shows
    the wrong sections first.
    """
    if node is None:
        return {}, {}, PROJECT_NOTES_PLACEHOLDER
    if reflects_in_notes_only(node):
        return ({"display": "none"}, {"display": "none"},
                "What got you there? Anything worth remembering?")
    return {f'--est-{name}': str(rating)
            for name, rating in (('value', node.value),
                                 ('interest', node.interest),
                                 ('difficulty', node.difficulty))
            if rating}, {}, PROJECT_NOTES_PLACEHOLDER


def calibration_modal_text(node):
    """Returns (title, prompt) for the time-calibration modal: the node name
    goes in the modal title, the prompt recalls its original estimate so the
    user can calibrate actual against estimated time."""
    est = getattr(node, 'time', 0) or 0
    if est > 0:
        prompt = (f"You estimated this project would take "
                  f"{format_time_friendly(est)}. "
                  f"How long did it actually take?")
    else:
        prompt = "How long did it actually take?"
    return node.name, prompt


def calibration_review_queue(manager):
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


def calibration_unit_for(hours):
    """The Unit-dropdown value matching the friendly formatter's choice for
    `hours` (e.g. a ~3.5w estimate → 'weeks'). Years cap to 'months' — the
    modal dropdown offers hours / days / weeks / months."""
    _, unit = hours_to_friendly_unit(hours or 0)
    return 'months' if unit == 'years' else unit


def calibration_prepop(node):
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
        return (None, None, None, calibration_unit_for(0), 5, 5, 5, '')

    saved = (node.actual_time_lower, node.actual_time_point, node.actual_time_upper)
    anchor = next((hours for hours in (saved[1], saved[0], saved[2])
                   if hours is not None), None)
    time_unit = calibration_unit_for(node.time if anchor is None else anchor)
    multiplier = settings.time_multiplier(time_unit)
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
