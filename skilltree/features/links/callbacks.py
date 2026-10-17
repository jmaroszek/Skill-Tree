"""The links feature's callbacks: building a bridge between two nodes, and
the link menu that adds or changes one relationship."""
from skilltree.features.links.bridge import register_bridge_callbacks
from skilltree.features.links.menu import register_link_menu_callbacks


def register_links_callbacks(app, services):
    register_bridge_callbacks(app, services)
    register_link_menu_callbacks(app, services)
