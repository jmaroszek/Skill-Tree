"""The editor's Dormant section and the events it follows.

Every event change (a save, a trigger, the clock waking a node) can change what is
stored for the open node. It used to replace whatever the user had changed there
and reset the baseline, so the unsaved-changes guard never saw the loss. A save
that found the node woken from under the editor also left the section saying
Dormant.
"""
import dash
import pytest

from skilltree.features.editor.callbacks import register_editor_callbacks
from skilltree.features.editor.form import NEW_EVENT_OPTION, build_dormancy_snapshot, rebase
from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import Event, Node
from support.callbacks import registered
from support.editor_forms import call, merged
from support.triggers import fire


def _node(name):
    return Node(name=name, type="Learn", description="", value=5, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                status="Open", context="Mind")


@pytest.fixture
def handlers():
    return registered(register_editor_callbacks)


@pytest.fixture
def events():
    GraphManager().add_node(_node("A"))
    events = EventManager(GraphManager())
    for name in ("Later", "Other"):
        events.add_event(Event(name=name))
    events.add_node_to_event("Later", "A")
    return events


def _section(services):
    return build_dormancy_snapshot(GraphManager().get_node("A"), services.events)


def _merge(services, form, loaded):
    return merged(rebase(GraphManager().get_node("A"), {}, {"dormancy": form},
                         {"name": "A", "dormancy": loaded},
                         stored_dormancy=_section(services)))


def test_an_event_change_keeps_unsaved_dormant_edits(handlers, events, services):
    loaded = _section(services)
    edited = {**loaded, "event": "Other"}
    events.set_node_delay("Later", "A", 7)  # elsewhere: the Events tab

    fields, baseline = _merge(services, edited, loaded)

    assert fields == {}
    # The baseline moves to what is stored, so the edit still counts as unsaved.
    assert baseline["dormancy"]["delay_value"] == 1 and baseline["dormancy"]["delay_unit"] == "weeks"
    assert baseline["dormancy"]["event"] == "Later"
    # The list keeps the user's choice on it.
    fire("events-refresh-trigger")
    options = handlers["refresh_dormant_event_options"](["dormant"], 1, "Other")
    assert "Other" in [o["value"] for o in options]


def test_an_event_change_reloads_an_untouched_section(handlers, events, services):
    loaded = _section(services)
    events.trigger_event_manually("Later")

    fields, baseline = _merge(services, loaded, loaded)

    assert fields["dormant_switch"] == [] and baseline["dormancy"]["dormant"] is False


def test_the_section_stays_when_nothing_changed(events, services):
    loaded = _section(services)
    assert _merge(services, loaded, loaded) == ({}, {})


def test_a_new_event_saved_from_the_form_takes_its_name_onto_the_list(handlers, events, services):
    """The form said "New event…" with a name. Now it's an event like any other,
    and the picker can't hold a value its list doesn't."""
    typed = {**_section(services), "event": NEW_EVENT_OPTION, "event_name": "Fresh"}
    events.add_event(Event(name="Fresh"))
    events.move_node_to_event("Later", "A", "Fresh")

    result = call(handlers["merge_outside_changes"], snapshot={"name": "A", "dormancy": typed},
                  original_name="A", dormancy=typed)

    [group] = result["groups"]
    assert group["fields"]["dormant_event"] == "Fresh"
    assert group["fields"]["dormant_event_name"] == ""
    assert "Fresh" in [o["value"] for o in group["fields"]["dormant_event_options"]]


def test_switching_dormant_off_leaves_the_list_alone(handlers):
    fire("node-dormant")
    assert handlers["refresh_dormant_event_options"]([], None, None) is dash.no_update
