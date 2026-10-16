"""A type change re-derives the node's own Blocked or Open.

The cascade re-derives a node's dependents on every save, not the node. A
Blocked Learn turned into a Goal stayed Blocked, a state Goals don't have, and
a Goal turned into an Action stayed Open with unfinished prerequisites. Both
lasted until the next launch repaired them.
"""
import pytest

from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import Node, EDGE_NEEDS_HARD


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5, time_o=1.0,
                  time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status="Open", context="Mind")
    fields.update(overrides)
    return Node(**fields)


@pytest.fixture
def manager():
    manager = GraphManager()
    manager.add_node(_node("Basics"))
    manager.add_node(_node("Craft", type="Goal", time_mode="inherited"))
    manager.add_edge("Basics", "Craft", EDGE_NEEDS_HARD)
    return manager


def _retype(manager, name, to_type, **changes):
    node = manager.get_node(name)
    node.type = to_type
    for key, value in changes.items():
        setattr(node, key, value)
    manager.update_node(node)
    return manager.get_node(name).status


def test_a_goal_turned_into_an_action_is_blocked(manager):
    assert manager.get_node("Craft").status == "Open"
    assert _retype(manager, "Craft", "Action", time_mode="manual") == "Blocked"


def test_a_blocked_node_turned_into_a_goal_is_open(manager):
    _retype(manager, "Craft", "Action", time_mode="manual")
    assert _retype(manager, "Craft", "Goal", time_mode="inherited") == "Open"


def test_a_stale_blocked_status_is_cleared_on_save(manager):
    node = manager.get_node("Basics")
    node.status = "Blocked"
    manager.update_node(node)

    assert manager.get_node("Basics").status == "Open"
