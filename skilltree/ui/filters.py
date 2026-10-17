"""The filters every canvas and list shares: reading the sidebar's controls,
and summarizing them."""
import logging

from dash import Input, State

from skilltree.store import settings

logger = logging.getLogger(__name__)

# The ends of every rating scale.
RATING_MIN, RATING_MAX = 1, 10


def build_filters(f_context, f_subcontext, f_done, f_value=None, f_interest=None,
                  f_time=None, f_difficulty=None, f_node_types=None,
                  f_time_unit="hours", f_show_dormant=None, f_time_min=None,
                  f_search=None):
    """Build a filter dict from sidebar filter component values for use with GraphManager.filter_nodes().

    `f_search` is the Search query as the filter-search-query store holds it:
    None, or ``{"text": ..., "descriptions": bool}``.
    """
    filters = {}

    text = (f_search or {}).get('text')
    if isinstance(text, str) and text.strip():
        filters['search'] = text.strip()
        if f_search.get('descriptions'):
            filters['search_descriptions'] = True

    # Show-dormant gate: when the sidebar's "Show Dormant" switch is on, this
    # flag flows into filter_nodes which then keeps dormant rows in the
    # filtered set. Default off matches the original "dormant nodes are
    # hidden from the main canvas" behavior.
    if f_show_dormant and "show_dormant" in f_show_dormant:
        filters['show_dormant'] = True

    contexts = []
    if f_context and f_context != "All":
        if isinstance(f_context, list):
            contexts = f_context
        elif f_context != "None":
            contexts = [f_context]
        else:
            contexts = [None]

    # Subcontext dropdown values are encoded as "ctx\x1fsub" composites by
    # update_filter_subcontexts so the (value -> context) mapping is explicit.
    # ASCII unit-separator (\x1f) is used instead of "::" because Dash mangles
    # values containing "::" during layout serialization. Plain strings
    # (legacy state / test fixtures that haven't adopted composites) are
    # accepted as context-agnostic subcontext names.
    ctx_to_subs: dict = {}
    plain_subs: list = []
    if f_subcontext and f_subcontext != "All":
        values = f_subcontext if isinstance(f_subcontext, list) else [f_subcontext]
        for raw in values:
            if not raw or not isinstance(raw, str):
                continue
            # Only strip standard ASCII whitespace — NOT all `str.isspace()`
            # chars, because the composite separator \x1f is whitespace by
            # Python's definition and would silently drop the "None" sentinel
            # (`"Body\x1f"` → `"Body"`).
            v = raw.strip(" \t\n\r\v\f")
            if not v:
                continue
            if "\x1f" in v:
                c, s = v.split("\x1f", 1)
                ctx_to_subs.setdefault(c, []).append(s if s else None)
            elif "::" in v:
                # Legacy persisted state from before the separator change.
                c, s = v.split("::", 1)
                ctx_to_subs.setdefault(c, []).append(s if s else None)
            else:
                plain_subs.append(v)

    if contexts and ctx_to_subs:
        # Selective union: for each selected context, use the subcontexts the user
        # explicitly tagged to that context. Contexts with no selection fall back
        # to "include all nodes of that context" (per UX introduced in 58b4866:
        # "show all Mind, but only specific STEM").
        pairs = [(c, ctx_to_subs.get(c) or None) for c in contexts]
        filters['context_subcontext_union'] = pairs
    elif contexts and plain_subs:
        # Legacy path: plain subcontext names with contexts selected — apply the
        # bare list against every selected context (pre-composite behavior).
        filters['context_subcontext_union'] = [(c, plain_subs) for c in contexts]
    elif contexts:
        filters['context'] = contexts
    elif ctx_to_subs or plain_subs:
        flat = [s for subs in ctx_to_subs.values() for s in subs] + plain_subs
        filters['subcontext'] = flat
    if f_node_types:
        if isinstance(f_node_types, list):
            if f_node_types:
                filters['node_types'] = f_node_types
        elif f_node_types != "All":
            filters['node_types'] = [f_node_types]
    # "Show Done" switch: ON ("show_done" in f_done) = no filter; OFF
    # (empty list, or any legacy value) = hide done. Default is hidden.
    if not (f_done and "show_done" in f_done):
        filters['hide_done'] = True
    for key, pair in (('value', f_value), ('interest', f_interest),
                      ('difficulty', f_difficulty)):
        low, high = rating_range(pair)
        if low > RATING_MIN:
            filters[f'min_{key}'] = low
        if high < RATING_MAX:
            filters[f'max_{key}'] = high
    low, high = time_range(f_time_min, f_time)
    if low is not None or high is not None:
        try:
            multiplier = settings.time_multiplier(f_time_unit or "hours")
            # Rounded as Node.time is, so a node sitting on a bound in another
            # unit stays in.
            if low is not None:
                filters['min_time'] = round(low * multiplier, 2)
            if high is not None:
                filters['max_time'] = round(high * multiplier, 2)
        except (ValueError, TypeError) as e:
            logger.warning("Invalid time filter (%r-%r, unit=%r): %s",
                           f_time_min, f_time, f_time_unit, e)
    return filters


