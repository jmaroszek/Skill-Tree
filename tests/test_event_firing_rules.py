"""Edge cases in how events fire and what they wake (found in the 2026-09 review).

- An event fires once. Firing it again, from a page that hadn't seen the
  first firing, used to re-date every delayed node still waiting, pushing
  its wake day later.
- A node that wakes already Done stays off Now: there is nothing left to
  work on. The bulk Add to Event dialog doesn't offer finished nodes at all,
  just as the editor won't make a Done node dormant.
- A completion fires its events even when one save writes the node twice.
  The second write used to replace the first one's completion hook, and it
  saw the node Done already.
"""
import datetime as real_datetime
import json

import dash
from dash._callback_context import context_value
from dash._utils import AttributeDict

import database
import event_callbacks
import event_manager as event_manager_module
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


def _callbacks():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    event_callbacks.register_event_callbacks(app)
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None:
            found[fn.__name__] = fn
    return found


def _with_trigger(fn, prop_id, *args):
    token = context_value.set(AttributeDict(
        triggered_inputs=[{"prop_id": prop_id, "value": args[0]}]))
    try:
        return fn(*args)
    finally:
        context_value.reset(token)


def test_firing_an_event_again_changes_nothing(monkeypatch):
    events = EventManager()
    events.add_event(Event(name="Spring"))
    events.create_dormant_node(_node("Garden"), "Spring", delay_days=3)
    events.trigger_event("Spring")
    wake = events.get_node_membership("Garden")["activation_date"]

    class TwoDaysLater(real_datetime.date):
        @classmethod
        def today(cls):
            return real_datetime.date.today() + real_datetime.timedelta(days=2)
    monkeypatch.setattr(event_manager_module, "date", TwoDaysLater)

    again = events.trigger_event("Spring")

    assert again == {"activated": [], "scheduled": [], "already_awake": [],
                     "now_intent": [], "now_deferred": []}
    assert events.get_node_membership("Garden")["activation_date"] == wake


def test_the_trigger_button_on_a_fired_event_says_so_and_announces_nothing():
    events = EventManager()
    events.add_event(Event(name="Spring"))
    events.create_dormant_node(_node("Garden"), "Spring")
    events.trigger_event_manually("Spring")
    announced = len(ConfigManager.get_pending_event_notifications())

    result = _callbacks()["trigger_event"](1, "Spring", [])

    message, modal_open = result[6], result[7]
    assert "already been triggered" in message and modal_open is False
    assert result[2] == "Triggered"
    assert len(ConfigManager.get_pending_event_notifications()) == announced


def test_a_node_that_wakes_done_stays_off_now():
    events = EventManager()
    events.add_event(Event(name="Spring"))
    events.create_dormant_node(_node("Planted", status=STATUS_DONE), "Spring",
                               now_on_trigger=True)
    events.create_dormant_node(_node("Weeding"), "Spring", now_on_trigger=True)

    result = events.trigger_event_manually("Spring")

    manager = GraphManager()
    assert result["now_pinned"] == ["Weeding"]
    assert manager.get_node("Planted").now == 0
    assert manager.get_node("Weeding").now > 0


def test_add_to_event_offers_no_finished_node():
    manager = GraphManager()
    manager.add_node(_node("Reading"))
    manager.add_node(_node("Finished", status=STATUS_DONE))
    EventManager().add_event(Event(name="Spring"))
    picked = json.dumps(["Reading", "Finished"]) + "|1700000000000"

    result = _with_trigger(_callbacks()["open_add_to_event_modal"],
                           "dormant-existing-trigger-input.value", picked, None, None)

    options, preselected = result[1], result[2]
    assert [o["value"] for o in options] == ["Reading"]
    assert preselected == ["Reading"]


def test_a_completion_fires_its_events_when_the_save_writes_the_node_twice():
    manager, events = GraphManager(), EventManager()
    manager.add_node(_node("Plan"))
    events.add_event(Event(name="Launch", trigger_nodes=["Plan"]))
    events.create_dormant_node(_node("Announce"), "Launch")

    with database.transaction():
        plan = manager.get_node("Plan")
        plan.status = STATUS_DONE
        manager.update_node(plan)
        plan = manager.get_node("Plan")
        plan.description = "Written in the same save."
        manager.update_node(plan)

    assert events.get_event("Launch").status == "Triggered"
    assert manager.get_node("Announce").dormant == 0


def test_a_node_reopened_and_redone_in_one_save_is_no_new_completion():
    """Done before the save and Done after it: nothing was completed."""
    manager, events = GraphManager(), EventManager()
    manager.add_node(_node("Plan", status=STATUS_DONE))
    # Made after Plan was finished, so it still waits.
    events.add_event(Event(name="Later", trigger_nodes=["Plan"]))

    with database.transaction():
        plan = manager.get_node("Plan")
        plan.status = "Open"
        manager.update_node(plan)
        plan = manager.get_node("Plan")
        plan.status = STATUS_DONE
        manager.update_node(plan)

    assert events.get_event("Later").status == "Pending"
