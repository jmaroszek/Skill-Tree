"""The undo-Done warning lists only the nodes the cascade will reopen.

It listed every Done node past a Hard link. A Goal keeps its status when a
prerequisite reopens, so the cascade stops there, but the warning named the
Goal and everything beyond it as nodes that would be re-blocked.
"""
import pytest

from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import Node, EDGE_NEEDS_HARD, STATUS_DONE


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5, time_o=1.0,
                  time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status=STATUS_DONE, context="Mind")
    fields.update(overrides)
    return Node(**fields)


@pytest.fixture
def manager():
    """Basics -> Practice -> Craft (Goal) -> Mastery, all Done."""
    manager = GraphManager()
    manager.add_node(_node("Basics"))
    manager.add_node(_node("Practice"))
    manager.add_node(_node("Craft", type="Goal", time_mode="inherited"))
    manager.add_node(_node("Mastery"))
    manager.add_edge("Basics", "Practice", EDGE_NEEDS_HARD)
    manager.add_edge("Practice", "Craft", EDGE_NEEDS_HARD)
    manager.add_edge("Craft", "Mastery", EDGE_NEEDS_HARD)
    return manager


def _reopen(manager, name):
    node = manager.get_node(name)
    node.status = "Open"
    manager.update_node(node)


def test_the_walk_stops_at_a_goal(manager):
    assert manager.get_downstream_done_dependents("Basics") == ["Practice"]


def test_it_names_what_the_cascade_reopens(manager):
    listed = manager.get_downstream_done_dependents("Basics")
    _reopen(manager, "Basics")

    reopened = [n.name for n in manager.get_all_nodes()
                if n.status != STATUS_DONE and n.name != "Basics"]
    assert reopened == listed


def test_nothing_is_written(manager):
    manager.get_downstream_done_dependents("Basics")

    assert all(n.status == STATUS_DONE for n in manager.get_all_nodes())
