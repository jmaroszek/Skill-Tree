"""Communities follow the filters the canvas does.

Community detection read only awake nodes, so with Show Dormant on, the
sleeping nodes the canvas drew belonged to no cluster, island or orphan
selection. Orphans were judged within the filtered graph, so hiding Done nodes
made orphans of the nodes linked only to them.
"""
import pytest

from skilltree.store.graph.manager import GraphManager
from skilltree.store.events import EventManager
from skilltree.domain.models import Event, Node, EDGE_NEEDS_SOFT, STATUS_DONE


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5, time_o=1.0,
                  time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status="Open", context="Mind")
    fields.update(overrides)
    return Node(**fields)


@pytest.fixture
def manager():
    manager = GraphManager()
    manager.add_node(_node("Reading"))
    manager.add_node(_node("Notes", status=STATUS_DONE))
    manager.add_node(_node("Alone"))
    manager.add_edge("Notes", "Reading", EDGE_NEEDS_SOFT)
    events = EventManager()
    events.add_event(Event(name="Spring"))
    events.create_dormant_node(_node("Seed"), "Spring")
    manager.add_edge("Seed", "Alone", EDGE_NEEDS_SOFT)
    return manager


def test_show_dormant_keeps_sleeping_nodes_in_their_community(manager):
    filters = {"show_dormant": True}
    communities = manager.detect_communities("components", filters)

    assert {"Seed", "Alone"} in communities


def test_hidden_dormant_nodes_stay_out(manager):
    filters = {"hide_done": False}
    names = set().union(*manager.detect_communities("components", filters))

    assert "Seed" not in names


def test_hiding_done_nodes_makes_no_orphans(manager):
    orphans = manager.detect_communities("orphans", {"hide_done": True})

    assert orphans == []
