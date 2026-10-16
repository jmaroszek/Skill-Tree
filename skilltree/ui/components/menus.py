"""The node context menu: the data attributes a row or card carries to open it."""
import json


def node_menu_attributes(node):
    """Data attributes that open the node context menu on a row or card.

    context_menu.js reads them on right-click as it reads a canvas node's data,
    so a node listed on Next or in the Goals sidebar gets the same menu it gets
    on a canvas: the same toggle labels, links and Goal-only items.
    """
    return {
        "data-node-menu": node.name,
        "data-type": node.type,
        "data-status": node.status,
        "data-now": str(int(bool(node.now))),
        "data-resource-links": json.dumps(node.resource_links),
    }
