"""A run of nodes entering Now together is ranked once.

Each start records the node's place in the recommendations, and that scored
the whole graph. A bulk Add to Now, or an event waking several nodes onto
Now, scored it once per node.
"""
from unittest.mock import patch

import pytest

from config import ConfigManager
from event_manager import EventManager
from graph_manager import GraphManager
from models import Event, Node


def _node(name, value):
    return Node(name=name, type="Learn", description="", value=value, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=value, difficulty=5,
                status="Open", context="Mind")


@pytest.fixture
def manager():
    manager = GraphManager()
    for name, value in (("Top", 10), ("Middle", 6), ("Low", 2)):
        manager.add_node(_node(name, value))
    ConfigManager.set_now_node_cap(5)
    return manager


def _ranks(manager, *names):
    return [next((e["rank"], e["ranked_of"])
                 for e in manager.get_node_lifecycle_events(name)
                 if e["event_type"] == "now_started") for name in names]


def _start(manager, *names):
    for index, name in enumerate(names, start=1):
        node = manager.get_node(name)
        node.now = index
        manager.update_node(node)


def test_a_batch_scores_once_and_records_the_same_ranks(manager):
    original = GraphManager.calculate_priority_scores
    with patch.object(GraphManager, "calculate_priority_scores", autospec=True,
                      side_effect=original) as scored:
        with manager.ranking_batch():
            _start(manager, "Low", "Top")

    assert scored.call_count == 1
    # As one at a time: Low ranks third of three, then Top first of two.
    assert _ranks(manager, "Low", "Top") == [(3, 3), (1, 2)]


def test_without_a_batch_each_start_scores(manager):
    original = GraphManager.calculate_priority_scores
    with patch.object(GraphManager, "calculate_priority_scores", autospec=True,
                      side_effect=original) as scored:
        _start(manager, "Low", "Top")

    assert scored.call_count == 2
    assert _ranks(manager, "Low", "Top") == [(3, 3), (1, 2)]


def test_an_event_waking_nodes_onto_now_scores_once(manager):
    events = EventManager()
    events.add_event(Event(name="Spring"))
    for name, value in (("Seed", 8), ("Sprout", 4)):
        events.create_dormant_node(_node(name, value), "Spring", now_on_trigger=True)
    original = GraphManager.calculate_priority_scores
    with patch.object(GraphManager, "calculate_priority_scores", autospec=True,
                      side_effect=original) as scored:
        events.trigger_event_manually("Spring")

    assert sorted(n.name for n in manager.get_now_nodes()) == ["Seed", "Sprout"]
    assert scored.call_count == 1