# The filters sidebar's controls, for a callback that applies all of them. It
# takes FILTER_INPUTS (or FILTER_STATES) as one argument, receives a dict of
# their values, and filters_from() turns that into build_filters' dict. Listed
# once, so every view filters alike: Details listed the controls one by one
# and had lost the Time filter's unit. A @prerendered callback can't take a
# group, since prerender calls it with a flat argument list.
SIDEBAR_FILTERS = {
    'context': ('filter-context', 'value'),
    'subcontext': ('filter-subcontext', 'value'),
    'done': ('filter-done', 'value'),
    'value': ('filter-value', 'value'),
    'interest': ('filter-interest', 'value'),
    'time_min': ('filter-time-min', 'value'),
    'time': ('filter-time', 'value'),
    'time_unit': ('filter-time-unit', 'value'),
    'difficulty': ('filter-difficulty', 'value'),
    'types': ('filter-node-type', 'value'),
    'dormant': ('filter-dormant', 'value'),
    'search': ('filter-search-query', 'data'),
}


FILTER_INPUTS = {key: Input(*prop) for key, prop in SIDEBAR_FILTERS.items()}


FILTER_STATES = {key: State(*prop) for key, prop in SIDEBAR_FILTERS.items()}


def filters_from(values):
    """build_filters' dict from the values of FILTER_INPUTS or FILTER_STATES."""
    values = values or {}
    return build_filters(
        values.get('context'), values.get('subcontext'), values.get('done'),
        values.get('value'), values.get('interest'), values.get('time'),
        values.get('difficulty'), values.get('types'),
        f_time_unit=values.get('time_unit'), f_show_dormant=values.get('dormant'),
        f_time_min=values.get('time_min'), f_search=values.get('search'))


def time_range(f_time_min, f_time):
    """The Time fields as ``(low, high)`` floats in the field's own unit.

    An empty, zero or unreadable end is None, meaning no bound. A minimum above
    the maximum matches nothing, so it filters nothing instead: both come back
    None, and the sidebar outlines the two fields.
    """
    def read(raw):
        try:
            number = float(raw)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    low, high = read(f_time_min), read(f_time)
    if low is not None and high is not None and low > high:
        return None, None
    return low, high


def rating_range(pair):
    """A rating slider's ``[low, high]`` value as two ints, clamped to 1-10.

    Anything that is not a usable pair (None before the page loads, a stray
    scalar) reads as the full range, which filters nothing.
    """
    try:
        low, high = (int(v) for v in pair)
    except (TypeError, ValueError):
        return RATING_MIN, RATING_MAX
    return max(RATING_MIN, min(low, high)), min(RATING_MAX, max(low, high))


