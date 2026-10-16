"""The node context menu: the data attributes a row or card carries to open it."""
import json
from dash import html


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


def menu_item(label, item_id, danger=False, icon=None):
    """One clickable row. ``danger`` marks a destructive command.

    ``icon`` is a Bootstrap Icon name without the ``bi-`` prefix.  Menu
    commands stay labelled; the icon simply makes their intent scannable.
    """
    class_name = "ctx-menu-item ctx-menu-item-danger" if danger else "ctx-menu-item"
    children = label if icon is None else [
        html.I(className=f"bi bi-{icon} ctx-menu-icon", **{"aria-hidden": "true"}),
        html.Span(label, className="ctx-menu-label"),
    ]
    return html.Div(children, id=item_id, className=class_name,
                    role="menuitem", tabIndex=-1)


def menu_divider(divider_id=None):
    """A separator between groups. Give it an id when a script hides it."""
    if divider_id:
        return html.Hr(id=divider_id, style={"margin": "2px"})
    return html.Hr(style={"margin": "2px"})


def menu_heading(text):
    """A muted, unclickable caption that names what a menu does."""
    return html.Div(text, className="ctx-menu-heading")


def floating_menu(menu_id, children):
    return html.Div(children, id=menu_id, className="ctx-menu",
                    role="menu",
                    style={"display": "none"})


def priority_items(prefix):
    """Priority 1–3 and Clear Priority, ids ``<prefix>-1`` … ``<prefix>-clear``.

    Shared by the node menu's Set Priority submenu and the goal rank popover.
    """
    return [
        menu_item("Priority 1", f"{prefix}-1", icon="1-circle"),
        menu_item("Priority 2", f"{prefix}-2", icon="2-circle"),
        menu_item("Priority 3", f"{prefix}-3", icon="3-circle"),
        menu_divider(),
        menu_item("Clear Priority", f"{prefix}-clear", icon="eraser"),
    ]
