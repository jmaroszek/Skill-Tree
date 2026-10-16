"""Cytoscape elements for nodes and edges, the same on every canvas.

The Nodes, Details and Events canvases each choose which nodes to show, then
build every element here. The hover tooltip, context menu, stylesheet and Now
pulse read these fields on whichever canvas raised them, so a node has to look
and describe itself the same way everywhere.
"""
from dataclasses import dataclass

from skilltree.domain.models import STATUS_BLOCKED, STATUS_DONE, STATUS_OPEN
from skilltree.store.settings import DEFAULT_NODE_COLORS, ConfigManager
from skilltree.ui import payloads as bridge_payloads


@dataclass(frozen=True)
class CanvasNodeStyles:
    """The lookups a canvas reads once per render to paint its nodes."""
    colors: dict
    shapes: dict
    trigger_names: frozenset


def canvas_node_styles(events):
    """Read every lookup ``build_node_element`` paints from.

    They travel as one bundle so no canvas can render without one of them.
    """
    return CanvasNodeStyles(
        colors=ConfigManager.get_node_colors(),
        shapes=ConfigManager.get_node_shapes(),
        trigger_names=frozenset(events.get_trigger_node_names()),
    )


def node_fill_color(node, colors):
    """Done or Blocked first, then the node's type color.

    Now is deliberately absent: it is drawn as the pulsing amber border
    (the `.now` class plus now_pulse.js), so the fill stays free to carry
    status and type.
    """
    if node.status == STATUS_DONE:
        return colors.get(STATUS_DONE, DEFAULT_NODE_COLORS[STATUS_DONE])
    if node.status == STATUS_BLOCKED:
        return colors.get(STATUS_BLOCKED, DEFAULT_NODE_COLORS[STATUS_BLOCKED])
    return colors.get(node.type, colors.get(STATUS_OPEN,
                                            DEFAULT_NODE_COLORS[STATUS_OPEN]))


# The node fields a canvas element carries, and who reads them. Every canvas
# builds its elements here, so they can't drift apart, which is what went
# wrong when each canvas picked its own fields. They used to carry every Node
# field instead, about 45, most of which nothing read. The largest,
# description, was about a seventh of the Nodes payload.
#   - The hover tooltip (callbacks.display_hover_data): type, context,
#     subcontext, value, interest, difficulty, time, time_mode, value_mode.
#   - The node context menu (assets/context_menu.js): type, status, now,
#     dormant, resource_links.
#   - Tap handlers read only the id; the editor re-reads the node itself.
# The stylesheet reads id, label, color, shape and now_color, which are set
# below. Add a field here when something new reads it from element data.
CANVAS_NODE_FIELDS = (
    'type', 'status', 'context', 'subcontext',
    'value', 'interest', 'difficulty',
    'time', 'time_mode', 'value_mode',
    'now', 'dormant', 'resource_links',
)


def build_node_element(node, styles, *, selected=None, dormant=None, extra_data=None):
    """Build a Cytoscape node element carrying CANVAS_NODE_FIELDS.

    A canvas passes only what is its own:
      selected    Cytoscape's selection state. Omitted when None, so the
                  render leaves the user's clicks alone.
      dormant     Replaces the node's own dormant flag, in the data and in
                  the class. Events marks its attached nodes this way.
      extra_data  Keys only one canvas reads, such as Details' view root.
    """
    data = {
        'id': node.name,
        'label': node.name,
        'color': node_fill_color(node, styles.colors),
        'shape': styles.shapes.get(node.type, 'rectangle'),
    }
    for field in CANVAS_NODE_FIELDS:
        data[field] = node.time if field == 'time' else getattr(node, field)
    if dormant is None:
        dormant = bool(node.dormant)
    else:
        data['dormant'] = 1 if dormant else 0
    if extra_data:
        data.update(extra_data)

    classes = []
    if node.name in styles.trigger_names:
        classes.append('trigger')
    if dormant:
        classes.append('dormant')
    if node.now:
        classes.append('now')
        data['now_color'] = styles.colors.get('Now', '#ffd000')  # literal: Cytoscape element data

    element = {'data': data}
    if selected is not None:
        element['selected'] = bool(selected)
    # Always emit `classes` (possibly empty) so Cytoscape's element diff
    # actually clears the class when a node loses it — omitting the key
    # leaves the prior value in place and a node that was just cleared
    # of Now would keep its pulse.
    element['classes'] = ' '.join(classes)
    return element


def build_edge_element(edge):
    """Build a Cytoscape edge element from a ``GraphManager.get_edges()`` row."""
    source, target, edge_type = edge['source'], edge['target'], edge['type']
    return {
        'data': {
            # Joined with underscores, "A_B" to "C" and "A" to "B_C" shared an
            # id, and Cytoscape drew only one of the two edges.
            'id': bridge_payloads.edge_key(source, target, edge_type),
            'source': source,
            'target': target,
            'type': edge_type,
        },
        # Nothing acts on a selected link. A click that selected one cleared
        # the node selection and left no outline to show for it.
        'selectable': False,
    }
