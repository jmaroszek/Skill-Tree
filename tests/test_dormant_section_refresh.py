"""The editor's Dormant section and the events it reloads for.

Every event change (a save, a trigger, the clock waking a node) reloads the
open editor's Dormant section. It used to replace whatever the user had
changed there and reset the baseline, so the unsaved-changes guard never saw
the loss. A save that found the node woken from under the editor also left
the section saying Dormant.
"""
import types

import dash
import pytest

import event_callbacks
from callback_helpers import NEW_NODE_DORMANCY, build_dormancy_snapshot
from event_manager import EventManager
from graph_manager import GraphManager
from models import Event, Node


def _node(name):
    return Node(name=name, type="Learn", description="", value=5, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                status="Open", context="Mind")


@pytest.fixture
def populate(monkeypatch):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    event_callbacks.register_event_callbacks(app)
    fn = next(spec["callback"] for spec in app.callback_map.values()
              if getattr(spec.get("callback"), "__name__", "") == "populate_node_dormancy")
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__

    def run(trigger, snapshot, form, save_result=None):
        monkeypatch.setattr(event_callbacks, "ctx",
                            types.SimpleNamespace(triggered_id=trigger))
        return fn("A", 1, save_result, None, snapshot, form)
    return run


@pytest.fixture
def events():
    GraphManager().add_node(_node("A"))
    events = EventManager()
    for name in ("Later", "Other"):
        events.add_event(Event(name=name))
    events.add_node_to_event("Later", "A")
    return events


def test_an_event_change_keeps_unsaved_dormant_edits(populate, events):
    loaded = build_dormancy_snapshot(GraphManager().get_node("A"))
    edited = {**loaded, "event": "Other"}
    snapshot = {"name": "A", "desc": "", "dormancy": loaded}
    events.set_node_delay("Later", "A", 7)  # elsewhere: the Events tab
    out = populate("events-refresh-trigger", snapshot, edited)
    dormant, options, event_value = out[0], out[1], out[2]
    assert dormant is dash.no_update and event_value is dash.no_update
    assert "Other" in [o["value"] for o in options]
    # The baseline moves to what is stored, so the edit still counts as unsaved.
    assert out[10]["dormancy"]["delay_value"] == 1 and out[10]["dormancy"]["delay_unit"] == "weeks"
    assert out[10]["dormancy"]["event"] == "Later"


def test_an_event_change_reloads_an_untouched_section(populate, events):
    loaded = build_dormancy_snapshot(GraphManager().get_node("A"))
    snapshot = {"name": "A", "dormancy": loaded}
    events.trigger_event_manually("Later")
    out = populate("events-refresh-trigger", snapshot, loaded)
    assert out[0] == [] and out[10]["dormancy"]["dormant"] is False


def test_a_save_that_found_the_node_awake_redraws_the_section(populate, events):
    loaded = build_dormancy_snapshot(GraphManager().get_node("A"))
    events.trigger_event_manually("Later")
    out = populate("editor-save-result-store", {"name": "A", "dormancy": loaded}, loaded,
                   save_result={"name": "A", "via": "btn-save", "woke": "Later"})
    assert out[0] == []
    assert out[10] is dash.no_update  # the post-save sync owns the baseline
    assert populate("editor-save-result-store", {"name": "A"}, NEW_NODE_DORMANCY,
                    save_result={"name": "A", "via": "btn-save"}) == (dash.no_update,) * 12
