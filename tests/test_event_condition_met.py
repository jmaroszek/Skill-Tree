"""An event whose completion condition already holds fires.

A completion fires the events watching it only on the save that marks the
node Done. An event could come to be satisfied another way, and then it
waited until a trigger node was reopened and finished again:

- an AND event whose unfinished trigger node is deleted,
- an edit that drops the unfinished trigger nodes, or switches AND to OR.

A new event watching a node that is already Done would fire as it was saved,
before anything was put in it to wake, so the save is refused instead.
"""
import logging
from unittest.mock import patch

import dash
import pytest

import database
import event_callbacks
from config import ConfigManager
from event_manager import EventManager
from graph_manager import GraphManager
from models import Event, Node, STATUS_DONE


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5, time_o=1.0,
                  time_m=2.0, time_p=4.0, interest=5, difficulty=5, status="Open",
                  context="Mind")
    fields.update(overrides)
    return Node(**fields)


def _finish(manager, name):
    item = manager.get_node(name)
    item.status = STATUS_DONE
    manager.update_node(item)


@pytest.fixture
def graph():
    """An AND event on Draft and Edit that holds Publish. Draft is Done."""
    manager, events = GraphManager(), EventManager()
    manager.add_node(_node("Draft"))
    manager.add_node(_node("Edit"))
    events.add_event(Event(name="Ready", trigger_nodes=["Draft", "Edit"],
                           trigger_mode="all"))
    events.create_dormant_node(_node("Publish"), "Ready")
    _finish(manager, "Draft")
    assert events.get_event("Ready").status == "Pending"
    ConfigManager.clear_pending_event_notifications()
    return manager, events


def _fired(manager, events):
    return (events.get_event("Ready").status == "Triggered"
            and manager.get_node("Publish").dormant == 0)


def test_deleting_the_unfinished_trigger_node_fires_the_event(graph):
    manager, events = graph

    manager.delete_node("Edit")

    assert _fired(manager, events)
    kinds = [e["kind"] for e in ConfigManager.get_pending_event_notifications()]
    assert kinds == ["trigger_node_deleted", "node_triggered"]


def test_an_edit_that_drops_the_unfinished_node_fires_the_event(graph):
    manager, events = graph

    events.update_event("Ready", Event(name="Ready", trigger_nodes=["Draft"],
                                       trigger_mode="all"))

    assert _fired(manager, events)
    entry = ConfigManager.get_pending_event_notifications()[-1]
    assert entry["kind"] == "node_triggered" and entry["already_met"] is True
    assert entry["trigger_node"] == "Draft"
    assert entry["activated"] == ["Publish"]


def test_switching_to_any_fires_the_event(graph):
    manager, events = graph

    events.update_event("Ready", Event(name="Ready", trigger_nodes=["Draft", "Edit"],
                                       trigger_mode="any"))

    assert _fired(manager, events)


def test_an_edit_that_leaves_it_waiting_changes_nothing(graph):
    manager, events = graph

    events.update_event("Ready", Event(name="Ready", description="Soon",
                                       trigger_nodes=["Draft", "Edit"],
                                       trigger_mode="all"))

    assert not _fired(manager, events)
    assert ConfigManager.get_pending_event_notifications() == []


def test_a_rolled_back_edit_fires_nothing(graph):
    manager, events = graph

    with pytest.raises(RuntimeError):
        with database.transaction():
            events.update_event("Ready", Event(name="Ready", trigger_nodes=["Draft"]))
            raise RuntimeError("the save was refused")

    assert not _fired(manager, events)
    assert events.get_event("Ready").trigger_nodes == ["Draft", "Edit"]


