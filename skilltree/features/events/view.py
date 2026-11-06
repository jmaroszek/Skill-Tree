"""What the event panel shows around an event's fields, sent with them.

Opening an event used to send only the fields. Which trigger section shows, the
trigger hint, the Trigger and Add buttons, and a fired event's locked trigger
fields came a pass later, from callbacks of their own. So each event drew in two
paints, and for a moment a fired event offered trigger fields to edit. The
panel's fill now sends all of it, and those callbacks answer the user's own
changes afterwards. Both call the rules here, so they can't disagree.
"""
from dash import Output

from skilltree.features.events.layout import trigger_mode_options, trigger_type_options

BUTTON_SHOWN = {"display": "flex", "alignItems": "center"}
_HIDDEN = {"display": "none"}

# The outputs event_view fills, in its order. Each also has a callback that
# keeps it in step with the user's changes, so they all allow duplicates.
VIEW_OUTPUTS = (
    ("event-date-section", "style"),
    ("event-node-section", "style"),
    ("event-trigger-mode-hint", "children"),
    ("event-trigger-btn-wrapper", "style"),
    ("event-trigger-type", "options"),
    ("event-trigger-date", "disabled"),
    ("event-trigger-node", "disabled"),
    ("event-trigger-mode", "options"),
    ("dormant-add-btn-wrapper", "style"),
)

VIEW_FILL = [Output(component, prop, allow_duplicate=True) for component, prop in VIEW_OUTPUTS]


def normalize_trigger_nodes(value):
    """Coerces a trigger-node dropdown value into a de-duplicated list.

    A multi Dropdown yields a list, but the same component can hand back a
    bare string (single leftover selection) or None (cleared), so all three
    shapes are flattened here rather than at each call site.
    """
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    out = []
    for name in value:
        if name and name not in out:
            out.append(name)
    return out


def trigger_section_styles(trigger_type):
    """The date and node-completion sections, for a trigger type."""
    return ({"display": "block"} if trigger_type == "date" else _HIDDEN,
            {"display": "block"} if trigger_type == "node" else _HIDDEN)


def trigger_mode_hint(trigger_mode, trigger_nodes):
    """Help text under a node-completion trigger, describing the live selection.

    At one node the any/all distinction is meaningless, so the text collapses
    to the plain single-node wording rather than naming a mode the user can't
    meaningfully act on.
    """
    names = normalize_trigger_nodes(trigger_nodes)
    if not names:
        return "Auto-triggers when the selected node is marked complete."
    if len(names) == 1:
        return f"Auto-triggers when {names[0]} is marked complete."
    if trigger_mode == "all":
        return f"Auto-triggers once all {len(names)} selected nodes are marked complete."
    return "Auto-triggers as soon as any one of the selected nodes is marked complete."


def event_state(event):
    """What a saved event's panel offers: the Trigger button, the trigger type's
    options, whether the date and nodes are locked, and the mode's options.

    Trigger is for an event that hasn't fired, and a fired event's trigger
    fields have nothing left to do. Its name and description stay editable, to
    correct or annotate the record. ``event`` is None for a new event."""
    fired = event is not None and event.status == "Triggered"
    return (BUTTON_SHOWN if event is not None and not fired else _HIDDEN,
            trigger_type_options(disabled=fired), fired, fired,
            trigger_mode_options(disabled=fired))


def add_dormant_style(event):
    """Nodes join a saved, untriggered event. A Triggered event will not fire
    again, so it stops accepting nodes; an unsaved one has no name for them to
    join yet (its table says to save first)."""
    if event is None or event.status == "Triggered":
        return _HIDDEN
    return {}


def event_view(event, trigger_type, trigger_nodes, trigger_mode):
    """VIEW_OUTPUTS' values for a panel showing ``event`` with these trigger
    fields. ``event`` is None for a new event or a closed panel."""
    return (*trigger_section_styles(trigger_type),
            trigger_mode_hint(trigger_mode, trigger_nodes),
            *event_state(event),
            add_dormant_style(event))