def is_filters_active(*, node_type=None, context=None, subcontext=None,
                      community=None, community_method=None,
                      value=None, interest=None, difficulty=None,
                      time=None, time_min=None, search=None):
    """Returns True if any sidebar filter is hiding nodes from the user.

    Defaults match the "Clear Filters" reset state in
    callbacks.clear_filters. Pass None for filters that don't affect the
    calling canvas (e.g. the Details canvas ignores Community)
    so the indicator only fires on filters that actually narrow what
    the user sees.

    Show Done and Show Dormant are deliberately absent. Both default to off
    and can only be switched *on*, which reveals nodes rather than hiding
    them — a canvas showing more than the baseline needs no warning, and the
    extra nodes are visible on their face anyway. The indicator exists for the
    narrowing you cannot see.
    """
    if (search or {}).get('text', '').strip():
        return True
    if node_type:
        return True
    if context:
        return True
    if subcontext:
        return True
    if community and community != "All":
        return True
    if community_method == "orphans":
        return True
    for pair in (value, interest, difficulty):
        if pair is not None and rating_range(pair) != (RATING_MIN, RATING_MAX):
            return True
    if time_range(time_min, time) != (None, None):
        return True
    return False


def filter_summary(*, node_type=None, context=None, subcontext=None,
                   community=None, community_method=None,
                   value=None, interest=None, difficulty=None,
                   time=None, time_min=None, time_unit=None, search=None):
    """The active filters as ``(short, full)`` labels, for the "Filtered" chip.

    Takes the same arguments as `is_filters_active`, plus the Time unit, and
    follows the same rule: a filter a canvas ignores is passed as None and
    never appears. Empty exactly when `is_filters_active` is False. Contexts
    come first, since they are the main axis; a list of three or more names
    shortens to a count, and the full names stay in `full` for the tooltip.
    """
    def group(items, noun):
        full = ", ".join(items)
        return (full if len(items) <= 2 else f"{len(items)} {noun}s", full)

    labels = []
    if context:
        labels.append(group(context, "context"))
    if subcontext:
        count = f"{len(subcontext)} subcontext{'' if len(subcontext) == 1 else 's'}"
        labels.append((count, count))
    if node_type:
        labels.append(group(node_type, "type"))
    for name, pair in (("Value", value), ("Interest", interest),
                       ("Effort", difficulty)):
        if pair is not None and rating_range(pair) != (RATING_MIN, RATING_MAX):
            low, high = rating_range(pair)
            labels.append((f"{name} {low}–{high}",) * 2)
    low, high = time_range(time_min, time)
    if (low, high) != (None, None):
        unit = time_unit or ''
        fmt = lambda n: f"{n:g}"  # noqa: E731
        if low is not None and high is not None:
            text = f"Time {fmt(low)}–{fmt(high)} {unit}"
        elif low is not None:
            text = f"Time ≥ {fmt(low)} {unit}"
        else:
            text = f"Time ≤ {fmt(high)} {unit}"
        labels.append((text.strip(),) * 2)
    query = ((search or {}).get('text') or '').strip()
    if query:
        labels.append((f'"{query}"',) * 2)
    if community and community != "All":
        labels.append((f"Community: {community}",) * 2)
    if community_method == "orphans":
        labels.append(("Orphans", "Orphans"))
    return labels


def filter_chip_state(labels, shown=3):
    """``(text, tooltip, hidden)`` for a filter chip from `filter_summary`."""
    if not labels:
        return "", "", True
    text = " · ".join(short for short, _ in labels[:shown])
    if len(labels) > shown:
        text += f" +{len(labels) - shown}"
    return text, "\n".join(full for _, full in labels), False


def filter_chip_updates(chip, current):
    """`filter_chip_state` as callback outputs, leaving what is already shown.

    ``current`` is the chip's present ``(text, title, hidden)``. A chip that
    already reads right is not rewritten, so a filter change that leaves the
    summary alone adds no round trip to the page.
    """
    from dash import no_update
    old = (current[0] or "", current[1] or "", bool(current[2]))
    return tuple(no_update if new == was else new for new, was in zip(chip, old))