def test_a_failure_to_fire_is_logged_and_the_edit_stays(graph, caplog):
    manager, events = graph

    def broken(self, event_name):
        with database.transaction():
            raise RuntimeError("disk full")
    with patch.object(EventManager, "fire_if_condition_met", broken), \
            caplog.at_level(logging.ERROR):
        events.update_event("Ready", Event(name="Ready", trigger_nodes=["Draft"]))

    assert events.get_event("Ready").trigger_nodes == ["Draft"]
    assert "Firing the satisfied event Ready failed" in caplog.text


def test_a_sleeping_done_node_does_not_count():
    events = EventManager()
    events.add_event(Event(name="Spring"))
    events.create_dormant_node(_node("Seed"), "Spring")
    events.add_event(Event(name="Bloom", trigger_nodes=["Seed"]))
    # A legacy sleeping completion: it counts once it wakes.
    with database.get_connection() as conn:
        conn.execute("UPDATE Nodes SET status='Done' WHERE name='Seed'")

    assert events.fire_if_condition_met("Bloom") is False
    events.trigger_event("Spring")
    assert events.get_event("Bloom").status == "Triggered"


def test_a_new_event_on_a_finished_node_is_refused():
    manager, events = GraphManager(), EventManager()
    manager.add_node(_node("Draft", status=STATUS_DONE))
    manager.add_node(_node("Edit", status=STATUS_DONE))
    manager.add_node(_node("Print"))

    with pytest.raises(ValueError, match="'Draft' is complete already"):
        events.add_event(Event(name="Any", trigger_nodes=["Draft", "Print"]))
    with pytest.raises(ValueError, match="trigger nodes are all complete already"):
        events.add_event(Event(name="All", trigger_nodes=["Draft", "Edit"],
                               trigger_mode="all"))
    assert events.get_all_events() == []

    # AND still waits on Print.
    events.add_event(Event(name="Waiting", trigger_nodes=["Draft", "Print"],
                           trigger_mode="all"))
    assert events.get_event("Waiting").status == "Pending"


def test_the_launch_safety_net_fires_events_left_waiting():
    manager, events = GraphManager(), EventManager()
    manager.add_node(_node("Draft"))
    events.add_event(Event(name="Ready", trigger_nodes=["Draft"]))
    events.create_dormant_node(_node("Publish"), "Ready")
    # Saved before saves checked: the trigger node was Done already.
    with database.get_connection() as conn:
        conn.execute("UPDATE Nodes SET status='Done' WHERE name='Draft'")

    assert events.fire_satisfied_events() == ["Ready"]
    assert manager.get_node("Publish").dormant == 0
    assert events.fire_satisfied_events() == []


def _save_event():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    event_callbacks.register_event_callbacks(app)
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if getattr(fn, "__name__", None) == "save_event":
            return fn
    raise LookupError("save_event")


def test_the_editor_says_the_save_fired_the_event(graph):
    manager, events = graph

    result = _save_event()(1, "Ready", "Ready", "", "node", None, ["Draft"], "all")

    assert result[2] == "Saved. Its trigger condition was already met, so it fired."
    assert result[3] == {"display": "none"}  # no Trigger button
    assert _fired(manager, events)


def test_the_editor_shows_the_refusal_for_a_new_event():
    GraphManager().add_node(_node("Draft", status=STATUS_DONE))

    result = _save_event()(1, None, "Ready", "", "node", None, ["Draft"], "any")

    assert "'Draft' is complete already" in result[2]
    assert EventManager().get_event("Ready") is None


def test_the_announcement_says_the_nodes_were_already_complete():
    base = {"kind": "node_triggered", "event": "Ready", "trigger_node": "Draft",
            "already_met": True, "activated": ["Publish"], "when": "2026-10-12"}
    one = event_callbacks._render_announcements(
        [{**base, "trigger_nodes": ["Draft"], "trigger_mode": "any"}])
    every = event_callbacks._render_announcements(
        [{**base, "trigger_nodes": ["Draft", "Edit"], "trigger_mode": "all"}])

    assert "Draft was already complete" in str(one)
    assert "all 2 trigger nodes were already complete" in str(every)
