"""The managers the app uses, one of each, wired together.

Construction does not open the database.
"""
from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager


class AppServices:
    """The one GraphManager and the one EventManager.

    The event manager works on the nodes through the graph manager. The graph
    manager tells it when a node turns Done and when deleting a node narrows
    an event's trigger set, since either can fire an event.
    """

    def __init__(self):
        self.graph = GraphManager()
        self.events = EventManager(self.graph)
        self.graph.on_node_done = self.events.auto_trigger_by_node_completion
        self.graph.on_trigger_set_narrowed = self.events.fire_if_met_after_commit
