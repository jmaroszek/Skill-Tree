"""A Synergy stored back to front is the same Synergy.

add_edge stores a Helps pair with its names in sorted order. Rows an older
build left the other way round were never fixed, and add_edge then stored the
pair a second time.
"""
import pytest

import database
from graph_manager import GraphManager
from models import Node, EDGE_HELPS


def _node(name):
    return Node(name=name, type="Learn", description="", value=5, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                status="Open", context="Mind")


@pytest.fixture
def manager():
    manager = GraphManager()
    for name in ("Alpha", "Beta", "Gamma"):
        manager.add_node(_node(name))
    # Back to front, as an older rename left them.
    with database.transaction() as conn:
        conn.execute("INSERT INTO Edges (source, target, type) VALUES ('Beta', 'Alpha', ?)",
                     (EDGE_HELPS,))
    return manager


def _helps(manager):
    return sorted((e["source"], e["target"]) for e in manager.get_edges()
                  if e["type"] == EDGE_HELPS)


def test_adding_the_pair_again_stores_nothing(manager):
    manager.add_edge("Alpha", "Beta", EDGE_HELPS)

    assert _helps(manager) == [("Beta", "Alpha")]


def test_the_safety_net_turns_it_round(manager):
    assert manager.canonicalize_helps_edges() == 1
    assert _helps(manager) == [("Alpha", "Beta")]
    assert manager.canonicalize_helps_edges() == 0


def test_a_duplicate_pair_collapses_to_one_row(manager):
    with database.transaction() as conn:
        conn.execute("INSERT INTO Edges (source, target, type) VALUES ('Alpha', 'Beta', ?)",
                     (EDGE_HELPS,))

    assert manager.canonicalize_helps_edges() == 1
    assert _helps(manager) == [("Alpha", "Beta")]
