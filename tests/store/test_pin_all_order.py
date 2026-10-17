"""With "Add to Now for all", a full Now list takes the flagged nodes first.

When an event wakes more nodes than Now has room for, the ones that made it
were chosen alphabetically, passing over the nodes flagged Add to Now. Now
they go first, then the rest in recommendation order.
"""
from skilltree.store import settings
from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import Event, Node


def _node(name, value):
    return Node(name=name, type="Learn", description="", value=value, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=value, difficulty=5,
                status="Open", context="Mind")


def _fire(cap):
    GraphManager()
    events = EventManager(GraphManager())
    events.add_event(Event(name="Spring"))
    for name, value, flagged in (("Alpha", 2, False), ("Mid", 9, False), ("Zed", 1, True)):
        events.create_dormant_node(_node(name, value), "Spring", now_on_trigger=flagged)
    settings.NOW_NODE_CAP.set(cap)
    return events.trigger_event_manually("Spring", pin_all_now=True)


def test_the_flagged_node_goes_first():
    result = _fire(cap=1)
    assert result["now_pinned"] == ["Zed"]
    assert sorted(result["now_skipped"]) == ["Alpha", "Mid"]


def test_then_the_rest_in_recommendation_order():
    result = _fire(cap=2)
    assert result["now_pinned"] == ["Zed", "Mid"]
    assert result["now_skipped"] == ["Alpha"]
