"""An event operation naming an event or node that is gone says so plainly.

Pickers are built once, so another window can delete what they list. These
used to surface as a raw database error, or, for an event deleted under its
editor, a "Saved." for an update that changed nothing.
"""
import pytest

from event_manager import EventManager
from graph_manager import GraphManager
from models import Event, Node


def _node(name):
    return Node(name=name, type="Learn", description="", value=5, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                status="Open", context="Mind")


@pytest.fixture
def events():
    manager = GraphManager()
    for name in ("A", "B"):
        manager.add_node(_node(name))
    events = EventManager()
    events.add_event(Event(name="Spring"))
    return events


def test_adding_a_node_to_a_deleted_event(events):
    with pytest.raises(ValueError, match="no event named 'Gone'"):
        events.add_node_to_event("Gone", "A")
    assert not GraphManager().get_node("A").dormant


def test_adding_a_deleted_node_to_an_event(events):
    with pytest.raises(ValueError, match="no node named 'Gone'"):
        events.add_node_to_event("Spring", "Gone")


def test_a_deleted_trigger_node(events):
    with pytest.raises(ValueError, match="no node named 'Gone'"):
        events.add_event(Event(name="Summer", trigger_nodes=["Gone"]))
    assert events.get_event("Summer") is None
    with pytest.raises(ValueError, match="no node named 'Gone'"):
        events.update_event("Spring", Event(name="Spring", trigger_nodes=["A", "Gone"]))
    assert events.get_event("Spring").trigger_nodes == []


def test_updating_a_deleted_event_saves_nothing(events):
    with pytest.raises(ValueError, match="no event named 'Gone'.*nothing was saved"):
        events.update_event("Gone", Event(name="Gone", description="edited"))
    assert events.get_event("Gone") is None


@pytest.mark.parametrize("change", [
    lambda events: events.set_node_delay("Spring", "B", 3),
    lambda events: events.set_now_on_trigger("Spring", "B", True),
])
def test_changing_a_node_no_longer_in_the_event(events, change):
    with pytest.raises(ValueError, match="'B' isn't in 'Spring' any more"):
        change(events)
